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

- a change of custodian was the ONLY event with a record nobody can alter
  (`nrs.asset.custody`, append-only on the model);
- a location move had a row only when `POST /assets/<id>/move` or a completed
  transfer made it, and that row is editable and deletable by any asset
  manager and cascades away with the asset. Every other writer of
  `location_id` — PATCH, the Odoo form, an import — left chatter and
  nothing else. **Handoff 28 closed that going forward**: a move is now an
  append-only `nrs.asset.movement`. Every move made BEFORE it is still
  exactly as described, and is still graded as such;
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
     "A change to any SAP field other than the SAP asset number — each sync "
     "overwrites the last, so only the most recent survives, and it carries "
     "a time but no person — and a change to the SAP asset number itself "
     "made before such changes began to be recorded on this system. From "
     "then on a change to the number is listed here, with who made it, and "
     "cannot be altered. This history says, for each kind of event, the "
     "date from which it has been kept that way."),
    ("provenance_change",
     "A change to the GRN, purchase order, vendor or import reference made "
     "before those fields began to be tracked on this system: it left "
     "nothing. A later change to the vendor or an import field is listed "
     "here as a line in the message log, which can be deleted. A change to "
     "the GRN or purchase order reference is now recorded so that nobody "
     "can alter it; this history gives the date that began, and a change "
     "made between the two dates is a message-log line."),
    ("disposal_executor",
     "Who carried out a disposal made before changes of status began to be "
     "recorded on this system. For those, the approval records its approver "
     "and the act of disposing records a date and no person; a status "
     "change shown from the message log names whoever saved the record, "
     "which is not the same claim. From the date this history gives for "
     "changes of status, the change into Disposed names who made it and "
     "cannot be altered."),
    ("maintenance_performed",
     "A planned maintenance visit being carried out. The schedule keeps one "
     "overwritten last-done date, with no person and no row per visit."),
    ("deleted_records",
     "Anything whose record has since been deleted. A change of custodian, "
     "a move, a verification, a change of status, a change to the GRN, "
     "purchase order or SAP asset number, a change to the warranty and a "
     "refused affix confirmation are protected from deletion, each "
     "from the date this history gives for it. Every other record here, and "
     "every one of those made before its date, can be removed without "
     "trace, so this history is a lower bound on what happened, never a "
     "complete account of it."),
)

#: Handoff 57: the history's sentence per gate action.
_GATE_SENTENCES = {
    "submit": "Submitted to Internal Audit",
    "verify": "Sighted and verified by Internal Audit",
    "approve": "Value for money approved",
    "query": "Queried by Internal Audit",
    "resubmit": "Store answered the query and resubmitted",
    "reject": "Rejected by Internal Audit",
    "request-tagging": "Tagging requested",
    "issue-tag": "Tag issued",
    "affix": "Tag affixed",
    # Handoff 59 §2: a unit with no label to fix passes the two tagging
    # gates by being skipped; the event's reason says why.
    "skip-tagging": "Tagging skipped",
    "register": "Submitted for registration",
    "approve-registration": "Registration approved — on the register",
    "return-registration": "Registration returned to the maker",
}
_REGISTER_STATE_WORDS = {
    "captured": "captured", "vfm_pending": "awaiting IAD verification",
    "vfm_verified": "verified", "vfm_approved": "VfM approved",
    "vfm_query": "queried", "vfm_rejected": "rejected",
    "tag_requested": "tagging requested", "tag_issued": "tag issued",
    "tagged": "tagged", "reg_ready": "ready for registration (no label)",
    "reg_submitted": "registration submitted",
    "registered": "registered",
}


def _json_or_none(raw):
    import json
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return raw


