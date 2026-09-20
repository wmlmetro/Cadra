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
            asset.write({"custodian_id": self.alice.id})
            self._flush_tracking()
        with freeze_time("2031-01-02 09:00:00"):
            asset.write({"state": "in_repair"})
            self._flush_tracking()
        with freeze_time("2031-01-03 09:00:00"):
            asset.write({"location_id": self.place_b.id})
            self._flush_tracking()
        with freeze_time("2031-01-04 09:00:00"):
            asset.write({"custodian_id": self.bob.id})
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
            asset.write({"custodian_id": self.alice.id,
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
        asset.write({"custodian_id": self.alice.id})
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
        asset.write({"custodian_id": self.alice.id})
        history = asset.asset_history()
        shown = [history["summary"]["statement"],
                 history["fidelity"]["custody"]["statement"],
                 history["fidelity"]["verification"]]
        shown += [n["statement"] for n in history["fidelity"]["not_recorded"]]
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
        """Not its `create_uid`, which every message has."""
        asset = self._asset()
        asset.write({"state": "in_repair"})
        self._flush_tracking()
        event = next(e for e in asset.asset_history()["events"]
                     if e["type"] == "status_changed")
        self.assertIsNotNone(event["actor"])
        self.env.cr.execute(
            "UPDATE mail_message SET author_id = NULL WHERE id = %s",
            (event["record"]["id"],))
        self.env.invalidate_all()
        event = next(e for e in asset.asset_history()["events"]
                     if e["type"] == "status_changed")
        self.assertIsNone(event["actor"])
        self.assertIsNone(event["actor_name"])

    def test_a_record_with_no_instant_is_omitted_and_counted(self):
        """One undated row must not cost the asset its whole history."""
        asset = self._asset()
        asset.write({"state": "in_repair"})
        self._flush_tracking()
        history = asset.asset_history()
        self.assertEqual(history["fidelity"]["undated_records_omitted"], 0)
        message_id = next(e for e in history["events"]
                          if e["type"] == "status_changed")["record"]["id"]
        self.env.cr.execute(
            "UPDATE mail_message SET date = NULL WHERE id = %s",
            (message_id,))
        self.env.invalidate_all()
        history = asset.asset_history()
        self.assertFalse([e for e in history["events"]
                          if e["type"] == "status_changed"])
        self.assertEqual(history["fidelity"]["undated_records_omitted"], 1)

    def test_a_request_is_an_event_without_its_reference(self):
        """The request belongs to `requests:read`; this is `assets:read`."""
        asset = self._asset()
        req = self.env["request.request"].search(
            [("nrs_asset_id", "!=", False)], limit=1)
        if not req:
            self.skipTest("no request on this database to point at an asset")
        self.env.cr.execute(
            "UPDATE request_request SET nrs_asset_id = %s WHERE id = %s",
            (asset.id, req.id))
        self.env.invalidate_all()
        event = next(e for e in asset.asset_history()["events"]
                     if e["type"] == "maintenance_request")
        self.assertEqual(event["summary"], "Maintenance request raised")
        self.assertNotIn(req.name, repr(event))

    def test_the_statement_counts_what_nobody_can_alter(self):
        asset = self._asset()
        asset.write({"custodian_id": self.alice.id})
        asset.write({"state": "in_repair"})
        self._flush_tracking()
        statement = asset.asset_history()["summary"]["statement"]
        self.assertIn("2 recorded event(s)", statement)
        self.assertIn("1 of them rest on a record that nobody can edit",
                      statement)

    def test_every_grade_used_is_a_grade_defined(self):
        asset = self._asset()
        asset.write({"custodian_id": self.alice.id, "state": "in_repair"})
        self._flush_tracking()
        history = asset.asset_history()
        defined = [g["grade"] for g in history["fidelity"]["evidence_grades"]]
        self.assertEqual(defined[0], "append_only", "strongest first")
        for event in history["events"]:
            self.assertIn(event["evidence"], defined)
        self.assertEqual(sorted(history["summary"]["by_evidence"]),
                         sorted(defined))


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

    def test_a_same_day_scrap_does_not_sort_before_the_tags_own_issue(self):
        """A bare date sorts at midnight — before the tag existed."""
        asset = self._asset()
        tag = asset.tag_ids[:1]
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

    def _move_like_the_route(self, asset, to):
        """What `POST /assets/<id>/move` does, in one transaction."""
        transfer = self.env["nrs.asset.transfer"].create({
            "asset_id": asset.id,
            "from_location_id": asset.location_id.id,
            "to_location_id": to.id,
            "reason": "history test move",
            "state": "done",
        })
        asset.write({"location_id": to.id})
        self._flush_tracking()
        return transfer

    def _moves(self, asset):
        return [e for e in asset.asset_history()["events"]
                if e["type"] == "location_moved"]

    def test_one_move_with_two_records_is_one_line(self):
        asset = self._asset()
        transfer = self._move_like_the_route(asset, self.place_b)
        moves = self._moves(asset)
        self.assertEqual(len(moves), 1)
        move = moves[0]
        self.assertEqual(move["evidence"], "editable_record")
        self.assertEqual(move["detail"]["transfer"]["reference"],
                         transfer.name)
        self.assertEqual(move["detail"]["transfer"]["reason"],
                         "history test move")
        self.assertEqual(move["detail"]["records"],
                         ["nrs.asset.transfer", "mail.message"])
        # The actor is the chatter row's — whoever made the write.
        self.assertEqual(move["actor"]["id"], self.env.user.id)

    def test_a_move_with_no_transfer_row_is_still_a_line(self):
        """PATCH, the Odoo form, an import: chatter and nothing else."""
        asset = self._asset()
        asset.write({"location_id": self.place_b.id})
        self._flush_tracking()
        moves = self._moves(asset)
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0]["evidence"], "chatter")
        self.assertIsNone(moves[0]["detail"]["transfer"])
        self.assertIn("History location B", moves[0]["summary"])

    def test_two_moves_between_the_same_places_stay_two(self):
        """Each side of the join is used once."""
        asset = self._asset()
        # NOT frozen. The join compares a message's `date`, which obeys
        # freezegun, with the transfer's `create_date`, which is the
        # database's clock and does not — freeze this step and the two
        # records of one move sit five years apart and rightly do not join.
        self._move_like_the_route(asset, self.place_b)
        with freeze_time("2031-02-02 09:00:00"):
            asset.write({"location_id": self.place_a.id})
            self._flush_tracking()
        with freeze_time("2031-02-03 09:00:00"):
            asset.write({"location_id": self.place_b.id})
            self._flush_tracking()
        moves = self._moves(asset)
        self.assertEqual(len(moves), 3)
        self.assertEqual(
            sorted(m["evidence"] for m in moves),
            ["chatter", "chatter", "editable_record"])

    def test_a_transfer_with_no_chatter_row_names_nobody(self):
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

    def test_a_transfer_that_is_not_done_is_not_a_move(self):
        asset = self._asset()
        self.env["nrs.asset.transfer"].create({
            "asset_id": asset.id,
            "from_location_id": self.place_a.id,
            "to_location_id": self.place_c.id,
            "state": "draft",
        })
        events = asset.asset_history()["events"]
        self.assertFalse([e for e in events if e["type"] == "location_moved"])
        recorded = [e for e in events if e["type"] == "transfer_recorded"]
        self.assertEqual(len(recorded), 1)
        self.assertIn("draft", recorded[0]["summary"])


@tagged("post_install", "-at_install")
class TestAssetHistorySaysWhereItBegins(AssetHistoryCase):

    def test_an_asset_with_no_history_says_so_in_words(self):
        """The defect that produced the handoff was an empty panel."""
        history = self._asset().asset_history()
        self.assertEqual(history["summary"]["events_after_registration"], 0)
        self.assertTrue(history["summary"]["statement"].startswith(
            "There is no recorded history for this asset"))
        # The registration itself is still shown.
        self.assertEqual({e["type"] for e in history["events"]},
                         {"registered", "tag_issued"})
        self.assertIsNone(history["fidelity"]
                          ["earliest_event_after_registration_at"])

    def test_one_event_ends_the_empty_statement(self):
        asset = self._asset()
        asset.write({"custodian_id": self.alice.id})
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
        asset.write({"custodian_id": self.alice.id})
        custody = asset.asset_history()["fidelity"]["custody"]
        self.assertFalse(custody["custodian_held_before_first_link"])
        self.assertTrue(custody["recording_began_at"])
