"""The SAP asset legs — INT-06, INT-07 and INT-09.

Same transport as INT-05, on purpose. `workflow.dispatch.log` already gives us
an outbox drained by an `ir.cron`, capped exponential backoff, `event_id`
idempotency, 4xx-is-permanent classification and a visible dead-letter state,
all proven live in handoff 06 against a receiver taken down and brought back.
SAP is another outbound target that will sometimes be down, so it gets the
same machinery and not a second one. Everything new here is the *payloads*,
the *triggers* and the *response*.

What each leg is:

- **INT-06** `asset.master.create` — Cadra asks SAP to create and capitalise
  the fixed asset. Fires on **tagging confirmed**, never on record creation.
  The September flow makes capitalisation follow tagging, and the reason is
  the same discipline as capture-before-GRN on the Vendra side: an asset
  record is a claim, a confirmed tag is evidence. Putting a value on NRS's
  books for something nobody has proven exists in a building is exactly what
  the tag capture work was built to prevent.

- **INT-07** — the SAP asset number coming back. Read out of the INT-06
  response and written onto the register through
  `nrs.asset._set_sap_master()`. See `docs/integrations/INT-06-07-09-sap-
  requirements.md` §3 for why synchronous is the recommendation and what the
  fallbacks are.

- **INT-09** `asset.transferred` / `asset.custodian_changed` /
  `asset.disposed` — lifecycle changes that move the SAP asset master. One
  envelope with an `event` discriminator rather than three shapes, so a
  fourth event later is a payload change and not a deployment on both sides.

Two rulings worth reading before changing anything here:

**A lifecycle event for an asset SAP has never heard of is not sent.** Not
held, not queued — not sent, and logged as such. If Cadra holds no SAP asset
number the asset was never capitalised, so there is no asset master to update
and SAP would have nothing to apply the change to. Nor is the change lost: the
INT-06 create carries the asset's CURRENT location and custodian, so whatever
moved before capitalisation is already in the create payload when it finally
fires.

**A transfer announces itself on completion, not on approval.** The September
register says the trigger is "transfer approved". Taken literally that is
wrong and we have not implemented it: in Cadra approval AUTHORISES the move
and completion RECORDS it — `action_complete` is what actually writes the
asset's new location and custodian. Announcing on approval would tell SAP an
asset had moved to a new cost centre while it was still in the old building,
and an approved-then-abandoned transfer would leave the SAP asset master
permanently wrong with nothing in Cadra to reconcile it against.
"""
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import json
import logging

from odoo.addons.myservice_asset_register.models.asset_disposal import (
    DEFAULT_SAP_DISPOSAL_TYPE,
    SAP_DISPOSAL_TYPE,
)

from .workflow_config import PURPOSE_SAP_ASSETS

_logger = logging.getLogger(__name__)

EVENT_ASSET_MASTER_CREATE = 'asset.master.create'
EVENT_ASSET_TRANSFERRED = 'asset.transferred'
EVENT_ASSET_CUSTODIAN_CHANGED = 'asset.custodian_changed'
EVENT_ASSET_DISPOSED = 'asset.disposed'

#: INT-09. Every one of these needs a SAP asset number to be addressable.
SAP_LIFECYCLE_EVENTS = frozenset({
    EVENT_ASSET_TRANSFERRED,
    EVENT_ASSET_CUSTODIAN_CHANGED,
    EVENT_ASSET_DISPOSED,
})

SAP_EVENT_TYPES = SAP_LIFECYCLE_EVENTS | {EVENT_ASSET_MASTER_CREATE}

#: Context flag set by `nrs.asset.transfer.action_complete`. A completed
#: transfer writes the asset's custodian as well as its location, and without
#: this the same physical act would raise both `asset.transferred` and
#: `asset.custodian_changed` — two events for one move, which a receiver has
#: no way to tell from a move followed by a reassignment.
CTX_IN_TRANSFER = 'cadra_sap_transfer'


def _iso(value):
    """Odoo stores naive UTC; the wire wants an explicit offset."""
    if not value:
        return None
    return fields.Datetime.to_string(value).replace(' ', 'T') + 'Z'


def _date(value):
    return fields.Date.to_string(value) if value else None


