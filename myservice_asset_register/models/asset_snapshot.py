"""What the asset register said on a past date — and, just as loudly, what it
cannot say.

Specification §13.4 opens its audit-report list with *"asset register snapshot
at any historical date (point-in-time view)"*, and INT-10 §2.5 answered that
question with **"No, except for depreciation"**. This module is the answer to
the half that is honestly answerable.

**The governing rule, from handoff 16 §B1:** *answer for the fields where the
answer is sound, and say plainly which fields are as-of-today rather than
as-of-the-date. A snapshot that silently mixes the two is worse than no
snapshot* — because an auditor will reconcile it against a figure and the
discrepancy will be ours. So every response carries `snapshot_fidelity()`,
which names the three classes of field before a single row is read, and every
row that is degraded **for that row specifically** carries `_fidelity`.

## Where the history comes from

Three stores, of decreasing strength:

1. **`nrs.asset.custody`** — append-only, refuses `write` and `unlink` even
   under `sudo()`. This is the only history in Cadra that cannot be deleted,
   so it wins for `custodian_id` wherever it reaches.
2. **`mail.tracking.value`** — 20 tracked fields (see below). Real history,
   but it hangs off `mail.message`, and anybody who can delete a message can
   delete the evidence. It is what we have for everything except custody.
3. **The depreciation engine** — not history at all but a *pure function of
   `as_of`*, which is stronger than either: it cannot have gaps. See the
   `value` block and its caveat below.

Everything else is a column with no history whatsoever. Those fields are
either published at today's value and labelled (`SNAPSHOT_AS_OF_TODAY`) or
named as unanswerable (`SNAPSHOT_NOT_RECOVERABLE`). Nothing is quietly
omitted: handoff 16 asks that *"where a field cannot be rolled back, the
report says so for that field rather than omitting the row."*

## The trap in deriving the tracked-field list

**A `related=` field inherits `tracking` from its target, invisibly.** A grep
for `tracking=True` across the five modules that `_inherit = 'nrs.asset'`
finds 18 fields and misses two: `tag_label_state`
(`related='physical_tag_id.label_state'`) and `active_tag_number`
(`related='active_tag_id.name'`) carry no `tracking=` of their own, inherit it
from `nrs.asset.tag.label`, and produce real `mail_tracking_value` rows —
11,934 of them on `nrs19`, the single largest tracked field in the estate. The
authoritative list is `ir_model_fields.tracking > 0` **in a live registry**,
which is what `test_snapshot_rollback.py` asserts this tuple against, so a
field that becomes tracked tomorrow cannot silently fall out of the snapshot.

This also settles a question INT-10 §2.6 left open: `is_tagged` is not a
column, it is `tag_label_state == 'affixed'` computed in the serialiser — so
**"was this asset tagged on 31 March?" is answerable**, from a rolled-back
`tag_label_state`.

## It never writes. That is an acceptance criterion, not an aspiration.

No `flush`, no `_apply_depreciation()` (which writes; `_depreciation_policy()`
does not), no compute forced. `value` is computed in memory from
`depreciation_engine.value_at`, which persists nothing by design — the same
property that makes `GET /assets/<id>/depreciation?as_of=` honest.
`test_snapshot_rollback.py` fingerprints `write_date`, the tracking table and
the custody table across a run and asserts none of them moved.
"""
from datetime import datetime, time, timedelta

from odoo import api, fields, models

# ── The cutoff ───────────────────────────────────────────────────────────
#
# `mail_message.date` and `nrs.asset.custody.changed_at` are both naive UTC.
# "As it stood on 31 March" is a sentence spoken in Lagos, so the day it names
# is a Lagos day: the snapshot cuts at the END of `as_of` in West Africa Time.
#
# WAT is a FIXED +01:00 — Nigeria has never observed daylight saving — so this
# is an exact arithmetic conversion and not an approximation standing in for a
# timezone database. That is why it is a constant rather than a `pytz` lookup:
# a lookup would imply a subtlety that does not exist here, and would make the
# cutoff depend on which timezone the calling user happens to have set.
#
# Consequence, stated so nobody has to discover it: a change made at
# 23:30 UTC on 31 March is 00:30 on 1 April in Lagos, and is therefore NOT in
# the 31 March snapshot. That is the intended reading.
SNAPSHOT_TZ_UTC_OFFSET_HOURS = 1

#: Human-readable statement of the above, for the response and the document.
SNAPSHOT_CUTOFF_DESCRIPTION = (
    "The snapshot cuts at the end of the requested day in West Africa Time "
    "(UTC+01:00, fixed — Nigeria observes no daylight saving), which is "
    "23:00:00 UTC on that date. A change recorded at or after that instant is "
    "rolled back; a change recorded before it stands."
)


def snapshot_cutoff(as_of):
    """`as_of` (a date, or anything `fields.Date.to_date` accepts) -> the
    naive UTC datetime the rollback cuts at.

    Exclusive upper bound: a tracking row or custody link whose timestamp is
    `>= cutoff` happened AFTER the snapshot and is undone; one strictly before
    it happened before and stands.
    """
    as_of = fields.Date.to_date(as_of)
    end_of_day_local = datetime.combine(as_of, time.min) + timedelta(days=1)
    return end_of_day_local - timedelta(hours=SNAPSHOT_TZ_UTC_OFFSET_HOURS)


