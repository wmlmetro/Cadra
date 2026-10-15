from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import json

_logger = logging.getLogger(__name__)

# Purposes. `workspace` is the original approval integration; `asset_events`
# is the outbound INT-05 leg that carries `asset.tag.affixed` to Vendra. They
# are separate CONFIG RECORDS rather than more fields on one, because they are
# different systems with different URLs, credentials and timeouts that happen
# to want the same adapter machinery.
PURPOSE_WORKSPACE = 'workspace'
PURPOSE_ASSET_EVENTS = 'asset_events'
# INT-06/07/09. A SEPARATE record from `asset_events` and not a second URL on
# it, for the reason above and one more: Vendra and SAP fail differently. SAP
# is an ERP behind a corporate gateway with change windows; Vendra is a
# service we operate. Sharing one retry policy between them would mean tuning
# for whichever is worse and being wrong for the other.
PURPOSE_SAP_ASSETS = 'sap_assets'

# Purposes whose rows are drained by the outbound event queue rather than sent
# synchronously. Anything added here must satisfy `_check_asset_event_config`.
EVENT_PURPOSES = (PURPOSE_ASSET_EVENTS, PURPOSE_SAP_ASSETS)


class WorkflowConfig(models.Model):
    """
    Stores the connection configuration for an outbound integration target.

    Historically this was only the NRS WorkSpace approval system, one active
    record per database. It now also carries the INT-05 asset-event callback
    to Vendra, distinguished by `purpose` — see `get_active_config`.
    """
    _name = 'workflow.config'
    _description = 'NRS WorkSpace Integration Configuration'
    _rec_name = 'name'

    name = fields.Char(string='Configuration Name', required=True,
                       default='NRS WorkSpace')
    active = fields.Boolean(default=True)

    # ── What this config points at ────────────────────────────────────
    #
    # Defaults to `workspace` so every row that existed before this field
    # did keeps its meaning: Odoo applies a new stored field's default to
    # existing rows when it adds the column, and `get_active_config()` still
    # resolves the approval config by default. A tenant with no Vendra simply
    # has no `asset_events` row, and no callback fires — which is the honest
    # state for seven of our eight tenants today.
    purpose = fields.Selection([
        (PURPOSE_WORKSPACE, 'NRS WorkSpace — request approvals'),
        (PURPOSE_ASSET_EVENTS, 'Asset lifecycle events (INT-05 → Vendra)'),
        (PURPOSE_SAP_ASSETS, 'SAP asset master & lifecycle (INT-06/07/09)'),
    ], string='Purpose', required=True, default=PURPOSE_WORKSPACE,
       help='Which integration this configuration describes. Asset lifecycle '
            'events are delivered by the retry queue, not synchronously.')

    # ── Adapter type ──────────────────────────────────────────────────
    adapter_type = fields.Selection([
        ('rest',  'REST API (HTTP/JSON)'),
        ('soap',  'SOAP / XML Web Service'),
        ('email', 'Email-based (structured email)'),
        ('stub',  'Stub / Test mode (no real send)'),
    ], string='Adapter Type', required=True, default='stub',
       help='Select once the NRS IT team confirms the NRS WorkSpace interface.')

    # ── REST adapter settings ─────────────────────────────────────────
    rest_base_url = fields.Char(
        string='Workflow API Base URL',
        help='e.g. https://workflow.nrs.gov.ng/api/v1')
    rest_endpoint_submit = fields.Char(
        string='Submit Endpoint',
        default='/requests/submit',
        help='Appended to base URL for new request submissions')
    rest_auth_type = fields.Selection([
        ('none',   'No authentication'),
        ('apikey', 'API Key (header)'),
        ('bearer', 'Bearer Token'),
        ('basic',  'Basic Auth (username/password)'),
    ], string='Auth Type', default='apikey')
    rest_api_key = fields.Char(string='API Key / Token')
    rest_api_key_header = fields.Char(
        string='API Key Header Name', default='X-API-Key')
    rest_username = fields.Char(string='Username')
    rest_password = fields.Char(string='Password')
    rest_timeout = fields.Integer(string='Timeout (seconds)', default=30)

    # ── Asset-event (INT-05) settings ─────────────────────────────────
    rest_endpoint_event = fields.Char(
        string='Event Endpoint',
        help="Appended to the base URL for outbound asset lifecycle events. "
             "Vendra is Frappe, so this is typically a whitelisted method "
             "path such as /api/method/vendra_network.api.tag_event.")
    # Handoff 62. `asset.register_state.changed` goes to its OWN receiver on
    # the same Vendra, beside `asset.tag.affixed`'s, so neither side's INT-05
    # handling had to change. Blank is the state of a Vendra that predates
    # that receiver (Vendra handoff 57): nothing is queued for it, rather
    # than every move of every unit being refused and dead-lettered.
    rest_endpoint_register_state = fields.Char(
        string='Register-State Endpoint',
        help="Appended to the base URL for `asset.register_state.changed` "
             "(INT-05b): a gated unit Vendra sent changed register state. "
             "Typically /api/method/vendra_network.api.cadra."
             "register_state_event. Blank: those events are not queued.")
    event_enabled = fields.Boolean(
        string='Deliver Asset Events',
        default=True,
        help='Pauses DELIVERY, not capture. Events raised while this is off '
             'are still queued and are delivered when it is switched back '
             'on — turning it off must not silently lose the affixes that '
             'happen meanwhile.')

    # ── SAP asset settings (INT-06/07/09) ─────────────────────────────
    #
    # INT-06 and INT-09 are different endpoints on the same host: one creates
    # an asset master, the other posts a change to one that already exists.
    # `rest_endpoint_event` alone could not express that — every event would
    # have gone to one path, and a transfer would have arrived at the
    # create-asset endpoint. See `_endpoint_for_event`.
    rest_endpoint_asset_master = fields.Char(
        string='Asset Master Endpoint',
        help='Appended to the base URL for INT-06 asset master creation. '
             'Lifecycle events (INT-09) go to the Event Endpoint instead.')
    sap_company_code = fields.Char(
        string='SAP Company Code',
        help='Sent on every INT-06 and INT-09 message. A SAP asset number is '
             'only unique within a company code, so an asset master posted '
             'without one is not addressable afterwards. Blank until NRS '
             'confirms the value — see the INT-06/07/09 requirements, §5.3.')

    # ── Retry policy (INT-05) ─────────────────────────────────────────
    #
    # Per tenant, because "how long do we keep trying" is a question about
    # the OTHER end's operational habits, not about Cadra. The defaults give
    # 1m, 2m, 4m, 8m, 16m, 32m, 60m, 60m — a little over three hours of
    # trying, which covers a redeploy or a certificate swap without a human
    # touching anything, and dead-letters before the queue becomes a place
    # events go to be forgotten.
    retry_max_attempts = fields.Integer(
        string='Max Delivery Attempts', default=8,
        help='After this many failed attempts the event is dead-lettered and '
             'surfaced to a human rather than retried forever.')
    retry_base_seconds = fields.Integer(
        string='Retry Base Delay (s)', default=60,
        help='First retry delay. Each subsequent attempt doubles it, up to '
             'the cap.')
    retry_cap_seconds = fields.Integer(
        string='Retry Delay Cap (s)', default=3600,
        help='Ceiling on the exponential backoff.')

    @api.constrains('purpose', 'adapter_type', 'rest_base_url',
                    'rest_endpoint_event', 'retry_max_attempts',
                    'retry_base_seconds', 'retry_cap_seconds')
    def _check_asset_event_config(self):
        """Reject an unusable asset-event config at save time.

        An event target that is missing its URL does not fail quietly — it
        fails once per affix, three hours later, in a dead-letter queue. The
        cheapest place to catch that is the form someone is already looking
        at.
        """
        for rec in self:
            if rec.purpose not in EVENT_PURPOSES:
                continue
            if rec.adapter_type not in ('rest', 'stub'):
                raise ValidationError(_(
                    'Asset lifecycle events can only be delivered by the REST '
                    'or Stub adapter. "%s" carries human-readable approvals, '
                    'not machine events.'
                ) % dict(self._fields['adapter_type'].selection).get(
                    rec.adapter_type, rec.adapter_type))
            if rec.adapter_type == 'rest':
                if not (rec.rest_base_url or '').strip():
                    raise ValidationError(_(
                        'An asset-event configuration using the REST adapter '
                        'needs a base URL.'))
                if not (rec.rest_endpoint_event or '').strip():
                    raise ValidationError(_(
                        'An asset-event configuration using the REST adapter '
                        'needs an event endpoint.'))
                if (rec.purpose == PURPOSE_SAP_ASSETS
                        and not (rec.rest_endpoint_asset_master or '').strip()):
                    raise ValidationError(_(
                        'A SAP configuration needs an asset master endpoint '
                        '(INT-06) as well as an event endpoint (INT-09). '
                        'They are different operations on different URLs, '
                        'and posting a transfer to the create-asset endpoint '
                        'would be a new asset master rather than a change to '
                        'the existing one.'))
            if rec.retry_max_attempts < 1:
                raise ValidationError(_(
                    'Max delivery attempts must be at least 1; 0 would '
                    'dead-letter every event without ever trying it.'))
            if rec.retry_base_seconds < 1:
                raise ValidationError(_(
                    'Retry base delay must be at least 1 second.'))
            if rec.retry_cap_seconds < rec.retry_base_seconds:
                raise ValidationError(_(
                    'Retry delay cap (%(cap)ss) cannot be below the base '
                    'delay (%(base)ss).'
                ) % {'cap': rec.retry_cap_seconds,
                     'base': rec.retry_base_seconds})

    # ── Email adapter settings ────────────────────────────────────────
    email_to = fields.Char(
        string='Workflow Email Address',
        help='Email address Workflow monitors for incoming requests')
    email_subject_prefix = fields.Char(
        string='Subject Prefix', default='[NRS-WORKFLOW]')

    # ── Callback / webhook settings ───────────────────────────────────
    callback_enabled = fields.Boolean(
        string='Enable Webhook Callback',
        default=True,
        help='Allow Workflow to POST approval outcomes back to myservice')
    callback_token = fields.Char(
        string='Callback Security Token',
        help='Shared secret Workflow must send in X-Callback-Token header')
    callback_url_hint = fields.Char(
        string='Callback URL (read-only)',
        compute='_compute_callback_url')

    # ── Stage mapping ─────────────────────────────────────────────────
    trigger_stage_ids = fields.Many2many(
        comodel_name='request.stage',
        relation='workflow_config_trigger_stage_rel',
        string='Auto-trigger Stages',
        help='Requests entering these stages are automatically sent to WorkSpace')
    approved_stage_id = fields.Many2one(
        comodel_name='request.stage',
        string='Approved → Move to Stage',
        help='Stage to advance request to when Workflow returns Approved')
    rejected_stage_id = fields.Many2one(
        comodel_name='request.stage',
        string='Rejected → Move to Stage',
        help='Stage to move request back to when Workflow returns Rejected')

    # ── Payload options ───────────────────────────────────────────────
    include_attachments = fields.Boolean(
        string='Include Attachments in Payload', default=True)
    payload_template = fields.Text(
        string='Custom Payload Template (JSON)',
        help='Optional Jinja2/JSON template override for the request payload. '
             'Leave blank to use default.')
    notes = fields.Text(string='Integration Notes',
                        help='Internal notes for the integration team')

    @api.depends('callback_enabled')
    def _compute_callback_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', 'https://myservice.com.ng')
        for rec in self:
            rec.callback_url_hint = f"{base}/myservice/workflow/callback"

    def action_test_connection(self):
        """Test the connection to the NRS WorkSpace."""
        self.ensure_one()
        if self.adapter_type == 'stub':
            return self._notify('Stub mode — no real connection. Change adapter type when ready.')
        adapter = self._get_adapter()
        result = adapter.ping()
        if result.get('ok'):
            return self._notify(f"Connection successful: {result.get('message','OK')}")
        raise UserError(f"Connection failed: {result.get('error','Unknown error')}")

    def _get_adapter(self):
        """Factory — returns the correct adapter based on config."""
        self.ensure_one()
        if self.adapter_type == 'rest':
            return WorkflowRestAdapter(self)
        elif self.adapter_type == 'email':
            return WorkflowEmailAdapter(self)
        else:
            return WorkflowStubAdapter(self)

    def _notify(self, msg):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'WorkSpace Integration',
                'message': msg,
                'type': 'success',
                'sticky': False,
            }
        }

    def _endpoint_for_event(self, event_type):
        """Which path this event goes to.

        Routing on the event type rather than on the config's purpose keeps
        the adapter free of interface-specific knowledge: it asks the target
        where this event goes and POSTs there. Anything not named here falls
        back to the general event endpoint, which is what INT-05's
        `asset.tag.affixed` has always used and must keep using.
        """
        self.ensure_one()
        if event_type == 'asset.master.create' and self.rest_endpoint_asset_master:
            return self.rest_endpoint_asset_master
        if event_type == 'asset.register_state.changed':
            # Its own receiver, never the general one: Vendra's tag receiver
            # refuses a body that is not a tag event. Blank here is caught
            # by the adapter as "no event endpoint" — permanent, said.
            return self.rest_endpoint_register_state
        return self.rest_endpoint_event

    @api.model
    def get_active_config(self, purpose=PURPOSE_WORKSPACE):
        """The active config for a purpose. Raises when there is none.

        Defaults to `workspace` so the approval flow's existing calls keep
        resolving the approval config even on a tenant that has since grown an
        `asset_events` row. Callers that can cope with "no target configured"
        must use `get_event_config()` instead — a missing Vendra is a normal
        state here, not an error.
        """
        cfg = self.search([
            ('active', '=', True),
            ('purpose', '=', purpose),
        ], limit=1)
        if not cfg:
            raise UserError(
                'No active Workflow integration configuration found for "%s". '
                'Please configure one under Settings → WorkSpace Integration.'
                % purpose)
        return cfg

    @api.model
    def get_event_config(self, include_disabled=False,
                         purpose=PURPOSE_ASSET_EVENTS):
        """The event target for a purpose, or an empty recordset.

        Empty is the ordinary answer on seven of our eight tenants: only the
        one wired to a Vendra has anywhere to send `asset.tag.affixed`. So
        this returns rather than raises, and the caller logs the skip.

        `include_disabled` is what the ENQUEUE path passes. `event_enabled`
        is an off-switch for DELIVERY, not a shredder: an affix that happens
        while the switch is off is still a real affix, and discarding its
        event would mean flipping the switch back on silently loses every
        event in between with no way to notice or backfill. The drain
        excludes disabled targets in its own domain, so the events queue and
        wait instead.

        `purpose` defaults to the Vendra leg so handoff 06's call sites keep
        their meaning unchanged; the SAP legs pass `PURPOSE_SAP_ASSETS`.
        """
        domain = [
            ('active', '=', True),
            ('purpose', '=', purpose),
        ]
        if not include_disabled:
            domain.append(('event_enabled', '=', True))
        return self.search(domain, limit=1)


