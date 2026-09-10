from odoo import models, fields, api
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = 'request.request'

    # ── Workflow status fields on the request ─────────────────────────
    workflow_status = fields.Selection([
        ('not_sent', 'Not Sent'),
        ('pending',  'Sent — Awaiting Approval'),
        ('approved', 'Approved by Workflow'),
        ('rejected', 'Rejected by Workflow'),
        ('queried',  'Queried — Response Required'),
    ], string='WorkSpace Status', default='not_sent',
       tracking=True, readonly=True, copy=False)

    workspace_ref = fields.Char(
        string='WorkSpace Reference',
        readonly=True, copy=False,
        help='Reference number assigned by the NRS WorkSpace',
    )
    workflow_payment_ref = fields.Char(
        string='Payment / Approval Reference',
        readonly=True, copy=False,
        help='Payment or approval reference returned by Workflow on approval',
    )
    workflow_dispatch_ids = fields.One2many(
        comodel_name='workflow.dispatch.log',
        inverse_name='request_id',
        string='WorkSpace Dispatch Log',
        readonly=True,
    )
    workflow_dispatch_count = fields.Integer(
        string='WorkSpace Dispatches',
        compute='_compute_workflow_dispatch_count',
    )

    @api.depends('workflow_dispatch_ids')
    def _compute_workflow_dispatch_count(self):
        for rec in self:
            rec.workflow_dispatch_count = len(rec.workflow_dispatch_ids)

    # ── Stage change hook — auto-trigger ──────────────────────────────
    def write(self, vals):
        result = super().write(vals)
        if 'stage_id' in vals:
            self._check_workflow_auto_trigger()
        return result

    def _check_workflow_auto_trigger(self):
        """Fire auto-send if the new stage is in the trigger list."""
        try:
            config = self.env['workflow.config'].get_active_config()
        except UserError:
            return  # No config — silent skip

        trigger_ids = config.trigger_stage_ids.ids
        if not trigger_ids:
            return

        for req in self:
            if (req.stage_id.id in trigger_ids
                    and req.workflow_status == 'not_sent'):
                _logger.info(
                    "Auto-triggering Workflow dispatch for request %s "
                    "(stage: %s)", req.name, req.stage_id.name)
                req._send_to_workflow(triggered_by='auto')

    # ── Core dispatch method ──────────────────────────────────────────
    def _send_to_workflow(self, triggered_by='manual', note=None):
        """
        Build the payload, call the adapter, record the log.
        Returns the dispatch log record.
        """
        self.ensure_one()
        config = self.env['workflow.config'].get_active_config()
        adapter = config._get_adapter()

        payload = self._build_workflow_payload()
        # Normalise ONCE, here, so the copy we store and the copy `requests`
        # puts on the wire cannot disagree. The log used `default=str` and
        # `requests` serialises `json=payload` WITHOUT one, so a value the
        # builder should not have produced — a `date`, a `Decimal`, a
        # recordset — logged fine and then raised `TypeError` inside the
        # adapter. With the adapter's outer clause now `RequestException`-only
        # (handoff 15) that surfaces as a traceback naming Cadra, which is
        # correct; before it surfaced as "Failed to send to NRS WorkSpace",
        # which sent whoever pressed the button to audit the wrong system.
        # Round-tripping makes the payload JSON-native, so neither can happen.
        payload = json.loads(json.dumps(payload, default=str))
        log = self.env['workflow.dispatch.log'].create({
            'request_id':   self.id,
            'direction':    'outbound',
            'status':       'pending',
            'sent_by':      self.env.user.id,
            'sent_at':      fields.Datetime.now(),
            'payload_sent': json.dumps(payload, indent=2, default=str),
            'adapter_type': config.adapter_type,
        })

        result = adapter.submit(payload)

        if result.get('ok'):
            log.write({
                'status':       'sent',
                'workspace_ref': result.get('workspace_ref', ''),
                'response_received': result.get('raw', result.get('message', '')),
            })
            self.write({
                'workflow_status': 'pending',
                'workspace_ref':    result.get('workspace_ref', ''),
            })
            self.message_post(
                body=f"<p>📤 <strong>Sent to NRS WorkSpace</strong> "
                     f"({triggered_by}) — Ref: <strong>{result.get('workspace_ref','')}</strong></p>"
                     + (f"<p>{note}</p>" if note else ''),
                subtype_xmlid='mail.mt_comment',
            )
        else:
            log.write({
                'status':        'error',
                'error_message': result.get('error', 'Unknown error'),
            })
            self.message_post(
                body=f"<p>❌ <strong>Workflow dispatch failed</strong>: "
                     f"{result.get('error','Unknown error')}</p>",
                subtype_xmlid='mail.mt_comment',
            )
            raise UserError(
                f"Failed to send to NRS WorkSpace:\n{result.get('error','Unknown error')}"
            )
        return log

    def _build_workflow_payload(self):
        """
        Build the JSON payload to send to Workflow.
        Structured to be human-readable for email fallback too.
        NRS IT team can request field additions here.
        """
        self.ensure_one()
        req = self

        payload = {
            'source_system':    'NRS myservice',
            'source_url':       f"https://myservice.com.ng/web#id={req.id}&model=request.request&view_type=form",
            'reference':        req.name or '',
            'type':             req.type_id.name if req.type_id else '',
            'category':         req.category_id.name if req.category_id else '',
            'service':          req.service_id.name if req.service_id else '',
            'location':         req.generic_location_id.name if req.generic_location_id else '',
            'stage':            req.stage_id.name if req.stage_id else '',
            'priority':         req.priority if hasattr(req, 'priority') else '',
            'requested_by':     req.author_id.name if req.author_id else '',
            'requested_by_email': req.author_id.email if req.author_id else '',
            'assigned_to':      req.user_id.name if req.user_id else '',
            'description':      req.request_text or '',
            'created_date':     str(req.date_created) if req.date_created else '',
            'submission_date':  str(fields.Datetime.now()),
        }

        # Add vehicle if present (from myservice_request_fields)
        if hasattr(req, 'vehicle_id') and req.vehicle_id:
            payload['vehicle'] = req.vehicle_id.name or ''
            payload['vehicle_plate'] = req.vehicle_id.license_plate or ''

        # Add attachments summary
        config = self.env['workflow.config'].get_active_config()
        if config.include_attachments and req.attachment_ids:
            payload['attachments'] = [
                {'name': a.name, 'size': a.file_size}
                for a in req.attachment_ids
            ]
        return payload

    # ── Manual send button ────────────────────────────────────────────
    def action_send_to_workflow(self):
        """Opens the send wizard for manual dispatch."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send to NRS WorkSpace',
            'res_model': 'workflow.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id},
        }

    def action_view_workflow_log(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'WorkSpace Dispatch Log',
            'res_model': 'workflow.dispatch.log',
            'view_mode': 'list,form',
            'domain': [('request_id', '=', self.id)],
            'target': 'current',
        }

    # ── Callback disposition — replay, contradiction, or apply ───────
    #
    # A callback is an EVENT, and an event that has already been applied is
    # not an instruction to apply it again. Both controllers used to act on
    # the CALL: a second byte-identical POST answered `200 {"ok": true}` and
    # re-did all three effects — a second dispatch-log row, a second chatter
    # post, and a second write of `approved_stage_id`. The third is the
    # damaging one. Where an approved stage is configured the stage was
    # written unconditionally, so a replay arriving after a human had moved
    # the request onward DRAGGED IT BACK, and `request.request.write` logged
    # a `stage_changed` event for a stage that had not changed — a
    # double-count inside the request's own audit trail.
    #
    # Handoff 06 settled the shape for INT-05 in the other direction: one
    # physical act is one event, and `_mark_affixed` fires on the
    # TRANSITION. This is the same rule pointed inbound.
    #
    # **Why the transition and not `workspace_ref`.** `workspace_ref` is the
    # natural dedup key and is stored on both the request and the log — and
    # it is optional in both published contracts (`data.get('workspace_ref',
    # '')` here, `nullable: True` in the v1 schema). Measured across all
    # eight local tenants before this was written: `request.request.
    # workspace_ref` is set on **0 of 407** requests, and every one of the 76
    # request-approval log rows that carries one carries the same pytest
    # fixture constant. A key that is absent by contract and empty in fact
    # cannot be the thing a dedup stands on. `workflow_status` is written by
    # every path that applies an outcome and is therefore always there;
    # `workspace_ref` corroborates in the log line instead.
    #
    # A re-send is what re-opens the door: `_send_to_workflow` sets
    # `workflow_status` back to `pending`, so a second decision on a second
    # dispatch transitions normally. Replay suppression only bites where
    # nothing new was asked.

    #: Outcomes that are a DECISION. A different decision arriving after one
    #: of these is two systems disagreeing, not a workflow progressing.
    WORKFLOW_DECISIONS = ('approved', 'rejected')

    #: The three dispositions a callback can have.
    CALLBACK_APPLY = 'apply'
    CALLBACK_REPLAY = 'replay'
    CALLBACK_CONFLICT = 'conflict'

    def _workflow_callback_disposition(self, outcome, comment=None):
        """What this callback should do: apply, replay, or conflict.

        Consulted by BOTH controllers before either writes anything — the
        dispatch-log row included, which is why this cannot live inside the
        three handlers. `myservice_api` appends its row before it calls
        them, so a check one layer in would still leave a row per replay.

        - `replay`   — the outcome already stands. Write nothing, answer
                       success: the caller replayed a request we honoured,
                       and telling them so is the truth.
        - `conflict` — a DIFFERENT outcome after a decision was recorded.
                       Refused, not absorbed. See the controllers.
        - `apply`    — everything else, including `queried` → `approved`
                       and any outcome on a request still `pending`.

        **`queried` dedups on the pair, not on the outcome alone.** A
        DECISION arrives once — a second `approved` is the same approval
        redelivered. A QUESTION does not: WorkSpace can legitimately ask a
        second, different question while the first is still open, and
        `current == outcome == 'queried'` swallowed it. The text is the only
        thing that separates a new question from a redelivery of the old
        one, so the text is what the comparison uses.

        `comment` defaults to `None`, which reproduces the outcome-only
        behaviour exactly — a caller that does not pass it gets today's
        answer rather than a quietly different one.
        """
        self.ensure_one()
        current = self.workflow_status
        if current == outcome:
            if (outcome == 'queried' and comment
                    and comment != self._last_recorded_comment()):
                return self.CALLBACK_APPLY
            return self.CALLBACK_REPLAY
        if current in self.WORKFLOW_DECISIONS:
            return self.CALLBACK_CONFLICT
        return self.CALLBACK_APPLY

    def _record_replay_extras(self, payment_ref=None, comment=None):
        """Record what a repeat carries that has somewhere to go; name the rest.

        A replay writes nothing about the OUTCOME, which is the point — the
        decision already stands and re-applying it is the defect handoff 18
        closed. But "does not re-apply the outcome" must not become "throws
        away everything else in silence" (rule 3), and it must not become
        "names it and drops it" either where the field has a home.

        `payment_ref` has a home. A workflow engine that sends the approval
        when it is granted and the payment reference when it clears is doing
        nothing wrong — both fields are optional in both published schemas —
        and a payment reference is the thing somebody looks for later and
        does not find. Writing `workflow_payment_ref` alone produces none of
        the five effects a replay is forbidden: no `stage_id` in the vals, so
        `request.request.write` computes an empty `moved` set and neither
        stamps `date_moved` nor logs a `stage_changed` event; the field is
        not `tracking=True`, so `mail.thread` posts nothing; and no
        dispatch-log row is written because this method does not touch the
        log. The disposition stays `replay`.

        `comment` has nowhere to go on a replay. Recording it would mean a
        chatter post and a dispatch-log rewrite, which are two of the five.
        After `_workflow_callback_disposition` learned to compare the text,
        the case narrows to a decision replay carrying new prose — a second
        `approved` with a different note — because a second `queried` with
        new text is no longer a replay at all. It is named and dropped.

        Returns `(stored, discarded)`, both sorted lists of field names,
        both empty when the repeat carries nothing new.
        """
        self.ensure_one()
        stored = []
        discarded = []
        if payment_ref and payment_ref != self.workflow_payment_ref:
            self.write({'workflow_payment_ref': payment_ref})
            stored.append('payment_ref')
        if comment and comment != self._last_recorded_comment():
            discarded.append('comment')
        return sorted(stored), sorted(discarded)

    def _last_recorded_comment(self):
        """The comment the previous callback on this request carried.

        Compared against the chatter body first, which was wrong: the
        outcome handlers wrap the comment in HTML, so matching it means
        matching markup, and every ordinary redelivery came back as a NEW
        question. A guard that fires on the common case is a guard somebody
        turns off — the first run of the suite failed on exactly that.

        `workflow.dispatch.log.workflow_comment` holds the text verbatim,
        written by all three outcome handlers, so the comparison is a string
        against the same string. No row means nothing to compare against and
        any comment counts as new, which is the safe direction.

        **The domain is scoped to rows that recorded an ANSWER**, and that is
        load-bearing rather than tidy. It used to take the newest inbound-side
        row whatever its status, and `_send_to_workflow` creates its outbound
        row as `pending` BEFORE calling the adapter and only promotes it to
        `sent` if the adapter succeeds — while the write that resets
        `workflow_status` to `pending` sits inside that same success branch.
        So a re-dispatch that FAILS leaves a newer row with an empty
        `workflow_comment` and the request still reading `queried`. The next
        ordinary redelivery of the SAME question then compared "Q1" against
        "" , judged it a new question and applied it: fresh chatter, the
        dispatch log rewritten. That is the "fires on the common case"
        failure this method was written to avoid, reached from the other
        side.

        `pending`, `sent`, `acknowledged`, `error` and `dead` are all states
        of a dispatch rather than answers to one, and none of them carries a
        comment. Only the three outcomes do.
        """
        self.ensure_one()
        log = self.env['workflow.dispatch.log'].sudo().search(
            [('request_id', '=', self.id),
             ('event_type', '=', False),
             ('status', 'in', ('approved', 'rejected', 'queried'))],
            limit=1, order='create_date desc, id desc')
        return log.workflow_comment or ''

    def _set_workflow_stage(self, stage):
        """Move to `stage`, and only if that is a move.

        `request.request.write` now branches on the value changing rather
        than on `'stage_id' in vals`, so this is belt and braces — but the
        callback is the caller that made the difference visible and the
        guard is one line where the consequence is a fabricated
        `stage_changed` event.
        """
        self.ensure_one()
        if stage and self.stage_id != stage:
            self.write({'stage_id': stage.id})

    # ── Callback handlers — called by the webhook controller ─────────
    def _workflow_callback_approved(self, workspace_ref, payment_ref=None,
                                    comment=None, log=None):
        self.ensure_one()
        config = self.env['workflow.config'].get_active_config()
        vals = {'workflow_status': 'approved'}
        if payment_ref:
            vals['workflow_payment_ref'] = payment_ref
        self.write(vals)

        # Advance to approved stage if configured
        self._set_workflow_stage(config.approved_stage_id)

        msg = (f"<p>✅ <strong>Approved by NRS WorkSpace</strong>"
               f" — Ref: {workspace_ref}</p>")
        if payment_ref:
            msg += f"<p>Payment/Approval Reference: <strong>{payment_ref}</strong></p>"
        if comment:
            msg += f"<p>Comment: {comment}</p>"
        self.message_post(body=msg, subtype_xmlid='mail.mt_comment')

        if log:
            log.write({
                'status': 'approved',
                'workspace_ref': workspace_ref,
                'payment_ref': payment_ref or '',
                'workflow_comment': comment or '',
                'responded_at': fields.Datetime.now(),
            })

    def _workflow_callback_rejected(self, workspace_ref, comment=None, log=None):
        self.ensure_one()
        config = self.env['workflow.config'].get_active_config()
        self.write({'workflow_status': 'rejected'})

        # Move back to rejected stage if configured
        self._set_workflow_stage(config.rejected_stage_id)

        msg = (f"<p>❌ <strong>Rejected by NRS WorkSpace</strong>"
               f" — Ref: {workspace_ref}</p>")
        if comment:
            msg += f"<p>Rejection reason: {comment}</p>"
        self.message_post(body=msg, subtype_xmlid='mail.mt_comment')

        if log:
            log.write({
                'status': 'rejected',
                'workspace_ref': workspace_ref,
                'workflow_comment': comment or '',
                'responded_at': fields.Datetime.now(),
            })

    def _workflow_callback_queried(self, workspace_ref, comment, log=None):
        self.ensure_one()
        self.write({'workflow_status': 'queried'})
        msg = (f"<p>💬 <strong>Query from NRS WorkSpace</strong>"
               f" — Ref: {workspace_ref}</p>"
               f"<p>{comment}</p>")
        self.message_post(body=msg, subtype_xmlid='mail.mt_comment')

        if log:
            log.write({
                'status': 'queried',
                'workspace_ref': workspace_ref,
                'workflow_comment': comment,
                'responded_at': fields.Datetime.now(),
            })