def snapshot_today():
    """The current date IN LAGOS — the day `as_of` is measured against.

    The cutoff above is a Lagos day. Until handoff 29 the route refused a
    future `as_of` by comparing it with `fields.Date.today()`, which is the
    SERVER's date — UTC, because the container is — so for one hour every
    night, 00:00 to 01:00 in Lagos, somebody
    asking for TODAY's register was told the date *"has not happened"*. The
    same fixed offset, for the reason given above; one definition of the day,
    used on both sides of the question.

    Invisible to CI, which runs in UTC and whose tests ask for the UTC date.
    It was found by running the suite at 00:50 in Lagos.
    """
    # `fields.Datetime.now()`, the codebase's idiom for naive UTC — not
    # `datetime.utcnow()`, which is deprecated on the image's Python.
    return (fields.Datetime.now()
            + timedelta(hours=SNAPSHOT_TZ_UTC_OFFSET_HOURS)).date()


# ── The three classes of field ───────────────────────────────────────────
#
# ROLLED BACK — every field on `nrs.asset` that carries tracking, and no
# others. An auditor's six questions (handoff 16: existence, custody,
# location, condition, state, value) are covered by this list plus `value`
# below; the rest of the list is here because it is sound and because the
# identity a register row is reconciled BY (its name, its code, its category)
# has to read as it read on the date or the reconciliation is against a
# different row.
#
# Nothing is in this tuple merely because it is tracked and nothing sound was
# left out of it. The two judgement calls are annotated at the field.
SNAPSHOT_ROLLED_BACK = (
    # Identity. `asset_code` is system-generated and readonly, so in practice
    # it never moves — it is rolled back anyway because a snapshot whose key
    # column is as-of-today cannot be joined to anything with confidence.
    'name',
    'asset_code',
    'asset_tag',
    # Tag lifecycle. Related-stored off `nrs.asset.tag.label`, tracking
    # inherited (see the module docstring). CAVEAT, published as a note:
    # INT-10 §2.6 records that the `printed` state was not recorded at all
    # before 2026-09-08, so a snapshot before that date under-reports
    # `printed` and says nothing wrong about `affixed`.
    'tag_label_state',
    'active_tag_number',
    # Classification. `domain` is `related='category_id.domain', store=True`;
    # it has its own tracking rows recording what the stored column actually
    # said, so rolling it back is faithful to the column rather than a
    # re-derivation from the rolled-back category.
    'category_id',
    'subcategory_id',
    'asset_type_id',
    'asset_level',
    'domain',
    # Location — one of the six.
    'building_id',
    'floor_id',
    'room_id',
    'location_id',
    # Custody — one of the six, and resolved from the custody CHAIN first.
    'custodian_id',
    # Condition and state — two of the six.
    'condition',
    'state',
    # Verification and retrieval.
    'last_verified_date',
    'retrieval_flag',          # `myservice_identity`; may not be installed.
    # Depreciation policy. `myservice_asset_depreciation`; may not be
    # installed. Rolled back because it has genuine tracking rows — but see
    # the `value` note: the rest of the depreciation inputs are NOT tracked,
    # so a row whose method moved after the cutoff has its `value` flagged.
    'depreciation_method',
    # Disposal — the sixth question an auditor asks, and tracked as of
    # handoff 16 §B2. These were in AS_OF_TODAY when this module was written,
    # correctly: `disposal_date` and `disposal_reason` carried no tracking
    # then and the other six did not exist. Now all eight are tracked, so the
    # snapshot can answer "was this asset disposed as at 31 March, and was
    # the authorising paper there on the day?" rather than reporting today's
    # answer under a historical heading. This is also what lets the register
    # snapshot and the disposal report be reconciled against each other for
    # the same date instead of quietly disagreeing.
    #
    # `test_every_tracked_field_is_rolled_back` is what forced this: the two
    # modules landed in the same change, and the contract test caught the
    # second one adding tracking that the first was not using. That is the
    # guard working — a field that gains a history and keeps being published
    # as-of-today is exactly the silent mixing this report must not do.
    'disposal_date',
    'disposal_reason',
    'disposal_method',
    'disposal_reference',
    'disposal_approved_by',
    'disposal_approved_date',
    'disposal_proceeds',
    # The disclosure that a date was RECOVERED rather than recorded. Rolled
    # back with the rest so a snapshot never presents a reconstructed date as
    # though it had been recorded at the time.
    'disposal_date_reconstructed',
)