def _employee(emp):
    """The custodian block. Absent on 44% of the live register — see the
    requirements document §7 — so every field here can legitimately be null.
    """
    if not emp:
        return None
    return {
        'name': emp.name or None,
        # `ir_number` lives in myservice_identity, which this module does not
        # depend on. Read it if the tenant has it, rather than making the SAP
        # leg require the identity module.
        'ir_number': (emp.ir_number or None)
                     if 'ir_number' in emp._fields else None,
        'email': emp.work_email or None,
        'department': emp.department_id.name or None
                      if emp.department_id else None,
    }


def _location(asset):
    """Cadra's own location tree, plus the SAP identifiers we do not have.

    `sap_cost_center` and `sap_plant` are sent as null and that is deliberate.
    The requirements document asks NRS for the cost-centre master and the rule
    that derives one (§5.2); until that arrives Cadra has `department` as free
    text with 808 distinct values in the live register, and deriving a cost
    centre from it by string matching would be a fiction. A null SAP rejects;
    a guess posts to the wrong cost centre and nothing about that looks like a
    failure.
    """
    return {
        'sap_cost_center': None,
        'sap_plant': None,
        'building': asset.building_id.name or None if asset.building_id else None,
        'floor': asset.floor_id.name or None if asset.floor_id else None,
        'room': asset.room_id.name or None if asset.room_id else None,
        'cadra_location_id': asset.location_id.id or None
                             if asset.location_id else None,
    }


