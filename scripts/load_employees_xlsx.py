#!/usr/bin/env python3
"""
load_employees_xlsx.py
═══════════════════════════════════════════════════════════════════════════════
Parse an Excel nominal-roll sheet and upsert hr.employee records via the
existing SAP sync pipeline (nrs.sap.sync.log.process_sap_payload).

Idempotent: rows are matched by IR number and existing records are updated
in place. Each row produces a sync-log entry, so results are auditable in
the UI under SAP Sync Logs.

Run via odoo shell (path resolved INSIDE the container — repo is mounted
at /mnt/extra-addons):

  docker compose -f docker-compose.dev.yml run --rm -T odoo bash -c \
    "EMPLOYEE_XLSX=/mnt/extra-addons/docs/'temp firs.xlsx' \
     odoo shell -c /etc/odoo/odoo.conf -d odoo --no-http \
     <<< \"exec(open('/mnt/extra-addons/scripts/load_employees_xlsx.py').read())\""

Override the source file with EMPLOYEE_XLSX; defaults to docs/temp firs.xlsx.
Override the sheet name with EMPLOYEE_SHEET; defaults to the first sheet.
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import openpyxl

# ─── Source ──────────────────────────────────────────────────────────────────
DEFAULT_PATH = '/mnt/extra-addons/docs/temp firs.xlsx'
XLSX_PATH = os.environ.get('EMPLOYEE_XLSX', DEFAULT_PATH)
SHEET_NAME = os.environ.get('EMPLOYEE_SHEET')  # None → first sheet

# ─── Column mapping ──────────────────────────────────────────────────────────
# Maps source xlsx header → key expected by process_sap_payload().
# Headers are normalised (stripped, case-insensitive) before lookup.
COLUMN_MAP = {
    'ir no':                       'ir_number',
    'ir number':                   'ir_number',
    'personnel number':            'displayName',  # source column holds the NAME
    'display name':                'displayName',
    'name':                        'displayName',
    'rank':                        'jobTitle',
    'job title':                   'jobTitle',
    'phone no.':                   'phone',
    'phone':                       'phone',
    'email':                       'email',
    'employment status':           'employmentStatus',
    'present location':            'location',
    'group/administration office': 'department',
    'department':                  'department',
    'sco':                         'costCenter',
}


def _norm(v):
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _load_rows(path, sheet_name=None):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet_name] if sheet_name else wb[wb.sheetnames[0]]

    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return []

    headers = [_norm(h).lower() for h in header_row]
    out = []
    for row in rows_iter:
        if not any(c not in (None, '') for c in row):
            continue
        payload = {}
        for header, raw in zip(headers, row):
            key = COLUMN_MAP.get(header)
            if not key:
                continue
            payload[key] = _norm(raw)
        if payload.get('ir_number'):
            out.append(payload)
    return out


# ─── Run ─────────────────────────────────────────────────────────────────────
print('\n' + '=' * 70)
print(f'  LOAD EMPLOYEES — {XLSX_PATH}')
print('=' * 70)

if not os.path.exists(XLSX_PATH):
    raise SystemExit(f'  ERROR: file not found: {XLSX_PATH}')

rows = _load_rows(XLSX_PATH, SHEET_NAME)
print(f'  Parsed {len(rows)} row(s) with an IR number.')

SyncLog = env['nrs.sap.sync.log']
created = updated = skipped = errored = 0
err_lines = []

for i, payload in enumerate(rows, 1):
    ir = payload.get('ir_number', '?')
    name = payload.get('displayName', '')
    try:
        existing = env['hr.employee'].search([('ir_number', '=', ir)], limit=1)
        employee, log = SyncLog.process_sap_payload(payload, sync_type='csv_import')
        if log.status == 'success':
            if existing:
                updated += 1
                tag = 'UPDATED'
            else:
                created += 1
                tag = 'CREATED'
        elif log.status == 'skipped':
            skipped += 1
            tag = 'SKIPPED'
        else:
            errored += 1
            tag = 'ERROR'
            err_lines.append(f'  {ir} ({name}): {log.error_message}')
        print(f'  [{i:>3}] {tag:8} IR={ir:<8} {name}')
    # catch-all: reported — counts the row into `errored`, appends it to
    # err_lines with the exception and rolls the cursor back; the run ends by
    # printing every error line. An employee that did not import is never
    # counted as imported.
    except Exception as e:
        errored += 1
        err_lines.append(f'  {ir} ({name}): {e}')
        print(f'  [{i:>3}] EXCEPTION IR={ir:<8} {name}: {e}')
        env.cr.rollback()

env.cr.commit()

print('\n' + '-' * 70)
print(f'  Created: {created}   Updated: {updated}   '
      f'Skipped: {skipped}   Errors: {errored}')
if err_lines:
    print('  Errors:')
    for line in err_lines[:20]:
        print(line)
print('-' * 70 + '\n')