# TRACKED FROM A KNOWN INSTANT — rolled back, and honest about how far.
#
# Every field in `SNAPSHOT_ROLLED_BACK` became tracked on SOME day, and the
# `rolled_back` note's claim — "no recorded change since the date means the
# current value IS the value at the date" — is only true back to that day.
# For the older fields nobody knows when that was and the note's `tracking`
# caveat is the best that can be said. For these six it is known exactly,
# because handoff 28 turned tracking on and stamped the instant on each
# database (`cadra.provenance_tracked_from`) — migration 19.0.1.15.0 on an
# upgrade, `hooks.stamp_tracking_began` on a fresh install.
#
# So they ARE rolled back — `test_every_tracked_field_is_rolled_back`
# requires it and is right to — but only for a requested date AT OR AFTER
# that instant. For an EARLIER date they are classed `as_of_today`, which is
# where they sat before they were tracked and is exactly what they are: a GRN
# reference rewritten the week before tracking began left nothing, and a
# snapshot of that week would otherwise present today's value as the value
# on the date. That is the defect this module exists to prevent, arriving
# through the act of fixing a different one.
#
# The classification moves with the DATE and is said once, in
# `snapshot_fidelity(as_of)` — NOT on every row. The first draft flagged
# each row under `_fidelity.as_of_today`, and `test_fidelity_keys_are_absent_
# when_the_row_is_sound` failed it, rightly: `_fidelity` on a row is a signal
# only because a sound row does not carry one, and on a database whose
# tracking began today that flag would have sat on every row of every
# historical snapshot, where every reader learns to skip it.
#
# Every database gets a stamp, so an absent one never has to mean anything.
# The first draft let absence mean "tracked from the first asset", on the
# grounds that a fresh install runs no migration — true of a database whose
# every asset was created by this code, and FALSE of the one that matters:
# the 15→19 cutover builds NEW databases and loads them by ETL with their
# original `create_date`s, and with no stamp the snapshot would have rolled
# provenance back across years it holds no record of. If a stamp is somehow
# absent anyway, nothing is flagged; that is the fallback, not the design.
SNAPSHOT_TRACKED_FROM_PARAM = 'cadra.provenance_tracked_from'
SNAPSHOT_TRACKED_FROM = (
    'grn_reference',
    'purchase_order_reference',
    'purchase_vendor',
    'import_source',
    'import_date',
    'import_ref',
    # Tracked in the same handoff and for a different reason — so that a
    # verifier being replaced or cleared is visible (`asset.py`). Before the
    # stamp it was NOT_RECOVERABLE and unpublished; it is published now, at
    # today's value and classed `as_of_today`, for any earlier date.
    'last_verified_by',
)
SNAPSHOT_ROLLED_BACK = SNAPSHOT_ROLLED_BACK + SNAPSHOT_TRACKED_FROM

# AS OF TODAY — no history exists for these, and they are published anyway,
# at their CURRENT value, labelled. Handoff 16: "where a field cannot be
# rolled back, the report says so for that field rather than omitting the
# row." Every one of these is a field an auditor reaches for while holding
# the snapshot — the provenance of the asset, what was paid for it, what SAP
# booked it as — and an omitted column sends them to a second query that
# answers as-of-today without saying so, which is the failure this whole
# module exists to prevent.
SNAPSHOT_AS_OF_TODAY = (
    'serial_number',
    'legacy_asset_code',
    'make',
    'model_name',
    'manufacturer',
    'department',
    'floor_room',
    'parent_id',
    # The six INT-03 provenance fields were here until handoff 28 tracked
    # them. They are now in `SNAPSHOT_TRACKED_FROM` below, which is where a
    # field goes when it has a history that begins on a known day.
    # Money as the register holds it. The point-in-time answer is `value`.
    'acquisition_date',
    'acquisition_cost',
    'purchase_date',
    'purchase_value',
    # SAP dual-code (INT-06/07). `sap_asset_number` is the control point and
    # is untracked, so "did it have a SAP code on 31 March?" is not a question
    # this report answers.
    'sap_asset_number',
    'sap_posting_state',
    'sap_reconciliation_state',
)

# NOT RECOVERABLE — named, and deliberately NOT published, because publishing
# a today's-value figure under a heading an auditor reads as historical is the
# specific harm. Two of these are topics rather than fields.
SNAPSHOT_NOT_RECOVERABLE = (
    # An asset deleted since `as_of` cannot be reconstructed from anything —
    # its tracking rows go with its messages and its custody links block the
    # delete but name an asset that is gone. So the snapshot is a LOWER BOUND
    # on the register's size, and an auditor reconciling a count must know it.
    'deleted_assets',
    # PRD §8.14's fourth element: which API call, which user or system made a
    # change. Cadra records the actor on a custody link and on a chatter
    # message and nowhere else; there is no `cadra.audit.log`.
    'change_source',
    # Stored money columns. `value` below is the point-in-time answer for the
    # two that have one; these four have no history and no engine.
    'current_value',
    'replacement_cost',
    'accumulated_depreciation',
    'current_book_value',
    # Verification: the date is tracked and rolled back, its evidence is not.
    'is_verified',
    # `last_verified_by` was here until handoff 28 tracked it; it is now in
    # `SNAPSHOT_TRACKED_FROM`.
    'verification_notes',
    # Retrieval: the flag is tracked, the circumstances are not.
    'assignment_date',
    'retrieval_reason',
    'retrieval_date',
    'maintenance_vendor_id',
    'notes',
    # SAP's own figures, as reported by SAP. Untracked and overwritten in
    # place on every sync, so only the latest sync survives.
    'sap_asset_subnumber',
    'sap_company_code',
    'sap_asset_class',
    'sap_capitalisation_date',
    'sap_capitalised_amount',
    'sap_net_book_value',
    'sap_accumulated_depreciation',
    'sap_synced_at',
    'sap_code_source',
)

