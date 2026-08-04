import base64
import json
import logging
import threading
import time

import openpyxl

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.modules.registry import Registry

_logger = logging.getLogger(__name__)


# Maps xlsx header (normalised: stripped + lowercased) → key expected by
# nrs.sap.sync.log.process_sap_payload(). Same mapping the dev seed script
# (scripts/load_employees_xlsx.py) uses, so xlsx loaded here behaves
# identically whether it came in via API or via odoo shell.
COLUMN_MAP = {
    'ir no':                       'ir_number',
    'ir number':                   'ir_number',
    'personnel number':            'displayName',
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

# Periodic commit interval — bounded so a mid-import crash never loses more
# than this many rows of work and the DB transaction stays small.
COMMIT_EVERY = 200

# Cap on per-job error retention. We keep the first N errors verbatim and
# only count the rest; otherwise an entirely bad sheet blows the field up.
MAX_ERROR_SAMPLES = 100


def _norm_cell(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


class NrsEmployeeImportJob(models.Model):
    _name = 'nrs.employee.import.job'
    _description = 'Employee Bulk Import Job (xlsx)'
    _order = 'create_date desc'
    _rec_name = 'display_name'

    display_name = fields.Char(compute='_compute_display_name', store=True)
    state = fields.Selection([
        ('pending',    'Pending'),
        ('processing', 'Processing'),
        ('completed',  'Completed'),
        ('failed',     'Failed'),
    ], default='pending', required=True, index=True)

    file_data = fields.Binary(string='Source File', attachment=True, required=True)
    file_name = fields.Char(string='File Name', required=True)
    sheet_name = fields.Char(
        string='Sheet',
        help='Sheet to read. If blank, the first sheet is used.',
    )

    total_rows     = fields.Integer(string='Rows With IR')
    processed      = fields.Integer()
    created_count  = fields.Integer(string='Created')
    updated_count  = fields.Integer(string='Updated')
    skipped_count  = fields.Integer(string='Skipped')
    error_count    = fields.Integer(string='Errors')

    progress_pct = fields.Float(compute='_compute_progress_pct', string='Progress %')

    errors = fields.Text(
        help='JSON list of up to %d error rows {row, ir_number, message}.'
        % MAX_ERROR_SAMPLES,
    )
    fatal_message = fields.Text(
        help='Set on failed jobs that aborted before/during row processing.',
    )

    started_at  = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    duration_ms = fields.Integer(readonly=True)

    @api.depends('file_name', 'create_date')
    def _compute_display_name(self):
        for job in self:
            stamp = (job.create_date or fields.Datetime.now()).strftime('%Y-%m-%d %H:%M')
            job.display_name = '%s — %s' % (stamp, job.file_name or 'employee-import')

    @api.depends('total_rows', 'processed')
    def _compute_progress_pct(self):
        for job in self:
            if job.total_rows:
                job.progress_pct = 100.0 * job.processed / job.total_rows
            else:
                job.progress_pct = 0.0

    # ------------------------------------------------------------------
    # Public API — invoked by myservice_api controller
    # ------------------------------------------------------------------

    def start_async(self):
        """Kick off processing in a daemon thread with a fresh Odoo env.

        We must NOT reuse self.env here — the request transaction will commit
        and close before the worker is done. The worker opens its own cursor
        via Registry(db_name).cursor() so it owns its lifecycle.
        """
        self.ensure_one()
        db_name = self.env.cr.dbname
        job_id = self.id

        # Commit the pending row so the worker thread can see it.
        self.env.cr.commit()

        thread = threading.Thread(
            target=self._worker_entrypoint,
            args=(db_name, job_id),
            name='nrs-employee-import-%d' % job_id,
            daemon=True,
        )
        thread.start()
        return job_id

    def to_status_dict(self):
        self.ensure_one()
        try:
            err_list = json.loads(self.errors) if self.errors else []
        except Exception:
            err_list = []
        return {
            'id': self.id,
            'state': self.state,
            'file_name': self.file_name,
            'sheet_name': self.sheet_name or '',
            'total_rows': self.total_rows,
            'processed': self.processed,
            'created': self.created_count,
            'updated': self.updated_count,
            'skipped': self.skipped_count,
            'errors': self.error_count,
            'progress_pct': round(self.progress_pct, 2),
            'started_at': self.started_at and self.started_at.isoformat() or None,
            'finished_at': self.finished_at and self.finished_at.isoformat() or None,
            'duration_ms': self.duration_ms,
            'fatal_message': self.fatal_message or '',
            'error_samples': err_list[:20],
        }

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    @staticmethod
    def _worker_entrypoint(db_name, job_id):
        """Top-level thread target. Owns its registry cursor + env."""
        try:
            with Registry(db_name).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                job = env['nrs.employee.import.job'].browse(job_id)
                job._run()
        except Exception:
            _logger.exception('Employee import job %s crashed at thread root', job_id)
            # Best-effort: open a second cursor to mark the job failed so the
            # status endpoint shows something useful instead of "processing
            # forever".
            try:
                with Registry(db_name).cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    env['nrs.employee.import.job'].browse(job_id).write({
                        'state': 'failed',
                        'fatal_message': 'Worker thread crashed — see odoo logs',
                        'finished_at': fields.Datetime.now(),
                    })
            except Exception:
                _logger.exception(
                    'Could not even mark import job %s as failed', job_id,
                )

    def _run(self):
        """Process the upload. Runs inside the worker's own transaction."""
        self.ensure_one()
        start = time.time()
        self.write({'state': 'processing', 'started_at': fields.Datetime.now()})
        self.env.cr.commit()

        try:
            rows = self._parse_xlsx()
        except Exception as e:
            _logger.exception('Failed to parse xlsx for job %s', self.id)
            self.write({
                'state': 'failed',
                'fatal_message': 'Parse error: %s' % e,
                'finished_at': fields.Datetime.now(),
                'duration_ms': int((time.time() - start) * 1000),
            })
            self.env.cr.commit()
            return

        self.write({'total_rows': len(rows)})
        self.env.cr.commit()

        SyncLog = self.env['nrs.sap.sync.log']
        Employee = self.env['hr.employee']
        created = updated = skipped = errored = 0
        sampled_errors = []

        for i, payload in enumerate(rows, 1):
            ir = payload.get('ir_number', '')
            try:
                pre_existing = Employee.search([('ir_number', '=', ir)], limit=1)
                _employee, log = SyncLog.process_sap_payload(
                    payload, sync_type='csv_import',
                )
                if log.status == 'success':
                    if pre_existing:
                        updated += 1
                    else:
                        created += 1
                elif log.status == 'skipped':
                    skipped += 1
                else:
                    errored += 1
                    if len(sampled_errors) < MAX_ERROR_SAMPLES:
                        sampled_errors.append({
                            'row': i,
                            'ir_number': ir,
                            'message': log.error_message or 'unknown',
                        })
            except Exception as e:
                # process_sap_payload already rolls back internally on its
                # own errors; for anything that escapes it we rollback to
                # the last savepoint here so the next row can proceed.
                self.env.cr.rollback()
                errored += 1
                if len(sampled_errors) < MAX_ERROR_SAMPLES:
                    sampled_errors.append({
                        'row': i,
                        'ir_number': ir,
                        'message': str(e),
                    })

            if i % COMMIT_EVERY == 0:
                self.write({
                    'processed': i,
                    'created_count': created,
                    'updated_count': updated,
                    'skipped_count': skipped,
                    'error_count': errored,
                    'errors': json.dumps(sampled_errors),
                })
                self.env.cr.commit()

        # Final write
        self.write({
            'state': 'completed',
            'processed': len(rows),
            'created_count': created,
            'updated_count': updated,
            'skipped_count': skipped,
            'error_count': errored,
            'errors': json.dumps(sampled_errors),
            'finished_at': fields.Datetime.now(),
            'duration_ms': int((time.time() - start) * 1000),
        })
        self.env.cr.commit()

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_xlsx(self):
        """Return a list of payload dicts ready for process_sap_payload.

        Decodes the stored base64 file and walks it with openpyxl in
        read-only mode (keeps memory flat for 10k+ row sheets).
        """
        self.ensure_one()
        raw = base64.b64decode(self.file_data)
        from io import BytesIO
        wb = openpyxl.load_workbook(BytesIO(raw), data_only=True, read_only=True)

        if self.sheet_name and self.sheet_name in wb.sheetnames:
            ws = wb[self.sheet_name]
        else:
            ws = wb[wb.sheetnames[0]]

        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            return []

        headers = [_norm_cell(h).lower() for h in header_row]

        out = []
        for row in rows_iter:
            if not any(c not in (None, '') for c in row):
                continue
            payload = {}
            for header, raw_cell in zip(headers, row):
                key = COLUMN_MAP.get(header)
                if not key:
                    continue
                payload[key] = _norm_cell(raw_cell)
            if payload.get('ir_number'):
                out.append(payload)
        return out
