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


def _raw_json_body():
    """The POSTed JSON body, JSON-RPC envelope stripped, or ``{}``.

    ``request.jsonrequest`` DOES NOT EXIST on Odoo 19. It is an attribute of
    the dispatcher, never of ``request``, so reading it raises
    ``AttributeError`` — and this file read it on the branch reached when
    ``kwargs`` is empty, which is exactly the branch whose intended answer is
    ``{'success': False, 'error': 'Empty payload'}``. A caller POSTing an
    empty or non-JSON-RPC body got a 500 instead, on an ``auth='none'`` route
    an external system calls.

    ``request.get_json_data()`` is the public replacement. The dispatcher has
    already parsed the body by the time a handler runs and werkzeug caches
    the raw data, so re-reading costs a parse and no I/O. ``ValueError``
    covers a body that is not JSON and one that is not UTF-8; the dispatcher
    would normally have refused first, so this is the belt on the braces.
    """
    try:
        payload = request.get_json_data()
    except (ValueError, AttributeError):
        return {}
    if isinstance(payload, dict) and 'params' in payload and 'jsonrpc' in payload:
        payload = payload['params']
    return payload or {}


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
        # Also support raw JSON POST (non-RPC), where the body IS the payload
        # and `kwargs` is empty because there was no `params` key to unpack.
        payload = kwargs if kwargs else _raw_json_body()

        if not payload:
            return {'success': False, 'error': 'Empty payload'}

        employees = payload if isinstance(payload, list) else [payload]
        # A JSON body is legally a list, an object, a string or a number, and
        # only the first two are employees. Without this, `["a", "b"]` or a
        # bare `5` reaches `emp_data.get(...)` and raises `AttributeError` —
        # a 500 on the unauthenticated route, on the same branch the fix
        # above exists to make answer properly. The twin below already
        # guarded this; this one stopped a line short.
        if not all(isinstance(emp, dict) for emp in employees):
            return {'success': False,
                    'error': 'Expected an employee object or a list of them'}
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
        payload = dict(kwargs) if kwargs else _raw_json_body()
        if not isinstance(payload, dict):
            # A raw JSON list is a legal body on the sync route above, which
            # handles many employees. This probe handles one, and
            # `.setdefault` on a list is an AttributeError — a 500 on an
            # authenticated route, same family as the defect above.
            return {'success': False,
                    'error': 'Expected a single employee object'}
        payload = dict(payload)
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
