"""INT-05b outbound — `asset.register_state.changed` (handoff 62).

What this is, plainly: with the receipt gates on, Vendra knew where one of its
units stood only when somebody opened the receipt and Vendra asked. Nobody was
TOLD when Internal Audit rejected a unit, queried one, or when a receipt's last
unit reached the register. Vendra's report 56 §4 designed the smallest message
that fixes it; this is Cadra's half, built to that design and to its contract,
`docs/integrations/INT-05b-register-state.md`.

Four rules, each a sentence of the contract:

- **Raised where every move passes.** `nrs.asset._gate_move` is the only
  writer of `register_state` (handoff 62 searched; `create` sets a birth
  state, which is not a change), so the event hangs on it — every gate, the
  four acts that are not gates (query, reject, resubmit, return), the affix,
  and the skip of a `record_only` unit's tagging. A batch is N single fires,
  so it raises N events.
- **One event per ACT, saying where the unit came to rest.** Two acts make two
  moves in one call: `request-tagging` passes through `tag_requested` to
  `tag_issued`, and IAD's approval of a `record_only` unit passes through
  `vfm_approved` to `reg_ready`. Nobody can ever see a unit in the state it
  passed through, so `_fire_gate` holds the inner moves back and raises one
  event for the state the act left — seven events for a labelled unit's seven
  gates, five for a `record_only` unit's five.
- **Only for units Vendra sent** (`import_source = vendra` with a
  `grn_reference`): Vendra has nothing to match anything else to.
- **INT-05's road, unchanged.** The same `workflow.config` target, bearer
  token, outbox row, retry ladder and dead-letter as `asset.tag.affixed`; the
  row is written in the gate's own transaction, so a move that rolls back
  (a refused unit in a batch, a dry run) takes its event with it. The target
  needs a Register-State Endpoint: a Vendra without one has nowhere to take
  the event, and nothing is queued for it.

The payload is Vendra's table and nothing more — no person's name, email or
id: Vendra says *Internal Audit*, not who.
"""
import logging

from odoo import models

from odoo.addons.myservice_asset_register.models.asset_gates import (
    REGISTERED, WAITING_ON)

from .asset_tag_event import _iso

_logger = logging.getLogger(__name__)

EVENT_REGISTER_STATE = 'asset.register_state.changed'

#: The acts whose words travel with the event (Vendra report 56 §4): the
#: question IAD asked, the reason IAD rejected, the reason the checker
#: returned. A resubmission's response and the system's own sentence on a
#: skipped tagging do not.
REASON_ACTIONS = ('query', 'reject', 'return-registration')

#: Set by `_fire_gate` while it runs, so the moves inside one act raise one
#: event between them — for the state the act left.
_ONE_ACT = 'cadra_register_state_one_act'


class NRSAssetRegisterStateEvent(models.Model):
    _inherit = 'nrs.asset'

    def _fire_gate(self, action, reason=None, payload=None, scopes=None):
        if self.env.context.get(_ONE_ACT):
            return super()._fire_gate(action, reason=reason, payload=payload,
                                      scopes=scopes)
        before = self.register_state
        result = super(NRSAssetRegisterStateEvent,
                       self.with_context(**{_ONE_ACT: True}))._fire_gate(
            action, reason=reason, payload=payload, scopes=scopes)
        if self.register_state != before:
            self._queue_register_state_event(action, reason)
        return result.with_env(self.env)

    def _gate_move(self, to, action, gate, reason=None, notes=None,
                   override_of=None):
        result = super()._gate_move(to, action, gate, reason=reason,
                                    notes=notes, override_of=override_of)
        # Outside an act `_fire_gate` is running — the affix, which the
        # station fires through the label — the move IS the act.
        if not self.env.context.get(_ONE_ACT):
            self._queue_register_state_event(action, reason)
        return result

    def _tells_vendra(self):
        """Whether Vendra sent this unit, so has something to match it to."""
        self.ensure_one()
        asset = self.sudo()
        return asset.import_source == 'vendra' \
            and bool((asset.grn_reference or '').strip())

    def _queue_register_state_event(self, action, reason=None):
        """Queue `asset.register_state.changed`, if Vendra sent this unit and
        the tenant's Vendra target takes it."""
        self.ensure_one()
        if not self._tells_vendra():
            return False
        # `include_disabled`, as `asset.tag.affixed`: a paused target still
        # queues; only the absence of one means there is nowhere to send.
        config = self.env['workflow.config'].sudo().get_event_config(
            include_disabled=True)
        if not config:
            _logger.info(
                "workflow: no asset-event target configured on this "
                "database; %s for asset %s not queued", EVENT_REGISTER_STATE,
                self.id)
            return False
        if config.adapter_type == 'rest' \
                and not (config.rest_endpoint_register_state or '').strip():
            # A Vendra that predates its receiver (Vendra handoff 57) would
            # refuse every one of these; queueing them would dead-letter each
            # move of each unit. Said in the log, where "why did nothing
            # arrive?" is asked first.
            _logger.info(
                "workflow: target %s has no register-state endpoint; %s for "
                "asset %s not queued", config.name, EVENT_REGISTER_STATE,
                self.id)
            return False
        return self.env['workflow.dispatch.log'].sudo()._enqueue_event(
            EVENT_REGISTER_STATE, self._register_state_payload(action, reason),
            config, asset=self)

    def _register_state_payload(self, action, reason=None):
        """The published body — Vendra report 56 §4's table, no more.

        `event_id` is added by the queue, which owns it. `reason` only on a
        query, a rejection or a return; `sap_asset_code` only on
        `registered`. No person: not the actor, not the approver, not who
        asked."""
        self.ensure_one()
        asset = self.sudo()
        state = asset.register_state
        body = {
            'asset_id': asset.id,
            'asset_code': asset.asset_code or None,
            'grn_reference': asset.grn_reference,
            'register_state': state,
            'waiting_on': WAITING_ON.get(state),
            'state_since': _iso(asset.register_state_since),
        }
        text = reason.strip() if isinstance(reason, str) else ''
        if action in REASON_ACTIONS and text:
            body['reason'] = text
        if state == REGISTERED:
            body['sap_asset_code'] = asset.sap_asset_number or None
        return body
