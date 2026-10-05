from odoo import models, fields, api, _
from odoo.exceptions import UserError

# The context key a caller sets to say WHERE an event came from. Anything that
# does not set it lands on `direct` — the Odoo form, an import, a shell
# session — exactly as `asset_custody.CUSTODY_SOURCE_KEY` does.
EVENT_SOURCE_KEY = 'cadra_event_source'

# The reason the caller gave, when it gave one. In the context for the reason
# custody's is: an ORM write that changes a status has nowhere to put a
# sentence. It is what makes *why is this asset missing* a recorded fact
# rather than a note squeezed into a field that means something else.
EVENT_REASON_KEY = 'cadra_event_reason'

# The flag `_record` sets on itself; `create` refuses without it.
EVENT_APPEND_KEY = 'cadra_event_append'

EVENT_VERIFIED = 'verified'
EVENT_VERIFICATION_DATE_SET = 'verification_date_set'
EVENT_STATUS_CHANGED = 'status_changed'
EVENT_REFERENCE_CHANGED = 'reference_changed'
EVENT_WARRANTY_CHANGED = 'warranty_changed'
EVENT_AFFIX_REFUSED = 'affix_refused'

# The symbologies a scanner can claim a value was read in — the
# BarcodeDetector-style names the app's camera passes up with every decode
# (handoff 54), published verbatim as the affix route's `scanned_format` /
# `serial_format` enum. Cadra's own labels print `code_128` and `qr_code`;
# anything else came off a manufacturer's label, which is the distinction
# the column below exists to preserve for an auditor.
SCANNED_FORMATS = (
    'code_128', 'code_39', 'code_93', 'codabar',
    'ean_13', 'ean_8', 'upc_a', 'upc_e', 'itf',
    'qr_code', 'data_matrix', 'pdf417', 'aztec')

# The three fields whose change is an event. They are what an auditor
# reconciles against Vendra and against SAP, they change rarely, and a change
# to one is exactly the thing somebody would want to hide (report 28 §4,
# ruled in handoff 30). `purchase_vendor` and the three import fields stay
# tracked in the chatter and are NOT here: the importer rewrites them on
# every re-import, and an append-only table is the wrong place to discover
# that a record is mostly data loading — which is what report 28 §0 found
# about location, after the fact.
REFERENCE_FIELDS = (
    'grn_reference', 'purchase_order_reference', 'sap_asset_number')

# The five fields of a warranty (handoff 34), and a change to any of them is
# an event. A warranty is a contractual fact somebody could have an interest
# in altering — lengthened after the laptop broke so the repair is somebody
# else's bill, or shortened so a replacement can be justified — and the
# person holding the broken asset needs the record to be the one that stood
# on the day. They are NOT tracked in the chatter: this is their record, and
# a chatter row beside it would be the same fact twice, one of them
# deletable.
#
# What it costs is what every event costs, and it is small here. An event is
# a CHANGE, so an asset created WITH a warranty — every INT-03 receipt that
# carries one — writes none and is not pinned; only a later edit is. The
# derived expiry is recorded when it moves, because it did move: a duration
# corrected from 24 to 36 months is two rows, the duration and the date,
# and a reader who asks only "when did the expiry change" finds it.
WARRANTY_FIELDS = (
    'warranty_start_date', 'warranty_months', 'warranty_expiry',
    'warrantor', 'warranty_reference')

