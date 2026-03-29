import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class SAPWebhookController(http.Controller):

    @http.route(
        '/api/sap/employee-sync', type='json', auth='none',
        methods=['POST'], csrf=False,
    )
    def sap_employee_sync(self, **kwargs):
        """Receive SAP SuccessFactors employee change events.

        Expects ``X-SAP-Webhook-Secret`` header for auth.
        Payload may be a single dict or a list of dicts.
        """
        secret = request.env['ir.config_parameter'].sudo().get_param(
            'myservice_identity.sap_webhook_secret', 'NRS_SAP_WEBHOOK_SECRET_2025',
        )
        if request.httprequest.headers.get('X-SAP-Webhook-Secret', '') != secret:
            _logger.warning(
                'SAP webhook: invalid secret from %s',
                request.httprequest.remote_addr,
            )
            return {'success': False, 'error': 'Unauthorized'}

        payload = request.jsonrequest
        if not payload:
            return {'success': False, 'error': 'Empty payload'}

        employees = payload if isinstance(payload, list) else [payload]
        results = []

        SyncLog = request.env['nrs.sap.sync.log'].sudo()
        for emp_data in employees:
            employee, log = SyncLog.process_sap_payload(emp_data, sync_type='webhook')
            results.append({
                'ir_number': emp_data.get('ir_number') or emp_data.get('userId', 'unknown'),
                'status': log.status,
                'employee_id': employee.id if employee else None,
                'changes': log.changes_applied or '',
            })

        return {'success': True, 'processed': len(results), 'results': results}

    @http.route(
        '/api/sap/employee-sync/test', type='json', auth='user',
        methods=['POST'], csrf=False,
    )
    def sap_sync_test(self, **kwargs):
        """Authenticated test endpoint for verifying integration."""
        payload = request.jsonrequest or {}
        payload.setdefault('event', 'TestEvent')
        employee, log = request.env['nrs.sap.sync.log'].sudo().process_sap_payload(
            payload, sync_type='manual',
        )
        return {
            'success': log.status in ('success', 'skipped'),
            'log_id': log.id,
            'status': log.status,
            'employee': employee.name if employee else None,
            'changes': log.changes_applied,
        }
