"""What has happened to this asset — one ordered history, and what it cannot say.

NRS were walked through an asset's life and then opened *Audit & Review*
expecting to see it. The screen had never asked for it. This module is the
answer to that question, built server-side for the three reasons handoff 27
gives, the third of which decides it: INT-10's external auditor asks the same
question NRS asked in that room and must get the same answer from the API
rather than only from the React app.

**It is a merge and an ordering, not a new record.** Nothing here writes. It
reads the seven places an asset's life leaves a mark and puts them on one
clock. What it adds is the thing none of those places says about itself: HOW
MUCH EACH RECORD IS WORTH. Measured in handoff 27 §A, and it is not a detail:

- a change of custodian is the ONLY event with a record nobody can alter
  (`nrs.asset.custody`, append-only on the model);
- a location move has a row only when `POST /assets/<id>/move` or a completed
  transfer made it, and that row is editable and deletable by any asset
  manager and cascades away with the asset. Every other writer of
  `location_id` — PATCH, the Odoo form, an import — leaves chatter and
  nothing else;
- status, condition, verification and the disposal paperwork exist ONLY as
  chatter tracking values, deletable by anyone who can edit the asset;
- a change to a cost, a SAP column or a GRN/PO reference leaves nothing.

So every event carries `evidence`, and `fidelity.not_recorded` names what no
query against this database can produce. A list that showed a deletable
chatter row and an append-only custody link as the same kind of line would
imply more than the record supports, which is the one thing the handoff
forbids in four different places.

Lives in `myservice_api`, not `myservice_asset_register`, for the reason
`asset_custody.py` next door sets out: it reads `workflow.dispatch.log` and
`request.request`, which the lower module does not depend on.
"""
from datetime import datetime, time, timedelta

from odoo import api, fields, models

# ─── how much a record is worth ──────────────────────────────────────
#
# Published with every response (`fidelity.evidence_grades`) so the grade on
# an event is never a bare word a reader has to look up. Ordered strongest
# first. The sentences are deliberately about what somebody can DO to the
# record, because that is the auditor's question; "durable" is a word that
# means whatever the reader hopes it means.
EVIDENCE_GRADES = (
    ("append_only",
     "Recorded when it happened, and the application refuses to edit or "
     "delete it for anyone, an administrator included. The refusal is in the "
     "application, not the database: somebody with direct database access is "
     "not stopped by it."),
    ("system_stamp",
     "Stamped by the database layer when the row was created and not "
     "editable through the application. It exists only as long as the row "
     "does: deleting the asset deletes it."),
    ("guarded_record",
     "Written by the application from the acting user, and refused to an "
     "ordinary edit. A privileged user who sets the right internal flag can "
     "still rewrite it, and nothing records that they did; and where it "
     "sits on a tag label, an asset manager can delete the label."),
    ("editable_record",
     "An ordinary record. Anyone holding the asset-manager group can edit "
     "or delete it afterwards, and no trace of the edit is kept."),
    ("chatter",
     "A change noted in the record's message log and nowhere else. Anyone "
     "who can edit the asset can delete the message, and the change "
     "disappears with it without leaving a gap anyone could see."),
)

# ─── what no query here can produce ──────────────────────────────────
#
# Each of these was looked for in handoff 27 §A and not found. Named in every
# response, populated or not, because a consumer cannot tell "this never
# happened" from "this is never written down" unless somebody says which.
NOT_RECORDED = (
    ("financial_change",
     "A change to a cost or a value — acquisition cost, purchase value, "
     "replacement cost, book value, accumulated depreciation. The figure is "
     "overwritten in place; nothing records that it changed, when, or who "
     "changed it."),
    ("sap_change",
     "A change to the SAP asset number or any other SAP field. Each sync "
     "overwrites the last, so only the most recent survives, and it carries "
     "a time but no person."),
    ("provenance_change",
     "A change to the GRN, purchase order, vendor or import reference. "
     "These can be rewritten over the API and no record is kept of the old "
     "value."),
    ("disposal_executor",
     "Who carried out a disposal. The approval records its approver; the "
     "act of disposing records a date and no person. A status change in "
     "this history names whoever saved the record, which is not the same "
     "claim."),
    ("maintenance_performed",
     "A planned maintenance visit being carried out. The schedule keeps one "
     "overwritten last-done date, with no person and no row per visit."),
    ("deleted_records",
     "Anything whose record has since been deleted. Only a change of "
     "custodian is protected from deletion; every other record here can be "
     "removed without trace, so this history is a lower bound on what "
     "happened, never a complete account of it."),
)