class NRSAssetSAPEvents(models.Model):
    _inherit = 'nrs.asset'

    # ── Config lookup ─────────────────────────────────────────────────

    @api.model
    def _sap_event_config(self):
        """The SAP target for this tenant, or an empty recordset.

        `include_disabled=True` for the same reason INT-05 uses it:
        `event_enabled` pauses DELIVERY, not capture. An asset tagged while
        the switch is off is still tagged, and discarding its posting would
        mean switching the target back on silently loses every capitalisation
        in between.
        """
        return self.env['workflow.config'].sudo().get_event_config(
            include_disabled=True, purpose=PURPOSE_SAP_ASSETS)

    # ── Enqueue ───────────────────────────────────────────────────────

    def _queue_sap_event(self, event_type, change=None):
        """Queue one SAP event for this asset. Does not deliver it."""
        self.ensure_one()
        config = self._sap_event_config()
        if not config:
            # The ordinary state on every tenant with no SAP. INFO rather than
            # silence so "why did nothing arrive?" has an answer in the first
            # place anyone looks.
            _logger.info(
                "workflow: no SAP asset target configured on this database; "
                "%s for asset %s not queued", event_type, self.id)
            return False

        if event_type in SAP_LIFECYCLE_EVENTS and not self.sap_asset_number:
            _logger.info(
                "workflow: asset %s has no SAP asset number; %s not sent — "
                "SAP has no asset master to update, and the INT-06 create "
                "will carry the current state when it fires",
                self.id, event_type)
            return False

        if event_type == EVENT_ASSET_MASTER_CREATE:
            if self.sap_asset_number:
                _logger.info(
                    "workflow: asset %s already carries SAP asset number %s; "
                    "not posting a second asset master",
                    self.id, self.sap_asset_number)
                return False
            if self.sap_posting_state in ('queued', 'posted'):
                _logger.info(
                    "workflow: asset %s already has an INT-06 posting in "
                    "flight (%s); not queueing another",
                    self.id, self.sap_posting_state)
                return False

        payload = (self._sap_master_payload() if event_type == EVENT_ASSET_MASTER_CREATE
                   else self._sap_lifecycle_payload(event_type, change or {}))

        row = self.env['workflow.dispatch.log'].sudo()._enqueue_event(
            event_type, payload, config, asset=self)

        if event_type == EVENT_ASSET_MASTER_CREATE:
            self.sudo().write({'sap_posting_state': 'queued'})
        return row

    # ── INT-06 payload ────────────────────────────────────────────────

    def _sap_master_payload(self):
        """The asset master request. Documented in the requirements doc §2.3.

        Shaped to mirror what Cadra's own API serialises for the same facts,
        so someone reading `GET /api/v1/assets/{id}` and reading this payload
        sees the same names for the same things — the discipline INT-05 set.
        """
        self.ensure_one()
        config = self._sap_event_config()
        tag = self.physical_tag_id

        # Two parallel, unrelated cost fields exist on the register and the
        # depreciation engine already rules acquisition_cost first. Send ONE
        # authoritative number and say which field it came from, rather than
        # sending both and leaving SAP to pick — an ambiguous amount on a
        # capitalisation is worse than a missing one.
        amount = self.acquisition_cost or self.purchase_value or 0.0
        if self.acquisition_cost:
            cost_basis = 'acquisition_cost'
        elif self.purchase_value:
            cost_basis = 'purchase_value'
        else:
            # 11,885 of 11,914 assets on the live register are in this state.
            # Sent honestly as zero with `cost_basis: none` so SAP can reject
            # it, rather than suppressed — a capitalisation Cadra quietly
            # declined to request is invisible to both sides.
            cost_basis = 'none'

        return {
            'event': EVENT_ASSET_MASTER_CREATE,
            'event_id': None,          # filled by the queue, which owns it
            'occurred_at': _iso(tag.affixed_date if tag else None)
                           or _iso(fields.Datetime.now()),
            'source': 'cadra',
            'company_code': (config.sap_company_code or None) if config else None,
            'asset': {
                'cadra_asset_code': self.asset_code or None,
                'cadra_asset_id': self.id,
                'description': self.name or None,
                'asset_class': {
                    # Null until NRS returns the mapping (requirements §5.1).
                    # Cadra will not guess an asset class: the wrong one gets
                    # the wrong useful life and the wrong depreciation key,
                    # and nothing about that failure looks like a failure.
                    'sap_asset_class': (self.category_id.sap_asset_class or None)
                                       if self.category_id else None,
                    'cadra_category_code': (self.category_id.code or None)
                                           if self.category_id else None,
                    'cadra_category': (self.category_id.name or None)
                                      if self.category_id else None,
                },
                'serial_number': self.serial_number or None,
                'make': self.make or None,
                'model': self.model_name or None,
                'manufacturer': self.manufacturer or None,
                # Cadra registers one row per physical unit — a GRN line of
                # five laptops becomes five assets with five tags. There is no
                # quantity field to send and there never should be.
                'quantity': 1,
                'condition': self.condition or None,
                'capitalisation': {
                    'amount': amount,
                    'currency': self.currency_id.name or None
                                if self.currency_id else None,
                    'cost_basis': cost_basis,
                    'acquisition_date': _date(self.acquisition_date
                                              or self.purchase_date),
                    # A PROPOSAL. SAP overrides it where period-close rules
                    # require, which is why the response must carry the date
                    # actually posted — see `_apply_sap_master_response`.
                    'proposed_capitalisation_date': _date(
                        tag.affixed_date.date() if tag and tag.affixed_date
                        else fields.Date.today()),
                },
                'procurement': {
                    'po_number': self.purchase_order_reference or None,
                    'grn_number': self.grn_reference or None,
                    # A NAME, not a vendor code. Cadra is not a vendor master;
                    # SAP derives the vendor from the PO (requirements §5.4).
                    'vendor_name': self.purchase_vendor or None,
                },
                'location': _location(self),
                'custodian': _employee(self.custodian_id),
                'hierarchy': {
                    'asset_level': self.asset_level or None,
                    'parent_cadra_asset_code': (self.parent_id.asset_code or None)
                                               if self.parent_id else None,
                },
                'tag': {
                    'number': tag.name or None if tag else None,
                    'label_state': tag.label_state or None if tag else None,
                    'affixed_at': _iso(tag.affixed_date) if tag else None,
                },
            },
        }

    # ── INT-09 payload ────────────────────────────────────────────────

    def _sap_lifecycle_payload(self, event_type, change):
        """One envelope, a typed `event`, and both codes on every message.

        `sap_asset_number` is what SAP keys on; `cadra_asset_code` is what
        makes the message diagnosable when the two systems disagree about
        which asset this is.
        """
        self.ensure_one()
        config = self._sap_event_config()
        return {
            'event': event_type,
            'event_id': None,          # filled by the queue
            'occurred_at': _iso(fields.Datetime.now()),
            'source': 'cadra',
            'company_code': (config.sap_company_code or None) if config else None,
            'asset': {
                'cadra_asset_code': self.asset_code or None,
                'cadra_asset_id': self.id,
                'sap_asset_number': self.sap_asset_number or None,
                'sap_asset_subnumber': self.sap_asset_subnumber or None,
            },
            'change': change,
        }

    # ── Triggers ──────────────────────────────────────────────────────

    def write(self, vals):
        """Raise INT-09 events on genuine transitions, after the write lands.

        State is read BEFORE and AFTER rather than inferred from `vals`: a
        write that sets `custodian_id` to the value it already held is not a
        custodian change, and a receiver cannot tell a no-op reassignment from
        a real one. One physical act, one event — the same rule `_mark_affixed`
        enforces on the tag side.
        """
        watching = ('custodian_id' in vals) or ('state' in vals)
        before = {}
        if watching:
            before = {r.id: (r.custodian_id.id, r.state) for r in self}

        result = super().write(vals)

        if not watching:
            return result

        in_transfer = self.env.context.get(CTX_IN_TRANSFER)
        for record in self:
            was_custodian, was_state = before.get(record.id, (None, None))

            if (record.state == 'disposed' and was_state != 'disposed'):
                # `disposal_type` was the literal `'disposal'` on every event
                # ever sent, and no approver went with it — while the
                # transfer event below has carried `approved_by` and
                # `approved_at` from the day it was written. The requirements
                # document §4.2 asks this event for both, plus the
                # disposal/retirement distinction, and until handoff 16 there
                # were no fields on the register to answer with.
                #
                # Additive, and deliberately non-breaking: an asset with no
                # recorded method still sends `'disposal'`, the exact value
                # SAP has been receiving, so nothing SAP already keys on
                # changes. The four new keys are null where Cadra does not
                # know — which today is most rows, and saying so is the point.
                record._queue_sap_event(EVENT_ASSET_DISPOSED, change={
                    'disposal_type': SAP_DISPOSAL_TYPE.get(
                        record.disposal_method, DEFAULT_SAP_DISPOSAL_TYPE),
                    'disposal_method': record.disposal_method or None,
                    'disposal_date': _date(record.disposal_date
                                           or fields.Date.today()),
                    'disposal_reason': record.disposal_reason or None,
                    'condition_at_disposal': record.condition or None,
                    'reference': record.disposal_reference or None,
                    'approved_by': record.disposal_approved_by.name or None
                                   if record.disposal_approved_by else None,
                    'approved_at': _iso(record.disposal_approved_date),
                    'proceeds': record.disposal_proceeds or None,
                    # A money figure with no currency beside it is how two
                    # systems agree on a number and disagree on what it is
                    # worth. Null when there are no proceeds to denominate.
                    'proceeds_currency': (record.currency_id.name or None)
                                         if record.disposal_proceeds else None,
                })

            # Suppressed inside a transfer: `asset.transferred` already
            # carries the custodian change, and raising both would report one
            # move as a move plus a reassignment.
            if (not in_transfer
                    and record.custodian_id.id != was_custodian
                    and record.state != 'disposed'):
                record._queue_sap_event(EVENT_ASSET_CUSTODIAN_CHANGED, change={
                    'from': {'custodian': _employee(
                        self.env['hr.employee'].browse(was_custodian)
                        if was_custodian else None)},
                    'to': {'custodian': _employee(record.custodian_id)},
                    'changed_at': _iso(fields.Datetime.now()),
                    'changed_by': self.env.user.name or None,
                })

        return result