# What each type may carry. `_record` refuses a key that does not belong to
# the type, so a status change cannot arrive with verification notes and the
# sparse columns below cannot drift into a bag of whatever a caller sent.
# This table is the typed payload: it is why the model can be ONE table
# without the per-type guarantees becoming "any column, any row".
_PAYLOAD_OF_TYPE = {
    EVENT_VERIFIED: frozenset({'from_value', 'to_value', 'notes'}),
    EVENT_VERIFICATION_DATE_SET: frozenset({'from_value', 'to_value'}),
    EVENT_STATUS_CHANGED: frozenset({'from_value', 'to_value', 'reason'}),
    # No `reason`: nothing that changes a reference has anywhere to take one
    # from, and a column no writer can fill reads as a reason nobody gave.
    EVENT_REFERENCE_CHANGED: frozenset(
        {'field_name', 'from_value', 'to_value'}),
    # No `reason`, for the reason above: a PATCH of a duration carries none.
    EVENT_WARRANTY_CHANGED: frozenset(
        {'field_name', 'from_value', 'to_value'}),
    # Handoff 51. A refused affix confirmation. `to_value` is the value the
    # caller tried to confirm with, AS ENTERED — a tag number, or for a
    # serial refusal the scanned serial; the expected value is on the label
    # or asset row and is deliberately not copied here. No `from_value`: a
    # refusal changes nothing, so there is no before. The point of the row
    # is the SEQUENCE it makes visible — a refusal and a confirmation
    # seconds apart, same asset, same operative, is readable in the history,
    # where today the wrong-then-revealed-right sequence leaves one clean
    # affix record saying a human verified the label.
    #
    # `reason` since handoff 52 §4 — WHICH refusal, one of three keys the
    # recorder writes itself (never caller text): `number_mismatch` (the
    # scanned tag is not the label issued — handoff 51's, and what a NULL
    # reason on a pre-52 row means), `scrapped` (the label presented is
    # dead), `serial_mismatch` (the serial read off the asset is not the
    # one on record — the label going onto the wrong box, and the cheaper
    # tell, since that refusal reveals nothing to the person refused). The
    # history sentence differs per reason so a reader can tell a wrong
    # label from a dead one.
    #
    # `scanned_format` since handoff 54 §7 — HOW `to_value` was read, when
    # the caller knew (the app's camera passes the symbology up with every
    # decode; a typed or keyboard-wedge entry has none to claim): the tag
    # read's format on `number_mismatch` and `scrapped`, the serial read's
    # on `serial_mismatch`. It is allowed HERE AND NOWHERE ELSE by ruling:
    # a successful affix stores nothing new, so the format exists only
    # where it tells an auditor whether a refused number came off Cadra's
    # own label (code_128 / qr_code) or a manufacturer's.
    EVENT_AFFIX_REFUSED: frozenset({'to_value', 'reason', 'scanned_format'}),
}

# Which fields each field-carrying type may name. A reference change naming a
# warranty field, or the reverse, is refused rather than filed under the
# wrong heading.
_FIELDS_OF_TYPE = {
    EVENT_REFERENCE_CHANGED: REFERENCE_FIELDS,
    EVENT_WARRANTY_CHANGED: WARRANTY_FIELDS,
}

# The sources a CALLER may declare through the context. `test` says something
# about the evidence itself and is never taken from the context — see
# `nrs.asset.append.only.mixin._resolve_source`.
_CONTEXT_SOURCES = (
    'api_verify', 'api_condemn', 'api_mark_missing', 'api_mark_found',
    'api_write', 'api_affix',
    'action', 'transfer', 'approval', 'direct')