_EVENT_TITLES = {
    "registered": "Registered",
    "tag_issued": "Tag issued",
    "tag_printed": "Tag printed",
    "tag_affixed": "Tag affixed",
    "tag_scrapped": "Tag scrapped",
    "custody_changed": "Custodian changed",
    "location_moved": "Location moved",
    "transfer_recorded": "Transfer recorded",
    "status_changed": "Status changed",
    "condition_changed": "Condition changed",
    "verified": "Verified",
    "disposal_approved": "Disposal approved",
    "disposal_recorded": "Disposal details recorded",
    "details_changed": "Details changed",
    "integration_event": "Event for an external system",
    "maintenance_request": "Maintenance request raised",
}
EVENT_TYPES = tuple(_EVENT_TITLES)

# Tracked fields that have a BETTER record than their chatter row, and are
# therefore read from that record and dropped from the chatter stream — an
# event listed twice would read as two events.
#
# `custodian_id`: the custody chain, which was itself backfilled from these
# very rows (migration 19.0.1.12.0), so the chain is a superset of them.
# The tag fields: the label row's own print and affix stamps.
# `location_id` is NOT here — it is handled by the matcher below, because
# most location changes have no better record at all.
_CHATTER_SUPERSEDED = frozenset({
    "custodian_id",
    "tag_label_state", "active_tag_number", "asset_tag",
})

# The disposal approval's two columns. NOT in the set above, and the first
# draft of this module put them there, called them "guarded" and graded the
# approval `guarded_record`. They are neither: no `write` refuses them and
# both are inputs on the Odoo form. They are absent from the API's
# `_WRITABLE_FIELDS`, which is a fact about one door. So an asset manager
# could rewrite the approver, and the history would have shown the new name,
# graded as protected, having DROPPED the tracking row that was the only
# sign of the edit — the exact overclaim this module exists to prevent,
# caught by the verification pass. Now: the columns are one `editable_record`
# event, the row of the FIRST stamping (empty → a name) is dropped as the
# same fact twice, and every later rewrite is listed.
_DISPOSAL_APPROVAL_FIELDS = frozenset({
    "disposal_approved_by", "disposal_approved_date",
})

# Which event a tracked field's change is. Anything unlisted is
# `details_changed`, so a field that becomes tracked tomorrow appears in the
# history on the same day rather than being silently absent from it.
_CHATTER_EVENT_OF_FIELD = {
    "state": "status_changed",
    "condition": "condition_changed",
    "last_verified_date": "verified",
    "disposal_method": "disposal_recorded",
    "disposal_reference": "disposal_recorded",
    "disposal_proceeds": "disposal_recorded",
    "disposal_date": "disposal_recorded",
    "disposal_date_reconstructed": "disposal_recorded",
    "disposal_reason": "disposal_recorded",
    # A REWRITE of the approval — the first stamping is dropped, see
    # `_DISPOSAL_APPROVAL_FIELDS`. Not `disposal_approved`: changing who is
    # recorded as having approved is not an approval.
    "disposal_approved_by": "disposal_recorded",
    "disposal_approved_date": "disposal_recorded",
}

# How far apart a transfer row and the chatter row of the location write it
# caused may be and still be the same act. `/move` creates the row and writes
# the location in one transaction, and `action_complete` writes the location
# and then the row's state; both land within a second. Two minutes is slack
# for a slow worker, not a claim about anything.
_TRANSFER_MATCH_WINDOW = timedelta(seconds=120)

# Tie-break within one second, ascending. For the first two it is the only
# order they can have happened in: a registration precedes the tag minted
# with the asset, and both precede the custody link written by the same
# `create`. Below that the sources cannot say, and this is a fixed,
# documented placement rather than a claim.
_RANK = {name: i for i, name in enumerate(EVENT_TYPES)}


def _iso(value):
    return value.isoformat() if value else None


def _when(value):
    """An instant as a person reads it. The statements are shown on screen."""
    return value.strftime("%Y-%m-%d %H:%M UTC") if value else None


def _shown(value):
    """A tracked value in a sentence. ONLY a missing value is a dash.

    `value or "—"` printed a dash for a tracked `False` and for a `0`, which
    are values: a box unticked and a figure set to nothing are both things
    that happened, and `detail.changes` said so while the summary beside it
    said there was nothing there.
    """
    if value is None or value == "":
        return "—"
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return value


