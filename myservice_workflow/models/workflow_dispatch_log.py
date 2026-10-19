from odoo import models, fields, api, release, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import config as odoo_config
from markupsafe import Markup, escape
import datetime
import json
import logging
import uuid

_logger = logging.getLogger(__name__)

_ODOO_MAJOR = release.version_info[0]

# Statuses the drain may act on. Deliberately the same two words Vendra's
# outbox uses (`Queued` / `Failed`) so the two halves of INT-03/INT-05 read
# the same way when someone is debugging both at once.
RETRYABLE_STATUSES = ('pending', 'error')

# Delivered, by either reading. `sent` means the receiver took it;
# `acknowledged` means it took it AND returned its own identity for it.
DELIVERED_STATUSES = ('sent', 'acknowledged')

# Ceiling on one drain pass. Bounded so a backlog cannot hold one
# transaction open across thousands of HTTP calls.
DRAIN_BATCH_SIZE = 50

class WorkflowDispatchLog(models.Model):
    """
    Audit log for every interaction with the NRS WorkSpace, and the outbound
    queue for asset lifecycle events (INT-05).

    Two kinds of row live here:

    - **Request approvals** (`event_type` unset). One row per `_send_to_workflow`
      call, written synchronously, never retried. Unchanged.
    - **Asset events** (`event_type` set, e.g. `asset.tag.affixed`). One row per
      EVENT, not per attempt: `event_id` has to stay stable across
      redeliveries so the receiver can dedupe, and "did this event land?" has
      to have exactly one answer a human can look at. Each attempt appends to
      `delivery_history` instead of spawning a row.

    Never deleted — permanent audit trail.
    """
    _name = 'workflow.dispatch.log'
    _description = 'WorkSpace Dispatch Log'
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(string='Reference', readonly=True, copy=False)
    request_id = fields.Many2one(
        comodel_name='request.request',
        string='Request',
        ondelete='set null',
        index=True,
        readonly=True,
    )
    direction = fields.Selection([
        ('outbound', 'Outbound (myservice → Workflow)'),
        ('inbound',  'Inbound (Workflow → myservice)'),
    ], string='Direction', required=True, readonly=True)

    status = fields.Selection([
        ('pending',      'Pending'),
        ('sent',         'Sent — Awaiting Response'),
        ('acknowledged', 'Acknowledged'),
        ('approved',     'Approved'),
        ('rejected',     'Rejected'),
        ('queried',      'Queried / Comments Received'),
        ('error',        'Failed'),
        ('dead',         'Dead — Delivery Abandoned'),
    ], string='Status', default='pending', tracking=True, readonly=True,
       help='`pending`/`error` mean "queued" and "will retry" for an asset '
            'event, but a request-approval dispatch is one-shot and is never '
            'retried — the labels stay neutral so they are not a false '
            'promise on the older rows.')

    workspace_ref = fields.Char(
        string='WorkSpace Reference No.',
        readonly=True,
        help='Reference number assigned by the NRS WorkSpace',
    )
    payment_ref = fields.Char(
        string='Payment / Approval Reference',
        readonly=True,
        help='Payment or approval reference returned by Workflow',
    )
    sent_by = fields.Many2one(
        comodel_name='res.users',
        string='Sent By',
        readonly=True,
        default=lambda self: self.env.user,
    )
    sent_at = fields.Datetime(string='Sent At', readonly=True)
    responded_at = fields.Datetime(string='Response Received At', readonly=True)

    payload_sent = fields.Text(
        string='Payload Sent',
        readonly=True,
        help='JSON payload sent to NRS WorkSpace',
    )
    response_received = fields.Text(
        string='Response Received',
        readonly=True,
        help='Raw response from NRS WorkSpace',
    )
    workflow_comment = fields.Text(
        string='Comment from Workflow',
        readonly=True,
        help='Comment, query, or rejection reason from the approver',
    )
    error_message = fields.Text(
        string='Error Message',
        readonly=True,
    )
    adapter_type = fields.Char(
        string='Adapter Used',
        readonly=True,
    )

    # ── Outbound event queue (INT-05) ─────────────────────────────────

    event_type = fields.Char(
        string='Event', readonly=True, copy=False, index=True,
        help='Set on asset lifecycle events (e.g. asset.tag.affixed). Empty '
             'on request-approval dispatches, which are one-shot and are '
             'never picked up by the retry queue.')
    event_id = fields.Char(
        # No `index=True`: the UNIQUE constraint below creates its own btree,
        # and a second identical index costs write throughput on every tenant
        # for nothing.
        string='Event ID', readonly=True, copy=False,
        help='The idempotency key sent to the receiver. Stable across every '
             'redelivery of this event, so a receiver that has already '
             'processed it can safely discard the repeat.')
    config_id = fields.Many2one(
        comodel_name='workflow.config', string='Target',
        ondelete='restrict', readonly=True, index=True)
    asset_id = fields.Many2one(
        comodel_name='nrs.asset', string='Asset',
        ondelete='set null', readonly=True, index=True)
    tag_label_id = fields.Many2one(
        comodel_name='nrs.asset.tag.label', string='Tag Label',
        ondelete='set null', readonly=True)

    attempts = fields.Integer(string='Attempts', default=0, readonly=True)
    max_attempts = fields.Integer(
        string='Max Attempts', readonly=True,
        help='Snapshotted from the configuration when the event was queued, '
             'so retuning the policy does not retroactively resurrect or '
             'kill events already in flight.')
    next_attempt_at = fields.Datetime(
        string='Next Attempt At', readonly=True, index=True,
        help='Cleared once the event is delivered or dead-lettered.')
    retry_base_seconds = fields.Integer(
        string='Retry Base Delay (s)', readonly=True,
        help='Snapshotted with max_attempts. Reading the base and cap live '
             'while the budget is frozen would let a mid-backlog retune '
             'reschedule every event already in flight — the same surprise '
             'the snapshot exists to prevent.')
    retry_cap_seconds = fields.Integer(
        string='Retry Delay Cap (s)', readonly=True)
    last_attempt_at = fields.Datetime(string='Last Attempt At', readonly=True)
    http_status = fields.Integer(string='Last HTTP Status', readonly=True)
    external_ref = fields.Char(
        string='Receiver Reference', readonly=True,
        help="The receiver's own identifier for this event, when it returns one.")
    delivery_history = fields.Text(
        string='Delivery History', readonly=True,
        help='One line per attempt. The per-attempt audit trail, kept here '
             'rather than as extra rows so that "did this event land?" has a '
             'single answer.')

    if _ODOO_MAJOR >= 19:
        _event_id_uniq = models.Constraint(
            "UNIQUE (event_id)",
            "An event id identifies one event and cannot be reused.",
        )
    else:
        _sql_constraints = [
            ("event_id_uniq",
             "UNIQUE (event_id)",
             "An event id identifies one event and cannot be reused."),
        ]

    # Fields that make a row a SEND INSTRUCTION rather than an audit record.
    # `readonly=True` on them is a web-client hint, not an ORM guard — this
    # repo ruled exactly that in handoff 03 for the tag capture fields, and
    # the stakes are higher here: the drain POSTs `payload_sent` verbatim to
    # Vendra using the tenant's own credentials. Without this guard any
    # internal user with a web session could hand-craft a row and forge an
    # `asset.tag.affixed`, walking straight around the `tagging:write`
    # separation that handoffs 03 and 05 exist to enforce.
    #
    # The ACL cannot carry this: `access_workflow_dispatch_log_user` must keep
    # `perm_create` because `request.request._send_to_workflow` writes its
    # audit row as the acting user, not as sudo.
    _EVENT_FIELDS = frozenset({
        'event_type', 'event_id', 'config_id', 'attempts', 'max_attempts',
        'next_attempt_at', 'last_attempt_at', 'retry_base_seconds',
        'retry_cap_seconds', 'delivery_history', 'external_ref',
        'http_status', 'asset_id', 'tag_label_id',
    })

    def _dispatch(self):
        """This recordset, flagged as the queue acting on itself."""
        return self.sudo().with_context(cadra_event_dispatch=True)

    def _assert_event_write_allowed(self, vals):
        touched = self._EVENT_FIELDS & set(vals)
        if touched and not self.env.context.get('cadra_event_dispatch'):
            raise ValidationError(_(
                'Delivery fields (%s) are written by the outbound event queue '
                'and cannot be set directly. A row carrying them is an '
                'instruction to POST to an integration partner, not an audit '
                'note — events are raised by the operation that observed '
                'them.'
            ) % ', '.join(sorted(touched)))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._assert_event_write_allowed(vals)
            if not vals.get('name'):
                seq = self.env['ir.sequence'].next_by_code('workflow.dispatch.log')
                vals['name'] = seq or 'WDL-NEW'
        return super().create(vals_list)

    def write(self, vals):
        self._assert_event_write_allowed(vals)
        return super().write(vals)

    # ── Inbound callback reconciliation ───────────────────────────────

    @api.model
    def _reconcile_callback(self, request_rec, outcome, workspace_ref, data):
        """The row a callback answers: the outbound dispatch, or a new inbound.

        Shared by BOTH callback controllers, and that sharing is the fix.
        The legacy `/myservice/workflow/callback` route found the
        `direction='outbound', status='sent'` row it was answering and
        rewrote it to the outcome; the documented `/api/v1` twin always
        appended a fresh inbound row and never touched the dispatch. So on a
        tenant using v1, an answered dispatch read `sent` for ever and
        "which dispatches are still unanswered" could not be asked at all.

        The legacy behaviour is the right one, so it is the one both get.

        There is no outbound request-approval row on any of the eight local
        tenants today — `_send_to_workflow` has never run on any of them —
        so this is latent rather than live. It stops being latent the first
        time a tenant sends one.
        """
        log = self.sudo().search([
            ('request_id', '=', request_rec.id),
            ('direction', '=', 'outbound'),
            ('status', '=', 'sent'),
            # Asset lifecycle events (INT-05) also live in this table and
            # also pass through `sent`. One of those is not an answer to an
            # approval request and must never be rewritten by a callback
            # about one — the same scoping ruling handoff 06 made for the
            # drain, which is scoped by `event_type` and not by status.
            ('event_type', '=', False),
        ], limit=1, order='create_date desc')

        if log:
            return log

        return self.sudo().create({
            'request_id':        request_rec.id,
            'direction':         'inbound',
            'status':            outcome,
            'workspace_ref':     workspace_ref,
            'response_received': json.dumps(data, default=str),
        })

    def action_view_request(self):
        if self.request_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'request.request',
                'res_id': self.request_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    # ── Enqueue ───────────────────────────────────────────────────────

    @api.model
    def _enqueue_event(self, event_type, payload, config,
                       asset=None, tag_label=None):
        """Queue one outbound event. Does NOT deliver it.

        Delivery is deliberately not attempted inline. Two reasons, and both
        are the difference between a queue and a hopeful HTTP call:

        1. The caller is inside an open transaction. POSTing before it
           commits would announce an affix that a later rollback un-does,
           and Vendra would hold a `Tagged` for an asset Cadra does not
           think is tagged.
        2. The affix endpoint's response time would become a function of
           whether Vendra is up. The Tag-Issuing Unit's confirmation must
           land in Cadra whether or not anyone downstream is listening.

        The cron is `_trigger`ed instead, which queues a run committed with
        this same transaction — so delivery follows the commit by seconds
        without being part of it.
        """
        event_id = uuid.uuid4().hex
        # The body carries the key as well as the header, so a receiver that
        # logs only bodies can still dedupe, and so the payload stored here is
        # byte-for-byte what goes on the wire on every redelivery.
        payload = dict(payload, event_id=event_id)
        row = self._dispatch().create({
            'direction': 'outbound',
            'status': 'pending',
            'event_type': event_type,
            'event_id': event_id,
            'config_id': config.id,
            'asset_id': asset.id if asset else False,
            'tag_label_id': tag_label.id if tag_label else False,
            'adapter_type': config.adapter_type,
            'payload_sent': json.dumps(payload, indent=2, default=str,
                                       sort_keys=True),
            'max_attempts': max(1, config.retry_max_attempts or 32),
            'retry_base_seconds': max(1, config.retry_base_seconds or 60),
            'retry_cap_seconds': max(1, config.retry_cap_seconds or 3600),
            'next_attempt_at': fields.Datetime.now(),
            'attempts': 0,
        })
        row._append_history('queued for %s' % (config.name or config.id))
        # Commits with our transaction: no delivery happens if the affix
        # rolls back.
        self._trigger_drain()
        _logger.info("workflow: queued %s event_id=%s row=%s",
                     event_type, event_id, row.name)
        return row

    @api.model
    def _trigger_drain(self, at=None):
        """Ask the drain cron to run, optionally at a specific time.

        `ir.cron._trigger` writes a trigger row inside the CURRENT
        transaction, which is what makes it safe to call from inside a
        business operation: if that operation rolls back, so does the request
        to deliver. Scheduling the exact `next_attempt_at` also means the
        backoff is the backoff — without it, a 60-second retry would actually
        wait for whenever the periodic interval next came round, and the
        configured delays would be fiction.
        """
        cron = self.env.ref('myservice_workflow.cron_workflow_outbound_events',
                            raise_if_not_found=False)
        if not cron:
            _logger.warning(
                "workflow: outbound event cron missing; queued events will "
                "wait for a manual drain")
            return False
        cron.sudo()._trigger(at)
        return True

    # ── Drain ─────────────────────────────────────────────────────────

    @api.model
    def _cron_drain_outbound_events(self, limit=DRAIN_BATCH_SIZE):
        """Deliver everything whose backoff has elapsed.

        Ineligible rows are excluded in the DOMAIN rather than skipped in the
        loop. With a bounded, oldest-first window that distinction is
        load-bearing: a row the loop skips never has its `next_attempt_at`
        advanced, so a handful of permanently-skipped rows would occupy the
        whole window forever and starve everything behind them. The loop's
        own except clause obeys the same rule — it pushes the row's next
        attempt out rather than leaving it where it is.
        """
        now = fields.Datetime.now()
        domain = [
            # The queue owns event rows only. Request-approval dispatches also
            # sit at `pending`/`error`, and re-POSTing one would resubmit a
            # human approval that nobody asked to resubmit.
            ('event_type', '!=', False),
            ('direction', '=', 'outbound'),
            ('status', 'in', list(RETRYABLE_STATUSES)),
            ('next_attempt_at', '<=', now),
        ]
        disabled = self.env['workflow.config'].sudo().with_context(
            active_test=False).search([
                '|', ('active', '=', False), ('event_enabled', '=', False),
            ])
        if disabled:
            domain.append(('config_id', 'not in', disabled.ids))

        rows = self.sudo().search(domain, order='next_attempt_at asc, id asc',
                                  limit=limit)
        if not rows:
            return 0

        in_test = self._in_test()

        delivered = 0
        for row in rows:
            try:
                if row._deliver_once():
                    delivered += 1
            except Exception:               # noqa: BLE001
                # catch-all: unknown — anything reaching here has already
                # escaped a method whose contract is that it does not raise,
                # so by construction it is something nobody anticipated.
                #
                # `_deliver_once` is written not to raise, but its own writes
                # and `config._get_adapter()` sit outside its inner try, and
                # the `_mark_delivered` / `_mark_failed` overrides in
                # `sap_asset_events.py` write to `nrs.asset` from in here too.
                # An escape would abort the whole batch AND leave the row at
                # the head of an oldest-first window with its `next_attempt_at`
                # unchanged — permanently blocking everything behind it. Roll
                # back to a clean cursor, then push the row back by one
                # backoff so the queue keeps moving.
                #
                # This does not turn a permanent failure into an infinite
                # retry: `_defer_after_error` reads the SNAPSHOTTED
                # `max_attempts`, which the config constraint holds at 1 or
                # more, so a row that keeps arriving here dead-letters on
                # schedule and becomes visible rather than looping.
                self.env.cr.rollback()
                _logger.exception(
                    "workflow: unhandled error delivering %s; deferring", row.name)
                try:
                    row._defer_after_error()
                    if not in_test:
                        self.env.cr.commit()
                except Exception:           # noqa: BLE001
                    # catch-all: unknown — this is the handler for "the
                    # handler failed", and the only honest thing to say about
                    # what arrives here is that the cursor is no longer
                    # trustworthy. The row keeps its old `next_attempt_at`, so
                    # the next pass will try it again; the traceback is the
                    # only evidence there will be, which is why it is logged
                    # and not swallowed.
                    self.env.cr.rollback()
                    _logger.exception(
                        "workflow: could not defer %s either", row.name)
                continue
            if not in_test:
                # Per row, so one slow receiver does not hold a transaction
                # open across the whole batch and a crash loses at most one
                # attempt's bookkeeping.
                self.env.cr.commit()

        # A full window means there is probably more behind it. Ask for
        # another pass rather than making a backlog wait a whole interval per
        # batch — after a long outage that is the difference between minutes
        # and hours.
        # capped-count-ok: asking whether the WINDOW came back full is
        # the whole point of the check — it is how the drain knows to
        # book another pass rather than making a backlog wait.
        if len(rows) == limit:
            self._trigger_drain()
        return delivered

    @api.model
    def _in_test(self):
        """Odoo 19 removed `Registry.in_test_mode()`; this is what is left.

        Committing inside a test breaks the surrounding rollback.
        """
        return bool(odoo_config.get('test_enable')
                    or odoo_config.get('test_file'))

    def _count_attempt(self):
        """Burn one attempt, durably."""
        self.ensure_one()
        self._dispatch().write({
            'attempts': (self.attempts or 0) + 1,
            'last_attempt_at': fields.Datetime.now(),
        })
        # COMMITTED, not merely flushed. A worker SIGKILLed or evicted while
        # blocked in the POST would otherwise roll the increment back, and the
        # row would return with its budget untouched — the poison-event loop
        # this counter exists to bound. The drain already commits per row, so
        # this only moves the boundary earlier.
        if not self._in_test():
            self.env.cr.commit()

    def _defer_after_error(self):
        """Push a row back one backoff without claiming to know what failed."""
        self.ensure_one()
        delay = self._backoff_seconds()
        self._dispatch().write({
            'status': 'error' if self.attempts < (self.max_attempts or 1)
                      else 'dead',
            'next_attempt_at': self._next_attempt_datetime(delay)
                               if self.attempts < (self.max_attempts or 1)
                               else False,
            'error_message': 'Unhandled error during delivery; see the server '
                             'log for the traceback.',
        })

    def _deliver_once(self):
        """One delivery attempt. Never raises — the queue records outcomes.

        The attempt is counted BEFORE the call. A worker that dies mid-request
        must still burn its attempt; the alternative is a poison event that
        retries forever because nothing ever gets far enough to record that it
        tried.
        """
        self.ensure_one()
        config = self.config_id
        if not config:
            self._count_attempt()
            self._mark_failed('Event has no target configuration', retryable=False)
            return False

        # Belt and braces on the backoff. Note this is a check, not a lock:
        # what actually stops two workers spending two attempts on one row is
        # that Odoo holds `FOR NO KEY UPDATE SKIP LOCKED` on the ir.cron row
        # for the whole action, so drains are serialised cluster-wide. That
        # holds only while the CRON IS THE ONLY ENTRY POINT — if a server
        # action or an API route is ever added over this queue, this method
        # needs its own `FOR UPDATE SKIP LOCKED` on the selected rows.
        now = fields.Datetime.now()
        if self.next_attempt_at and self.next_attempt_at > now:
            return False

        self._count_attempt()

        try:
            payload = json.loads(self.payload_sent or '{}')
        except ValueError as e:
            self._mark_failed('Stored payload is not valid JSON: %s' % e,
                              retryable=False)
            return False

        adapter = config._get_adapter()
        # An event whose body names itself is delivered exactly as it always
        # was; one whose body does not (handoff 62) is told its type, which
        # the adapter routes on.
        route = {} if payload.get('event') else {'event_type': self.event_type}
        try:
            result = adapter.deliver(payload, self.event_id,
                                     request_ref=self.name, **route)
        except Exception as e:                      # noqa: BLE001
            # catch-all: unknown — `deliver()` is an ADAPTER BOUNDARY whose
            # published contract is "never raises", so anything arriving here
            # is by definition outside what this module can enumerate, and the
            # adapter that raised is itself the defect being reported.
            #
            # `retryable=True` is deliberate and is NOT a classification
            # decision taken from an exception. The classifier lives in
            # `_classify`, which only ever sees an HTTP response; a raise
            # means no response was classified at all, and the queue's stated
            # default for "nothing said" is to retry, because retrying a
            # deliverable event costs a minute and dropping one costs an audit
            # trail. It cannot become an infinite retry — `max_attempts` is
            # snapshotted on the row and bounded by the config constraint — so
            # a permanently-raising adapter dead-letters and is seen.
            _logger.exception("workflow: adapter raised delivering %s", self.name)
            self._mark_failed('%s: %s' % (type(e).__name__, e), retryable=True)
            return False

        if result.get('ok'):
            self._mark_delivered(result)
            return True
        self._mark_failed(result.get('error') or 'Unknown delivery error',
                          retryable=result.get('retryable', True),
                          http_status=result.get('status'),
                          body=result.get('body'))
        return False

    # ── Outcomes ──────────────────────────────────────────────────────

    def _mark_delivered(self, result):
        self.ensure_one()
        now = fields.Datetime.now()
        acknowledged = bool(result.get('acknowledged'))
        self._dispatch().write({
            'status': 'acknowledged' if acknowledged else 'sent',
            'sent_at': now,
            'responded_at': now if acknowledged else False,
            'next_attempt_at': False,
            'error_message': False,
            'http_status': result.get('status') or 0,
            'response_received': (result.get('body') or '')[:4000],
            'external_ref': result.get('external_ref') or False,
        })
        self._append_history(
            'attempt %d delivered (HTTP %s)%s' % (
                self.attempts, result.get('status'),
                ' ref=%s' % result['external_ref']
                if result.get('external_ref') else ''))
        _logger.info("workflow: delivered %s event_id=%s in %d attempt(s)",
                     self.name, self.event_id, self.attempts)

    def _mark_failed(self, error, retryable=True, http_status=None, body=None):
        """Record a failed attempt and decide whether there will be another."""
        self.ensure_one()
        error = (error or '')[:2000]
        vals = {
            'error_message': error,
            'http_status': http_status or 0,
        }
        if body:
            vals['response_received'] = body[:4000]

        if not retryable:
            vals.update({'status': 'dead', 'next_attempt_at': False})
            self._dispatch().write(vals)
            self._append_history(
                'attempt %d failed permanently — not retryable: %s'
                % (self.attempts, error))
            self._raise_dead_letter(
                'The receiver rejected this event permanently, so it will not '
                'be retried.')
        elif self.attempts >= (self.max_attempts or 1):
            vals.update({'status': 'dead', 'next_attempt_at': False})
            self._dispatch().write(vals)
            self._append_history(
                'attempt %d failed — attempt budget exhausted: %s'
                % (self.attempts, error))
            self._raise_dead_letter(
                'Delivery was abandoned after %d attempts.' % self.attempts)
        else:
            delay = self._backoff_seconds()
            next_at = self._next_attempt_datetime(delay)
            vals.update({'status': 'error', 'next_attempt_at': next_at})
            self._dispatch().write(vals)
            self._append_history(
                'attempt %d failed, retrying in %ds: %s'
                % (self.attempts, delay, error))
            # Book the retry for the moment the backoff actually elapses,
            # rather than leaving it to whenever the periodic drain next runs.
            self._trigger_drain(at=next_at)
            _logger.warning(
                "workflow: %s attempt %d/%d failed, retry in %ds: %s",
                self.name, self.attempts, self.max_attempts, delay, error)

    def _next_attempt_datetime(self, delay_seconds):
        return fields.Datetime.now() + datetime.timedelta(seconds=delay_seconds)

    def _backoff_seconds(self):
        """Capped exponential backoff: base × 2^(attempts-1), ceiling applied.

        No jitter. This is a single-tenant, low-volume event stream pointed at
        one receiver — there is no herd to thunder — and a deterministic delay
        is one a test can assert and an operator can predict.
        """
        self.ensure_one()
        base = max(1, self.retry_base_seconds or 60)
        cap = max(base, self.retry_cap_seconds or 3600)
        exponent = max((self.attempts or 1) - 1, 0)
        # Bound the exponent before it becomes a very large int: 2**30 is
        # already far past any sane cap.
        exponent = min(exponent, 30)
        return int(min(base * (2 ** exponent), cap))

    def _append_history(self, line):
        self.ensure_one()
        stamp = fields.Datetime.to_string(fields.Datetime.now())
        entry = '[%s] %s' % (stamp, line)
        existing = self.delivery_history or ''
        self._dispatch().write({
            'delivery_history': (existing + '\n' + entry).strip()
        })

    def _raise_dead_letter(self, summary):
        """Make an abandoned event visible to a person, not just to the log.

        A dead letter that only exists as a row nobody queries is the same
        failure the retry queue was built to remove — an event silently not
        arriving. So it lands in three places: the error log, a dedicated
        menu, and the chatter of the asset it is about, which is where the
        person who cares about that asset is already looking.
        """
        self.ensure_one()
        _logger.error(
            "workflow: DEAD LETTER %s event=%s event_id=%s after %d attempt(s): %s",
            self.name, self.event_type, self.event_id, self.attempts,
            self.error_message)
        if self.asset_id:
            try:
                # `error_message` holds up to 300 characters of the receiver's
                # own response body. A receiver answering with an HTML error
                # page would otherwise mangle the note it is being reported
                # in, so everything interpolated here is escaped.
                if self.event_type == 'asset.register_state.changed':
                    # Handoff 62: not a tag; the unit's state stands.
                    body = Markup(_(
                        '<p>⚠️ <strong>Integration event not delivered</strong>'
                        ' — %(summary)s</p>'
                        '<p>Event <code>%(event)s</code> (%(ref)s) could not '
                        'be delivered to %(target)s after %(attempts)d '
                        'attempt(s). The unit\'s register state in Cadra is '
                        'unaffected; the downstream system has not been told '
                        'it changed.</p>'
                        '<p>Last error: %(error)s</p>'
                    ))
                else:
                    body = Markup(_(
                        '<p>⚠️ <strong>Integration event not delivered</strong> — '
                        '%(summary)s</p>'
                        '<p>Event <code>%(event)s</code> (%(ref)s) could not be '
                        'delivered to %(target)s after %(attempts)d attempt(s). '
                        'The tag record in Cadra is unaffected; the downstream '
                        'system has not been told about it.</p>'
                        '<p>Last error: %(error)s</p>'
                    ))
                body = body % {
                    'summary': escape(summary),
                    'event': escape(self.event_type or ''),
                    'ref': escape(self.name or ''),
                    'target': escape(self.config_id.name
                                     or 'the configured receiver'),
                    'attempts': self.attempts,
                    'error': escape((self.error_message or '')[:500]),
                }
                self.asset_id.sudo().message_post(body=body)
            except Exception:               # noqa: BLE001
                # catch-all: unknown — `message_post` runs the whole mail.thread
                # stack (followers, subtypes, notification scheduling), and the
                # `Markup(_(...)) % {...}` above can be broken by a translation
                # that loses a placeholder. Neither surface is enumerable here.
                # Verified rather than assumed: `nrs.asset` does inherit
                # `mail.thread` (`myservice_asset_register/models/asset.py`),
                # so the one thing a narrow clause would have bought — catching
                # a `message_post` that no longer exists — is not in play.
                #
                # Never let the notification break the drain: the dead letter
                # is already recorded in the error log and in the row, and an
                # escape from here would roll the DEAD-LETTERING back at the
                # loop above and hand the event another attempt it has already
                # spent. Losing the chatter note is the smaller failure.
                _logger.exception(
                    "workflow: could not post dead-letter note for %s", self.name)

    # ── Human actions ─────────────────────────────────────────────────

    def action_retry_now(self):
        """Put a failed or dead event back on the queue.

        Extends the budget rather than resetting `attempts`, so the row keeps
        saying how many times it has actually been tried — that count is the
        evidence of how hard the receiver was down, and zeroing it would erase
        it.
        """
        for row in self:
            if not row.event_type:
                raise UserError(_(
                    'Only asset lifecycle events are delivered by the retry '
                    'queue. Re-send a request approval from the request '
                    'itself.'))
            if row.status in DELIVERED_STATUSES:
                raise UserError(_(
                    'Event %s has already been delivered. Re-sending it would '
                    'be a duplicate the receiver is expected to discard.'
                ) % row.name)
            budget = max(1, (row.config_id.retry_max_attempts or 32)
                         if row.config_id else 32)
            row._dispatch().write({
                'status': 'pending',
                'max_attempts': (row.attempts or 0) + budget,
                'next_attempt_at': fields.Datetime.now(),
            })
            row._append_history('manual retry requested by %s; budget extended '
                                'to %d attempts' % (self.env.user.login,
                                                    row.max_attempts))
        self._trigger_drain()
        return True