#: One sentence per field or topic that needs one. Published in the response.
SNAPSHOT_NOTES = {
    'cutoff': SNAPSHOT_CUTOFF_DESCRIPTION,
    'rolled_back': (
        "Answered as of the requested date, from the chain of custody and "
        "the chatter tracking values. A field with no recorded change since "
        "the date correctly reports its current value: no change means the "
        "current value IS the value at the date."
    ),
    'tracked_from': (
        "These fields have been tracked only since the instant given in "
        "`tracked_from.since`. For a requested date at or after it they are "
        "rolled back like any other tracked field. For an earlier date they "
        "are listed under `as_of_today` instead and published at today's "
        "value: a change made before tracking began left no record, so "
        "Cadra cannot say what the value was on the date."
    ),
    'as_of_today': (
        "Published at its CURRENT value. These fields carry no history at "
        "all, so the figure shown may have been different on the requested "
        "date and Cadra cannot tell you whether it was."
    ),
    'not_recoverable': (
        "Neither rolled back nor published. Cadra holds no history for these "
        "and showing today's figure beside historical ones would invite a "
        "reconciliation that cannot be right."
    ),
    'tracking': (
        "Outside the chain of custody, the history is Odoo's chatter "
        "tracking values, which hang off mail messages and can be deleted by "
        "anyone able to delete a message. Where a tenant's register was "
        "seeded by direct SQL no tracking rows were produced at all, so its "
        "rolled-back fields will report today's values throughout."
    ),
    'deleted_assets': (
        "An asset deleted since the requested date cannot be reconstructed. "
        "The snapshot is therefore a LOWER BOUND on how many assets the "
        "register held on that date."
    ),
    'custodian_id': (
        "Resolved from the append-only chain of custody where the chain "
        "reaches back to the date, and from the chatter tracking values "
        "otherwise. Where a row lists `custodian_id` in its `_fidelity."
        "unknown`, the chain and the tracking values are BOTH silent for "
        "that asset: the custodian shown is the custodian today, and there "
        "is no evidence of who held it on the requested date. The chain "
        "begins on 9 September 2026 and its backfilled portion begins where "
        "`custodian_id` became a tracked field, not where the register does."
    ),
    'value': (
        "Computed at the requested date by the depreciation engine, which is "
        "a pure function of the date and persists nothing — so it has no "
        "gaps. But only `depreciation_method` is tracked: the cost basis, "
        "useful life, salvage rate and start date it is computed FROM are "
        "read as they stand today. Where a row's depreciation method changed "
        "after the requested date, `value` is listed in that row's "
        "`_fidelity.as_of_today`. An `erp_managed` asset has no value "
        "history in Cadra at all and lists `value` in `_fidelity.unknown`."
    ),
    'tag_label_state': (
        "The `printed` state was not being recorded before 8 September 2026 "
        "(two defects, both fixed that day), so a snapshot before that date "
        "under-reports printing. `affixed` is trustworthy throughout. "
        "`is_tagged` at the date is `tag_label_state == 'affixed'`."
    ),
    'active_tag_number': (
        "The number of the ACTIVE tag, which excludes a tag pending "
        "replacement. Requesting a replacement does not peel the label off "
        "the asset, so this can read empty while a physical label is on it."
    ),
    'depreciation_method': (
        "Most of the tracking rows on this field across the estate were "
        "written by a module-install backfill at a single timestamp rather "
        "than by policy decisions. A large row count here is not evidence of "
        "a policy that moved."
    ),
    'domain': (
        "Related to the category's FM domain and stored, with its own "
        "tracking rows. It is rolled back from those rows — what the stored "
        "column said — not re-derived from the rolled-back category."
    ),
}


# Reaches the field through `ir_model_fields` because Odoo 19 has no
# `field` char column on `mail_tracking_value`, and the message through
# `mail_message` because that is where the timestamp and the record live.
# `field_id` is nullable (`ondelete='set null'` for a removed field), so
# the inner join is also the filter that drops rows nothing can decode.
#
# Ordered NEWEST first and folded into a dict: the last row written for a
# given (asset, field) is therefore the EARLIEST change at or after the
# cutoff, whose OLD value is by definition the value at the cutoff.
# `m.id` breaks ties inside one transaction, where hundreds share a second.
_SNAPSHOT_TRACKING_SQL = """
    SELECT m.res_id            AS asset_id,
           f.name              AS field_name,
           m.date              AS changed_at,
           mtv.old_value_integer,
           mtv.old_value_float,
           mtv.old_value_char,
           mtv.old_value_text,
           mtv.old_value_datetime
      FROM mail_tracking_value mtv
      JOIN ir_model_fields f ON f.id = mtv.field_id
      JOIN mail_message m ON m.id = mtv.mail_message_id
     WHERE f.model = 'nrs.asset'
       AND m.model = 'nrs.asset'
       AND f.name = ANY(%s)
       AND m.res_id = ANY(%s)
     ORDER BY m.date DESC, m.id DESC
"""


