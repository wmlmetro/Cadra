import csv
import io
import logging
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class RedhubsAPIController(http.Controller):

    def _check_api_key(self):
        key = request.httprequest.headers.get('X-API-Key', '')
        stored = request.env['ir.config_parameter'].sudo().get_param(
            'myservice_identity.redhubs_api_key', 'NRS_REDHUBS_KEY_2025',
        )
        return key == stored

    @http.route(
        '/api/myservice/assets/export', type='json', auth='none',
        methods=['POST'], csrf=False,
    )
    def export_assets(self, **kwargs):
        """Outbound asset register for Redhubs / external systems."""
        if not self._check_api_key():
            return {'success': False, 'error': 'Unauthorized'}

        assets = request.env['nrs.asset'].sudo().search([])
        result = []
        for a in assets:
            result.append({
                'asset_code': a.asset_code,
                'name': a.name,
                'category': a.category_id.name if a.category_id else None,
                'condition': a.condition,
                'state': a.state,
                'location': a.location_id.name if a.location_id else None,
                'assigned_to': a.custodian_id.name if a.custodian_id else None,
                'assigned_ir': a.assigned_ir_number or None,
                'assigned_dept': a.assigned_employee_dept or None,
                'assignment_date': str(a.assignment_date) if a.assignment_date else None,
                'retrieval_flag': a.retrieval_flag,
                'serial_number': a.serial_number or None,
                'last_updated': str(fields.Datetime.now()),
            })
        return {
            'success': True,
            'count': len(result),
            'assets': result,
            'exported_at': str(fields.Datetime.now()),
        }

    @http.route(
        '/api/myservice/assets/export/csv', type='http', auth='none',
        methods=['GET'], csrf=False,
    )
    def export_assets_csv(self, **kwargs):
        """CSV export for systems that don't support JSON."""
        key = request.httprequest.args.get('api_key', '')
        stored = request.env['ir.config_parameter'].sudo().get_param(
            'myservice_identity.redhubs_api_key', 'NRS_REDHUBS_KEY_2025',
        )
        if key != stored:
            return request.make_response('Unauthorized', status=401)

        assets = request.env['nrs.asset'].sudo().search([])
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Asset Code', 'Name', 'Category', 'Condition', 'State',
            'Location', 'Assigned To', 'IR Number', 'Department',
            'Assignment Date', 'Retrieval Flag', 'Serial Number',
        ])
        for a in assets:
            writer.writerow([
                a.asset_code,
                a.name,
                a.category_id.name if a.category_id else '',
                a.condition or '',
                a.state or '',
                a.location_id.name if a.location_id else '',
                a.custodian_id.name if a.custodian_id else '',
                a.assigned_ir_number or '',
                a.assigned_employee_dept or '',
                str(a.assignment_date) if a.assignment_date else '',
                'YES' if a.retrieval_flag else 'NO',
                a.serial_number or '',
            ])
        return request.make_response(
            output.getvalue(),
            headers=[
                ('Content-Type', 'text/csv'),
                ('Content-Disposition', 'attachment; filename=nrs_assets.csv'),
            ],
        )