def _user_ref(user):
    """`{id, name}` for a user that still exists, else None. Never a guess."""
    if not user:
        return None
    return {"id": user.id, "name": user.name}


class NRSAssetHistory(models.Model):
    _inherit = "nrs.asset"

    # ── the one public entry point ───────────────────────────────────

    def asset_history(self, newest_first=True):
        """Everything recorded about this asset, on one clock.

        Returns the dict the route publishes as `data`. An OBJECT, for the
        reason the access report and the register snapshot give: there is
        nowhere honest to put a boundary declaration on an array, and
        `summary.statement` and `fidelity` have to arrive with the events
        rather than beside them.

        NOT capped and NOT paged, for `CAP_EXEMPT_REASON_CUSTODY`'s reason —
        a history is complete or it is evidence of nothing, and a merged
        list over seven sources has no single id a cursor could walk.

        Read with sudo by the caller's choice, not here: the route has
        already decided the credential may read the asset.
        """
        self.ensure_one()
        events = []
        events += self._history_registered()
        events += self._history_tags()
        events += self._history_custody()
        location_rows, other_chatter = self._history_chatter()
        events += self._history_locations(location_rows)
        events += other_chatter
        events += self._history_disposal_approval()
        events += self._history_dispatches()
        events += self._history_requests()

        undated = sum(1 for e in events if e is None)
        events = [e for e in events if e is not None]
        events.sort(key=lambda e: e["_sort"], reverse=bool(newest_first))
        for e in events:
            del e["_sort"]

        return {
            "asset": {"id": self.id, "asset_code": self.asset_code,
                      "name": self.name},
            "order": "newest_first" if newest_first else "oldest_first",
            "summary": self._history_summary(events),
            "fidelity": dict(self._history_fidelity(events),
                             undated_records_omitted=undated),
            "events": events,
        }

    # ── the event shape ──────────────────────────────────────────────

    def _history_event(self, etype, at, record, evidence, *, summary,
                       actor=None, actor_name=None, precision="second",
                       source=None, reconstructed=False, detail=None):
        """One line of the history. Every key present on every event.

        `actor` is the user the RECORD names, or None. It is never filled
        from a neighbouring field that means something else — an event whose
        record holds no person says so by being blank. `actor_name` is the
        name as the record holds it, which outlives the user.

        `at` for a day-precision event is a bare date and sorts at the START
        of its day. That is a placement, not a claim, and `at_precision`
        says so on the event.
        """
        if not at:
            # `mail.message.date` is not required, and a row inserted by SQL
            # can lack `create_date`. One such row must not cost the asset
            # its whole history; it cannot be placed on a clock, so it is
            # left out and `fidelity.undated_records_omitted` says how many.
            return None
        if precision == "day":
            sort_at = datetime.combine(at, time.min)
            at_out = at.isoformat()
        else:
            # Sorted to the WHOLE SECOND, and that is not a rounding nicety.
            # `create_date` carries microseconds; a custody link's
            # `changed_at` and a message's `date` are whole seconds. Compared
            # raw, anything in the same second as the registration — the
            # custody link written by the very `create` that assigned the
            # asset, or an integration that registers and then acts — sorts
            # BEFORE it (`:44.000` < `:44.730`), and the history opens with
            # an asset changing hands before it existed. Found by looking at
            # the screen; no test had caught it. Inside one second the
            # sources cannot say what came first, so `_RANK` does, in the
            # only order those things can have happened in.
            sort_at = at.replace(microsecond=0)
            at_out = _iso(at)
        model, rec_id = record
        return {
            "id": "%s:%s:%s" % (etype, model, rec_id),
            "type": etype,
            "title": _EVENT_TITLES[etype],
            "summary": summary,
            "at": at_out,
            "at_precision": precision,
            "actor": actor,
            "actor_name": actor_name or (actor or {}).get("name"),
            "evidence": evidence,
            "reconstructed": bool(reconstructed),
            "source": source,
            "record": {"model": model, "id": rec_id},
            "detail": detail or {},
            "_sort": (sort_at, _RANK[etype], model, rec_id),
        }

    # ── the sources ──────────────────────────────────────────────────

    def _history_registered(self):
        # The provenance block is the asset's CURRENT values, not what was
        # sent at registration — all six are rewritable and untracked
        # (`NOT_RECORDED.provenance_change`). Said on the event, because a
        # GRN reference printed under "Registered" reads as what arrived.
        source = self.import_source or None
        via = dict(self._fields["import_source"]._description_selection(
            self.env)).get(source) if source else None
        return [self._history_event(
            "registered", self.create_date, ("nrs.asset", self.id),
            "system_stamp",
            summary=("Registered from %s" % via) if via else "Registered",
            actor=_user_ref(self.create_uid),
            detail={
                "asset_code": self.asset_code,
                "import_source": source,
                "grn_reference": self.grn_reference or None,
                "purchase_order_reference":
                    self.purchase_order_reference or None,
                "provenance_is_current_value": True,
            })]

    def _history_tags(self):
        events = []
        for tag in self.tag_ids:
            rec = ("nrs.asset.tag.label", tag.id)
            base = {"tag_number": tag.name}
            events.append(self._history_event(
                "tag_issued", tag.create_date, rec, "system_stamp",
                summary="Tag %s issued" % tag.name,
                actor=_user_ref(tag.create_uid), detail=base))
            if tag.printed_date:
                # The LAST print. A reprint overwrites the stamp, so an
                # earlier one is not recoverable from this row.
                events.append(self._history_event(
                    "tag_printed", tag.printed_date, rec, "guarded_record",
                    summary="Tag %s printed" % tag.name,
                    actor=_user_ref(tag.printed_by),
                    detail=dict(base, only_latest_print_is_kept=True)))
            if tag.affixed_date:
                # `affixed_by` is who RECORDED the confirmation — usually an
                # API client. Who physically fitted the label is free text
                # and is not a Cadra user, so it goes in `detail`, never in
                # `actor`.
                events.append(self._history_event(
                    "tag_affixed", tag.affixed_date, rec, "guarded_record",
                    summary="Tag %s affixed" % tag.name,
                    actor=_user_ref(tag.affixed_by),
                    detail=dict(base,
                                fitted_by_name=tag.affixed_by_name or None)))
            if tag.scrapped_date:
                # `action_approve_replacement` stamps an instant and an
                # approver in the same write as the scrap DATE. Where they
                # exist they are the better record, and using the bare date
                # would sort a same-day scrap at midnight — BEFORE the issue
                # of the tag it scrapped.
                timed = bool(tag.approved_date)
                events.append(self._history_event(
                    "tag_scrapped",
                    tag.approved_date if timed else tag.scrapped_date, rec,
                    "editable_record",
                    precision="second" if timed else "day",
                    summary="Tag %s scrapped" % tag.name,
                    actor=_user_ref(tag.approved_by) if timed else None,
                    detail=base))
        return events

    def _history_custody(self):
        events = []
        for link in self.custody_ids:
            before = link.from_custodian_name or "unassigned"
            after = link.to_custodian_name or "unassigned"
            events.append(self._history_event(
                "custody_changed", link.changed_at,
                ("nrs.asset.custody", link.id), "append_only",
                summary="%s → %s" % (before, after),
                actor=_user_ref(link.changed_by_id),
                actor_name=link.changed_by_name or None,
                source=link.source,
                # The serializer's own docstring: a reconstruction presented
                # as a contemporaneous record is worse than no record.
                reconstructed=link.source == "tracking_backfill",
                detail={
                    "from_custodian": (
                        {"id": link.from_custodian_id.id,
                         "name": link.from_custodian_id.name}
                        if link.from_custodian_id else None),
                    "to_custodian": (
                        {"id": link.to_custodian_id.id,
                         "name": link.to_custodian_id.name}
                        if link.to_custodian_id else None),
                    "from_custodian_name": link.from_custodian_name or None,
                    "to_custodian_name": link.to_custodian_name or None,
                    "reason": link.reason or None,
                }))
        return events

    def _history_chatter(self):
        """Tracked changes, split into location rows and everything else.

        Tracking VALUES only. A message body is free text somebody typed and
        is not published here — this route is `assets:read`, and a note on
        an asset was never promised to every holder of that scope.
        """
        messages = self.env["mail.message"].search([
            ("model", "=", "nrs.asset"), ("res_id", "=", self.id),
            ("tracking_value_ids", "!=", False),
        ])
        location_rows, events = [], []
        for msg in messages:
            actor, actor_name = self._history_message_actor(msg)
            grouped = {}
            for tv in msg.tracking_value_ids:
                field = self._history_tracked_field(tv)
                if field["name"] in _CHATTER_SUPERSEDED:
                    continue
                if field["name"] == "location_id":
                    location_rows.append({
                        "message": msg, "value": tv,
                        "actor": actor, "actor_name": actor_name})
                    continue
                change = self._history_change(tv, field)
                if (field["name"] in _DISPOSAL_APPROVAL_FIELDS
                        and change["old"] is None):
                    continue
                etype = _CHATTER_EVENT_OF_FIELD.get(
                    field["name"], "details_changed")
                grouped.setdefault(etype, []).append(change)
            for etype, changes in grouped.items():
                events.append(self._history_event(
                    etype, msg.date, ("mail.message", msg.id), "chatter",
                    summary="; ".join(
                        "%s: %s → %s" % (c["label"], _shown(c["old"]),
                                         _shown(c["new"])) for c in changes),
                    actor=actor, actor_name=actor_name,
                    detail={"changes": changes}))
        return location_rows, events

    def _history_message_actor(self, msg):
        """Who the MESSAGE says made the change.

        `author_id` is a partner. When it resolves to a user that user is the
        actor; when it does not — a partner with no login, or a message with
        no author — `actor` is None and only the recorded name, if there is
        one, is carried. `create_uid` is not consulted: the migration that
        built the custody chain from these rows documents why the author
        beats the database user, and a fallback would put a name on an event
        whose record does not hold one.
        """
        author = msg.author_id
        if not author:
            return None, None
        user = author.with_context(active_test=False).user_ids[:1]
        return _user_ref(user), author.name or None

    @api.model
    def _history_tracked_field(self, tv):
        if tv.field_id:
            return {"name": tv.field_id.name,
                    "label": tv.field_id.field_description,
                    "type": tv.field_id.ttype}
        # The field has been removed from the model since. Odoo keeps what it
        # was in `field_info`; the change still happened.
        info = tv.field_info or {}
        return {"name": info.get("name") or "unknown",
                "label": info.get("desc") or "Unknown field",
                "type": info.get("type") or "char"}

    @api.model
    def _history_change(self, tv, field):
        def value(prefix):
            ttype = field["type"]
            if ttype in ("integer",):
                return getattr(tv, prefix + "_value_integer")
            if ttype in ("float", "monetary"):
                return getattr(tv, prefix + "_value_float")
            if ttype == "boolean":
                return bool(getattr(tv, prefix + "_value_integer"))
            if ttype == "date":
                raw = getattr(tv, prefix + "_value_datetime")
                return raw.date().isoformat() if raw else None
            if ttype == "datetime":
                return _iso(getattr(tv, prefix + "_value_datetime"))
            if ttype == "text":
                return getattr(tv, prefix + "_value_text") or None
            # char, selection (stored as its label), many2one (its name)
            return getattr(tv, prefix + "_value_char") or None
        return {"field": field["name"], "label": field["label"],
                "old": value("old"), "new": value("new")}

    def _history_locations(self, location_rows):
        """Location moves: the transfer rows, the chatter rows, and the join.

        One physical move can leave two records — a transfer row and the
        chatter row of the `location_id` write it caused — and listing both
        would read as two moves. They are joined when they name the same
        from/to pair within `_TRANSFER_MATCH_WINDOW` of the row's creation or
        last write, each side used once, closest first. A failed join is two
        lines, never a wrong claim: nothing is dropped on the strength of it.

        A joined event takes its instant and its actor from the chatter row,
        which is the write itself, and its paperwork from the transfer. A
        transfer with no chatter row keeps the instant the ROW was created —
        a system stamp — rather than `transfer_date`, which is a day somebody
        typed; and it has NO actor, because `create_uid` is whoever raised
        the transfer and the record does not say who moved the asset.
        """
        events = []
        unmatched = list(location_rows)
        for t in self.transfer_ids.sorted("id"):
            row = None
            if t.state == "done":
                candidates = [
                    r for r in unmatched
                    if r["value"].old_value_integer == t.from_location_id.id
                    and r["value"].new_value_integer == t.to_location_id.id
                    and self._history_transfer_gap(t, r["message"].date)
                    <= _TRANSFER_MATCH_WINDOW]
                if candidates:
                    row = min(candidates, key=lambda r: (
                        self._history_transfer_gap(t, r["message"].date),
                        r["message"].id))
                    unmatched.remove(row)
            detail = {
                "from_location": t.from_location_id.display_name or None,
                "to_location": t.to_location_id.display_name or None,
                "transfer": {
                    "id": t.id, "reference": t.name, "state": t.state,
                    "transfer_date": _iso(t.transfer_date),
                    "reason": t.reason or None,
                    "recorded_by": _user_ref(t.create_uid),
                    "approved_by": _user_ref(t.approved_by),
                    "approved_at": _iso(t.approved_date),
                },
                "records": (["nrs.asset.transfer", "mail.message"]
                            if row else ["nrs.asset.transfer"]),
            }
            summary = "%s → %s" % (
                t.from_location_id.display_name or "—",
                t.to_location_id.display_name or "—")
            if t.state != "done":
                # Raised, approved or rejected, and the asset has not moved
                # on the strength of it. Its own event type so that nobody
                # reads a rejected transfer as a move.
                events.append(self._history_event(
                    "transfer_recorded", t.create_date,
                    ("nrs.asset.transfer", t.id), "editable_record",
                    summary="%s (%s)" % (summary, t.state), detail=detail))
                continue
            if not row:
                # The instant below is when the ROW was created. For `/move`
                # that is the move; for a transfer raised in Odoo and
                # completed later it is when it was RAISED. Said on the
                # event, because the list would otherwise place a move at a
                # moment the asset may not have moved.
                detail["at_is_when_the_transfer_was_recorded"] = True
                summary += " (time shown is when the transfer was recorded)"
            events.append(self._history_event(
                "location_moved",
                row["message"].date if row else t.create_date,
                ("nrs.asset.transfer", t.id), "editable_record",
                summary=summary,
                actor=row["actor"] if row else None,
                actor_name=row["actor_name"] if row else None,
                detail=detail))
        for r in unmatched:
            tv = r["value"]
            events.append(self._history_event(
                "location_moved", r["message"].date,
                ("mail.message", r["message"].id), "chatter",
                summary="%s → %s" % (tv.old_value_char or "—",
                                     tv.new_value_char or "—"),
                actor=r["actor"], actor_name=r["actor_name"],
                detail={
                    "from_location": tv.old_value_char or None,
                    "to_location": tv.new_value_char or None,
                    "transfer": None,
                    "records": ["mail.message"],
                }))
        return events

    @api.model
    def _history_transfer_gap(self, transfer, instant):
        return min(abs(instant - transfer.create_date),
                   abs(instant - transfer.write_date))

    def _history_disposal_approval(self):
        if not self.disposal_approved_date:
            return []
        return [self._history_event(
            "disposal_approved", self.disposal_approved_date,
            ("nrs.asset", self.id), "editable_record",
            summary="Disposal approved",
            actor=_user_ref(self.disposal_approved_by),
            # The approver and the instant are the columns as they stand
            # NOW. A rewrite since is listed as its own event.
            detail={"reference": self.disposal_reference or None,
                    "method": self.disposal_method or None,
                    "is_current_value": True})]

    def _history_dispatches(self):
        events = []
        logs = self.env["workflow.dispatch.log"].search(
            [("asset_id", "=", self.id)])
        for log in logs:
            events.append(self._history_event(
                "integration_event", log.create_date,
                ("workflow.dispatch.log", log.id), "guarded_record",
                summary="%s (%s)" % (log.event_type or log.name, log.status),
                actor=_user_ref(log.sent_by),
                detail={"reference": log.name,
                        "direction": log.direction or None,
                        "event_type": log.event_type or None,
                        "status": log.status,
                        "sent_at": _iso(log.sent_at)}))
        return events

    def _history_requests(self):
        events = []
        requests = self.env["request.request"].search(
            [("nrs_asset_id", "=", self.id)])
        for req in requests:
            # THAT a request was raised, when and by whom — not its
            # reference or its content. `request_count` already tells every
            # holder of `assets:read` that requests exist; the request
            # itself belongs to `requests:read`, which this caller may not
            # hold, and a route cannot see its caller's scopes today.
            events.append(self._history_event(
                "maintenance_request", req.create_date,
                ("request.request", req.id), "editable_record",
                summary="Maintenance request raised",
                actor=_user_ref(req.create_uid)))
        return events

    # ── what the list says about itself ──────────────────────────────

    def _history_is_registration(self, event):
        """The registration, or the tag minted in the same transaction.

        Every asset is given a tag by the `create()` that makes it, stamped
        with the same transaction instant. Counting that as something that
        happened AFTER registration would mean no asset ever had an empty
        history, and the sentence that says so could never be reached — on
        the one screen it was written for.
        """
        if event["type"] == "registered":
            return True
        return (event["type"] == "tag_issued"
                and event["at"] == _iso(self.create_date))

    def _history_summary(self, events):
        after = [e for e in events if not self._history_is_registration(e)]
        by_evidence = {grade: 0 for grade, _ in EVIDENCE_GRADES}
        for e in events:
            by_evidence[e["evidence"]] += 1
        registered = (fields.Date.to_string(self.create_date.date())
                      if self.create_date else "an unrecorded date")
        if not after:
            # The failure that produced handoff 27 was an empty panel. The
            # words are here, in the response, so that every consumer gets
            # them — not only a front end that remembered to write them.
            statement = (
                "There is no recorded history for this asset beyond its "
                "registration on %s. That means nothing was recorded, which "
                "is not the same as nothing having happened: some kinds of "
                "change are never written down at all, and they are listed "
                "with this history." % registered)
        else:
            # Counts the ONE grade nobody can alter. The first draft counted
            # `chatter + editable_record` as "can be edited or deleted", which
            # understated it: a tag label is deletable by an asset manager
            # too, and its events are neither of those grades.
            firm = sum(1 for e in after if e["evidence"] == "append_only")
            statement = (
                "%d recorded event(s) since registration on %s. %d of them "
                "rest on a record that nobody can edit or delete; the rest "
                "can be altered or removed afterwards, and each event says "
                "what its record is worth. This history is a lower bound on "
                "what happened, not a complete account of it."
                % (len(after), registered, firm))
        return {
            "events": len(events),
            "events_after_registration": len(after),
            "by_evidence": by_evidence,
            "reconstructed_events": sum(
                1 for e in events if e["reconstructed"]),
            "statement": statement,
        }

    def _history_fidelity(self, events):
        links = self.custody_ids.sorted(lambda c: (c.changed_at, c.id))
        first = links[:1]
        # When the recorder began on THIS TENANT. The backfilled rows were
        # created by the migration that introduced the model, so the oldest
        # `create_date` is that instant — measured, the way
        # `fidelity.record_starts_at` is on the access report, not declared.
        self.env.cr.execute("SELECT min(create_date) FROM nrs_asset_custody")
        began = self.env.cr.fetchone()[0]
        # A custodian the chain never saw arrive: the first link already has
        # a `from`, or there are no links and the asset is held by somebody.
        if first:
            unrecorded = bool(first.from_custodian_id
                              or first.from_custodian_name)
        else:
            unrecorded = bool(self.custodian_id)
        if not began:
            custody_statement = (
                "No change of custodian has ever been recorded on this "
                "system, for any asset.")
        elif unrecorded:
            custody_statement = (
                "This asset was already held by somebody when custody "
                "recording reached it, and how it came to be held is not "
                "recorded. Changes of custodian are recorded on this system "
                "from %s; earlier ones were reconstructed from the message "
                "log where it had them, and are marked as reconstructed."
                % _when(began))
        else:
            custody_statement = (
                "Changes of custodian are recorded on this system from %s. "
                "Any shown before that were reconstructed from the message "
                "log and are marked as reconstructed." % _when(began))
        dated = [e["at"] for e in events
                 if not self._history_is_registration(e)]
        return {
            "registered_at": _iso(self.create_date),
            "earliest_event_after_registration_at":
                min(dated) if dated else None,
            "custody": {
                "recording_began_at": _iso(began),
                "links": len(links),
                "reconstructed_links": len(links.filtered(
                    lambda c: c.source == "tracking_backfill")),
                "first_link_at": _iso(first.changed_at) if first else None,
                "custodian_held_before_first_link": unrecorded,
                "statement": custody_statement,
            },
            "evidence_grades": [
                {"grade": grade, "meaning": meaning}
                for grade, meaning in EVIDENCE_GRADES],
            "not_recorded": [
                {"event": event, "statement": text}
                for event, text in NOT_RECORDED],
            "verification": (
                "Each verification shown is a change to the last-verified "
                "date. The application's own Verify button sets that date "
                "and nothing else, so the event names whoever saved the "
                "date; no separate record says a physical check was made."),
        }