class NRSAssetSnapshot(models.Model):
    """Read-only point-in-time reconstruction of `nrs.asset`.

    Public surface, in the order a caller uses it:

        snapshot_fidelity()               what this report can and cannot say
        snapshot_existence_domain(as_of)  which assets existed on the date
        recordset.snapshot_at(as_of)      the rows themselves
    """

    _inherit = 'nrs.asset'

    # ── What the report can and cannot answer ────────────────────────

    @api.model
    def _snapshot_not_yet_tracked(self, cutoff):
        """The `SNAPSHOT_TRACKED_FROM` fields that were NOT yet tracked at
        `cutoff`, and so cannot be rolled back to it. Empty when there is no
        stamp, no cutoff, or the cutoff is inside the tracked period."""
        tracked_from = self._snapshot_tracked_from()
        if not (tracked_from and cutoff and cutoff < tracked_from):
            return []
        return [f for f in SNAPSHOT_TRACKED_FROM if f in self._fields]

    @api.model
    def snapshot_fidelity(self, as_of=None):
        """The boundary, stated before any row is read. Same for every row.

        The three lists are filtered to fields this tenant actually has: a
        field belonging to a module that is not installed is not a degraded
        answer, it is an absent column, and saying "as of the date" about a
        field that does not exist would be its own small lie. Anything
        filtered out is named in `notes['uninstalled']`.
        """
        # `as_of` is optional so that a caller asking only "what can this
        # report say" still gets an answer; with it, the two lists below are
        # the ones that apply to THAT date — see `SNAPSHOT_TRACKED_FROM`.
        late = self._snapshot_not_yet_tracked(
            snapshot_cutoff(as_of) if as_of else None)
        rolled = [f for f in SNAPSHOT_ROLLED_BACK
                  if f in self._fields and f not in late]
        today = [f for f in SNAPSHOT_AS_OF_TODAY if f in self._fields] + late
        # Topics have no field to check; field names are checked.
        not_recoverable = [
            f for f in SNAPSHOT_NOT_RECOVERABLE
            if f in ('deleted_assets', 'change_source') or f in self._fields
        ]

        notes = dict(SNAPSHOT_NOTES)
        missing = [
            f for f in SNAPSHOT_ROLLED_BACK + SNAPSHOT_AS_OF_TODAY
            if f not in self._fields
        ]
        if missing:
            notes['uninstalled'] = (
                "Not present on this deployment because the module that "
                "declares it is not installed: %s." % ", ".join(missing)
            )
        if not self._snapshot_has_depreciation():
            notes['value'] = (
                "The depreciation module is not installed on this "
                "deployment, so no point-in-time value can be computed and "
                "every row lists `value` in its `_fidelity.unknown`."
            )
        tracked_from = self._snapshot_tracked_from()
        return {
            'rolled_back': rolled,
            'as_of_today': today,
            'not_recoverable': not_recoverable,
            # ADDITIVE (handoff 28). The subset of `rolled_back` whose history
            # begins on a known instant, and that instant — null where these
            # fields have been tracked since this database's first asset.
            'tracked_from': {
                'fields': [f for f in SNAPSHOT_TRACKED_FROM
                           if f in self._fields],
                'since': tracked_from.isoformat() if tracked_from else None,
            },
            'notes': notes,
        }

    # ── Existence ────────────────────────────────────────────────────

    @api.model
    def snapshot_existence_domain(self, as_of):
        """Domain selecting the assets that existed on `as_of`.

        `create_date` is written by Postgres as `now() at time zone 'UTC'`, so
        it is in the same naive-UTC space as the cutoff and comparable without
        conversion.

        This is a one-sided test and cannot be otherwise: an asset created
        before the date and deleted since leaves nothing behind to select.
        That is `deleted_assets` in `not_recoverable`, and it is why the
        snapshot is a lower bound rather than a count.
        """
        cutoff = fields.Datetime.to_string(snapshot_cutoff(as_of))
        return [('create_date', '<', cutoff)]

    # ── The rows ─────────────────────────────────────────────────────

    def snapshot_at(self, as_of):
        """`{asset_id: row_dict}` for the assets in `self` that existed on
        `as_of`. Reads only — this method must never write.

        An asset in `self` whose `create_date` is at or after the cutoff is
        omitted, not returned empty: it was not on the register that day, and
        a row for it would be a fabrication. Callers should filter with
        `snapshot_existence_domain()` so their page and their count agree.

        Each row carries:

          `id`
          every installed field in `SNAPSHOT_ROLLED_BACK`, as of the date
          every installed field in `SNAPSHOT_AS_OF_TODAY`, as of today
          `value`      {'accumulated_depreciation', 'book_value', 'state'}
          `_fidelity`  {'as_of_today': [...], 'unknown': [...]} — present ONLY
                       when non-empty, and naming fields degraded for THIS row
          `_changed_since` [...] — present ONLY when non-empty, naming the
                       rolled-back fields whose value on the date differs from
                       today's. This is what stops "tracked but never changed"
                       and "not tracked at all" from producing byte-identical
                       rows with no way to tell them apart.

        Many2one values are `{'id': .., 'name': ..}` or `None`, and where the
        value was rolled back the NAME is the one recorded in the tracking row
        rather than the record's name today — the record may have been renamed
        or deleted since, and the snapshot should read as it read.

        Dates and datetimes are ISO strings (`v.isoformat()`), matching the
        API's own serialiser, so a row is JSON-safe as it stands.
        """
        as_of = fields.Date.to_date(as_of)
        cutoff = snapshot_cutoff(as_of)

        existed = self.filtered(
            lambda r: r.create_date and r.create_date < cutoff)
        if not existed:
            return {}

        # A field tracked only from a known instant is rolled back for a date
        # inside its history and published at today's value for one before
        # it — the same two lists `snapshot_fidelity(as_of)` publishes.
        late = self._snapshot_not_yet_tracked(cutoff)
        rolled_fields = [f for f in SNAPSHOT_ROLLED_BACK
                         if f in self._fields and f not in late]
        today_fields = [f for f in SNAPSHOT_AS_OF_TODAY
                        if f in self._fields] + late

        # Three bulk reads for the whole page, never one per asset. `nrs19`
        # holds 11,878 assets and 24,959 tracking rows; per-asset queries turn
        # a 100-row page into 300 round trips.
        changes, tracked_at_all = self._snapshot_tracking(
            existed.ids, rolled_fields, cutoff)
        custody = self._snapshot_custody(existed.ids, cutoff)
        selection_keys = self._snapshot_selection_keys(rolled_fields)

        has_depreciation = self._snapshot_has_depreciation()

        rows = {}
        for rec in existed:
            degraded_today = []
            unknown = []
            changed = []
            row = {'id': rec.id}

            for fname in rolled_fields:
                current = self._snapshot_current_value(rec, fname)
                raw = changes.get(rec.id, {}).get(fname)
                if raw is None:
                    value = current
                else:
                    value, unmapped = self._snapshot_decode(
                        fname, raw, selection_keys)
                    if unmapped:
                        # Publish what the tracking row actually says and flag
                        # it. Guessing a key from an unrecognised label would
                        # put a value into an enum an integrator branches on.
                        unknown.append(fname)
                row[fname] = value
                if not self._snapshot_same(fname, value, current):
                    changed.append(fname)

            # Custody overrides the tracking answer wherever the chain speaks,
            # because the chain cannot be deleted and the tracking rows can.
            if 'custodian_id' in rolled_fields:
                resolved, evidenced = custody.get(rec.id, (None, False))
                if evidenced:
                    row['custodian_id'] = resolved
                    moved = not self._snapshot_same(
                        'custodian_id', resolved,
                        self._snapshot_current_value(rec, 'custodian_id'))
                    if moved and 'custodian_id' not in changed:
                        changed.append('custodian_id')
                    elif not moved and 'custodian_id' in changed:
                        changed.remove('custodian_id')
                elif not changes.get(rec.id, {}).get('custodian_id') \
                        and not tracked_at_all.get(rec.id, {}).get(
                            'custodian_id') \
                        and rec.custodian_id:
                    # No chain, no tracking row of ANY date, and somebody
                    # holds it today. We are showing today's custodian and we
                    # have no evidence they held it on the date. Saying so is
                    # the whole point of `_fidelity`.
                    unknown.append('custodian_id')

            for fname in today_fields:
                row[fname] = self._snapshot_current_value(rec, fname)

            value_block, value_state = self._snapshot_value(
                rec, as_of, has_depreciation)
            row['value'] = value_block
            if value_state == 'unknown':
                unknown.append('value')
            elif 'depreciation_method' in rolled_fields and \
                    row.get('depreciation_method') != rec.depreciation_method:
                # The method on the date is not the method the figures were
                # computed under. The value is real; it is just not the value
                # that policy would have produced. Say which.
                degraded_today.append('value')

            fidelity = {}
            if degraded_today:
                fidelity['as_of_today'] = degraded_today
            if unknown:
                fidelity['unknown'] = unknown
            if fidelity:
                row['_fidelity'] = fidelity
            if changed:
                row['_changed_since'] = changed

            rows[rec.id] = row
        return rows

    @api.model
    def _snapshot_tracked_from(self):
        """When the `SNAPSHOT_TRACKED_FROM` fields began to be tracked HERE.

        Read from the database, not from a constant: a client's own server is
        upgraded on its own day, and a date typed into the source would claim
        a history on every deployment made after it. None means no stamp,
        which means tracked from the first asset.
        """
        raw = self.env['ir.config_parameter'].sudo().get_param(
            SNAPSHOT_TRACKED_FROM_PARAM)
        return fields.Datetime.to_datetime(raw) if raw else None

    # ── Tracking values ──────────────────────────────────────────────

    @api.model
    def _snapshot_tracking(self, asset_ids, field_names, cutoff):
        """One query for the whole page.

        Returns `(changes, tracked_at_all)`:

          `changes[asset_id][field]`        the earliest tracking row at or
                                            after the cutoff, or absent
          `tracked_at_all[asset_id][field]` True if ANY tracking row exists for
                                            that pair, whatever its date

        The second is not redundant. Without it, "this field is tracked and
        has never changed" and "this asset predates tracking entirely" produce
        the identical output — today's value — and an auditor cannot tell a
        stable field from an unrecorded one. It is what lets `custodian_id`
        say `unknown` on a tenant whose register was seeded by direct SQL,
        rather than presenting today's custodian as a historical fact.
        """
        changes = {}
        tracked_at_all = {}
        if not asset_ids or not field_names:
            return changes, tracked_at_all

        self.env.cr.execute(
            _SNAPSHOT_TRACKING_SQL, (list(field_names), list(asset_ids)))
        for row in self.env.cr.dictfetchall():
            aid = row['asset_id']
            fname = row['field_name']
            tracked_at_all.setdefault(aid, {})[fname] = True
            if row['changed_at'] and row['changed_at'] >= cutoff:
                # Newest-first, so a later assignment is an earlier change.
                changes.setdefault(aid, {})[fname] = row
        return changes, tracked_at_all

    @api.model
    def _snapshot_decode(self, fname, raw, selection_keys):
        """Decode one tracking row's OLD value. -> `(value, unmapped)`.

        The typed columns are not interchangeable and Odoo picks between them
        by field type at write time (`mail.tracking.value._create_tracking_
        values`): m2o and boolean and integer go to `_integer`, float and
        MONETARY to `_float`, selection and char and the m2o display name to
        `_char`, text to `_text`, datetime to `_datetime` — and **date to
        `_datetime` at midnight**, which is the one that surprises people,
        because there is no `old_value_date` column at all.
        """
        ftype = self._fields[fname].type

        if ftype == 'many2one':
            rec_id = raw['old_value_integer'] or None
            name = raw['old_value_char'] or None
            if not rec_id and not name:
                # Odoo writes (0, '') for an empty m2o — genuinely empty, not
                # missing.
                return None, False
            return {'id': rec_id, 'name': name}, False

        if ftype == 'selection':
            label = raw['old_value_char'] or ''
            if not label:
                return None, False
            key = selection_keys.get(fname, {}).get(label)
            if key is None:
                # The char column holds the TRANSLATED label, so a row written
                # under a language this deployment no longer carries, or an
                # option since removed from the selection, cannot be mapped.
                # Publish the label and mark the row degraded rather than
                # inventing a key an integrator would branch on.
                return label, True
            return key, False

        if ftype == 'boolean':
            return bool(raw['old_value_integer']), False
        if ftype == 'integer':
            return raw['old_value_integer'] or 0, False
        if ftype in ('float', 'monetary'):
            return raw['old_value_float'] or 0.0, False
        if ftype == 'text':
            return raw['old_value_text'] or None, False
        if ftype == 'date':
            stamp = raw['old_value_datetime']
            return (stamp.date().isoformat() if stamp else None), False
        if ftype == 'datetime':
            stamp = raw['old_value_datetime']
            return (stamp.isoformat() if stamp else None), False
        # char, and anything else Odoo stored as char.
        return raw['old_value_char'] or None, False

    @api.model
    def _snapshot_current_value(self, rec, fname):
        """Today's value, in the same published shape as a rolled-back one.

        The two paths MUST agree on shape, or a field that happens not to have
        moved comes back looking different from the same field on the next
        row, and a consumer writes two branches for one column.
        """
        field = self._fields[fname]
        value = rec[fname]
        if field.type == 'many2one':
            return {'id': value.id, 'name': value.display_name} if value \
                else None
        if field.type in ('date', 'datetime'):
            return value.isoformat() if value else None
        if field.type == 'selection':
            return value or None
        if field.type in ('char', 'text', 'html'):
            return value or None
        if field.type in ('float', 'monetary'):
            return value or 0.0
        return value

    @api.model
    def _snapshot_same(self, fname, a, b):
        """Did this field move between the date and today?

        Many2ones are compared by ID and never by the published dict. The
        rolled-back side carries the name AS RECORDED and the current side
        carries the name today, so a record that was merely RENAMED would
        otherwise be reported as a change of location, or of custodian —
        which is exactly the finding an auditor would chase first and exactly
        the one that is not there.
        """
        if self._fields[fname].type == 'many2one':
            return (a or {}).get('id') == (b or {}).get('id')
        return a == b

    @api.model
    def _snapshot_selection_keys(self, field_names):
        """`{field: {label_or_key: technical_key}}`.

        Built with `fields_get` and NOT `dict(field.selection)`: two of these
        fields (`domain`, `tag_label_state`) are RELATED selections, where
        `.selection` is a callable and `dict()` over it raises `TypeError` —
        the defect that 500'd `/barcode/lookup` for every asset it found in
        handoff 05.

        The current language and `en_US` are both loaded, because the char
        column holds whatever label the acting user's language produced and
        the tenant may since have changed language. Each technical key also
        maps to itself: Odoo's own writer falls back to the raw key when a
        value is not in the selection, so a key can legitimately appear in the
        label column.
        """
        keys = {}
        selection_fields = [
            f for f in field_names if self._fields[f].type == 'selection']
        if not selection_fields:
            return keys
        sources = [
            self.with_context(lang='en_US').fields_get(
                selection_fields, ['selection']),
            self.fields_get(selection_fields, ['selection']),
        ]
        for fname in selection_fields:
            mapping = {}
            for source in sources:
                options = source.get(fname, {}).get('selection') or []
                for key, label in options:
                    mapping[key] = key
                    if label:
                        mapping[label] = key
            keys[fname] = mapping
        return keys

    # ── Custody ──────────────────────────────────────────────────────

    @api.model
    def _snapshot_custody(self, asset_ids, cutoff):
        """`{asset_id: (value_or_None, evidenced)}` — who held it then.

        The chain beats the tracking values for one reason and it is decisive:
        `nrs.asset.custody` refuses `write` and `unlink` on the model itself,
        so a link cannot be removed by anybody, including an administrator
        under `sudo()`. A `mail.tracking.value` row disappears with its
        message, and anybody who can delete a message can delete it.

        `evidenced` is False when the chain holds nothing for that asset. The
        caller then falls back to the tracking values, and says `unknown` if
        those are silent too.

        One query for the page, ordered so the chain reads forwards.
        """
        resolved = {}
        if not asset_ids:
            return resolved

        # `sudo()` on a read, matching every other route in this API. The
        # model refuses writes unconditionally, so sudo cannot widen anything
        # here beyond visibility.
        links = self.env['nrs.asset.custody'].sudo().search(
            [('asset_id', 'in', list(asset_ids))], order='changed_at, id')

        by_asset = {}
        for link in links:
            by_asset.setdefault(link.asset_id.id, []).append(link)

        for aid, chain in by_asset.items():
            after = [link for link in chain
                     if link.changed_at and link.changed_at >= cutoff]
            if after:
                # The earliest link recorded after the cutoff carries, in its
                # FROM side, exactly who held the asset immediately before it.
                first = after[0]
                resolved[aid] = (
                    self._snapshot_custodian_value(
                        first.from_custodian_id, first.from_custodian_name),
                    True,
                )
                continue
            # Every link predates the cutoff: the last one is still standing.
            last = chain[-1]
            resolved[aid] = (
                self._snapshot_custodian_value(
                    last.to_custodian_id, last.to_custodian_name),
                True,
            )
        return resolved

    @api.model
    def _snapshot_custodian_value(self, employee, recorded_name):
        """The name AS RECORDED wins over the employee's name today.

        A custody link snapshots both names precisely because an `hr.employee`
        can be renamed or deleted and the m2o then goes null. The link
        degrades; the evidence does not — and a snapshot's job is to read as
        it read.
        """
        if not employee and not recorded_name:
            return None
        return {
            'id': employee.id if employee else None,
            'name': recorded_name or (employee.name if employee else None),
        }

    # ── Value ────────────────────────────────────────────────────────

    @api.model
    def _snapshot_has_depreciation(self):
        """Whether `myservice_asset_depreciation` is installed here."""
        return 'depreciation_method' in self._fields and hasattr(
            self, '_depreciation_policy')

    @api.model
    def _snapshot_value(self, rec, as_of, has_depreciation):
        """`({accumulated_depreciation, book_value, state}, status)`.

        `_depreciation_policy()` and NOT `_apply_depreciation()`: the first
        gathers kwargs, the second writes the figures onto the record, and
        this report writes nothing.

        `value_at` is a pure function of `as_of` — it rebuilds the schedule
        from the start date and reads off the last elapsed period, persisting
        no period rows. That is why depreciation is the one thing INT-10 §2.5
        could already answer at a date: missing twelve monthly runs and
        missing one produce identical output, so it has no gaps to have.
        """
        empty = {
            'accumulated_depreciation': None,
            'book_value': None,
            'state': None,
        }
        if not has_depreciation:
            return empty, 'unknown'
        try:
            from odoo.addons.myservice_asset_depreciation.models import (
                depreciation_engine as engine,
            )
        except ImportError:
            return empty, 'unknown'

        accumulated, book_value, state = engine.value_at(
            as_of, **rec._depreciation_policy())
        if accumulated is None and book_value is None:
            # `erp_managed`: an external system owns the figures and Cadra
            # has never held a value history for this asset. Not a zero.
            return {
                'accumulated_depreciation': None,
                'book_value': None,
                'state': state,
            }, 'unknown'
        return {
            'accumulated_depreciation': accumulated,
            'book_value': book_value,
            'state': state,
        }, 'ok'