class NRSAssetTagLabelSAP(models.Model):
    """INT-06 fires on the tag transition, alongside INT-05."""
    _inherit = 'nrs.asset.tag.label'

    def _mark_affixed(self, scanned_tag_number, affixed_by_name=None,
                      affixed_date=None):
        """Capture, then queue the asset master posting on a real transition.

        Deliberately the same shape as the INT-05 override in
        `asset_tag_event.py` and independent of it: whichever runs first calls
        `super()` before deciding, so both see the same transition exactly
        once regardless of import order. A repeat confirmation raises neither
        event, because `_mark_affixed` refuses to rewrite the original record
        and the transition therefore does not happen twice.
        """
        was_affixed = self.label_state == 'affixed'
        result = super()._mark_affixed(
            scanned_tag_number, affixed_by_name=affixed_by_name,
            affixed_date=affixed_date)

        if not was_affixed and self.label_state == 'affixed':
            self.asset_id._queue_sap_event(EVENT_ASSET_MASTER_CREATE)
        return result


class NRSAssetTransferSAP(models.Model):
    _inherit = 'nrs.asset.transfer'

    def action_complete(self):
        """Announce the move once it has actually happened.

        See the module docstring for why this is completion and not approval.
        """
        pending = self.filtered(lambda t: t.state != 'done')
        before = {
            t.id: (t.asset_id.location_id, t.asset_id.custodian_id)
            for t in pending
        }
        result = super(
            NRSAssetTransferSAP,
            self.with_context(**{CTX_IN_TRANSFER: True})
        ).action_complete()

        for transfer in pending:
            if transfer.state != 'done':
                continue
            from_location, from_custodian = before[transfer.id]
            transfer.asset_id._queue_sap_event(EVENT_ASSET_TRANSFERRED, change={
                'transfer_reference': transfer.name or None,
                'transfer_date': _date(transfer.transfer_date),
                'reason': transfer.reason or None,
                'approved_by': transfer.approved_by.name or None
                               if transfer.approved_by else None,
                'approved_at': _iso(transfer.approved_date),
                'from': {
                    'location': {
                        'name': from_location.name or None if from_location else None,
                        'cadra_location_id': from_location.id or None
                                             if from_location else None,
                        'sap_cost_center': None,
                    },
                    'custodian': _employee(from_custodian),
                },
                'to': {
                    'location': {
                        'name': transfer.to_location_id.name or None
                                if transfer.to_location_id else None,
                        'cadra_location_id': transfer.to_location_id.id or None
                                             if transfer.to_location_id else None,
                        'sap_cost_center': None,
                    },
                    'custodian': _employee(transfer.to_custodian_id
                                           or transfer.asset_id.custodian_id),
                },
            })
        return result


