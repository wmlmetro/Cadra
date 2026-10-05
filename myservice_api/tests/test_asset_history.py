"""The asset history — that it is in order, and that it does not overclaim.

Handoff 27's four requirements are one requirement in four places: the list
must not imply more than the record supports. Each class below is one of
them, asserted against the builder rather than the route, because ordering
across seven sources is the substance of the thing and an ordering nobody
tests is an ordering that will be wrong.

    1. It is on one clock, across sources, in both directions.
    2. A reconstructed row says so; a blank actor stays blank.
    3. One physical move is one line — and a move with no transfer row is
       still a line, graded as the weaker record it is.
    4. It says where it begins, what it cannot record, and — in words — when
       it has nothing to show.

Time is frozen per step because everything here happens inside one second of
one transaction. `fields.Datetime.now()` — the custody link's `changed_at`
and a message's `date` — obeys freezegun; `create_date` is the database's
transaction clock and does not, so the frozen instants are all in the future
of it and the assertions filter on that.

Run with:
    odoo -d <db> -u myservice_api --test-enable \\
         --test-tags /myservice_api --stop-after-init
"""
import uuid

# Handoff 35 gates every writer of `location_id` and `custodian_id` behind a
# second person, and these tests write both directly through the ORM to build
# the history they then read. Each such write declares
# `cadra_approval_exempt="test"` AT ITS OWN CALL SITE — per call and never
# once per file or per class, for the reason `approval_policy.EXEMPT_REASONS`
# and `myservice_nrs_base/database_class.py` both give: a flag added for one
# legitimate afternoon becomes the way everybody runs by the end of the
# month. A test declaring itself a fixture is not the same thing as a switch
# that turns the rule off.


from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import freeze_time
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

_FUTURE = "2031-"