# ══════════════════════════════════════════════════════════════════════
# ADAPTERS
# ══════════════════════════════════════════════════════════════════════
#
# `submit()` carries a human approval and is one-shot. `deliver()` carries a
# machine event and is driven by the retry queue, so its result has to say
# more than ok/not-ok: the queue needs to know whether trying again could
# possibly help.
#
# The `deliver()` contract:
#
#   {'ok':           bool,        # delivered
#    'retryable':    bool,        # only meaningful when ok is False
#    'status':       int | None,  # HTTP status, when there was one
#    'body':         str,         # response text, truncated
#    'external_ref': str | None,  # the receiver's own id for the event
#    'acknowledged': bool,        # receiver returned an identity, not just 2xx
#    'error':        str | None}
#
# `retryable` defaults to True in the queue for anything that forgets to say,
# because retrying a deliverable event costs a minute and dropping one costs
# an audit trail.

# 429 is the only 4xx worth retrying: it is the receiver asking us to wait,
# not refusing the payload. Every other 4xx is a statement about the request
# itself, and a request does not become valid by being sent eight more times.
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429})

# A receiver that recognises our `event_id` as already processed has, by
# definition, received the event. Treating its 409 as a failure would
# dead-letter events that landed perfectly.
DUPLICATE_STATUS_CODES = frozenset({409})

