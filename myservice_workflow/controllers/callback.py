from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class WorkflowCallbackController(http.Controller):
    """
    Receives inbound callbacks from the NRS Workflow system.

    The Workflow system POSTs approval outcomes to this endpoint.
    Supported payload formats:
      - JSON body (preferred)
      - Form-encoded (fallback)

    Expected JSON structure:
    {
        "reference":     "REQ-2026-001",       // myservice request name
        "workflow_ref":  "WF-ABC-12345",        // Workflow's own reference
        "outcome":       "approved",            // approved | rejected | queried
        "payment_ref":   "PAY-2026-099",        // optional — for payment approvals
        "comment":       "Approved by Director" // optional comment / rejection reason
    }

    Security: Workflow must include the shared token in X-Callback-Token header,
    or as a ?token= query parameter (for systems that can't set custom headers).
    """

    @http.route(
        '/myservice/workflow/callback',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def workflow_callback(self, **kwargs):
        try:
            config = request.env['workflow.config'].sudo().get_active_config()

            # ── Token validation ──────────────────────────────────────
            if config.callback_token:
                provided = (
                    request.httprequest.headers.get('X-Callback-Token')
                    or kwargs.get('token', '')
                )
                if provided != config.callback_token:
                    _logger.warning(
                        "Workflow callback: invalid token from %s",
                        request.httprequest.remote_addr)
                    return request.make_response(
                        json.dumps({'error': 'Unauthorized'}),
                        headers=[('Content-Type', 'application/json')],
                        status=401,
                    )

            # ── Parse payload ─────────────────────────────────────────
            data = {}
            content_type = request.httprequest.content_type or ''
            if 'application/json' in content_type:
                try:
                    data = json.loads(request.httprequest.data.decode('utf-8'))
                except Exception:
                    data = kwargs
            else:
                data = kwargs  # form-encoded fallback

            _logger.info("Workflow callback received: %s", json.dumps(data, default=str))

            ref         = data.get('reference', '')
            workflow_ref= data.get('workflow_ref', '')
            outcome     = (data.get('outcome') or data.get('status') or '').lower().strip()
            payment_ref = data.get('payment_ref', '')
            comment     = data.get('comment') or data.get('reason') or data.get('message') or ''

            if not ref:
                return self._json_response({'error': 'reference field is required'}, 400)
            if outcome not in ('approved', 'rejected', 'queried'):
                return self._json_response(
                    {'error': f"Unknown outcome '{outcome}'. Expected: approved, rejected, queried"}, 400)

            # ── Find the request ──────────────────────────────────────
            req = request.env['request.request'].sudo().search(
                [('name', '=', ref)], limit=1)
            if not req:
                _logger.warning("Workflow callback: request '%s' not found", ref)
                return self._json_response({'error': f"Request '{ref}' not found"}, 404)

            # ── Find or create dispatch log ───────────────────────────
            log = request.env['workflow.dispatch.log'].sudo().search([
                ('request_id', '=', req.id),
                ('direction', '=', 'outbound'),
                ('status', '=', 'sent'),
            ], limit=1, order='create_date desc')

            if not log:
                # Create inbound log if no matching outbound found
                log = request.env['workflow.dispatch.log'].sudo().create({
                    'request_id':         req.id,
                    'direction':          'inbound',
                    'status':             outcome,
                    'workflow_ref':       workflow_ref,
                    'response_received':  json.dumps(data, default=str),
                })

            # ── Route to correct handler ──────────────────────────────
            if outcome == 'approved':
                req._workflow_callback_approved(
                    workflow_ref=workflow_ref,
                    payment_ref=payment_ref or None,
                    comment=comment or None,
                    log=log,
                )
            elif outcome == 'rejected':
                req._workflow_callback_rejected(
                    workflow_ref=workflow_ref,
                    comment=comment or None,
                    log=log,
                )
            elif outcome == 'queried':
                req._workflow_callback_queried(
                    workflow_ref=workflow_ref,
                    comment=comment,
                    log=log,
                )

            return self._json_response({
                'ok': True,
                'message': f"Outcome '{outcome}' applied to request '{ref}'",
            })

        except Exception as e:
            _logger.error("Workflow callback error: %s", e, exc_info=True)
            return self._json_response({'error': str(e)}, 500)

    @http.route(
        '/myservice/workflow/callback/test',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def callback_test(self, **kwargs):
        """Simple GET endpoint to verify the callback URL is reachable."""
        try:
            config = request.env['workflow.config'].sudo().get_active_config()
            return self._json_response({
                'ok': True,
                'message': 'Callback endpoint is live',
                'callback_enabled': config.callback_enabled,
                'adapter': config.adapter_type,
            })
        except Exception as e:
            return self._json_response({'ok': False, 'error': str(e)})

    def _json_response(self, data, status=200):
        return request.make_response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')],
            status=status,
        )