class AssetHistoryCase(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Asset = self.env["nrs.asset"]
        self.category = self.env["nrs.asset.category"].create(
            {"name": "History test category"})
        Employee = self.env["hr.employee"]
        self.alice = Employee.create({"name": "History Alice"})
        self.bob = Employee.create({"name": "History Bob"})
        Location = self.env["generic.location"]
        self.place_a = Location.create({"name": "History location A"})
        self.place_b = Location.create({"name": "History location B"})
        self.place_c = Location.create({"name": "History location C"})

    def _flush_tracking(self):
        # Odoo 19 writes tracking values from a `cr.precommit` callback, and
        # a TransactionCase never commits — `test_disposal_report.py` sets
        # out the mechanism. Without this the chatter stream is empty and
        # every assertion about it passes vacuously.
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.env.flush_all()

    def _asset(self, **vals):
        asset = self.Asset.create(dict(
            {"name": "History test asset", "category_id": self.category.id,
             "location_id": self.place_a.id}, **vals))
        # `create` registers `_track_discard`, which nulls the initial
        # values until the precommit runs; a tracked write before this flush
        # records nothing.
        self._flush_tracking()
        return asset

    def _later(self, history):
        """The events this test made happen, by their frozen instants."""
        return [e for e in history["events"] if e["at"].startswith(_FUTURE)]

    def _backfilled_link(self, asset, **vals):
        return self.env["nrs.asset.custody"].sudo().with_context(
            cadra_custody_append=True).create(dict({
                "asset_id": asset.id,
                "to_custodian_id": self.alice.id,
                "to_custodian_name": self.alice.name,
                "changed_at": "2025-01-05 10:00:00",
                "source": "tracking_backfill",
            }, **vals))


@tagged("post_install", "-at_install")
class TestAssetHistoryOrder(AssetHistoryCase):

    def _a_life(self):
        asset = self._asset()
        with freeze_time("2031-01-01 09:00:00"):
            asset.with_context(
                cadra_approval_exempt="test").write({"custodian_id": self.alice.id})
            self._flush_tracking()
        with freeze_time("2031-01-02 09:00:00"):
            asset.write({"state": "in_repair"})
            self._flush_tracking()
        with freeze_time("2031-01-03 09:00:00"):
            asset.with_context(
                cadra_approval_exempt="test").write({"location_id": self.place_b.id})
            self._flush_tracking()
        with freeze_time("2031-01-04 09:00:00"):
            asset.with_context(
                cadra_approval_exempt="test").write({"custodian_id": self.bob.id})
            self._flush_tracking()
        return asset

    def test_sources_are_merged_onto_one_clock(self):
        """Custody, chatter, a move, custody — interleaved, not grouped."""
        history = self._a_life().asset_history(newest_first=False)
        self.assertEqual(history["order"], "oldest_first")
        self.assertEqual(
            [e["type"] for e in self._later(history)],
            ["custody_changed", "status_changed", "location_moved",
             "custody_changed"])

    def test_newest_first_is_the_exact_reverse(self):
        asset = self._a_life()
        oldest = [e["id"] for e in asset.asset_history(
            newest_first=False)["events"]]
        newest = [e["id"] for e in asset.asset_history(
            newest_first=True)["events"]]
        self.assertEqual(newest, list(reversed(oldest)))
        self.assertEqual(
            asset.asset_history()["order"], "newest_first",
            "newest first is the default")

    def test_registration_is_first_even_inside_its_own_instant(self):
        """The tag is minted by the same `create`, at the same instant."""
        events = self._asset().asset_history(newest_first=False)["events"]
        self.assertEqual(events[0]["type"], "registered")
        self.assertEqual(events[1]["type"], "tag_issued")
        self.assertEqual(events[0]["at"], events[1]["at"])

    def test_nothing_sorts_before_the_registration_it_followed(self):
        """Whole seconds against microseconds: `:44.000` is before `:44.730`.

        The custody link is stamped at the top of the second the asset was
        created in — which is what happens to every asset created already
        assigned, and to any integration that registers and then acts. It
        came after the registration and must be listed after it.
        """
        asset = self._asset()
        self.assertTrue(asset.create_date.microsecond,
                        "needs a create_date inside its second to mean much")
        with freeze_time(asset.create_date.replace(microsecond=0)):
            asset.with_context(
                cadra_approval_exempt="test").write({"custodian_id": self.alice.id,
                         "location_id": self.place_b.id})
            self._flush_tracking()
        types = [e["type"] for e in
                 asset.asset_history(newest_first=False)["events"]]
        self.assertEqual(types[0], "registered")
        self.assertLess(types.index("registered"),
                        types.index("custody_changed"))
        self.assertLess(types.index("registered"),
                        types.index("location_moved"))
        newest = [e["type"] for e in asset.asset_history()["events"]]
        self.assertEqual(newest[-1], "registered")

    def test_every_event_has_every_key(self):
        keys = {"id", "type", "title", "summary", "at", "at_precision",
                "actor", "actor_name", "evidence", "reconstructed", "source",
                "record", "detail"}
        events = self._a_life().asset_history()["events"]
        for event in events:
            self.assertEqual(set(event), keys, event["id"])
        ids = [e["id"] for e in events]
        self.assertEqual(len(ids), len(set(ids)), "event ids must be unique")

    def test_a_custody_change_is_listed_once(self):
        """`custodian_id` is tracked too; the chain supersedes that row."""
        later = self._later(self._a_life().asset_history())
        self.assertEqual(
            sum(1 for e in later if e["type"] == "custody_changed"), 2)
        for event in later:
            for change in event["detail"].get("changes", []):
                self.assertNotEqual(change["field"], "custodian_id")


@tagged("post_install", "-at_install")
class TestAssetHistoryDoesNotOverclaim(AssetHistoryCase):

    def test_a_reconstructed_link_says_so(self):
        asset = self._asset()
        link = self._backfilled_link(asset)
        event = next(e for e in asset.asset_history()["events"]
                     if e["record"] == {"model": "nrs.asset.custody",
                                        "id": link.id})
        self.assertTrue(event["reconstructed"])
        self.assertEqual(event["source"], "tracking_backfill")
        self.assertEqual(event["evidence"], "append_only")
        self.assertEqual(asset.asset_history()["summary"]
                         ["reconstructed_events"], 1)

    def test_a_live_link_is_not_marked_reconstructed(self):
        asset = self._asset()
        asset.with_context(
            cadra_approval_exempt="test").write({"custodian_id": self.alice.id})
        event = next(e for e in asset.asset_history()["events"]
                     if e["type"] == "custody_changed")
        self.assertFalse(event["reconstructed"])
        self.assertEqual(event["actor"]["id"], self.env.uid)

    def test_an_actor_the_record_does_not_have_is_blank(self):
        """No `changed_by` on the link. Not "system", not `create_uid`."""
        asset = self._asset()
        link = self._backfilled_link(asset)
        self.assertFalse(link.changed_by_id)
        self.assertTrue(link.create_uid, "there IS a create_uid to fall "
                        "back on, which is what makes this a test")
        event = next(e for e in asset.asset_history()["events"]
                     if e["record"]["id"] == link.id
                     and e["type"] == "custody_changed")
        self.assertIsNone(event["actor"])
        self.assertIsNone(event["actor_name"])

    def test_a_name_outlives_the_user(self):
        asset = self._asset()
        link = self._backfilled_link(asset, changed_by_name="Someone Gone")
        event = next(e for e in asset.asset_history()["events"]
                     if e["record"]["id"] == link.id
                     and e["type"] == "custody_changed")
        self.assertIsNone(event["actor"])
        self.assertEqual(event["actor_name"], "Someone Gone")

    def test_a_message_body_is_never_published(self):
        asset = self._asset()
        asset.message_post(body="the combination is 4471",
                           message_type="comment")
        self._flush_tracking()
        self.assertNotIn("4471", repr(asset.asset_history()))

    def test_an_untracked_change_adds_no_event_and_is_named(self):
        """A changed cost leaves nothing — and the response says so."""
        asset = self._asset()
        before = len(asset.asset_history()["events"])
        asset.write({"acquisition_cost": 123456.0})
        self._flush_tracking()
        history = asset.asset_history()
        self.assertEqual(len(history["events"]), before)
        named = {n["event"] for n in history["fidelity"]["not_recorded"]}
        self.assertIn("financial_change", named)
        self.assertIn("deleted_records", named)

    def test_a_tracked_false_is_a_value_not_a_dash(self):
        """`value or "—"` hid an unticked box behind the sign for nothing."""
        asset = self._asset()
        asset.write({"retrieval_flag": True})
        self._flush_tracking()
        event = next(
            e for e in asset.asset_history()["events"]
            if any(c["field"] == "retrieval_flag"
                   for c in e["detail"].get("changes", [])))
        change = event["detail"]["changes"][0]
        self.assertIs(change["old"], False)
        self.assertIs(change["new"], True)
        self.assertIn("No → Yes", event["summary"])
        self.assertNotIn("—", event["summary"])

    def test_the_statements_are_words_not_field_names(self):
        """They are shown to a client on a screen, not only to a parser."""
        asset = self._asset()
        asset.with_context(
            cadra_approval_exempt="test").write({"custodian_id": self.alice.id})
        history = asset.asset_history()
        shown = [history["summary"]["statement"],
                 history["fidelity"]["custody"]["statement"],
                 history["fidelity"]["verification"]]
        shown += [n["statement"] for n in history["fidelity"]["not_recorded"]]
        shown += [k["statement"] for k in history["fidelity"]["events"]]
        shown += [g["meaning"] for g in history["fidelity"]["evidence_grades"]]
        for text in shown:
            self.assertNotIn("`", text)
            self.assertNotIn("fidelity.", text)

    def test_a_rewritten_disposal_approver_is_visible(self):
        """The verification pass's blocking finding, pinned.

        `disposal_approved_by` is an ordinary input on the Odoo form. The
        first draft graded the approval `guarded_record` and DROPPED its
        tracking rows as superseded — so an asset manager could change who
        approved a disposal and the history showed the new name, graded as
        protected, with the only sign of the edit hidden.
        """
        other = self.env["res.users"].create({
            "name": "History Other Approver",
            "login": "history-other-approver"})
        asset = self._asset()
        asset.write({"disposal_approved_by": self.env.uid,
                     "disposal_approved_date": "2026-03-01 10:00:00"})
        self._flush_tracking()
        events = asset.asset_history()["events"]
        approvals = [e for e in events if e["type"] == "disposal_approved"]
        self.assertEqual(len(approvals), 1, "the first stamping, once")
        self.assertEqual(approvals[0]["evidence"], "editable_record")
        self.assertFalse([e for e in events
                          if e["type"] == "disposal_recorded"])

        asset.write({"disposal_approved_by": other.id})
        self._flush_tracking()
        events = asset.asset_history()["events"]
        approval = next(e for e in events if e["type"] == "disposal_approved")
        self.assertEqual(approval["actor"]["id"], other.id)
        self.assertTrue(approval["detail"]["is_current_value"])
        rewrite = next(e for e in events if e["type"] == "disposal_recorded")
        change = next(c for c in rewrite["detail"]["changes"]
                      if c["field"] == "disposal_approved_by")
        self.assertEqual(change["old"], self.env.user.name)
        self.assertEqual(change["new"], "History Other Approver")
        self.assertEqual(rewrite["evidence"], "chatter")

    def test_a_message_with_no_author_names_nobody(self):
        """Not its `create_uid`, which every message has.

        A change of CONDITION, because this is about a message-log line and
        since handoff 30 a change of status is not one: its event's record
        is an `nrs.asset.event`, whose id this test would have written into
        `mail_message` as though it were a message's.
        """
        asset = self._asset()
        asset.write({"condition": "poor"})
        self._flush_tracking()
        event = next(e for e in asset.asset_history()["events"]
                     if e["type"] == "condition_changed")
        self.assertEqual(event["record"]["model"], "mail.message")
        self.assertIsNotNone(event["actor"])
        self.env.cr.execute(
            "UPDATE mail_message SET author_id = NULL WHERE id = %s",
            (event["record"]["id"],))
        self.env.invalidate_all()
        event = next(e for e in asset.asset_history()["events"]
                     if e["type"] == "condition_changed")
        self.assertIsNone(event["actor"])
        self.assertIsNone(event["actor_name"])

    def test_a_record_with_no_instant_is_omitted_and_counted(self):
        """One undated row must not cost the asset its whole history.

        A change of condition, for the reason given in the test above.
        """
        asset = self._asset()
        asset.write({"condition": "poor"})
        self._flush_tracking()
        history = asset.asset_history()
        self.assertEqual(history["fidelity"]["undated_records_omitted"], 0)
        event = next(e for e in history["events"]
                     if e["type"] == "condition_changed")
        self.assertEqual(event["record"]["model"], "mail.message")
        self.env.cr.execute(
            "UPDATE mail_message SET date = NULL WHERE id = %s",
            (event["record"]["id"],))
        self.env.invalidate_all()
        history = asset.asset_history()
        self.assertFalse([e for e in history["events"]
                          if e["type"] == "condition_changed"])
        self.assertEqual(history["fidelity"]["undated_records_omitted"], 1)

    def _a_request_on(self, asset):
        req = self.env["request.request"].search(
            [("nrs_asset_id", "!=", False), ("name", "!=", False)], limit=1)
        if not req:
            self.skipTest("no request on this database to point at an asset")
        self.env.cr.execute(
            "UPDATE request_request SET nrs_asset_id = %s WHERE id = %s",
            (asset.id, req.id))
        self.env.invalidate_all()
        return req

    def test_a_request_is_an_event_without_its_reference(self):
        """The request belongs to `requests:read`; this is `assets:read`.
        And a withheld reference SAYS it is withheld — a bare null would
        read as a request that has no reference."""
        asset = self._asset()
        req = self._a_request_on(asset)
        event = next(e for e in asset.asset_history()["events"]
                     if e["type"] == "maintenance_request")
        self.assertEqual(event["summary"], "Maintenance request raised")
        self.assertNotIn(req.name, repr(event))
        self.assertIsNone(event["detail"]["reference"])
        self.assertIs(event["detail"]["reference_withheld"], True)

    def test_a_request_carries_its_reference_for_a_caller_who_may_read_it(
            self):
        """Handoff 30 §D1. It was withheld from everybody on the grounds
        that a route cannot see its caller's scopes, which was false. The
        ROUTE decides; the builder publishes what it is told to."""
        asset = self._asset()
        req = self._a_request_on(asset)
        event = next(
            e for e in asset.asset_history(
                request_references=True)["events"]
            if e["type"] == "maintenance_request")
        self.assertEqual(event["detail"]["reference"], req.name)
        self.assertIs(event["detail"]["reference_withheld"], False)
        self.assertEqual(event["summary"],
                         "Maintenance request %s raised" % req.name)

    def test_the_statement_counts_what_nobody_can_alter(self):
        """Three things happen and two of them have a record nobody can
        alter. Until handoff 30 this test changed a STATUS for its
        alterable event; a change of status is now the other kind, so the
        alterable one is a change of condition, which is still only a
        message-log line."""
        asset = self._asset(custodian_id=self.alice.id)
        asset.with_context(
            cadra_approval_exempt="test").write({"custodian_id": self.bob.id})
        asset.write({"state": "in_repair"})
        asset.write({"condition": "poor"})
        self._flush_tracking()
        statement = asset.asset_history()["summary"]["statement"]
        self.assertIn("3 recorded event(s)", statement)
        self.assertIn("2 of them rest on a record that nobody can edit",
                      statement)

    def test_the_verification_statement_matches_the_button(self):
        """The sentence is shown to a client. Handoff 28 changed what the
        Verify button does and the sentence went on saying the old thing;
        handoff 30 changed it again — each press is now a record of its
        own — and this is what stops the sentence being left behind a
        second time."""
        asset = self._asset()
        asset.action_verify(notes="sighted")
        self._flush_tracking()
        self.assertEqual(asset.last_verified_by, self.env.user)
        history = asset.asset_history()
        statement = history["fidelity"]["verification"]
        self.assertIn("records who checked the asset", statement)
        self.assertIn("each time it is pressed", statement)
        self.assertIn("cannot be edited or deleted", statement)
        self.assertIn("clears the verifier", statement)
        self.assertIn("keeps only the most recent", statement)
        self.assertNotIn("nothing else", statement)
        self.assertNotIn("survive only", statement)
        verified = [e for e in history["events"] if e["type"] == "verified"]
        self.assertEqual(len(verified), 1,
                         "the event, and not its two message-log rows too")
        verified = verified[0]
        self.assertEqual(verified["actor"]["id"], self.env.uid)
        self.assertEqual(verified["evidence"], "append_only")
        self.assertEqual(verified["record"]["model"], "nrs.asset.event")
        self.assertEqual(verified["detail"]["notes"], "sighted")
        self.assertIs(verified["detail"]["verifier_recorded"], True)

    def test_a_changed_vendor_is_still_only_a_message_log_line(self):
        """Tracked since handoff 28 and deliberately NOT promoted in handoff
        30: the importer rewrites it on every re-import."""
        asset = self._asset(purchase_vendor="Acme")
        asset.write({"purchase_vendor": "Apex"})
        self._flush_tracking()
        events = [e for e in asset.asset_history()["events"]
                  if e["type"] == "provenance_changed"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["evidence"], "chatter",
                         "visible, which it was not; not protected")
        self.assertEqual(events[0]["record"]["model"], "mail.message")
        self.assertEqual(
            {c["field"] for c in events[0]["detail"]["changes"]},
            {"purchase_vendor"})

    def test_every_grade_used_is_a_grade_defined(self):
        asset = self._asset()
        asset.with_context(
            cadra_approval_exempt="test").write({"custodian_id": self.alice.id, "state": "in_repair"})
        self._flush_tracking()
        history = asset.asset_history()
        defined = [g["grade"] for g in history["fidelity"]["evidence_grades"]]
        self.assertEqual(defined[0], "append_only", "strongest first")
        for event in history["events"]:
            self.assertIn(event["evidence"], defined)
        self.assertEqual(sorted(history["summary"]["by_evidence"]),
                         sorted(defined))


@tagged("post_install", "-at_install")
class TestAssetHistoryRecordedEvents(AssetHistoryCase):
    """Since handoff 30 a verification, a change of status and a change to
    the GRN, purchase order or SAP asset number each have a record nobody
    can alter — and where one exists IT is the event.

    Two halves, as for moves. The first is something that happens NOW: an
    `nrs.asset.event`, append-only, with the message-log row of the same
    write folded into it rather than listed beside it. The second is
    something that happened BEFORE the recorder existed, which is every
    status change and every verification on every tenant today, and must
    still be graded as the message-log line it is — simulated by removing
    the event row with SQL, which is the only way a row of that model can
    be made to not exist.

    **Everything in one test shares one `create_date`**, because that is
    the transaction's stamp and a test is one transaction — and the fold is
    matched on exactly that stamp. So a test that needs an OLD message-log
    line beside a NEW event has to move the old message's stamp by SQL as
    well, or the new event folds the old line away and the test passes for
    the wrong reason.
    """

    def _forget_the_events(self, asset):
        """As it was before the recorder: it happened, and no row says so."""
        self.env.flush_all()
        self.env.cr.execute(
            "DELETE FROM nrs_asset_event WHERE asset_id = %s", (asset.id,))
        self.env.invalidate_all()

    def _age_the_message_log(self, asset):
        """Put this asset's message-log lines in an earlier transaction."""
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE mail_message SET create_date = create_date "
            "- interval '1 day' WHERE model = 'nrs.asset' AND res_id = %s",
            (asset.id,))
        self.env.invalidate_all()

    def _of_type(self, asset, etype):
        return [e for e in asset.asset_history()["events"]
                if e["type"] == etype]

    # ── a change of status ───────────────────────────────────────────

    def test_a_status_change_is_listed_once(self):
        """`state` is tracked too. One act, two records, one line."""
        asset = self._asset()
        asset.write({"state": "in_repair"})
        self._flush_tracking()
        changes = self._of_type(asset, "status_changed")
        self.assertEqual(len(changes), 1,
                         [(c["evidence"], c["summary"]) for c in changes])
        change = changes[0]
        self.assertEqual(change["evidence"], "append_only")
        self.assertEqual(change["record"]["model"], "nrs.asset.event")
        self.assertEqual(change["detail"]["from"], "active")
        self.assertEqual(change["detail"]["to"], "in_repair")
        self.assertEqual(change["summary"], "Active → Under Repair")
        self.assertEqual(change["actor"]["id"], self.env.uid)
        self.assertEqual(change["source"], "direct")
        self.assertFalse(change["reconstructed"])

    def test_the_fold_takes_only_the_status_out_of_the_message(self):
        """A write that changes the status AND something else leaves one
        message with two tracked values. Only the one the event records is
        folded away; the other is still a line."""
        asset = self._asset()
        asset.write({"state": "in_repair", "condition": "poor"})
        self._flush_tracking()
        self.assertEqual(len(self._of_type(asset, "status_changed")), 1)
        condition = self._of_type(asset, "condition_changed")
        self.assertEqual(len(condition), 1)
        self.assertEqual(condition[0]["evidence"], "chatter")
        self.assertEqual(
            [c["field"] for c in condition[0]["detail"]["changes"]],
            ["condition"])

    def test_marking_missing_says_why(self):
        """*Why is this asset missing* — evidence of what was said at the
        time, not a note somebody can tidy up afterwards."""
        asset = self._asset()
        asset.action_mark_missing(reason="not in the store at handover")
        self._flush_tracking()
        change = self._of_type(asset, "status_changed")
        self.assertEqual(len(change), 1)
        self.assertEqual(change[0]["detail"]["reason"],
                         "not in the store at handover")
        self.assertEqual(change[0]["source"], "action")
        self.assertEqual(change[0]["evidence"], "append_only")

    def test_a_condemn_names_who_and_why_and_still_shows_the_condition(self):
        """`disposal_executor`, closed going forward: the actor of the
        change into Disposed is who carried the disposal out. The CONDITION
        it set in the same write has no record of its own and is still a
        message-log line — folding the message away whole would have lost
        it."""
        asset = self._asset()
        asset.action_condemn(reason="fire damage, beyond repair")
        self._flush_tracking()
        status = self._of_type(asset, "status_changed")
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0]["evidence"], "append_only")
        self.assertEqual(status[0]["detail"]["to"], "disposed")
        self.assertEqual(status[0]["detail"]["reason"],
                         "fire damage, beyond repair")
        self.assertEqual(status[0]["actor"]["id"], self.env.uid)
        condition = self._of_type(asset, "condition_changed")
        self.assertEqual(len(condition), 1)
        self.assertEqual(condition[0]["evidence"], "chatter")

    def test_a_status_change_from_before_the_recorder_is_still_chatter(self):
        asset = self._asset()
        asset.write({"state": "in_repair"})
        self._flush_tracking()
        self._forget_the_events(asset)
        changes = self._of_type(asset, "status_changed")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["evidence"], "chatter")
        self.assertEqual(changes[0]["record"]["model"], "mail.message")

    def test_old_and_new_status_changes_sit_in_one_list_graded_differently(
            self):
        asset = self._asset()
        asset.write({"state": "in_repair"})
        self._flush_tracking()
        self._forget_the_events(asset)
        self._age_the_message_log(asset)
        asset.write({"state": "active"})
        self._flush_tracking()
        changes = self._of_type(asset, "status_changed")
        self.assertEqual(sorted(c["evidence"] for c in changes),
                         ["append_only", "chatter"],
                         [(c["evidence"], c["summary"]) for c in changes])

    def test_an_event_written_under_a_test_credential_says_so(self):
        """`source: test`, decided from the ACTING USER and over whatever
        the route declared — custody's rule, reached through the abstract
        guard. The override sits on the MIXIN in this module and the model
        is declared a module below, so that it reaches `nrs.asset.event` at
        all is a fact about how the registry was built, and is checked here
        by acting rather than by reading the class."""
        client = self.create_api_client({
            "name": "history probe test credential",
            "client_id": "historyprobe_%s" % uuid.uuid4().hex[:8],
            "scopes": "assets:read assets:write",
        })
        asset = self._asset()
        # What a route does: the credential's own user, with sudo.
        asset.with_user(client.user_id).sudo().with_context(
            cadra_event_source="api_mark_missing",
        ).action_mark_missing(reason="written by the suite")
        self._flush_tracking()
        change = self._of_type(asset, "status_changed")
        self.assertEqual(len(change), 1)
        self.assertEqual(change[0]["source"], "test")
        self.assertEqual(change[0]["actor"]["id"], client.user_id.id)
        self.assertEqual(change[0]["detail"]["reason"],
                         "written by the suite")

    # ── a verification ───────────────────────────────────────────────

    def test_two_checks_on_one_day_are_two_lines(self):
        asset = self._asset()
        with freeze_time("2031-02-01 09:00:00"):
            asset.action_verify(notes="sighted")
            self._flush_tracking()
        with freeze_time("2031-02-01 15:00:00"):
            asset.action_verify()
            self._flush_tracking()
        checks = [e for e in self._later(
            asset.asset_history(newest_first=False))
            if e["type"] == "verified"]
        self.assertEqual(len(checks), 2)
        self.assertEqual({c["evidence"] for c in checks}, {"append_only"})
        self.assertEqual(checks[0]["detail"]["notes"], "sighted")
        self.assertIsNone(checks[1]["detail"]["notes"])
        self.assertEqual(checks[1]["detail"]["previous_verified_on"],
                         "2031-02-01")

    def test_a_written_date_is_never_listed_as_a_verification(self):
        """The message log calls ANY change of `last_verified_date`
        "verified". Folded away, so that a PATCHed date reads as what it
        is — and names whoever wrote it without saying they checked
        anything."""
        asset = self._asset()
        asset.write({"last_verified_date": "2026-06-01"})
        self._flush_tracking()
        self.assertFalse(self._of_type(asset, "verified"))
        written = self._of_type(asset, "verification_date_set")
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0]["evidence"], "append_only")
        self.assertEqual(written[0]["detail"]["verified_on"], "2026-06-01")
        self.assertIs(written[0]["detail"]["verifier_recorded"], False)
        self.assertIn("does not say who checked", written[0]["summary"])
        self.assertEqual(written[0]["actor"]["id"], self.env.uid)

    def test_a_verification_from_before_the_recorder_is_still_chatter(self):
        asset = self._asset()
        asset.action_verify()
        self._flush_tracking()
        self._forget_the_events(asset)
        checks = self._of_type(asset, "verified")
        self.assertTrue(checks)
        self.assertEqual({c["evidence"] for c in checks}, {"chatter"})

    # ── a change of reference ────────────────────────────────────────

    def test_a_changed_grn_is_listed_once_and_cannot_be_altered(self):
        asset = self._asset(grn_reference="GRN-1")
        asset.write({"grn_reference": "GRN-2"})
        self._flush_tracking()
        changes = self._of_type(asset, "provenance_changed")
        self.assertEqual(len(changes), 1,
                         [(c["evidence"], c["summary"]) for c in changes])
        self.assertEqual(changes[0]["evidence"], "append_only")
        self.assertEqual(changes[0]["record"]["model"], "nrs.asset.event")
        self.assertEqual(changes[0]["detail"]["changes"], [{
            "field": "grn_reference",
            "label": self.Asset._fields["grn_reference"].string,
            "old": "GRN-1", "new": "GRN-2"}])

    def test_a_grn_and_a_vendor_in_one_write_are_two_lines_of_two_grades(
            self):
        """One message, two tracked values, and only one of them has a
        better record. This is the write the old single test made."""
        asset = self._asset(grn_reference="GRN-1")
        asset.write({"grn_reference": "GRN-2", "purchase_vendor": "Acme"})
        self._flush_tracking()
        changes = self._of_type(asset, "provenance_changed")
        by_grade = {c["evidence"]: c for c in changes}
        self.assertEqual(sorted(by_grade), ["append_only", "chatter"],
                         [(c["evidence"], c["summary"]) for c in changes])
        self.assertEqual(
            [c["field"] for c in by_grade["append_only"]["detail"]["changes"]],
            ["grn_reference"])
        self.assertEqual(
            [c["field"] for c in by_grade["chatter"]["detail"]["changes"]],
            ["purchase_vendor"])

    def test_a_changed_sap_number_is_listed(self):
        """It is not tracked, so until handoff 30 a change to it left
        nothing anywhere."""
        asset = self._asset()
        asset._set_sap_master({"sap_asset_number": "400000993301"})
        self._flush_tracking()
        changes = self._of_type(asset, "provenance_changed")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["evidence"], "append_only")
        self.assertEqual(changes[0]["detail"]["changes"][0]["field"],
                         "sap_asset_number")
        self.assertEqual(changes[0]["detail"]["changes"][0]["new"],
                         "400000993301")

    def test_a_grn_change_from_before_the_recorder_is_still_chatter(self):
        asset = self._asset(grn_reference="GRN-1")
        asset.write({"grn_reference": "GRN-2"})
        self._flush_tracking()
        self._forget_the_events(asset)
        changes = self._of_type(asset, "provenance_changed")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["evidence"], "chatter")

    # ── from when ────────────────────────────────────────────────────

    def test_the_response_says_from_when_for_each_kind(self):
        kinds = self._asset().asset_history()["fidelity"]["events"]
        self.assertEqual(
            [k["event"] for k in kinds],
            ["verified", "verification_date_set", "status_changed",
             "provenance_changed", "warranty_changed", "affix_refused"],
            "by the name the EVENT is published under, not the stored type")
        for kind in kinds:
            self.assertEqual(
                set(kind), {"event", "recording_began_at", "statement"})
            self.assertTrue(kind["statement"])

    def test_from_when_is_answered_per_kind(self):
        """They share a table and did not necessarily begin together."""
        asset = self._asset()
        asset.write({"state": "in_repair"})
        self.env.flush_all()
        # Raw SQL: `create_date` is the transaction's clock, which
        # `freeze_time` cannot move, and the model refuses `write`.
        self.env.cr.execute(
            "UPDATE nrs_asset_event SET create_date = '2001-02-03 04:05:06' "
            "WHERE asset_id = %s", (asset.id,))
        self.env.invalidate_all()
        kinds = {k["event"]: k
                 for k in asset.asset_history()["fidelity"]["events"]}
        self.assertEqual(kinds["status_changed"]["recording_began_at"],
                         "2001-02-03T04:05:06")
        self.assertIn("2001-02-03 04:05 UTC",
                      kinds["status_changed"]["statement"])
        for other in ("verified", "verification_date_set",
                      "provenance_changed"):
            self.assertNotEqual(
                kinds[other]["recording_began_at"], "2001-02-03T04:05:06",
                "%s did not begin when status changes did" % other)

    def test_a_kind_nobody_has_recorded_says_so(self):
        """The table is EMPTIED first, by raw SQL, inside this test's
        transaction and rolled back with it: CI runs the HTTP suite before
        this one, and the events it writes are permanent by design."""
        asset = self._asset()
        self.env.flush_all()
        self.env.cr.execute("DELETE FROM nrs_asset_event")
        self.env.invalidate_all()
        asset.write({"state": "in_repair"})
        kinds = {k["event"]: k
                 for k in asset.asset_history()["fidelity"]["events"]}
        self.assertTrue(kinds["status_changed"]["recording_began_at"])
        self.assertTrue(
            kinds["status_changed"]["statement"].startswith("From "))
        for other in ("verified", "verification_date_set",
                      "provenance_changed"):
            self.assertIsNone(kinds[other]["recording_began_at"])
            self.assertTrue(kinds[other]["statement"].startswith(
                "No record of this kind has been written"), other)
        # The refusal has its own empty wording, like the warranty's: there
        # is no message-log line to send a reader looking for — a refusal
        # used to leave nothing at all.
        self.assertIsNone(kinds["affix_refused"]["recording_began_at"])
        self.assertTrue(kinds["affix_refused"]["statement"].startswith(
            "No affix confirmation has been refused"))
        self.assertNotIn("message log", kinds["affix_refused"]["statement"])

    def test_what_is_never_recorded_no_longer_claims_these_leave_nothing(
            self):
        """`not_recorded` said a change to a GRN reference "leaves nothing"
        and that the act of disposing "records no person". Both stopped
        being true in handoff 30, and nothing fails when a sentence on a
        client's screen goes stale unless something holds it."""
        named = {n["event"]: n["statement"] for n in
                 self._asset().asset_history()["fidelity"]["not_recorded"]}
        self.assertIn("before", named["provenance_change"])
        self.assertIn("nobody can alter", named["provenance_change"])
        self.assertIn("before", named["disposal_executor"])
        self.assertIn("names who made it", named["disposal_executor"])
        self.assertIn("other than the SAP asset number",
                      named["sap_change"])


