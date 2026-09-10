from odoo import http
from odoo.addons.myservice_nrs_base.caller_ip import caller_ip_label
from odoo.exceptions import UserError
from odoo.http import request
import hmac
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

    Security: WorkSpace must include the shared token in the X-Callback-Token
    header. A tenant whose `workflow.config` carries no `callback_token` is
    REFUSED — see `workflow_callback` — because an absent credential is the
    one case where "no check" and "check passed" are the same code path, and
    this is the route that approves and rejects requests.

    DEPRECATED: the token is also accepted as a `?token=` query parameter, for
    ONE MORE RELEASE. A credential in a URL is in nginx access logs, proxy
    logs, browser history and any referrer. Every use logs a WARNING naming
    the caller, so the migration has a visible end date.
    """

    @http.route(
        '/myservice/workflow/callback',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def workflow_callback(self, **kwargs):
        """Apply an approval outcome POSTed by the NRS WorkSpace.

        Authentication is the shared `callback_token` in the
        **X-Callback-Token header**.

        .. deprecated::
           The `?token=` query parameter is accepted for ONE MORE RELEASE and
           then removed. It is compared exactly as the header is — a wrong
           `?token=` is still a 401 — but every request that supplies its
           credential that way logs a WARNING naming the caller, because a
           secret in a URL is recorded by every proxy, access log, browser
           history and referrer between WorkSpace and here.
        """
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
        except Exception as e:
            # catch-all: reported — this route is `type='http'`, `auth='public'`
            # and answers a MACHINE, so the one thing it may never do is let
            # Odoo render an HTML error page. `get_active_config()` raises
            # `UserError` and nothing else, which is why the clause is scoped
            # to this one call rather than wrapped round the handler — a
            # `UserError` clause over the whole thing would swallow an outcome
            # handler's `ValidationError` (its subclass on Odoo 19) and answer
            # 503, inviting WorkSpace to retry a payload that can never be
            # accepted. But scoping it to `UserError` alone left a cursor or
            # ORM failure on that `search` producing exactly the HTML page the
            # rule forbids, so the clause is broad and the SCOPE is what keeps
            # it honest.
            if not isinstance(e, UserError):
                _logger.exception("Workflow callback: could not resolve the "
                                  "WorkSpace configuration")
                return self._json_response(
                    {'error': 'Workflow integration is not available'}, 503)
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
            #
            # `if config.callback_token:` meant a tenant that never set one
            # had NO authentication on the endpoint that approves and rejects
            # requests — and an absent credential is the one case where "no
            # check" and "check passed" are the same code path. It refuses.
            #
            # 503 with the same opaque body as an unconfigured tenant, not
            # 401, for three reasons: the caller may have sent a perfectly
            # good token and the fault is OURS; handoff 15 already chose 503
            # for "this tenant was never wired to a WorkSpace", and a config
            # row with no token is the same class of state; and the sentence
            # naming our internal configuration must not be handed to an
            # UNAUTHENTICATED caller. That sentence goes to the log instead,
            # at ERROR — an approval endpoint standing open is not a warning
            # — naming the field and the tenant so an operator can act.
            if not config.callback_token:
                _logger.error(
                    "Workflow callback REFUSED: no callback_token is set on "
                    "the active WorkSpace configuration for database '%s'. "
                    "Set workflow.config.callback_token (Settings → WorkSpace "
                    "Integration); until then this endpoint refuses every "
                    "callback rather than applying an unauthenticated "
                    "approval. %s",
                    request.env.cr.dbname, caller_ip_label())
                return self._json_response(
                    {'error': 'Workflow integration is not available'}, 503)

            header_token = request.httprequest.headers.get('X-Callback-Token')
            if header_token:
                provided = header_token
            else:
                # DEPRECATED — one more release. The value is still COMPARED
                # (a wrong token is still a 401); what is deprecated is the
                # channel. The warning fires whenever something other than
                # the header supplied the credential, match or no match, so
                # the log is the list of callers who still have to migrate.
                #
                # The two off-header channels are named SEPARATELY because
                # they are not equally bad and a migration list that conflates
                # them is wrong about who is at risk. `type='http'` merges the
                # query string AND form fields into `kwargs`, so reading
                # `kwargs['token']` cannot tell them apart — the query string
                # is read from `httprequest.args` explicitly instead. A token
                # in the URL is in nginx's access log, every proxy in front of
                # us and the caller's browser history; a token in a form body
                # is in none of those and is merely non-standard.
                query_token = request.httprequest.args.get('token') or ''
                form_token = kwargs.get('token') or ''
                provided = query_token or form_token
                if query_token:
                    _logger.warning(
                        "Workflow callback: token supplied in the QUERY "
                        "STRING, where it lands in every access log between "
                        "the caller and this process. Deprecated, removed "
                        "next release — send the X-Callback-Token header. "
                        "%s", caller_ip_label())
                elif form_token:
                    _logger.warning(
                        "Workflow callback: token supplied as a FORM FIELD. "
                        "Deprecated, removed next release — send the "
                        "X-Callback-Token header. %s", caller_ip_label())

            if not self._token_matches(provided, config.callback_token):
                _logger.warning(
                    "Workflow callback: invalid token. %s", caller_ip_label())
                return self._json_response({'error': 'Unauthorized'}, 401)

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
                # Form-encoded fallback. `token` is STRIPPED rather than
                # carried through: on a `type='http'` route Odoo merges the
                # query string and the form fields into `kwargs`, so a
                # credential sent on either deprecated channel arrived inside
                # the payload dict — and the INFO line below logs that dict
                # verbatim. The tenant's live shared secret was written to our
                # own log on every non-JSON callback, which is the defect
                # item A2 exists to remove, reproduced one layer in.
                #
                # A credential is authentication, not content. It is consumed
                # by the check above and has no business in the payload at
                # all, so it is removed here rather than masked at the log
                # line — masking leaves it one careless `%s` away from coming
                # back.
                data = {k: v for k, v in kwargs.items() if k != 'token'}

            # `data` is now credential-free on both paths: the JSON branch
            # parses the body, which never carried the token, and the form
            # branch has had it stripped.
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

            # ── Replay, contradiction, or apply ───────────────────────
            #
            # Before ANYTHING is written. A second byte-identical POST used
            # to answer `200 {"ok": true}` and do it all again: another
            # dispatch-log row, another chatter post, and another write of
            # the configured approved stage — which dragged a request a
            # human had since moved onward back to where the approval put
            # it, and appended a `stage_changed` event for a stage that had
            # not changed.
            #
            # The check has to sit here rather than inside the three
            # handlers because the dispatch-log row is written before they
            # are called. `_workflow_callback_disposition` is on the model
            # so that the `/api/v1` twin reaches the identical decision.
            #
            # The comment goes in because `queried` dedups on the PAIR: a
            # decision arrives once, but WorkSpace can ask a second, genuinely
            # different question while the first is still open, and comparing
            # the outcome alone dropped it.
            disposition = req._workflow_callback_disposition(outcome, comment)

            if disposition == req.CALLBACK_REPLAY:
                # The caller replayed a request we honoured. Telling them so
                # is the truth, and not applying the outcome a second time is
                # the whole point — handoff 06's "one physical act is one
                # event", inbound.
                #
                # But "does not re-apply" must not mean "discards in silence",
                # and it must not mean "names it and drops it" where the field
                # has a home. The disposition compares the outcome (and, for
                # `queried`, the text), so a second `approved` carrying a
                # `payment_ref` the first did not have is still a replay — and
                # both fields are optional in the published schema, so a
                # caller sending the approval first and the reference when it
                # clears is doing nothing wrong. The reference is RECORDED;
                # anything with nowhere to go is named. Rule 3.
                stored, discarded = req._record_replay_extras(
                    payment_ref, comment)
                if stored:
                    # INFO, not WARNING. This is the feature working: the
                    # caller sent something useful late and we kept it. A
                    # level that says "look at this" on the correct path is
                    # how a log stops being read.
                    _logger.info(
                        "Workflow callback: request %s is already '%s'; the "
                        "outcome was NOT applied again and the repeat carried "
                        "%s, which is now recorded on the request. "
                        "(workspace_ref=%r) %s",
                        ref, outcome, ', '.join(stored), workspace_ref,
                        caller_ip_label())
                if discarded:
                    # WARNING is right here and only here: something the
                    # caller sent has nowhere to go and is gone.
                    _logger.warning(
                        "Workflow callback: request %s is already '%s'; the "
                        "repeat was NOT applied and it carried %s, which is "
                        "therefore discarded. (workspace_ref=%r) %s",
                        ref, outcome, ', '.join(discarded), workspace_ref,
                        caller_ip_label())
                if not stored and not discarded:
                    _logger.info(
                        "Workflow callback: request %s is already '%s'; "
                        "replay ignored, nothing written (workspace_ref=%r). "
                        "%s", ref, outcome, workspace_ref, caller_ip_label())
                if stored:
                    # "nothing changed" stopped being true the moment a late
                    # reference was recorded, and a body that says it anyway
                    # is the silent degradation one sentence further on.
                    message = ("Outcome '%s' was already applied to request "
                               "'%s' and was not applied again; %s recorded"
                               % (outcome, ref, ', '.join(stored)))
                else:
                    message = ("Outcome '%s' was already applied to request "
                               "'%s'; nothing changed" % (outcome, ref))
                body = {
                    'ok': True,
                    'replayed': True,
                    'message': message,
                }
                # Additive, both of them. `discarded_fields` keeps exactly the
                # meaning it shipped with — what the repeat carried that went
                # nowhere — and `stored_fields` is a new key beside it, so a
                # caller reading only the old one is never told a stored field
                # was dropped.
                if stored:
                    body['stored_fields'] = stored
                if discarded:
                    body['discarded_fields'] = discarded
                return self._json_response(body)

            if disposition == req.CALLBACK_CONFLICT:
                # Two systems disagreeing about one request. NOT absorbed:
                # applying it would overwrite a recorded decision on the say-so
                # of a message that may be a stale redelivery arriving out of
                # order, and there is nothing in the payload that can tell the
                # two apart. 409 names both outcomes so the caller knows
                # exactly what we hold; a reversal is a human decision and now
                # requires one. ERROR, not WARNING — this is the one case here
                # where somebody has to look.
                _logger.error(
                    "Workflow callback CONFLICT: request %s is '%s' and the "
                    "callback says '%s'. Refused — a recorded decision is not "
                    "overwritten by a later contradicting one. Re-send the "
                    "request to WorkSpace if the decision genuinely changed. "
                    "(workspace_ref=%r) %s",
                    ref, req.workflow_status, outcome, workspace_ref,
                    caller_ip_label())
                return self._json_response({
                    'error': ("Request '%s' is already '%s'; refusing to "
                              "apply '%s'" % (ref, req.workflow_status, outcome)),
                    'current_outcome': req.workflow_status,
                    'attempted_outcome': outcome,
                }, 409)

            # ── Find or create dispatch log ───────────────────────────
            # Shared with the /api/v1 twin, which used to always append a
            # fresh inbound row and so left an answered outbound dispatch
            # reading `sent` for ever.
            log = request.env['workflow.dispatch.log'].sudo()._reconcile_callback(
                req, outcome, workspace_ref, data)

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
                'replayed': False,
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

    @staticmethod
    def _token_matches(provided, expected):
        """Constant-time comparison of two shared secrets.

        `!=` on a string leaks the length of the matching prefix through
        timing. `hmac.compare_digest` accepts `str` only when BOTH sides are
        ASCII-only and raises `TypeError` otherwise — and `provided` is
        attacker-controlled text, so that is a `TypeError` an unauthenticated
        caller could trigger at will. Encoding both sides to UTF-8 bytes
        removes the guard and the exception together: `compare_digest` on
        `bytes` has no such restriction.
        """
        if not provided or not expected:
            return False
        return hmac.compare_digest(
            str(provided).encode('utf-8'), str(expected).encode('utf-8'))

    def _json_response(self, data, status=200):
        return request.make_response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')],
            status=status,
        )
