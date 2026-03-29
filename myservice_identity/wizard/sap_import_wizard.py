import base64
import csv
import io
import logging
from odoo import models, fields
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

COLUMN_MAP = {
    'IR Number': 'ir_number',
    'ir_number': 'ir_number',
    'personIdExternal': 'ir_number',
    'Display Name': 'displayName',
    'displayName': 'displayName',
    'First Name': 'firstName',
    'Last Name': 'lastName',
    'Job Title': 'jobTitle',
    'Department': 'department',
    'Cost Center': 'costCenter',
    'Location': 'location',
    'Grade': 'gradeCode',
    'Email': 'email',
    'Status': 'employmentStatus',
    'Hire Date': 'hireDate',
    'Manager IR': 'managerIR',
}


class SAPImportWizard(models.TransientModel):
    _name = 'nrs.sap.import.wizard'
    _description = 'SAP SuccessFactors CSV Import Wizard'

    file_data = fields.Binary(string='CSV File', required=True)
    file_name = fields.Char(string='File Name')
    delimiter = fields.Selection(
        [(',', 'Comma'), (';', 'Semicolon'), ('\t', 'Tab')],
        default=',', string='Delimiter',
    )
    preview_html = fields.Html(string='Preview', readonly=True)
    result_html = fields.Html(string='Import Result', readonly=True)

    def _decode_file(self):
        if not self.file_data:
            raise UserError('Please upload a CSV file.')
        return base64.b64decode(self.file_data).decode('utf-8-sig')

    def action_preview(self):
        data = self._decode_file()
        reader = csv.DictReader(io.StringIO(data), delimiter=self.delimiter)
        rows = list(reader)[:5]
        if not rows:
            raise UserError('No data found in file.')

        headers = list(rows[0].keys())
        html = '<p><strong>Preview (first 5 rows)</strong></p>'
        html += '<table class="table table-sm table-bordered"><thead><tr>'
        html += ''.join('<th>%s</th>' % h for h in headers)
        html += '</tr></thead><tbody>'
        for row in rows:
            html += '<tr>' + ''.join(
                '<td>%s</td>' % row.get(h, '') for h in headers
            ) + '</tr>'
        html += '</tbody></table>'

        self.preview_html = html
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_import(self):
        data = self._decode_file()
        reader = csv.DictReader(io.StringIO(data), delimiter=self.delimiter)
        rows = list(reader)
        if not rows:
            raise UserError('No data found in file.')

        success = error = skipped = 0
        errors = []
        SyncLog = self.env['nrs.sap.sync.log']

        for i, row in enumerate(rows, 1):
            try:
                payload = {}
                for col, val in row.items():
                    mapped = COLUMN_MAP.get(col.strip(), col.strip())
                    payload[mapped] = val.strip() if val else ''

                if not payload.get('ir_number'):
                    skipped += 1
                    continue

                _emp, log = SyncLog.process_sap_payload(payload, sync_type='csv_import')
                if log.status == 'success':
                    success += 1
                elif log.status == 'skipped':
                    skipped += 1
                else:
                    error += 1
                    errors.append(
                        'Row %d (%s): %s' % (i, payload.get('ir_number'), log.error_message)
                    )
            except Exception as e:
                error += 1
                errors.append('Row %d: %s' % (i, e))

        cls = 'success' if error == 0 else 'warning'
        html = (
            '<div class="alert alert-%s">'
            '<strong>Import Complete</strong><br/>'
            'Created/Updated: %d<br/>'
            'Skipped (no change): %d<br/>'
            'Errors: %d</div>' % (cls, success, skipped, error)
        )
        if errors:
            html += '<ul>' + ''.join('<li>%s</li>' % e for e in errors[:20]) + '</ul>'

        self.result_html = html
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