@tagged("post_install", "-at_install")
class TestAssetHistoryTags(AssetHistoryCase):

    def test_print_and_affix_name_who_recorded_them(self):
        asset = self._asset()
        tag = asset.tag_ids[:1]
        tag.with_context(cadra_tag_capture=True).write({
            "label_state": "affixed",
            "printed_date": "2031-03-01 09:00:00",
            "printed_by": self.env.uid,
            "affixed_date": "2031-03-02 09:00:00",
            "affixed_by": self.env.uid,
            "affixed_by_name": "A Tag Unit Operative",
        })
        later = self._later(asset.asset_history(newest_first=False))
        self.assertEqual([e["type"] for e in later],
                         ["tag_printed", "tag_affixed"])
        affixed = later[1]
        self.assertEqual(affixed["evidence"], "guarded_record")
        self.assertEqual(affixed["actor"]["id"], self.env.uid)
        # Who FITTED it is free text and not a Cadra user: detail, never actor.
        self.assertEqual(affixed["detail"]["fitted_by_name"],
                         "A Tag Unit Operative")
        self.assertNotEqual(affixed["actor_name"], "A Tag Unit Operative")

    def test_a_refused_affix_is_a_line_before_the_confirmation(self):
        """Handoff 51: the wrong-then-right sequence is visible, in order.

        Both acts land in ONE frozen second, which is the hard case: the
        refusal must still read first, and that is `_RANK` — the refusal is
        deliberately ranked above `tag_affixed` in `_EVENT_TITLES`. The
        refusal recorder writes on its own cursor; under the test registry
        that cursor is a TestCursor over this very transaction, so the row
        is visible here and rolled back with the test.
        """
        asset = self._asset()
        tag = asset.tag_ids[:1]
        with freeze_time("2031-03-02 09:00:00"):
            # A bare try/except, NOT `assertRaises`: Odoo's `assertRaises`
            # wraps its block in a savepoint and rolls back to it, which
            # unwound the recorder's same-cursor test-mode write — the
            # production defect in miniature, caught by this test's own
            # first run (report 51 §2). The exception here is pure Python,
            # raised before any failing SQL, so the cursor needs no
            # savepoint to stay usable.
            try:
                tag._mark_affixed("NOT-THE-TAG")
                self.fail("a wrong number must be refused")
            except ValidationError as caught:
                # The refusal text is handoff 39's ruling, verbatim: it
                # names the expected number. Unchanged by the recording.
                self.assertIn("NOT-THE-TAG", str(caught))
                self.assertIn(tag.name, str(caught))
            self.assertEqual(tag.label_state, "issued",
                             "a refusal moves nothing on the label")
            tag._mark_affixed(tag.name, affixed_by_name="Second Try")
        later = self._later(asset.asset_history(newest_first=False))
        self.assertEqual([e["type"] for e in later],
                         ["affix_refused", "tag_affixed"])
        refusal = later[0]
        self.assertEqual(refusal["evidence"], "append_only")
        self.assertEqual(refusal["detail"]["scanned"], "NOT-THE-TAG")
        self.assertIn("NOT-THE-TAG", refusal["summary"])
        self.assertEqual(refusal["actor"]["id"], self.env.uid)

    def test_a_same_day_scrap_does_not_sort_before_the_tags_own_issue(self):
        """A bare date sorts at midnight — before the tag existed."""
        asset = self._asset()
        tag = asset.tag_ids[:1]
        # Since handoff 38 a replacement is REQUESTED by one person and
        # decided by another, and the model refuses a decision on a tag
        # nobody asked to replace. The requester here is a second user;
        # this test's own user is the approver it names.
        requester = self.env["res.users"].create({
            "name": "History Tag Requester",
            "login": "history-tag-requester-%s" % uuid.uuid4().hex[:8],
            "email": "history-tag-requester@example.com"})
        tag.with_user(requester).sudo().action_request_replacement(
            reason="damaged", approver=self.env.user)
        tag.action_approve_replacement()
        events = asset.asset_history(newest_first=False)["events"]
        mine = [e["type"] for e in events
                if e["record"] == {"model": "nrs.asset.tag.label",
                                   "id": tag.id}]
        self.assertEqual(mine, ["tag_issued", "tag_scrapped"])
        scrapped = next(e for e in events if e["type"] == "tag_scrapped")
        self.assertEqual(scrapped["at_precision"], "second")
        self.assertEqual(scrapped["actor"]["id"], self.env.uid)

    def test_a_scrap_with_only_a_date_says_day(self):
        asset = self._asset()
        tag = asset.tag_ids[:1]
        tag.with_context(cadra_tag_capture=True).write(
            {"scrapped_date": "2031-04-01"})
        scrapped = next(e for e in asset.asset_history()["events"]
                        if e["type"] == "tag_scrapped")
        self.assertEqual(scrapped["at"], "2031-04-01")
        self.assertEqual(scrapped["at_precision"], "day")
        self.assertIsNone(scrapped["actor"])


