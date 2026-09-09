from odoo import http
from odoo.exceptions import UserError
from odoo.http import request
import json
import logging
import uuid

_logger = logging.getLogger(__name__)


class WorkflowCallbackController(http.Controller):
    """
    Receives inbound callbacks from the NRS WorkSpace.

    The NRS WorkSpace POSTs approval outcomes to this endpoint.
    Supported payload formats:
      - JSON body (preferred)
      - Form-encoded (fallback)

    Expected JSON structure:
    {
        "reference":     "REQ-2026-001",       // myservice request name
        "workspace_ref":  "WF-ABC-12345",        // Workflow's own reference
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
        # Resolved OUTSIDE the main try, and with its own narrow clause, so
        # that "this tenant has no WorkSpace configuration" cannot be confused
        # with a failure applying an outcome. `get_active_config()` raises
        # UserError and nothing else; on Odoo 19 UserError is the PARENT of
        # ValidationError, AccessError and MissingError, so a clause this wide
        # sitting over the whole handler would swallow an outcome handler's
        # ValidationError and answer 503 — inviting WorkSpace to retry a
        # payload that will never be accepted. Same ordering defect handoff 09
        # found in `cadra_route`, avoided by scope rather than by order.
        try:
            config = request.env['workflow.config'].sudo().get_active_config()
        except UserError as e:
            # A tenant that was never wired to a WorkSpace. That is a real
            # state, not a server fault — and answering 500 in the config's
            # own words ("Please configure one under Settings → WorkSpace
            # Integration") handed an UNAUTHENTICATED caller a sentence about
            # our internal menu structure. 503 is the honest code; the body
            # says nothing the caller could not infer from the route existing.
            _logger.warning("Workflow callback refused: %s", e)
            return self._json_response(
                {'error': 'Workflow integration is not available'}, 503)

        try:
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
                except ValueError:
                    # Reported, not optional. The caller DECLARED
                    # `application/json`; falling back to `kwargs` here throws
                    # the body away and leaves only the query string, so the
                    # very next check answered "reference field is required"
                    # — telling an integration to add a field it had already
                    # sent, for a body we could not read. Rule 3: never let an
                    # integration guess.
                    #
                    # `ValueError` covers both ways in: `json.JSONDecodeError`
                    # is a ValueError, and so is the `UnicodeDecodeError` from
                    # a body that is not UTF-8. Nothing else here can raise.
                    _logger.warning(
                        "Workflow callback: body declared %s but did not "
                        "parse as JSON (from %s)", content_type,
                        request.httprequest.remote_addr, exc_info=True)
                    return self._json_response(
                        {'error': 'Request body is not valid JSON'}, 400)
            else:
                data = kwargs  # form-encoded fallback

            _logger.info("Workflow callback received: %s", json.dumps(data, default=str))

            ref         = data.get('reference', '')
            workspace_ref= data.get('workspace_ref', '')
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
                    'workspace_ref':       workspace_ref,
                    'response_received':  json.dumps(data, default=str),
                })

            # ── Route to correct handler ──────────────────────────────
            if outcome == 'approved':
                req._workflow_callback_approved(
                    workspace_ref=workspace_ref,
                    payment_ref=payment_ref or None,
                    comment=comment or None,
                    log=log,
                )
            elif outcome == 'rejected':
                req._workflow_callback_rejected(
                    workspace_ref=workspace_ref,
                    comment=comment or None,
                    log=log,
                )
            elif outcome == 'queried':
                req._workflow_callback_queried(
                    workspace_ref=workspace_ref,
                    comment=comment,
                    log=log,
                )

            return self._json_response({
                'ok': True,
                'message': f"Outcome '{outcome}' applied to request '{ref}'",
            })

        except Exception:
            # catch-all: unknown — a public webhook must answer JSON rather
            # than let Odoo render an HTML error page at a machine, and what
            # can arrive here is every ORM and business-logic failure reachable
            # from three callback handlers on `request.request`.
            #
            # Two things changed. The body no longer carries `str(e)`: this
            # route is `auth='public'`, and the exception text on this path can
            # be an Odoo message naming models, fields, groups or SQL. A
            # correlation id goes to the caller and the traceback goes to the
            # log, which is the same trade `POST /auth/token` makes.
            #
            # And the cursor is rolled back. The handler catches, so nothing
            # raises out of the dispatcher and Odoo COMMITS the request as a
            # success: a callback that failed halfway through left its inbound
            # dispatch-log row and any partial stage change committed, then
            # answered 500 and invited WorkSpace to send the whole thing again.
            incident = uuid.uuid4().hex[:12]
            _logger.error("Workflow callback error [incident=%s]",
                          incident, exc_info=True)
            request.env.cr.rollback()
            return self._json_response(
                {'error': 'Internal error applying the callback',
                 'incident': incident}, 500)

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
        except UserError as e:
            # Reported. `get_active_config()` raising is the only failure this
            # probe has, and it means "no WorkSpace configuration on this
            # tenant" — which is a real answer to "is the callback endpoint
            # live?", and the answer is no. It used to come back as HTTP 200,
            # so anything checking the STATUS of this probe — which is what a
            # probe is for — was told the integration was healthy on every
            # tenant that has never been configured. The message is safe to
            # keep here: unlike the callback itself, this route is
            # `auth='user'`.
            return self._json_response({'ok': False, 'error': str(e)}, 503)

    def _json_response(self, data, status=200):
        return request.make_response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')],
            status=status,
        )