_EVENT_TITLES = {
    "registered": "Registered",
    "tag_issued": "Tag issued",
    "tag_printed": "Tag printed",
    # Handoff 51. BEFORE `tag_affixed` on purpose: `_RANK` breaks same-second
    # ties in this order, and the sequence this event exists to make visible
    # — a refusal, then a confirmation with the number the refusal revealed,
    # seconds apart — must read refusal-first when both land in one second.
    "affix_refused": "Affix confirmation refused",
    "tag_affixed": "Tag affixed",
    # Handoff 57 (kept by 58): a receipt gate fired.
    "gate_fired": "Receipt gate",
    "tag_scrapped": "Tag scrapped",
    "custody_changed": "Custodian changed",
    "location_moved": "Location moved",
    "transfer_recorded": "Transfer recorded",
    "status_changed": "Status changed",
    "condition_changed": "Condition changed",
    "verified": "Verified",
    "verification_date_set": "Verification date written",
    "disposal_approved": "Disposal approved",
    "disposal_recorded": "Disposal details recorded",
    "provenance_changed": "Provenance changed",
    # Handoff 34. Recorded append-only from the day the fields existed, so
    # there is no earlier message-log stretch to fall back on.
    "warranty_changed": "Warranty changed",
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
    # The verifier, tracked since handoff 28. A change of verifier with no
    # change of DATE — a second verification on the same day, or a date that
    # arrived by PATCH and cleared the old verifier — is a line of its own.
    "last_verified_by": "verified",
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
    # Where the asset came from — what an auditor traces back to Vendra and
    # to SAP. Tracked since handoff 28, so graded `chatter` like every other
    # tracked change: VISIBLE, which it was not before, and not protected.
    "grn_reference": "provenance_changed",
    "purchase_order_reference": "provenance_changed",
    "purchase_vendor": "provenance_changed",
    "import_source": "provenance_changed",
    "import_date": "provenance_changed",
    "import_ref": "provenance_changed",
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

    def asset_history(self, newest_first=True, request_references=False):
        """Everything recorded about this asset, on one clock.

        `request_references` — whether a maintenance request's reference is
        published. The ROUTE decides, from the caller's scopes: the request
        belongs to `requests:read`, and this history is `assets:read`.

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
        recorded, covered = self._history_recorded_events()
        events += recorded
        location_rows, other_chatter = self._history_chatter(covered)
        events += self._history_locations(location_rows)
        events += other_chatter
        events += self._history_disposal_approval()
        events += self._history_dispatches()
        events += self._history_requests(request_references)

        undated = sum(1 for e in events if e is None)
        events = [e for e in events if e is not None]
        events.sort(key=lambda e: e["_sort"], reverse=bool(newest_first))
        # THE OPENING STATE IS NOT HISTORY. The `create` that makes an asset
        # also mints its tag, and — when it is created at a location or
        # already assigned — writes the first movement and the first custody
        # link, all in one transaction and therefore under one `create_date`.
        # Counting those as things that happened AFTER registration would
        # mean no asset ever had an empty history, and the sentence handoff
        # 27 exists for could never be reached on the screen it was written
        # for. They are still LISTED; they are just not counted as a life.
        opening = {e["id"] for e in events if e["_initial"]}
        for e in events:
            del e["_sort"]
            del e["_initial"]

        return {
            "asset": {"id": self.id, "asset_code": self.asset_code,
                      "name": self.name},
            "order": "newest_first" if newest_first else "oldest_first",
            "summary": self._history_summary(events, opening),
            "fidelity": dict(self._history_fidelity(events, opening),
                             undated_records_omitted=undated),
            "events": events,
        }

    # ── the event shape ──────────────────────────────────────────────

    def _history_event(self, etype, at, record, evidence, *, summary,
                       actor=None, actor_name=None, precision="second",
                       source=None, reconstructed=False, detail=None,
                       initial=False):
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
            # Part of the asset's OPENING STATE rather than of its history:
            # see `asset_history`. Private, stripped before publishing.
            "_initial": bool(initial),
        }

    # ── the sources ──────────────────────────────────────────────────

    def _history_registered(self):
        # The provenance block is the asset's CURRENT values, not what was
        # sent at registration — all are rewritable, and tracked only since
        # `fidelity.provenance_tracked_from`. Said on the event, because a
        # GRN reference printed under "Registered" reads as what arrived.
        source = self.import_source or None
        via = dict(self._fields["import_source"]._description_selection(
            self.env)).get(source) if source else None
        return [self._history_event(
            "registered", self.create_date, ("nrs.asset", self.id),
            "system_stamp", initial=True,
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
                actor=_user_ref(tag.create_uid), detail=base,
                initial=tag.create_date == self.create_date))
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
        approvals = self._history_approvals()
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
                initial=(not link.from_custodian_id
                         and not link.from_custodian_name
                         and link.create_date == self.create_date),
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
                    # See the movement event: both people, or null.
                    "approval": self._history_approval_block(
                        approvals.get(("nrs.asset.custody", link.id))),
                }))
        return events

    # The chatter fields an `nrs.asset.event` of each type also records.
    # `sap_asset_number` is not tracked, so there is nothing of it to fold.
    _EVENT_COVERS = {
        "verified": ("last_verified_date", "last_verified_by"),
        "verification_date_set": ("last_verified_date", "last_verified_by"),
        "status_changed": ("state",),
    }

    def _history_recorded_events(self):
        """`nrs.asset.event` rows, and the chatter rows they make redundant.

        Since handoff 30 a verification, a change of status and a change to
        the GRN, purchase order or SAP asset number each have a record nobody
        can alter. Where one exists IT is the event. Everything that happened
        BEFORE recording began is still a message-log line, still graded as
        one, and `fidelity.events` says where the line falls.
        """
        events, covered = [], set()
        labels = dict(
            self._fields["state"].get_description(self.env)["selection"])
        field_labels = {
            name: self._fields[name].get_description(self.env)["string"]
            for name in ("grn_reference", "purchase_order_reference",
                         "sap_asset_number", "warranty_start_date",
                         "warranty_months", "warranty_expiry", "warrantor",
                         "warranty_reference") if name in self._fields}
        for ev in self.event_ids:
            etype = ev.event_type
            for fname in self._EVENT_COVERS.get(etype, ()):
                covered.add((ev.create_date, fname))
            detail = {"records": ["nrs.asset.event"]}
            if etype == "verified":
                published = "verified"
                summary = "Verified by %s" % (ev.actor_name or "—")
                detail.update(verified_on=ev.to_value or None,
                              previous_verified_on=ev.from_value or None,
                              notes=ev.notes or None,
                              verifier_recorded=True)
            elif etype == "verification_date_set":
                published = "verification_date_set"
                summary = ("Verification date set to %s — the record does "
                           "not say who checked the asset"
                           % (ev.to_value or "nothing"))
                detail.update(verified_on=ev.to_value or None,
                              previous_verified_on=ev.from_value or None,
                              verifier_recorded=False)
            elif etype == "status_changed":
                published = "status_changed"
                summary = "%s → %s" % (
                    labels.get(ev.from_value, ev.from_value or "—"),
                    labels.get(ev.to_value, ev.to_value or "—"))
                detail.update({"from": ev.from_value or None,
                               "to": ev.to_value or None,
                               "reason": ev.reason or None})
            elif etype == "affix_refused":
                # Handoff 51. The scanned value as entered; nothing about
                # the label changed, which is the point — the row exists so
                # that a refusal followed seconds later by a confirmation
                # is a sequence anybody reading this history can see.
                #
                # One sentence PER REASON since handoff 52 §4, so a reader
                # can tell a wrong label from a dead one from a label going
                # onto the wrong box. A row with no reason predates the
                # reasons and is handoff 51's number mismatch — the only
                # kind that was recorded then.
                published = "affix_refused"
                reason = ev.reason or "number_mismatch"
                if reason == "scrapped":
                    summary = ("Affix confirmation refused — the label "
                               "presented (%s) has been scrapped and is no "
                               "longer valid for any asset"
                               % (ev.to_value or "—"))
                elif reason == "serial_mismatch":
                    summary = ("Affix confirmation refused — the serial "
                               "read off the asset (%s) is not the serial "
                               "on record for it; the label may have been "
                               "going onto the wrong asset"
                               % (ev.to_value or "—"))
                else:
                    summary = ("Affix confirmation refused — the number "
                               "read off the asset (%s) is not the label "
                               "issued for it" % (ev.to_value or "—"))
                # `scanned_format` since handoff 54: how the refused value
                # was read, when the caller knew. Null is "not known" — a
                # typed entry, a keyboard wedge, or a pre-54 row.
                detail.update(scanned=ev.to_value or None, reason=reason,
                              scanned_format=ev.scanned_format or None)
            elif etype == "gate_fired":
                # Handoff 57 (kept by 58). One row per move
                # of the register state, by `nrs.asset._fire_gate` alone.
                published = "gate_fired"
                summary = _GATE_SENTENCES.get(
                    ev.gate_action, "Receipt gate: %s" % (ev.gate_action or "—"))
                summary = "%s (%s → %s)" % (
                    summary, _REGISTER_STATE_WORDS.get(ev.from_value,
                                                       ev.from_value or "—"),
                    _REGISTER_STATE_WORDS.get(ev.to_value, ev.to_value or "—"))
                if ev.reason:
                    summary += " — %s" % ev.reason
                detail.update({"from": ev.from_value or None,
                               "to": ev.to_value or None,
                               "gate": ev.gate or None,
                               "action": ev.gate_action or None,
                               "reason": ev.reason or None,
                               "evidence": _json_or_none(ev.notes)})
            else:
                # A reference or a warranty field: the same shape, a field
                # with a before and an after. The warranty fields carry no
                # tracking, so `covered` finds nothing of theirs to drop.
                published = ("warranty_changed"
                             if etype == "warranty_changed"
                             else "provenance_changed")
                covered.add((ev.create_date, ev.field_name))
                label = field_labels.get(ev.field_name, ev.field_name)
                summary = "%s: %s → %s" % (
                    label, _shown(ev.from_value or None),
                    _shown(ev.to_value or None))
                detail.update(changes=[{
                    "field": ev.field_name, "label": label,
                    "old": ev.from_value or None,
                    "new": ev.to_value or None}])
            events.append(self._history_event(
                published, ev.occurred_at, ("nrs.asset.event", ev.id),
                "append_only", summary=summary,
                actor=_user_ref(ev.actor_id),
                actor_name=ev.actor_name or None,
                source=ev.source, detail=detail))
        return events, covered

    def _history_event_fidelity(self):
        """From when each kind of event has a record nobody can alter.

        PER KIND. They share a table and did not necessarily begin together
        on a given database, and a shared table is exactly where that is
        easy to get wrong.
        """
        Event = self.env["nrs.asset.event"]
        kinds = (
            ("verified", "verified",
             "a verification made with the Verify button"),
            ("verification_date_set", "verification_date_set",
             "a verification date written any other way"),
            ("status_changed", "status_changed", "a change of status"),
            ("reference_changed", "provenance_changed",
             "a change to the GRN reference, the purchase order reference "
             "or the SAP asset number"),
            ("warranty_changed", "warranty_changed",
             "a change to the warranty"),
            ("affix_refused", "affix_refused",
             "a refused affix confirmation"),
            ("gate_fired", "gate_fired",
             "a receipt gate fired (submit, verify, approve, tagging, "
             "registration)"),
        )
        out = []
        for stored, published, what in kinds:
            began = Event.recording_began_at(stored)
            if stored == "warranty_changed":
                # No message-log fallback to promise. The five warranty
                # fields were never tracked — they arrived with their event,
                # in handoff 34 — so there is no earlier stretch at all, and
                # the verification pass caught the generic sentence telling a
                # reader to look for one.
                statement = (
                    "No warranty has been changed on this system yet, for "
                    "any asset. Every change to a warranty is recorded so "
                    "that nobody can edit or delete it; a warranty entered "
                    "when an asset was registered is not a change, and is "
                    "shown on the asset." if not began else
                    "From %s, when the first one was made here, a change "
                    "to the warranty is recorded so that nobody can edit or "
                    "delete it. There is no earlier record to look for: a "
                    "warranty was never recorded any other way." % _when(began))
            elif stored == "affix_refused":
                # Also no message-log fallback — a refusal used to leave
                # NOTHING behind, not even a deletable line, which is the
                # defect handoff 51 closed. The generic sentence would send
                # a reader looking for an earlier record that never existed.
                statement = (
                    "No affix confirmation has been refused on this system "
                    "yet, for any asset. Every refusal is recorded so that "
                    "nobody can edit or delete it." if not began else
                    "From %s, when the first one happened here, a refused "
                    "affix confirmation is recorded so that nobody can edit "
                    "or delete it. There is no earlier record to look for: "
                    "before then a refusal left nothing behind at all."
                    % _when(began))
            elif stored == "gate_fired":
                # No message-log fallback either: the receipt gates arrived
                # with their event (handoff 57), so a gate has never been
                # recorded any other way. On a tenant with the switch off —
                # every fresh database — none has ever fired, and the generic
                # sentence would send a reader looking for log lines that do
                # not exist.
                statement = (
                    "No receipt gate has fired on this system yet, for any "
                    "asset. Every gate a received unit passes is recorded so "
                    "that nobody can edit or delete it." if not began else
                    "From %s, when the first one fired here, every receipt "
                    "gate a unit passes is recorded so that nobody can edit "
                    "or delete it. There is no earlier record to look for: "
                    "the gates did not exist before then." % _when(began))
            elif not began:
                statement = (
                    "No record of this kind has been written on this system "
                    "yet, for any asset: %s is shown only where the message "
                    "log holds it." % what)
            else:
                statement = (
                    "From %s, %s is recorded so that nobody can edit or "
                    "delete it. An earlier one is shown only where the "
                    "message log holds it, and says so."
                    % (_when(began), what))
            out.append({
                "event": published,
                "recording_began_at": _iso(began),
                "statement": statement,
            })
        return out

    def _history_chatter(self, covered=frozenset()):
        """Tracked changes, split into location rows and everything else.

        Tracking VALUES only. A message body is free text somebody typed and
        is not published here — this route is `assets:read`, and a note on
        an asset was never promised to every holder of that scope.

        `covered` — `(transaction stamp, field)` pairs that an append-only
        `nrs.asset.event` already records. Such a row is the same act seen
        twice and is dropped, for `_CHATTER_SUPERSEDED`'s reason; matched by
        transaction and not by the clock, for `_history_chatter_row_of`'s.
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
                if (msg.create_date, field["name"]) in covered:
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
        recorded_transfers = set()
        # SINCE HANDOFF 28 a move has a record of its own: `nrs.asset.movement`,
        # append-only, written by `nrs.asset.write` underneath every writer of
        # `location_id`. Where one exists IT is the event, and the transfer
        # row and the chatter row of the same act are folded into it rather
        # than listed beside it. Everything below this loop is unchanged and
        # now describes only what happened BEFORE recording began — which is
        # still most of `nrs19`, and the list has to keep saying so.
        approvals = self._history_approvals()
        for m in self.movement_ids:
            row = self._history_chatter_row_of(m, unmatched)
            if row:
                unmatched.remove(row)
            t = m.transfer_id
            if t:
                recorded_transfers.add(t.id)
            before = m.from_location_name or None
            after = m.to_location_name or None
            if not before:
                summary = "Placed at %s" % (after or "—")
            elif not after:
                summary = "%s → nowhere" % before
            else:
                summary = "%s → %s" % (before, after)
            events.append(self._history_event(
                "location_moved", m.moved_at,
                ("nrs.asset.movement", m.id), "append_only",
                summary=summary,
                actor=_user_ref(m.moved_by_id),
                actor_name=m.moved_by_name or None,
                source=m.source,
                reconstructed=m.source == "tracking_backfill",
                detail={
                    "from_location": before,
                    "to_location": after,
                    "reason": m.reason or None,
                    # The paperwork, where the move had any. The reference is
                    # the one RECORDED with the move and survives the
                    # transfer row being deleted; the rest is read live from
                    # a document an asset manager can edit, and is null once
                    # it is gone.
                    "transfer": ({
                        # IN-BAND, because this block sits inside an event
                        # graded `append_only` and only ONE key of it is:
                        # `reference` was recorded with the move. The rest is
                        # read live from a document an asset manager can
                        # edit — an approver shown here is what that document
                        # says TODAY.
                        "evidence": "editable_record",
                        "id": t.id or None,
                        "reference": m.transfer_reference,
                        "state": t.state if t else None,
                        "transfer_date": _iso(t.transfer_date) if t else None,
                        "reason": (t.reason or None) if t else None,
                        "recorded_by": _user_ref(t.create_uid) if t else None,
                        "approved_by": _user_ref(t.approved_by) if t else None,
                        "approved_at": _iso(t.approved_date) if t else None,
                    } if m.transfer_reference else None),
                    # BOTH PEOPLE, on a move that took two. Null on a move
                    # that took one — which is every move made before
                    # handoff 35 and every move on a tenant with the switch
                    # off, and a reader can tell those apart from this being
                    # absent only because the key is always present.
                    "approval": self._history_approval_block(
                        approvals.get(("nrs.asset.movement", m.id))),
                    "records": ["nrs.asset.movement"]
                               + (["nrs.asset.transfer"] if t else [])
                               + (["nrs.asset.change.request"]
                                  if approvals.get(
                                      ("nrs.asset.movement", m.id)) else [])
                               + (["mail.message"] if row else []),
                },
                initial=(not m.from_location_id
                         and not m.from_location_name
                         and m.create_date == self.create_date)))
        for t in self.transfer_ids.sorted("id"):
            if t.id in recorded_transfers:
                continue
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

    def _history_approvals(self):
        """The approved change requests for this asset, by what they produced.

        `{('nrs.asset.movement', id): request}` and the same for custody, so
        the two event builders can each ask one dict rather than searching
        per row. ONE query for the asset, not one per movement.

        WHY THIS EXISTS (handoff 36 §C). An approved move records the
        APPROVER as its actor — `nrs.asset.movement.moved_by_id` is whoever
        clicked, which is right, because their authority is what moved the
        asset. But Vendra's report 43 read the history of an approved move
        and found that *the requester appears nowhere*: the artefact an
        auditor reads answered *who approved this* while losing *who asked
        for it*, which is exactly half of the two-person control it is meant
        to evidence.

        **The fix is ADDITIVE and `actor` is left alone.** `actor` means the
        same thing on all fourteen event types — the person the record names
        as having done it — and repurposing it here would be a published key
        changing meaning on one event, which is the defect handoff 32 built a
        guard against. So the second person arrives as a new `approval`
        block, and a reader who wants one name still gets the one they
        always got.
        """
        self.ensure_one()
        index = {}
        CR = self.env.get("nrs.asset.change.request")
        if CR is None:
            # Belt and braces, and HONESTLY LABELLED: `myservice_api` names
            # `myservice_asset_register` in its `depends`, so if this code is
            # running the model is in the registry and this branch is dead.
            #
            # It does NOT protect against the case somebody will assume it
            # does — a tenant carrying this Python against an un-upgraded
            # schema. There the model IS in the registry and the TABLE is
            # missing, so the search below raises `UndefinedTable` and this
            # check never fires. That case is covered by upgrading every
            # tenant before the code ships, which is the rule in `CLAUDE.md`,
            # and by nothing here.
            return index
        for req in CR.sudo().search([("asset_id", "=", self.id),
                                     ("state", "=", "approved")]):
            if req.movement_id:
                index[("nrs.asset.movement", req.movement_id.id)] = req
            if req.custody_id:
                index[("nrs.asset.custody", req.custody_id.id)] = req
        return index

    @api.model
    def _history_approval_block(self, req):
        """The two-person evidence, or None when the change had one person.

        Graded `append_only` IN-BAND and deliberately, against the same
        definition the grades table publishes — *the application refuses to
        edit or delete it for anyone, an administrator included*. A DECIDED
        `nrs.asset.change.request` meets that exactly: `unlink` refuses
        unconditionally and `write` refuses on a decided record, both under
        `sudo()`. It is a state machine rather than an append-only row, so
        the grade is asserted here rather than assumed from the model's
        name — and it is only ever attached to a request in `approved`.

        Contrast the `transfer` block a few lines below, which is
        `editable_record` and says so for the opposite reason.
        """
        if not req:
            return None
        return {
            "evidence": "append_only",
            "reference": req.name,
            # WHO ASKED. The name as recorded, beside the live link, for the
            # reason every other `*_name` in this file exists: the link goes
            # null if the user is deleted and the evidence must not.
            "requested_by": _user_ref(req.requested_by_id),
            "requested_by_name": req.requested_by_name or None,
            "requested_at": _iso(req.requested_at),
            # WHO WAS ASKED — a nomination, and not necessarily who decided.
            "approver_asked": _user_ref(req.approver_id),
            # WHO DECIDED. The same person as the event's `actor`, published
            # again here so the block reads as a complete account of the two
            # halves without the reader having to join it to the event.
            "approved_by": _user_ref(req.approved_by_id),
            "approved_by_name": req.approved_by_name or None,
            "approved_at": _iso(req.decided_at),
            "decision_reason": req.decision_reason or None,
        }

    @api.model
    def _history_chatter_row_of(self, movement, rows):
        """The chatter row of the write that produced this movement, or None.

        **By TRANSACTION, not by the clock.** The movement row and the
        tracking message are created inside one transaction, so their
        `create_date`s — Postgres's transaction stamp — are identical. The
        first draft matched on the two wall-clock instants being within 120
        seconds, and that fails exactly where it matters: a message's `date`
        is taken at PRECOMMIT, so in an import or a seed that runs for longer
        than two minutes every early line's move came apart from its own
        chatter row and was listed twice.

        **By NAME where the id is gone.** Deleting a location nulls
        `from_location_id`/`to_location_id` on the movement, while the
        tracking value still holds the original id — so every move into or
        out of a since-deleted place lost its join too. The names were
        recorded for precisely that case.
        """
        def same_place(location, name, tracked_id, tracked_name):
            if location:
                return tracked_id == location.id
            return (tracked_name or "") == (name or "") or (
                not name and not tracked_id)

        for row in rows:
            tv = row["value"]
            if (row["message"].create_date == movement.create_date
                    and same_place(movement.from_location_id,
                                   movement.from_location_name,
                                   tv.old_value_integer, tv.old_value_char)
                    and same_place(movement.to_location_id,
                                   movement.to_location_name,
                                   tv.new_value_integer, tv.new_value_char)):
                return row
        return None

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

    def _history_requests(self, with_reference=False):
        events = []
        requests = self.env["request.request"].search(
            [("nrs_asset_id", "=", self.id)])
        for req in requests:
            # THAT a request was raised, when and by whom, to everybody who
            # may read the asset: `request_count` already tells every holder
            # of `assets:read` that requests exist. Its REFERENCE only to a
            # caller who also holds `requests:read`, which is who the request
            # belongs to (ruled in handoff 30 §D1). It was withheld from
            # everybody until then, on the grounds that "a route cannot see
            # its caller's scopes" — which was false, and is retracted in
            # GO-LIVE §14.1. Still not its content: a request's text was
            # never promised to a reader of assets.
            reference = (req.name or None) if with_reference else None
            events.append(self._history_event(
                "maintenance_request", req.create_date,
                ("request.request", req.id), "editable_record",
                summary=("Maintenance request %s raised" % reference
                         if reference else "Maintenance request raised"),
                actor=_user_ref(req.create_uid),
                detail={"reference": reference,
                        # Said, so that a null reads as WITHHELD and not as
                        # a request that has no reference.
                        "reference_withheld": not with_reference}))
        return events

    # ── what the list says about itself ──────────────────────────────

    def _history_summary(self, events, opening):
        after = [e for e in events if e["id"] not in opening]
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

    def _history_location_fidelity(self):
        """Where the record of this asset's moves begins. Custody's twin.

        The movement record began on the day the recorder was installed and
        was NOT backfilled (handoff 28 ruled that separately). So an asset
        that was already somewhere on that day has no record of how it got
        there: its first movement already has a `from`, or it has no
        movements and is somewhere. `nrs19` holds 11,943 assets of which
        every one placed before today is in that state, and the list has to
        say so on each rather than letting a short record read as a quiet
        life.
        """
        Movement = self.env["nrs.asset.movement"]
        began = Movement.recording_began_at()
        moves = self.movement_ids.sorted(lambda m: (m.moved_at, m.id))
        first = moves[:1]
        if first:
            unrecorded = bool(first.from_location_id
                              or first.from_location_name)
        else:
            unrecorded = bool(self.location_id)
        if not began:
            statement = (
                "No change of location has yet been recorded on this system, "
                "for any asset. A move shown here rests on a transfer "
                "document or on the message log, and says which.")
        elif unrecorded:
            statement = (
                "This asset was already somewhere when the recording of "
                "moves reached it, and how it came to be there is not "
                "recorded. Moves are recorded on this system from %s; an "
                "earlier one is shown only where a transfer document or the "
                "message log holds it, and says which." % _when(began))
        else:
            statement = (
                "Moves are recorded on this system from %s, and cannot be "
                "edited or deleted afterwards. An earlier one is shown only "
                "where a transfer document or the message log holds it, and "
                "says which." % _when(began))
        return {
            "recording_began_at": _iso(began),
            "movements": len(moves),
            "reconstructed_movements": len(moves.filtered(
                lambda m: m.source == "tracking_backfill")),
            "first_movement_at": _iso(first.moved_at) if first else None,
            "located_before_first_movement": unrecorded,
            "statement": statement,
        }

    def _history_provenance_from(self):
        """When a change to the GRN/PO/vendor/import fields began to show.

        The same parameter the register snapshot reads, stamped per database
        by migration 19.0.1.15.0. Null means tracked from the first asset.
        """
        raw = self.env["ir.config_parameter"].sudo().get_param(
            "cadra.provenance_tracked_from")
        return _iso(fields.Datetime.to_datetime(raw)) if raw else None

    def _history_fidelity(self, events, opening):
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
        dated = [e["at"] for e in events if e["id"] not in opening]
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
            "location": self._history_location_fidelity(),
            "events": self._history_event_fidelity(),
            "provenance_tracked_from": self._history_provenance_from(),
            "evidence_grades": [
                {"grade": grade, "meaning": meaning}
                for grade, meaning in EVIDENCE_GRADES],
            "not_recorded": [
                {"event": event, "statement": text}
                for event, text in NOT_RECORDED],
            # Rewritten in handoff 28, which made the previous sentence
            # false: it said the Verify button "sets that date and nothing
            # else". It now records the verifier. A statement published on a
            # client's screen goes stale the day the behaviour under it
            # changes, and nothing fails when it does — so this one is held
            # by `test_the_verification_statement_matches_the_button`.
            # …and again in handoff 30, which made THAT sentence false: it
            # said earlier verifications "survive only as the message-log
            # lines listed here". Each is now a record of its own.
            "verification": (
                "The Verify button records who checked the asset, each time "
                "it is pressed, as an event that cannot be edited or "
                "deleted. A verification date written any other way is "
                "listed as a date that was written, names whoever wrote it, "
                "and clears the verifier: the record does not say that "
                "anybody checked the asset. The asset itself keeps only the "
                "most recent date and verifier. A verification made before "
                "this system began recording them is shown only as a "
                "message-log line, and this history gives the date that "
                "began."),
        }