@tagged("post_install", "-at_install")
class TestAssetHistoryMoves(AssetHistoryCase):
    """Since handoff 28 a move has a record of its own, and it is the event.

    Two halves. The first is a move made NOW: an `nrs.asset.movement`,
    append-only, with the transfer document and the chatter row of the same
    act folded into it. The second is a move made BEFORE the recorder
    existed, which is still most of `nrs19` and must still be graded as the
    weaker record it is — simulated here by removing the movement row with
    SQL, which is the only way a row of that model can be made to not exist.
    """

    def _move_like_the_route(self, asset, to):
        """What `POST /assets/<id>/move` does, in one transaction."""
        transfer = self.env["nrs.asset.transfer"].create({
            "asset_id": asset.id,
            "from_location_id": asset.location_id.id,
            "to_location_id": to.id,
            "reason": "history test move",
            "state": "done",
        })
        asset.with_context(
            cadra_movement_source="api_move",
            cadra_movement_reason="history test move",
            cadra_movement_transfer_id=transfer.id,
            # The route this imitates raises an approval REQUEST on a tenant
            # that wants one; what it does after the approval is exactly the
            # write below. These tests are about what the history says of a
            # move, not about who agreed to it, so they declare the fixture
            # exemption and write the move directly. `test_change_request.py`
            # owns the approval path.
            cadra_approval_exempt="test",
        ).write({"location_id": to.id})
        self._flush_tracking()
        return transfer

    def _forget_the_movements(self, asset, keep_opening=True):
        """As it was before the recorder: the move happened, no row says so."""
        self.env.flush_all()
        self.env.cr.execute(
            "DELETE FROM nrs_asset_movement WHERE asset_id = %s"
            + (" AND from_location_id IS NOT NULL" if keep_opening else ""),
            (asset.id,))
        self.env.invalidate_all()

    def _moves(self, asset):
        """Real moves — not the opening 'Placed at', which has no `from`."""
        return [e for e in asset.asset_history()["events"]
                if e["type"] == "location_moved"
                and e["detail"]["from_location"]]

    # ── a move made now ──────────────────────────────────────────────

    def test_a_move_is_append_only_and_folds_in_its_paperwork(self):
        asset = self._asset()
        transfer = self._move_like_the_route(asset, self.place_b)
        moves = self._moves(asset)
        self.assertEqual(len(moves), 1, "three records of one act: one line")
        move = moves[0]
        self.assertEqual(move["evidence"], "append_only")
        self.assertEqual(move["record"]["model"], "nrs.asset.movement")
        self.assertEqual(move["source"], "api_move")
        self.assertEqual(move["detail"]["reason"], "history test move")
        self.assertEqual(move["detail"]["transfer"]["reference"],
                         transfer.name)
        self.assertEqual(move["detail"]["records"],
                         ["nrs.asset.movement", "nrs.asset.transfer",
                          "mail.message"])
        self.assertEqual(move["actor"]["id"], self.env.user.id)

    def test_a_plain_write_is_append_only_too_and_invents_no_transfer(self):
        """PATCH, the Odoo form, an import. The quiet door, no longer quiet."""
        asset = self._asset()
        asset.with_context(
            cadra_approval_exempt="test").write({"location_id": self.place_b.id})
        self._flush_tracking()
        moves = self._moves(asset)
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0]["evidence"], "append_only")
        self.assertEqual(moves[0]["source"], "direct")
        self.assertIsNone(moves[0]["detail"]["transfer"])
        self.assertIn("History location B", moves[0]["summary"])

    def test_the_reference_outlives_the_transfer_document(self):
        asset = self._asset()
        transfer = self._move_like_the_route(asset, self.place_b)
        reference = transfer.name
        transfer.unlink()
        self.env.invalidate_all()
        move = self._moves(asset)[0]
        self.assertEqual(move["detail"]["transfer"]["reference"], reference)
        self.assertIsNone(move["detail"]["transfer"]["id"])
        self.assertEqual(move["detail"]["records"][:1],
                         ["nrs.asset.movement"])
        self.assertNotIn("nrs.asset.transfer", move["detail"]["records"])

    def test_the_opening_placement_is_listed_and_is_not_history(self):
        asset = self._asset()
        history = asset.asset_history(newest_first=False)
        placed = [e for e in history["events"]
                  if e["type"] == "location_moved"]
        self.assertEqual(len(placed), 1)
        self.assertTrue(placed[0]["summary"].startswith("Placed at"))
        self.assertEqual(placed[0]["evidence"], "append_only")
        self.assertEqual(history["summary"]["events_after_registration"], 0)

    def test_a_deleted_location_is_a_move_to_nowhere(self):
        asset = self._asset(location_id=self.place_c.id)
        self.place_c.unlink()
        self.env.invalidate_all()
        move = self._moves(asset)[0]
        self.assertEqual(move["source"], "location_deleted")
        self.assertTrue(move["summary"].endswith("nowhere"))
        self.assertEqual(move["evidence"], "append_only")

    # ── a move made before the recorder existed ──────────────────────

    def test_an_old_move_with_a_transfer_row_is_still_only_editable(self):
        asset = self._asset()
        transfer = self._move_like_the_route(asset, self.place_b)
        self._forget_the_movements(asset)
        moves = self._moves(asset)
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0]["evidence"], "editable_record")
        self.assertEqual(moves[0]["detail"]["transfer"]["reference"],
                         transfer.name)
        self.assertEqual(moves[0]["detail"]["records"],
                         ["nrs.asset.transfer", "mail.message"])

    def test_an_old_move_with_no_transfer_row_is_still_only_chatter(self):
        asset = self._asset()
        asset.with_context(
            cadra_approval_exempt="test").write({"location_id": self.place_b.id})
        self._flush_tracking()
        self._forget_the_movements(asset)
        moves = self._moves(asset)
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0]["evidence"], "chatter")
        self.assertIsNone(moves[0]["detail"]["transfer"])

    def test_an_old_transfer_with_no_chatter_row_names_nobody(self):
        """`create_uid` raised the transfer. It is not who moved the asset."""
        asset = self._asset()
        transfer = self.env["nrs.asset.transfer"].create({
            "asset_id": asset.id,
            "from_location_id": self.place_a.id,
            "to_location_id": self.place_c.id,
            "state": "done",
        })
        move = next(m for m in self._moves(asset)
                    if m["record"]["id"] == transfer.id)
        self.assertIsNone(move["actor"])
        self.assertIsNone(move["actor_name"])
        self.assertEqual(move["detail"]["transfer"]["recorded_by"]["id"],
                         self.env.uid)
        self.assertEqual(move["detail"]["records"], ["nrs.asset.transfer"])
        self.assertTrue(
            move["detail"]["at_is_when_the_transfer_was_recorded"])
        self.assertIn("when the transfer was recorded", move["summary"])

    def test_a_located_asset_with_no_record_says_so(self):
        """What EVERY asset placed before handoff 28 will show: it is
        somewhere, and no row says how it came to be there."""
        asset = self._asset()
        self._forget_the_movements(asset, keep_opening=False)
        location = asset.asset_history()["fidelity"]["location"]
        self.assertEqual(location["movements"], 0)
        self.assertTrue(location["located_before_first_movement"])
        self.assertIn("already somewhere", location["statement"])

    def test_a_first_movement_with_a_from_says_so_too(self):
        asset = self._asset()
        asset.with_context(
            cadra_approval_exempt="test").write({"location_id": self.place_b.id})
        self._forget_the_movements(asset, keep_opening=False)  # all of them
        asset.with_context(
            cadra_approval_exempt="test").write({"location_id": self.place_c.id})           # first row
        location = asset.asset_history()["fidelity"]["location"]
        self.assertEqual(location["movements"], 1)
        self.assertTrue(location["located_before_first_movement"])

    def test_an_asset_placed_under_the_recorder_is_not_flagged(self):
        location = self._asset().asset_history()["fidelity"]["location"]
        self.assertFalse(location["located_before_first_movement"])

    def test_a_transfer_of_another_asset_cannot_be_borrowed(self):
        """The link arrives in the context, and a caller controls that."""
        mine, theirs = self._asset(), self._asset()
        approved = self.env["nrs.asset.transfer"].create({
            "asset_id": theirs.id,
            "from_location_id": self.place_a.id,
            "to_location_id": self.place_b.id,
            "state": "done", "approved_by": self.env.uid})
        mine.with_context(
            cadra_movement_source="transfer",
            cadra_movement_transfer_id=approved.id,
            cadra_approval_exempt="test",
        ).write({"location_id": self.place_b.id})
        move = self._moves(mine)[0]
        self.assertIsNone(move["detail"]["transfer"])
        self.assertEqual(move["source"], "direct",
                         "`transfer` claimed with no transfer of its own")

    def test_a_caller_cannot_file_a_move_under_test(self):
        asset = self._asset()
        asset.with_context(cadra_movement_source="test",
                          cadra_approval_exempt="test").write(
            {"location_id": self.place_b.id})
        self.assertEqual(self._moves(asset)[0]["source"], "direct")

    def test_the_transfer_block_says_it_is_read_from_an_editable_document(self):
        asset = self._asset()
        self._move_like_the_route(asset, self.place_b)
        move = self._moves(asset)[0]
        self.assertEqual(move["evidence"], "append_only")
        self.assertEqual(move["detail"]["transfer"]["evidence"],
                         "editable_record")

    def test_a_move_into_a_place_since_deleted_is_still_one_line(self):
        """The FK nulls the movement's location id; the tracking value keeps
        the original. The join falls back to the recorded name."""
        asset = self._asset()
        asset.with_context(
            cadra_approval_exempt="test").write({"location_id": self.place_c.id})
        self._flush_tracking()
        asset.with_context(
            cadra_approval_exempt="test").write({"location_id": self.place_b.id})
        self._flush_tracking()
        self.place_c.unlink()
        self.env.invalidate_all()
        moves = self._moves(asset)
        self.assertEqual(len(moves), 2, [m["summary"] for m in moves])
        self.assertEqual({m["evidence"] for m in moves}, {"append_only"})

    def test_two_old_moves_between_the_same_places_stay_two(self):
        """The LEGACY join, each side used once."""
        asset = self._asset()
        self._move_like_the_route(asset, self.place_b)
        asset.with_context(
            cadra_approval_exempt="test").write({"location_id": self.place_a.id})
        self._flush_tracking()
        asset.with_context(
            cadra_approval_exempt="test").write({"location_id": self.place_b.id})
        self._flush_tracking()
        self._forget_the_movements(asset)
        moves = self._moves(asset)
        self.assertEqual(len(moves), 3)
        self.assertEqual(sorted(m["evidence"] for m in moves),
                         ["chatter", "chatter", "editable_record"])

    def test_a_transfer_that_is_not_done_is_not_a_move(self):
        asset = self._asset()
        self.env["nrs.asset.transfer"].create({
            "asset_id": asset.id,
            "from_location_id": self.place_a.id,
            "to_location_id": self.place_c.id,
            "state": "draft",
        })
        self.assertFalse(self._moves(asset))
        recorded = [e for e in asset.asset_history()["events"]
                    if e["type"] == "transfer_recorded"]
        self.assertEqual(len(recorded), 1)
        self.assertIn("draft", recorded[0]["summary"])

    def test_old_and_new_moves_sit_in_one_list_graded_differently(self):
        asset = self._asset()
        asset.with_context(
            cadra_approval_exempt="test").write({"location_id": self.place_b.id})
        self._flush_tracking()
        self._forget_the_movements(asset)
        asset.with_context(
            cadra_approval_exempt="test").write({"location_id": self.place_c.id})
        self._flush_tracking()
        self.assertEqual(sorted(m["evidence"] for m in self._moves(asset)),
                         ["append_only", "chatter"])