class NRSAssetEvent(models.Model):
    """Something that happened to an asset, which nobody can alter.

    Handoff 30 ruled three more records of the kind `nrs.asset.custody` and
    `nrs.asset.movement` are, and asked first whether building them as a
    third, fourth and fifth near-identical table was a design or an accident.
    This is the answer for the three that did not exist yet: ONE model with a
    type, the common columns, and a payload whose shape is fixed per type by
    `_PAYLOAD_OF_TYPE`. The case both ways, and why custody and movement were
    left where they are, is `docs/handoffs/30-REPORT.md` §1.

    - **`verified`** — every time this asset was checked, and by whom: the
      ACTOR IS THE VERIFIER. `last_verified_date` / `last_verified_by` are
      ONE overwritten pair; a register that is physically verified every
      year kept only the last year.
    - **`verification_date_set`** — somebody wrote a verification DATE, over
      PATCH, on the form or by import, and the record does not say who
      checked anything — which is why `nrs.asset.write` clears the verifier
      then. A TYPE OF ITS OWN and not a `verified` with a different
      `source`, because `source` is overwritten with `test` under a test
      credential and the difference between *"Ada checked it"* and *"a date
      was written"* must not be something a label can erase.
    - **`status_changed`** — every change of `state`, with the reason where
      one was given. It is where *why is this asset missing* lives, and it
      closes `disposal_executor` going forward: the actor of the change into
      `disposed` is who carried the disposal out.
    - **`reference_changed`** — a change to one of `REFERENCE_FIELDS`, with
      the value before and the value after AS THEY READ AT THE TIME.
    - **`warranty_changed`** — a change to one of `WARRANTY_FIELDS` (handoff
      34), recorded the same way: a date as its ISO string, a duration as
      its number of months, a name as it was typed.
    - **`affix_refused`** — a tag-affix confirmation the register REFUSED
      because the scanned number did not match the label issued (handoff
      51). The one type here that records a write that did NOT happen, and
      the one not written under `nrs.asset.write`: the check is
      `nrs.asset.tag.label._mark_affixed`, whose refusal unwinds the
      request's transaction, so the row is written there on its own cursor
      — see `_record_affix_refusal` on the tag model for the measurement.

    The field-change types are written by `nrs.asset.write`, where every
    writer passes — not by any route — because every field they watch has
    many writers. `affix_refused` is written beside the check that refuses,
    for the same reason: every caller of the check passes through it.

    **An event is a CHANGE, so an asset's opening values write none.** That
    is a deliberate difference from custody and movement, which record the
    first custodian and the first placement. Every asset has a `state` from
    birth; recording it would pin every asset ever created
    (`ondelete='restrict'`) for a row that says only that it was created,
    which `create_date` already says. The first CHANGE of a reference
    carries the opening value in `from_value`, so nothing is lost by it.
    """

    _name = 'nrs.asset.event'
    _inherit = ['nrs.asset.append.only.mixin']
    _description = 'Asset Event Record'
    # Chronological; `id` breaks ties inside one transaction.
    _order = 'occurred_at, id'

    _append_key = EVENT_APPEND_KEY
    _source_key = EVENT_SOURCE_KEY
    _context_sources = _CONTEXT_SOURCES

    asset_id = fields.Many2one(
        'nrs.asset', string='Asset', required=True, index=True,
        # NOT cascade, for custody's reason: deleting the asset would erase
        # what happened to it, which is the defect this model exists to
        # remove.
        ondelete='restrict')

    event_type = fields.Selection([
        (EVENT_VERIFIED, 'Verified'),
        (EVENT_VERIFICATION_DATE_SET, 'Verification date written'),
        (EVENT_STATUS_CHANGED, 'Status changed'),
        (EVENT_REFERENCE_CHANGED, 'Reference changed'),
        (EVENT_WARRANTY_CHANGED, 'Warranty changed'),
        (EVENT_AFFIX_REFUSED, 'Affix confirmation refused'),
    ], string='Event', required=True, index=True)

    occurred_at = fields.Datetime(
        string='Recorded At', required=True, index=True,
        default=lambda self: fields.Datetime.now())

    # WHO MADE THE WRITE. On a `verified` event that is the verifier.
    actor_id = fields.Many2one(
        'res.users', string='By', ondelete='set null')
    actor_name = fields.Char(string='By (as recorded)')

    # ── the typed payload — see `_PAYLOAD_OF_TYPE` ────────────────────
    field_name = fields.Selection(
        [(name, name) for name in REFERENCE_FIELDS + WARRANTY_FIELDS],
        string='Field', index=True)
    # Chars, AS RECORDED. A status is stored by its key (`missing`), a
    # verification by the ISO date written, a reference verbatim — none of
    # them a foreign key, so nothing outside this row can empty it.
    from_value = fields.Char(string='Before (as recorded)')
    to_value = fields.Char(string='After (as recorded)')
    reason = fields.Text(string='Reason')
    notes = fields.Text(string='Verification Notes')
    # Carried only by `affix_refused` (`_PAYLOAD_OF_TYPE`). NULL means the
    # format is NOT KNOWN — a typed entry, a hardware scanner's keyboard
    # wedge, or any row from before handoff 54 — never that nothing was
    # scanned; the keys are the names, as `field_name` does above, because
    # the values ARE the published enum.
    scanned_format = fields.Selection(
        [(name, name) for name in SCANNED_FORMATS],
        string='Scanned Format')

    source = fields.Selection([
        ('api_verify', 'API — verify'),
        ('api_condemn', 'API — condemn'),
        ('api_mark_missing', 'API — mark missing'),
        ('api_mark_found', 'API — mark found'),
        ('api_write', 'API — asset create or update'),
        ('api_affix', 'API — tag-affix confirmation'),
        ('action', 'A button on the asset (verify, condemn, mark missing '
                   'or found)'),
        ('transfer', 'Asset transfer completion'),
        # Handoff 35. Completing an approved MOVE sets nothing about status
        # today, but `nrs.asset.write` declares one source for all three
        # recorders from one context, and a source a recorder cannot accept
        # is a `UserError` on a write that had nothing to do with events.
        ('approval', 'Approved change request'),
        ('direct', 'Direct write (Odoo UI, import or script)'),
        ('test', 'Written by the automated test suite'),
    ], string='Source', required=True, default='direct', index=True)

    def _append_only_message(self):
        return _(
            "The record of what has happened to an asset is append-only. An "
            "event cannot be edited or deleted once written — not through "
            "the interface, not over the API, and not as an administrator "
            "with sudo. What happens next is recorded as a new event; the "
            "history is the evidence."
        )

    def _no_hand_written_rows_message(self):
        return _(
            "An asset event cannot be created directly. One is written only "
            "as a side effect of the asset actually being verified, changing "
            "status, having a reference or its warranty changed, or having "
            "an affix confirmation refused, so that the record says "
            "what happened rather than what somebody typed."
        )

    # ── When the record began, PER TYPE ───────────────────────────────

    @api.model
    def recording_began_at(self, event_type):
        """The instant of the oldest row of this type HERE, or None.

        Per type and not per table, and that is the one thing a shared model
        makes easier to get wrong: a database whose first status change was
        recorded in September and whose first verification was recorded in
        March did not begin recording verifications in September. Measured,
        not declared, for `nrs.asset.movement.recording_began_at`'s reason.
        """
        self.env.cr.execute(
            "SELECT min(create_date) FROM nrs_asset_event "
            "WHERE event_type = %s", (event_type,))
        return self.env.cr.fetchone()[0]

    # ── The one way a row is written ──────────────────────────────────

    @api.model
    def _record(self, asset, event_type, *, source=None, occurred_at=None,
                actor=None, **payload):
        """Append one event. The only way a row is ever written."""
        allowed = _PAYLOAD_OF_TYPE.get(event_type)
        if allowed is None:
            raise UserError(_("Unknown asset event type: %s") % event_type)
        stray = set(payload) - allowed
        if stray:
            raise UserError(_(
                "An asset event of type %(type)s cannot carry %(keys)s.",
                type=event_type, keys=', '.join(sorted(stray))))
        fields_of_type = _FIELDS_OF_TYPE.get(event_type)
        if fields_of_type is not None \
                and payload.get('field_name') not in fields_of_type:
            raise UserError(_(
                "An asset event of type %(type)s must name one of: "
                "%(fields)s", type=event_type,
                fields=', '.join(fields_of_type)))
        user = actor if actor is not None else self.env.user
        vals = {
            'asset_id': asset.id,
            'event_type': event_type,
            'occurred_at': occurred_at or fields.Datetime.now(),
            'actor_id': user.id if user else False,
            'actor_name': user.name if user else False,
            'source': self._resolve_source(source, user),
        }
        for key in allowed:
            vals[key] = payload.get(key) or False
        return self.sudo().with_context(
            **{self._append_key: True}).create(vals)