_MAX_STORED_BODY = 2000


class WorkflowStubAdapter:
    """
    Stub adapter — simulates a successful send without contacting
    any external system. Use during development and testing.
    """
    def __init__(self, config):
        self.config = config

    def ping(self):
        return {'ok': True, 'message': 'Stub adapter — always succeeds'}

    def submit(self, payload):
        import uuid
        ref = f"WF-STUB-{uuid.uuid4().hex[:8].upper()}"
        _logger.info("STUB: Would send payload to Workflow — ref: %s", ref)
        _logger.info("STUB payload: %s", json.dumps(payload, indent=2, default=str))
        return {
            'ok': True,
            'workspace_ref': ref,
            'message': 'Stub — simulated submission accepted',
        }

    def deliver(self, payload, event_id, request_ref=None, event_type=None):
        import uuid
        ref = f"EV-STUB-{uuid.uuid4().hex[:8].upper()}"
        _logger.info("STUB: would deliver event %s (event_id=%s) — ref %s",
                     payload.get('event') or event_type, event_id, ref)
        return {
            'ok': True, 'retryable': False, 'status': 200,
            'body': json.dumps({'stub': True, 'ref': ref}),
            'external_ref': ref, 'acknowledged': True, 'error': None,
        }


class WorkflowRestAdapter:
    """
    REST/JSON adapter. Connects to the Workflow API endpoint.
    NRS IT team to provide: base URL, auth credentials, endpoint paths.
    """
    def __init__(self, config):
        self.config = config

    def _get_headers(self):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.config.rest_auth_type == 'apikey':
            headers[self.config.rest_api_key_header or 'X-API-Key'] = \
                self.config.rest_api_key or ''
        elif self.config.rest_auth_type == 'bearer':
            headers['Authorization'] = f"Bearer {self.config.rest_api_key or ''}"
        return headers

    def _get_auth(self):
        if self.config.rest_auth_type == 'basic':
            return (self.config.rest_username or '',
                    self.config.rest_password or '')
        return None

    def ping(self):
        import requests as req
        try:
            url = (self.config.rest_base_url or '').rstrip('/') + '/ping'
            r = req.get(url, headers=self._get_headers(),
                        auth=self._get_auth(),
                        timeout=self.config.rest_timeout or 10)
            if r.status_code < 400:
                return {'ok': True, 'message': f"HTTP {r.status_code}"}
            return {'ok': False, 'error': f"HTTP {r.status_code}: {r.text[:200]}"}
        # "The target is unreachable" is the answer this button exists to
        # produce, and every way of being unreachable — DNS, TLS, a refused
        # connection, a timeout, a base URL with no scheme — arrives as a
        # `RequestException`. Nothing else in the block can raise: the config
        # reads are Char fields guarded with `or ''`, and `status_code` and
        # `text` do not raise. So anything else is a defect in Cadra, and
        # `action_test_connection` reporting it as "Connection failed" would
        # send whoever pressed the button to look at the wrong system.
        except req.RequestException as e:
            return {'ok': False, 'error': f"{type(e).__name__}: {e}"}

    def submit(self, payload):
        import requests as req
        try:
            base = (self.config.rest_base_url or '').rstrip('/')
            endpoint = (self.config.rest_endpoint_submit or '/requests/submit').lstrip('/')
            url = f"{base}/{endpoint}"
            r = req.post(
                url,
                headers=self._get_headers(),
                auth=self._get_auth(),
                json=payload,
                timeout=self.config.rest_timeout or 30,
            )
            _logger.info("Workflow REST submit → %s  status=%s", url, r.status_code)
            if r.status_code in (200, 201, 202):
                unparsed = False
                try:
                    data = r.json()
                except ValueError:
                    # NOT optional. We sent `Accept: application/json` and the
                    # request was accepted, so a body we cannot read is not
                    # "the remote is allowed to answer anything" — it is the
                    # one case where a failed submission looks like a
                    # successful one. `workspace_ref` below then falls back to
                    # `WF-200`, a string Cadra invented, which is written onto
                    # the request as *the NRS WorkSpace's own reference* and
                    # shown to the approver in the chatter. An intercepting
                    # proxy or an SSO login page answering `200 text/html` is
                    # exactly this shape.
                    #
                    # `ok` stays True because a 2xx IS an acceptance and
                    # calling it a failure would raise a UserError that aborts
                    # the stage change that triggered the send. What changes is
                    # that it is announced in the log and admitted in the
                    # returned `message`, and `raw` keeps the body it actually
                    # sent. (`requests` raises its own JSONDecodeError, which
                    # is a ValueError; that is the only thing `r.json()` can
                    # raise.)
                    data = {}
                    unparsed = True
                    _logger.warning(
                        "Workflow REST submit → %s accepted with HTTP %s but "
                        "answered a body that is not JSON (content-type %r): "
                        "%s", url, r.status_code,
                        r.headers.get('Content-Type'), r.text[:300],
                        exc_info=True)
                return {
                    'ok': True,
                    'workspace_ref': data.get('reference') or data.get('ref')
                                    or data.get('id') or f"WF-{r.status_code}",
                    'message': data.get(
                        'message',
                        'Submitted — but the response was not JSON and '
                        'carried no WorkSpace reference'
                        if unparsed else 'Submitted'),
                    'raw': r.text[:500],
                }
            return {
                'ok': False,
                'error': f"HTTP {r.status_code}: {r.text[:300]}",
            }
        # Every network-level failure `requests` can produce, `InvalidJSONError`
        # included — that is what a payload it cannot serialise for the wire
        # arrives as. Deliberately NOT `Exception`: the only other thing in
        # here that can raise is a `TypeError` out of `json.dumps` for a value
        # the payload builder should not have produced. `_send_to_workflow`
        # stores the payload with `default=str` and `requests` sends it
        # without, so the two CAN disagree — and reporting that to a user as
        # "Failed to send to NRS WorkSpace" points them at WorkSpace for a
        # defect in Cadra.
        except req.RequestException as e:
            _logger.error("Workflow REST submit error: %s", e, exc_info=True)
            return {'ok': False, 'error': f"{type(e).__name__}: {e}"}

    def deliver(self, payload, event_id, request_ref=None, event_type=None):
        """POST one asset lifecycle event. Never raises — the queue reads the
        returned dict and decides whether to try again.

        `event_type` is passed by the queue only for an event whose body does
        not name itself (`asset.register_state.changed`, handoff 62, whose
        body is Vendra's table and nothing more); every other event is routed
        on its body's `event`, exactly as before.

        Timeouts are split: a TCP connect that has not completed in ten
        seconds is a dead host, not a slow query, and the read budget should
        not be spent waiting for one. Mirrors Vendra's client, which learned
        the same thing pointing the other way down this wire.
        """
        import requests as req
        base = (self.config.rest_base_url or '').rstrip('/')
        # The event says where it goes. INT-06 (asset master creation) and
        # INT-09 (lifecycle changes) are separate operations on separate SAP
        # endpoints, so the adapter asks the config to resolve the path for
        # THIS event rather than assuming one endpoint per target.
        endpoint = (self.config._endpoint_for_event(
            payload.get('event') or event_type) or '').lstrip('/')
        if not base or not endpoint:
            # Config validation should have caught this at save time; if a row
            # got in another way, say so permanently rather than retrying a
            # URL that does not exist.
            return {'ok': False, 'retryable': False, 'status': None, 'body': '',
                    'external_ref': None, 'acknowledged': False,
                    'error': 'Asset-event configuration has no base URL or '
                             'event endpoint'}
        url = f"{base}/{endpoint}"

        headers = self._get_headers()
        # The `X-` prefix is load-bearing in this programme: Cadra's own
        # inbound reader is `X-Idempotency-Key`, and Vendra found that a plain
        # `Idempotency-Key` is silently ignored. Both directions use the same
        # spelling so neither side has to remember which way it is going.
        headers['X-Idempotency-Key'] = event_id
        headers['X-Event-Id'] = event_id
        if request_ref:
            # Correlates a receiver-side log line back to a dispatch row.
            headers['X-Request-Id'] = request_ref

        timeout = self.config.rest_timeout or 30
        try:
            r = req.post(url, headers=headers, auth=self._get_auth(),
                         json=payload,
                         timeout=(max(1, min(10, timeout)), timeout))
        except req.Timeout as e:
            # Safe to retry precisely because the event carries an idempotency
            # key: a replay the receiver already saw is a dedupe, not a second
            # event.
            return {'ok': False, 'retryable': True, 'status': None, 'body': '',
                    'external_ref': None, 'acknowledged': False,
                    'error': f"timeout after {timeout}s: {e}"}
        except req.RequestException as e:
            return {'ok': False, 'retryable': True, 'status': None, 'body': '',
                    'external_ref': None, 'acknowledged': False,
                    'error': f"{type(e).__name__}: {e}"}

        _logger.info("Workflow event deliver → %s  status=%s  event_id=%s",
                     url, r.status_code, event_id)
        return self._classify(r)

    @classmethod
    def _classify(cls, r):
        """Turn one HTTP response into a delivery verdict.

        Split out from `deliver` because "which answers are worth trying
        again" is the single decision the retry queue rests on, and it should
        be assertable without a socket.
        """
        body = (r.text or '')[:_MAX_STORED_BODY]

        if r.status_code in DUPLICATE_STATUS_CODES:
            return {'ok': True, 'retryable': False, 'status': r.status_code,
                    'body': body, 'external_ref': cls._ref_from(r),
                    'acknowledged': True,
                    'error': None}

        if 200 <= r.status_code < 300:
            ref = cls._ref_from(r)
            return {'ok': True, 'retryable': False, 'status': r.status_code,
                    'body': body, 'external_ref': ref,
                    # An identity back is a genuine acknowledgement; a bare
                    # 202 is only "received". Recording them as the same
                    # thing would overstate what we know.
                    'acknowledged': bool(ref), 'error': None}

        retryable = (r.status_code >= 500
                     or r.status_code in RETRYABLE_STATUS_CODES)
        return {'ok': False, 'retryable': retryable, 'status': r.status_code,
                'body': body, 'external_ref': None, 'acknowledged': False,
                'error': f"HTTP {r.status_code}: {body[:300]}"}

    @classmethod
    def _ref_from(cls, response):
        """The receiver's own id for the event, if it returned one."""
        try:
            data = response.json()
        except ValueError:
            # Optional, and the delivery contract already admits the gap
            # rather than hiding it: no identity back means `acknowledged` is
            # False, so `_classify` lands the row at `sent` — "received" — and
            # not at `acknowledged`, while `body` keeps up to 2000 characters
            # of whatever did come back for a human to look at. A receiver is
            # entitled to answer 202 with an empty body and a proxy is
            # entitled to answer 200 with HTML; neither is a delivery failure
            # and neither is an acknowledgement. Narrow because `requests`
            # raises its own JSONDecodeError, which is a ValueError, and that
            # is the only thing `response.json()` can raise.
            _logger.debug(
                "workflow: receiver answered a body that is not JSON; "
                "recording the event as sent, not acknowledged")
            return None
        if not isinstance(data, dict):
            return None
        # Frappe wraps whitelisted method returns in `message`; Cadra's own
        # envelope uses `data`. Look through one level of either.
        inner = data.get('message') or data.get('data') or data
        if not isinstance(inner, dict):
            return None
        # `sap_asset_number` first: on INT-06 it is the receiver's identity
        # for the thing it just created, which is exactly what this field is
        # for, and it is more useful in the log than an echoed event id.
        # Harmless on the Vendra leg, which never sends it.
        for key in ('sap_asset_number', 'event_id', 'name', 'reference',
                    'ref', 'id'):
            value = inner.get(key)
            if value:
                return str(value)
        return None