@tagged("post_install", "-at_install")
class TestAssetHistorySaysWhereItBegins(AssetHistoryCase):

    def test_an_asset_with_no_history_says_so_in_words(self):
        """The defect that produced the handoff was an empty panel."""
        history = self._asset().asset_history()
        self.assertEqual(history["summary"]["events_after_registration"], 0)
        self.assertTrue(history["summary"]["statement"].startswith(
            "There is no recorded history for this asset"))
        # The registration itself is still shown.
        # Registered, tagged and placed — by one `create`, in one
        # transaction. Listed, and none of it a life.
        self.assertEqual({e["type"] for e in history["events"]},
                         {"registered", "tag_issued", "location_moved"})
        self.assertIsNone(history["fidelity"]
                          ["earliest_event_after_registration_at"])

    def test_one_event_ends_the_empty_statement(self):
        asset = self._asset(custodian_id=self.alice.id)
        self.assertEqual(asset.asset_history()["summary"]
                         ["events_after_registration"], 0,
                         "created already assigned: the opening state")
        asset.with_context(
            cadra_approval_exempt="test").write({"custodian_id": self.bob.id})
        summary = asset.asset_history()["summary"]
        self.assertEqual(summary["events_after_registration"], 1)
        self.assertFalse(summary["statement"].startswith("There is no"))

    def test_a_custodian_the_chain_never_saw_arrive_is_flagged(self):
        """Held by somebody, and no link says how: 6,643 assets on nrs19."""
        asset = self._asset()
        self.env.flush_all()
        # Raw SQL on purpose. The ORM cannot produce this state any more —
        # the recorder is in `write` — but every asset assigned before the
        # recorder existed is in it.
        self.env.cr.execute(
            "UPDATE nrs_asset SET custodian_id = %s WHERE id = %s",
            (self.alice.id, asset.id))
        asset.invalidate_recordset()
        custody = asset.asset_history()["fidelity"]["custody"]
        self.assertEqual(custody["links"], 0)
        self.assertTrue(custody["custodian_held_before_first_link"])

    def test_a_first_link_with_a_from_is_flagged_too(self):
        asset = self._asset()
        self._backfilled_link(asset, from_custodian_id=self.bob.id,
                              from_custodian_name=self.bob.name)
        custody = asset.asset_history()["fidelity"]["custody"]
        self.assertTrue(custody["custodian_held_before_first_link"])
        self.assertEqual(custody["reconstructed_links"], 1)
        self.assertEqual(custody["first_link_at"], "2025-01-05T10:00:00")

    def test_an_asset_assigned_under_the_recorder_is_not_flagged(self):
        asset = self._asset()
        asset.with_context(
            cadra_approval_exempt="test").write({"custodian_id": self.alice.id})
        custody = asset.asset_history()["fidelity"]["custody"]
        self.assertFalse(custody["custodian_held_before_first_link"])
        self.assertTrue(custody["recording_began_at"])


