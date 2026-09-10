"""SAP SuccessFactors inbound webhook.

Handoff 17 item B. ``/api/sap/employee-sync`` resolved its shared secret with
``get_param('...sap_webhook_secret', 'NRS_SAP_WEBHOOK_SECRET_...')`` — a
default committed to this repository. On any tenant where the parameter was
never set, an unauthenticated caller holding a string from git history could
write employee records. Unset configuration now REFUSES, loudly, at ERROR.

``get_param`` with no default returns ``False`` for a parameter that does not
exist, and a stored empty value is no better; both refuse rather than
compare-equal to an absent header.

The literal that used to sit here is in git history and cannot be removed from
it. The secret it authenticates must be rotated on the box.
"""
import hmac
import logging

from odoo import http
from odoo.http import request

from odoo.addons.myservice_nrs_base.caller_ip import caller_ip_label

_logger = logging.getLogger(__name__)

#: The ONE name of the SAP credential in this module, resolved in exactly one
#: place below so a default cannot creep back into a second call site.
SAP_SECRET_PARAM = 'myservice_identity.sap_webhook_secret'


def _expected_sap_secret():
    """The configured SAP webhook secret, or ``None`` when there is none."""
    value = request.env['ir.config_parameter'].sudo().get_param(SAP_SECRET_PARAM)
    return value or None


def _secrets_equal(supplied, expected):
    """Constant-time comparison; both sides encoded, so non-ASCII is safe."""
    return hmac.compare_digest(
        str(supplied or '').encode('utf-8'),
        str(expected or '').encode('utf-8'),
    )


class SAPWebhookController(http.Controller):

    @http.route(
        '/api/sap/employee-sync', type='json', auth='none',
        methods=['POST'], csrf=False,
    )
    def sap_employee_sync(self, **kwargs):
        """Receive SAP SuccessFactors employee change events.

        Requires the ``X-SAP-Webhook-Secret`` header, matched against
        ``myservice_identity.sap_webhook_secret``. An unset parameter refuses
        every caller and says so at ERROR — the body stays opaque, because
        this is an ``auth='none'`` route and must not name our configuration
        to whoever is knocking.

        Payload may be a single dict or a list of dicts.
        """
        expected = _expected_sap_secret()
        if expected is None:
            _logger.error(
                'REFUSED /api/sap/employee-sync: the webhook secret is not '
                'configured. Set the ir.config_parameter %r on database %s; '
                'until then this route answers Unauthorized to every caller.',
                SAP_SECRET_PARAM, request.env.cr.dbname,
            )
            return {'success': False, 'error': 'Unauthorized'}

        supplied = request.httprequest.headers.get('X-SAP-Webhook-Secret')
        if not _secrets_equal(supplied, expected):
            _logger.warning(
                'SAP webhook: invalid secret. %s', caller_ip_label(),
            )
            return {'success': False, 'error': 'Unauthorized'}

        # For type='json' routes, Odoo unpacks JSON-RPC params into kwargs.
        # Also support raw JSON POST (non-RPC) where request.jsonrequest
        # holds the payload directly.
        if kwargs:
            payload = kwargs
        else:
            payload = request.jsonrequest or {}
            # Strip JSON-RPC envelope if present
            if 'params' in payload and 'jsonrpc' in payload:
                payload = payload['params']

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
        payload = dict(kwargs) if kwargs else dict(request.jsonrequest or {})
        if 'params' in payload and 'jsonrpc' in payload:
            payload = payload['params']
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