class WorkflowEmailAdapter:
    """
    Email adapter — sends a structured email to the NRS WorkSpace's
    monitored inbox. Used when Workflow has no API but monitors email.
    """
    def __init__(self, config):
        self.config = config

    def ping(self):
        if not self.config.email_to:
            return {'ok': False, 'error': 'No Workflow email address configured'}
        return {'ok': True, 'message': f"Email adapter ready → {self.config.email_to}"}

    def deliver(self, payload, event_id, request_ref=None, event_type=None):
        """Machine events do not go by email.

        `_check_asset_event_config` refuses this combination at save time, so
        reaching here means a row got in another way. Permanent, not
        retryable: mailing the same event eight times would not make it
        arrive as an API call.
        """
        return {'ok': False, 'retryable': False, 'status': None, 'body': '',
                'external_ref': None, 'acknowledged': False,
                'error': 'The email adapter cannot deliver machine events; '
                         'configure the asset-event target with the REST '
                         'adapter.'}

    def submit(self, payload):
        import uuid
        ref = f"WF-EMAIL-{uuid.uuid4().hex[:8].upper()}"
        try:
            subject = (
                f"{self.config.email_subject_prefix or '[NRS-WORKFLOW]'} "
                f"Approval Request: {payload.get('reference','N/A')} — "
                f"{payload.get('type','Request')}"
            )
            body = self._build_email_body(payload, ref)
            mail = self.config.env['mail.mail'].sudo().create({
                'subject': subject,
                'email_to': self.config.email_to,
                'body_html': body,
                'state': 'outgoing',
            })
            mail.send()
            # `mail.mail.send()` does NOT raise when delivery fails. Its
            # default is `raise_exception=False`, under which a dead SMTP
            # host, a missing outgoing mail server or a refused recipient is
            # recorded ON THE MAIL RECORD and the call returns normally. So
            # returning `ok` on the strength of the call not raising is how an
            # approval that never left the server came to be reported as
            # "📤 Sent to NRS WorkSpace" in the chatter and left the request
            # at "Sent — Awaiting Approval", waiting for a reply to a message
            # nobody received. `state` is certain to exist — it is set in the
            # `create` above — and is re-read because `_send` writes it
            # through a different environment.
            mail = mail.exists()
            if mail:
                mail.invalidate_recordset(['state'])
            if mail and mail.state == 'exception':
                _logger.error(
                    "Workflow email to %s was NOT delivered (ref %s); Odoo "
                    "recorded the failure against the mail record",
                    self.config.email_to, ref)
                return {
                    'ok': False,
                    'error': 'The approval email to %s was not delivered. '
                             'Odoo recorded the reason against the message '
                             'in Settings → Technical → Email → Emails.'
                             % self.config.email_to,
                }
            _logger.info("Workflow email sent to %s ref=%s", self.config.email_to, ref)
            return {'ok': True, 'workspace_ref': ref, 'message': f"Email sent to {self.config.email_to}"}
        except Exception as e:
            # catch-all: unknown — `mail.mail` create/send reaches Odoo core's
            # mail stack and the SMTP libraries under it, and this module
            # cannot enumerate that failure surface from here.
            #
            # Broad rather than narrowed because of what `submit()` owes its
            # caller: `_send_to_workflow` reads a VERDICT DICT and turns a
            # failure into a UserError itself. An escape from here does not
            # reach that code — it aborts the `write()` that triggered the
            # send, so a mail server outage would come back as a traceback on
            # a stage change. The traceback is logged either way.
            _logger.error("Workflow email error: %s", e, exc_info=True)
            return {'ok': False, 'error': f"{type(e).__name__}: {e}"}

    def _build_email_body(self, payload, ref):
        rows = ''.join(
            f"<tr><td style='padding:6px 12px;font-weight:600;background:#f5f5f5'>{k}</td>"
            f"<td style='padding:6px 12px'>{v}</td></tr>"
            for k, v in payload.items()
            if k not in ('attachments', 'raw_text')
        )
        return f"""
<div style='font-family:Arial,sans-serif;max-width:640px'>
  <div style='background:#1A1A1A;padding:16px 24px;border-bottom:3px solid #E85426'>
    <h2 style='color:#fff;margin:0;font-size:16px'>NRS myservice — Workflow Approval Request</h2>
    <p style='color:rgba(255,255,255,0.6);margin:4px 0 0;font-size:12px'>Ref: {ref}</p>
  </div>
  <table style='width:100%;border-collapse:collapse;margin:16px 0'>{rows}</table>
  <p style='font-size:12px;color:#888'>
    This request was submitted from NRS myservice.com.ng.<br>
    To respond, use your NRS WorkSpace or reply to this email with:
    APPROVED / REJECTED / QUERY: [your comment]
  </p>
</div>"""