class WorkflowDispatchLogSAP(models.Model):
    """INT-07 — reading SAP's answer back onto the register."""
    _inherit = 'workflow.dispatch.log'

    def _mark_delivered(self, result):
        outcome = super()._mark_delivered(result)
        if self.event_type == EVENT_ASSET_MASTER_CREATE:
            self._apply_sap_master_response(result)
        return outcome

    def _raise_dead_letter(self, summary):
        """An abandoned asset master is a dual-code exception, not just a log.

        Without this the asset would sit at `Queued for SAP` for ever and the
        reconciliation view would call it `pending` — a permanently pending
        row is the quiet failure this whole control exists to remove.
        """
        outcome = super()._raise_dead_letter(summary)
        if self.event_type == EVENT_ASSET_MASTER_CREATE and self.asset_id:
            self.asset_id.sudo().write({'sap_posting_state': 'failed'})
        return outcome

    def action_retry_now(self):
        """Put the asset back in flight when its posting is re-queued.

        `_raise_dead_letter` moves the asset to `failed`, which is what makes
        it show as a dual-code exception. A manual retry means somebody has
        fixed the cause and the posting is live again — leaving the asset at
        `failed` would keep it on the exception report while it was actually
        being delivered, and an exception report with rows that are not
        exceptions is one people learn to ignore.
        """
        outcome = super().action_retry_now()
        for row in self:
            if row.event_type == EVENT_ASSET_MASTER_CREATE and row.asset_id:
                if not row.asset_id.sap_asset_number:
                    row.asset_id.sudo().write({'sap_posting_state': 'queued'})
        return outcome

    def _apply_sap_master_response(self, result):
        """Write SAP's asset number and figures onto the register.

        Three refusals, and each one is the "never let an integration guess"
        rule applied to a different way this can go wrong:

        1. **A body we cannot parse is not an acknowledgement.** The event is
           delivered — SAP took it — but no code came back, so the asset stays
           `pending` rather than being marked reconciled on a `200` alone.
        2. **A response for a different asset is refused outright.** If SAP
           echoes a `cadra_asset_code` that is not this asset's, correlation
           has gone wrong somewhere and writing the code anyway would link an
           SAP asset to the wrong physical thing — precisely the failure the
           unique-code constraint was added to prevent.
        3. **`not_capitalised` is recorded, not treated as a code.** SAP
           declining to capitalise (below threshold, say) is a legitimate
           answer, and it is not the same fact as an asset awaiting its code.
        """
        self.ensure_one()
        asset = self.asset_id
        if not asset:
            return False

        # Delivered, whatever the body turns out to say.
        asset.sudo().write({'sap_posting_state': 'posted'})

        body = result.get('body') or self.response_received or ''
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            _logger.warning(
                "workflow: %s delivered but SAP's response was not JSON; no "
                "asset code recorded for asset %s", self.name, asset.id)
            return False
        if not isinstance(data, dict):
            return False
        # Same one-level unwrap the adapter's `_ref_from` does: Frappe wraps
        # in `message`, Cadra's own envelope in `data`.
        inner = data.get('message') or data.get('data') or data
        if not isinstance(inner, dict):
            inner = data

        echoed = inner.get('cadra_asset_code')
        if echoed and asset.asset_code and echoed != asset.asset_code:
            _logger.error(
                "workflow: %s — SAP answered for asset code %r but this event "
                "was for %r. Refusing to write a SAP asset number onto the "
                "wrong asset.", self.name, echoed, asset.asset_code)
            self._append_history(
                'response rejected: SAP echoed asset code %s, expected %s'
                % (echoed, asset.asset_code))
            # Delivered, but the answer was unusable — and an asset left at
            # `posted` would read as `pending`, "awaiting SAP code", for ever.
            # A correlation failure is a finding, not a queue still working,
            # so it drops into the exception state where somebody sees it.
            # Same argument as the dead-letter override above.
            asset.sudo().write({'sap_posting_state': 'failed'})
            return False

        if inner.get('status') == 'not_capitalised':
            reason = inner.get('reason') or 'no reason given'
            _logger.info(
                "workflow: SAP declined to capitalise asset %s (%s)",
                asset.id, reason)
            self._append_history('SAP declined to capitalise: %s' % reason)
            try:
                asset.sudo().message_post(body=_(
                    'SAP accepted the asset master request but did not '
                    'capitalise this asset (%s). No SAP asset code will be '
                    'returned for it.'
                ) % reason)
            except Exception:               # noqa: BLE001
                # catch-all: unknown — `message_post` runs the whole
                # mail.thread stack and this module cannot enumerate its
                # failure surface; the note is a courtesy and the fact is
                # already in the log and in `delivery_history`.
                #
                # Verified rather than assumed: `nrs.asset` does inherit
                # `mail.thread` (`myservice_asset_register/models/asset.py`),
                # so a narrow clause would not be buying a check on a
                # `message_post` that has gone away.
                #
                # Broad because of WHERE this sits. `_apply_sap_master_response`
                # is called from `_mark_delivered`, inside the drain loop's own
                # try: an escape from here would be caught up there, the cursor
                # rolled back, and the row — already delivered to SAP, already
                # written `posted` — would be handed another attempt. A failed
                # chatter note would become a second INT-06 asset master POST.
                _logger.exception(
                    "workflow: could not post not-capitalised note for %s",
                    self.name)
            return False

        if not inner.get('sap_asset_number'):
            _logger.warning(
                "workflow: %s delivered but SAP's response carried no "
                "sap_asset_number; asset %s stays awaiting its code",
                self.name, asset.id)
            return False

        try:
            asset._set_sap_master(inner)
        except ValidationError as e:
            # The commonest cause is SAP returning an asset number already
            # linked to a different Cadra asset — a correlation failure, and
            # the same class of problem as a mismatched echo above. Recorded
            # and dropped into the exception state rather than retried: the
            # number will not become free by being written again.
            _logger.error(
                "workflow: %s — SAP's asset number was refused by the "
                "register: %s", self.name, e)
            self._append_history('response rejected by the register: %s' % e)
            asset.sudo().write({'sap_posting_state': 'failed'})
            return False
        self._append_history(
            'SAP asset number %s recorded on %s'
            % (inner['sap_asset_number'], asset.asset_code or asset.id))
        _logger.info(
            "workflow: INT-07 — asset %s linked to SAP asset number %s",
            asset.id, inner['sap_asset_number'])
        return True