@tagged("post_install", "-at_install")
class TestBothPeopleAreInTheRecord(AssetHistoryCase):
    """An approved change names the person who ASKED as well as the one who
    agreed. Handoff 36 §C.

    Vendra's report 43 walked the approval flow handoff 35 built and found
    that the history of an approved move recorded the APPROVER as the actor
    and *the requester appeared nowhere*. That is half of a two-person
    control missing from the artefact the control exists to produce: an
    auditor reading it learns who authorised the move and cannot learn who
    wanted it.

    **`actor` is deliberately unchanged.** It means the same thing on every
    event type — the person the record names as having done it — and the
    approver's click is what moved the asset. Changing its meaning on one
    event is the defect `test_published_names_resolve.py` exists to catch.
    The second person arrives as an additive `approval` block.
    """

    def _two_users(self):
        Users = self.env["res.users"].sudo()
        groups = [(4, self.env.ref("base.group_user").id),
                  (4, self.env.ref(
                      "myservice_asset_register.group_asset_manager").id)]
        out = []
        for login in ("history-36-asker", "history-36-approver"):
            user = Users.search([("login", "=", login)], limit=1)
            if not user:
                user = Users.create({"name": login, "login": login,
                                     "group_ids": groups})
            else:
                user.write({"group_ids": groups})
            out.append(user)
        return out

    def _approved_move(self):
        """Raise a move as one person and approve it as another."""
        asker, approver = self._two_users()
        asset = self._asset(location_id=self.place_a.id)
        req = self.env["nrs.asset.change.request"].with_user(asker).create({
            "asset_id": asset.id,
            "change_type": "location",
            "to_location_id": self.place_b.id,
            "approver_id": approver.id,
            "reason": "handoff 36 history test",
        })
        req.with_user(approver).action_approve()
        asset.invalidate_recordset()
        return asset, req, asker, approver

    def _moved_event(self, asset):
        events = asset.asset_history()["events"]
        moves = [e for e in events if e["type"] == "location_moved"]
        self.assertTrue(moves, "the approved move must appear in the history")
        return moves[0]

    def test_the_requester_is_in_the_record_and_the_actor_is_not_changed(self):
        asset, req, asker, approver = self._approved_move()
        event = self._moved_event(asset)

        # UNCHANGED: the actor is still whoever moved it.
        self.assertEqual(event["actor"]["id"], approver.id)

        block = event["detail"]["approval"]
        self.assertTrue(block, "an approved move must carry its approval")
        self.assertEqual(block["reference"], req.name)
        self.assertEqual(block["requested_by"]["id"], asker.id)
        self.assertEqual(block["approved_by"]["id"], approver.id)
        # The two halves are DIFFERENT people, which is the whole control.
        self.assertNotEqual(block["requested_by"]["id"],
                            block["approved_by"]["id"])

    def test_the_names_survive_the_users_being_deleted(self):
        """The `*_name` copies are the evidence; the links are convenience.

        Same rule as every other `*_name` in this file — a link goes null
        when the row it points at is deleted, and an audit record whose
        content can be emptied from outside is not one.
        """
        asset, req, asker, approver = self._approved_move()
        block = self._moved_event(asset)["detail"]["approval"]
        self.assertEqual(block["requested_by_name"], asker.display_name)
        self.assertEqual(block["approved_by_name"], approver.display_name)

    def test_a_move_nobody_approved_says_so_rather_than_omitting_the_key(self):
        """`approval` is null, not absent.

        Every move made before handoff 35, and every move on a tenant with
        the switch off, had one person. A consumer must be able to tell that
        from a server too old to publish the key at all, which it can only
        do if the key is always there.
        """
        asset = self._asset(location_id=self.place_a.id)
        asset.with_context(cadra_approval_exempt="test").write(
            {"location_id": self.place_b.id})
        event = self._moved_event(asset)
        self.assertIn("approval", event["detail"])
        self.assertIsNone(event["detail"]["approval"])

    def test_an_approved_custody_change_carries_it_too(self):
        asker, approver = self._two_users()
        asset = self._asset(custodian_id=self.alice.id)
        req = self.env["nrs.asset.change.request"].with_user(asker).create({
            "asset_id": asset.id,
            "change_type": "custody",
            "to_custodian_id": self.bob.id,
            "approver_id": approver.id,
        })
        req.with_user(approver).action_approve()
        asset.invalidate_recordset()
        events = asset.asset_history()["events"]
        changes = [e for e in events if e["type"] == "custody_changed"
                   and e["detail"].get("approval")]
        self.assertTrue(changes, "the approved custody change must carry it")
        block = changes[0]["detail"]["approval"]
        self.assertEqual(block["requested_by"]["id"], asker.id)
        self.assertEqual(block["approved_by"]["id"], approver.id)

    def test_the_block_is_graded_and_the_grade_is_one_that_is_published(self):
        """A bare word a reader has to look up is what the grades table
        exists to prevent, so the block's own grade must be in it."""
        from odoo.addons.myservice_api.models.asset_history import (
            EVIDENCE_GRADES)
        asset, _req, _a, _b = self._approved_move()
        block = self._moved_event(asset)["detail"]["approval"]
        self.assertIn(block["evidence"], [g for g, _ in EVIDENCE_GRADES])
        # `append_only` is asserted against the grade's own words: a DECIDED
        # request refuses `write` and `unlink` for everyone, sudo included.
        self.assertEqual(block["evidence"], "append_only")
