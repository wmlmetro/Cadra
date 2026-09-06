"""INT-05 outbound — `asset.tag.affixed`.

Handoff 03 built the capture half: a label becomes `affixed` only through a
confirmation carrying the tag number scanned off the asset, and the
serial-to-tag match is the control. This is the transport half — telling
Vendra that it happened, so its receipt line can finally read `Tagged`
instead of stopping at `Registered`.

Two disciplines carried over from capture, because transport is where they
are easiest to lose:

- **The event claims only what the capture proves.** `affixed` means somebody
  confirmed through the scoped endpoint. `printed_at` may be null in the
  payload — a label can be affixed without Cadra ever having observed a
  render — and null is the honest value, not a reason to infer one.
- **A repeat confirmation is not a second event.** `_mark_affixed` already
  refuses to rewrite the original record; the event is raised on the
  transition, so a retrying client does not produce two `asset.tag.affixed`
  for one physical act.
"""
from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)

EVENT_TAG_AFFIXED = 'asset.tag.affixed'


def _iso(value):
    """Odoo stores naive UTC; the wire wants an explicit offset.

    A bare `2026-09-14 11:32:07` forces the receiver to guess a timezone, and
    the two systems are not guaranteed to guess the same one.
    """
    if not value:
        return None
    return fields.Datetime.to_string(value).replace(' ', 'T') + 'Z'


def _date(value):
    return fields.Date.to_string(value) if value else None


class NRSAssetTagLabel(models.Model):
    _inherit = 'nrs.asset.tag.label'

    def _mark_affixed(self, scanned_tag_number, affixed_by_name=None,
                      affixed_date=None):
        """Capture first, then queue the event on a genuine transition."""
        was_affixed = self.label_state == 'affixed'
        result = super()._mark_affixed(
            scanned_tag_number, affixed_by_name=affixed_by_name,
            affixed_date=affixed_date)

        if not was_affixed and self.label_state == 'affixed':
            self._queue_tag_affixed_event()
        return result

    def _queue_tag_affixed_event(self):
        """Queue `asset.tag.affixed`, if this tenant has anywhere to send it."""
        self.ensure_one()
        # `include_disabled`: a paused target still queues. Only the total
        # ABSENCE of a target means there is nowhere for this event to go.
        config = self.env['workflow.config'].sudo().get_event_config(
            include_disabled=True)
        if not config:
            # The ordinary state on every tenant with no Vendra. Logged rather
            # than silent so that "why did nothing arrive?" has an answer in
            # the place someone will look first.
            _logger.info(
                "workflow: no asset-event target configured on this database; "
                "%s for asset %s not queued", EVENT_TAG_AFFIXED,
                self.asset_id.id)
            return False
        return self.env['workflow.dispatch.log'].sudo()._enqueue_event(
            EVENT_TAG_AFFIXED,
            self._tag_affixed_payload(),
            config,
            asset=self.asset_id,
            tag_label=self,
        )

    def _tag_affixed_payload(self):
        """The published INT-05 body.

        Shaped to mirror what Cadra's own API serialises for the same facts,
        so an integrator reading `GET /api/v1/assets/{id}` and reading this
        event sees the same names for the same things.
        """
        self.ensure_one()
        asset = self.asset_id
        return {
            'event': EVENT_TAG_AFFIXED,
            # Repeated in the X-Idempotency-Key header. In the body too so a
            # receiver that logs only bodies can still dedupe.
            'event_id': None,          # filled by the queue, which owns it
            'occurred_at': _iso(self.affixed_date),
            'source': 'cadra',
            'asset': {
                'id': asset.id,
                'asset_code': asset.asset_code or None,
                'name': asset.name or None,
                'serial_number': asset.serial_number or None,
            },
            'tag': {
                # A label id is NOT an asset id and the two spaces collide —
                # the same trap `data.tagging.label_id` exists to close on the
                # read side. Named explicitly for the same reason.
                'label_id': self.id,
                'number': self.name,
                'label_state': self.label_state,
                'issued_at': _iso(self.create_date),
                # Null when Cadra never observed a render. The label is still
                # affixed; we just cannot claim to have printed it.
                'printed_at': _iso(self.printed_date),
                'affixed_at': _iso(self.affixed_date),
                # Kept apart deliberately. `affixed_by` is the Cadra
                # credential that submitted the confirmation — the
                # Tag-Issuing Unit's API client. `affixed_by_name` is the
                # human who physically fitted the label, who is not a Cadra
                # user. Collapsing them into one string would throw away
                # which of the two any given value is.
                'affixed_by': self.affixed_by.name or None if self.affixed_by else None,
                'affixed_by_name': self.affixed_by_name or None,
            },
            # Echoed so Vendra can match the event to a receipt line without
            # holding a Cadra id. This is what closes the loop CR-01 opened.
            'provenance': {
                'grn_reference': asset.grn_reference or None,
                'purchase_order_reference': asset.purchase_order_reference or None,
                'purchase_vendor': asset.purchase_vendor or None,
                'import_source': asset.import_source or None,
                'import_date': _date(asset.import_date),
                'import_ref': asset.import_ref or None,
            },
        }
