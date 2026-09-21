"""What has happened to an asset — the record, and the rule that ends it.

`nrs.asset.event` is the third append-only record on an asset, after the
chain of custody and the movement record, and it makes the same two promises
for the same reasons:

    1. Every verification, every real change of status and every change to
       one of the three references an auditor reconciles produces exactly one
       row, whoever made it.
    2. A row, once written, cannot be changed or removed by anybody.

It is ONE table for three kinds of thing, so there is a third promise the
twins did not need: a row of one type cannot carry another type's payload,
and *when recording began* is answered per type and not per table.

And handoff 30 §B put a rule beside the recorder, in the same method and for
the same reason: **disposed is terminal.** `TestDisposedIsTerminal` is the
transition table, and the table is the specification.

All of it goes through the ORM, as `test_custody_chain.py` and
`test_movement_record.py` do, and not through any route: `state` has the
API's PATCH, three action methods, a completed transfer and the form, and a
recorder proved at one door is a recorder proved at one door.

Run with:
    odoo -d <db> -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register --stop-after-init
"""
from datetime import date, datetime

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import freeze_time
from odoo.tools import mute_logger
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase


class EventCase(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Asset = self.env["nrs.asset"]
        self.Event = self.env["nrs.asset.event"]
        self.category = self.env["nrs.asset.category"].create(
            {"name": "Event test category"})
        Location = self.env["generic.location"]
        self.room = Location.create({"name": "Event test room"})
        self.elsewhere = Location.create({"name": "Event test elsewhere"})
        Employee = self.env["hr.employee"]
        self.alice = Employee.create({"name": "Event Alice"})
        self.bob = Employee.create({"name": "Event Bob"})

    def _asset(self, **vals):
        """Created NOWHERE and UNASSIGNED unless a test says otherwise — an
        asset with a custody link or a movement cannot be deleted, and two
        tests below need to know that only an EVENT is what pins it."""
        return self.Asset.create(dict(
            {"name": "Event test asset", "category_id": self.category.id},
            **vals))

    def _events(self, asset, event_type=None):
        domain = [("asset_id", "=", asset.id)]
        if event_type:
            domain.append(("event_type", "=", event_type))
        return self.Event.search(domain, order="id")


@tagged("post_install", "-at_install")
class TestEventAppendOnly(EventCase):

    def _an_event(self):
        asset = self._asset()
        asset.write({"state": "in_repair"})
        events = self._events(asset)
        self.assertEqual(len(events), 1)
        return asset, events

    def test_a_row_cannot_be_edited(self):
        _, events = self._an_event()
        with self.assertRaises(UserError):
            events.write({"reason": "rewritten"})

    def test_a_row_cannot_be_edited_with_sudo(self):
        """The administrator is refused too. That is the whole point."""
        _, events = self._an_event()
        with self.assertRaises(UserError) as raised:
            events.sudo().write({"to_value": "active"})
        self.assertIn("sudo", str(raised.exception))

    def test_a_row_cannot_be_deleted(self):
        _, events = self._an_event()
        with self.assertRaises(UserError):
            events.unlink()

    def test_a_row_cannot_be_deleted_with_sudo(self):
        _, events = self._an_event()
        with self.assertRaises(UserError):
            events.sudo().unlink()

    def test_a_row_cannot_be_written_by_hand(self):
        """Not by ACL — by the model. One bad ACL line must not reach it."""
        asset = self._asset()
        with self.assertRaises(UserError):
            self.Event.sudo().create({
                "asset_id": asset.id, "event_type": "verified",
                "to_value": "2020-01-01", "actor_name": "Somebody Senior",
                "occurred_at": "2020-01-01 00:00:00"})

    def test_the_access_rules_grant_nothing_but_read(self):
        """The second of the two locks the model's docstring names. The flag
        `create` checks travels in the context, and a context is something
        an RPC caller supplies — so what stops a hand-written row over
        `call_kw` is the flag AND an ACL that grants `create` to nobody."""
        loose = self.env["ir.model.access"].search([
            ("model_id.model", "=", "nrs.asset.event"),
            "|", "|", ("perm_create", "=", True),
            ("perm_write", "=", True), ("perm_unlink", "=", True)])
        self.assertFalse(loose, loose.mapped("name"))

    def test_deleting_the_asset_is_refused(self):
        """`restrict`, not `cascade`. The asset is nowhere and unassigned, so
        the event is the ONLY thing holding it — see
        `test_an_asset_nothing_has_happened_to_can_be_deleted`, which is the
        same asset without one.

        The exception type is deliberately not pinned, for the reason
        `test_custody_chain.py` gives: the refusal comes from a foreign key.
        """
        asset, _ = self._an_event()
        self.assertFalse(asset.custody_ids)
        self.assertFalse(asset.movement_ids)
        self.env.flush_all()
        with self.assertRaises(Exception), \
                mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            asset.unlink()
            self.env.flush_all()

    def test_the_events_are_not_a_field_a_duplicate_copies(self):
        """`copy=False` is what keeps another asset's verifications off a
        duplicate, where they could never be removed."""
        self.assertFalse(self.Asset._fields["event_ids"].copy)

    def test_duplicating_an_asset_does_not_copy_its_events(self):
        asset, _ = self._an_event()
        asset.action_verify(notes="sighted")
        self.assertEqual(len(self._events(asset)), 2)
        # NOT a bare `copy()`: that fails on every asset today, before it
        # reaches anything of ours — see `test_movement_record.py`.
        twin = asset.copy({"asset_tag": False, "asset_code": False})
        self.assertFalse(
            self._events(twin),
            "a duplicate opens with the original's state, and an opening "
            "value is not an event")


@tagged("post_install", "-at_install")
class TestThePayloadIsTyped(EventCase):
    """One table, three kinds of thing. What stops it becoming "any column,
    any row" is `_record`, and these are its refusals."""

    def test_an_unknown_type_is_refused(self):
        with self.assertRaises(UserError):
            self.Event._record(self._asset(), "teleported",
                               from_value="here", to_value="there")

    def test_a_status_change_cannot_carry_verification_notes(self):
        with self.assertRaises(UserError) as raised:
            self.Event._record(self._asset(), "status_changed",
                               from_value="active", to_value="missing",
                               notes="sighted in the basement")
        self.assertIn("notes", str(raised.exception))

    def test_a_verification_cannot_carry_a_reason(self):
        with self.assertRaises(UserError):
            self.Event._record(self._asset(), "verified",
                               to_value="2026-06-01", reason="because")

    def test_a_written_date_cannot_carry_notes(self):
        """The notes are the VERIFIER's. A date that was merely written has
        no verifier, so it has nobody's notes either."""
        with self.assertRaises(UserError):
            self.Event._record(self._asset(), "verification_date_set",
                               to_value="2026-06-01", notes="sighted")

    def test_a_reference_change_cannot_carry_a_reason(self):
        with self.assertRaises(UserError):
            self.Event._record(self._asset(), "reference_changed",
                               field_name="grn_reference",
                               from_value="GRN-1", to_value="GRN-2",
                               reason="typo")

    def test_a_reference_change_must_name_one_of_the_three(self):
        """`purchase_vendor` is tracked in the chatter and is NOT an event:
        the importer rewrites it on every re-import."""
        with self.assertRaises(UserError):
            self.Event._record(self._asset(), "reference_changed",
                               field_name="purchase_vendor",
                               from_value="Acme", to_value="Apex")

    def test_a_reference_change_that_names_no_field_is_refused(self):
        with self.assertRaises(UserError):
            self.Event._record(self._asset(), "reference_changed",
                               from_value="GRN-1", to_value="GRN-2")

    def test_a_refused_event_leaves_no_row(self):
        asset = self._asset()
        with self.assertRaises(UserError):
            self.Event._record(asset, "status_changed", notes="stray")
        self.assertFalse(self._events(asset))


@tagged("post_install", "-at_install")
class TestTheEventSourceIsTruthful(EventCase):

    def test_an_undeclared_write_is_direct(self):
        asset = self._asset()
        asset.write({"state": "in_repair"})
        self.assertEqual(self._events(asset).source, "direct")

    def test_a_declared_source_is_carried(self):
        asset = self._asset()
        asset.with_context(cadra_event_source="api_write").write(
            {"state": "in_repair"})
        self.assertEqual(self._events(asset).source, "api_write")

    def test_a_caller_cannot_file_an_event_under_test(self):
        """The context is caller-controlled over `call_kw`. `test` says the
        row is an artefact, and anybody able to mark an asset missing could
        otherwise file a real loss as one."""
        asset = self._asset()
        asset.with_context(cadra_event_source="test").write(
            {"state": "missing"})
        self.assertEqual(self._events(asset).source, "direct")

    def test_a_source_nobody_defined_is_direct(self):
        asset = self._asset()
        asset.with_context(cadra_event_source="the_board_said_so").write(
            {"state": "missing"})
        self.assertEqual(self._events(asset).source, "direct")

    def test_a_button_is_labelled_action(self):
        asset = self._asset()
        asset.action_mark_missing()
        self.assertEqual(self._events(asset).source, "action")

    def test_the_found_button_is_labelled_action_too(self):
        asset = self._asset(state="missing")
        asset.action_mark_found()
        self.assertEqual(self._events(asset).source, "action")

    def test_a_route_that_has_said_so_is_left_standing(self):
        """`POST /assets/<id>/mark-missing` declares itself before it calls
        the button; the button must not relabel it `action`."""
        asset = self._asset()
        asset.with_context(
            cadra_event_source="api_mark_missing").action_mark_missing()
        self.assertEqual(self._events(asset).source, "api_mark_missing")


@tagged("post_install", "-at_install")
class TestEveryStatusChangeIsRecorded(EventCase):

    def test_a_real_change_is_exactly_one_event(self):
        asset = self._asset()
        asset.with_context(
            cadra_event_reason="not found at the annual count",
        ).write({"state": "missing"})
        event = self._events(asset)
        self.assertEqual(len(event), 1)
        self.assertEqual(event.event_type, "status_changed")
        # The KEYS, as recorded — not the labels, which a translation or a
        # relabelled selection would rewrite underneath the record.
        self.assertEqual(event.from_value, "active")
        self.assertEqual(event.to_value, "missing")
        self.assertEqual(event.reason, "not found at the annual count")
        self.assertFalse(event.field_name)
        self.assertFalse(event.notes)

    def test_the_event_names_who_made_the_change(self):
        asset = self._asset()
        asset.write({"state": "missing"})
        event = self._events(asset)
        self.assertEqual(event.actor_id, self.env.user)
        self.assertEqual(event.actor_name, self.env.user.name)

    def test_a_change_with_no_reason_has_none(self):
        """A column no writer filled must not read as a reason somebody
        gave."""
        asset = self._asset()
        asset.write({"state": "missing"})
        self.assertFalse(self._events(asset).reason)

    def test_writing_the_same_status_records_nothing(self):
        """The Cadra app's edit form re-sends `state` on every save. Saving a
        form is not a change of status."""
        asset = self._asset()
        asset.write({"state": "active"})
        self.assertFalse(self._events(asset))

    def test_a_write_that_does_not_name_the_status_records_nothing(self):
        asset = self._asset()
        asset.write({"name": "renamed", "condition": "poor"})
        self.assertFalse(self._events(asset))

    def test_a_multi_record_write_records_only_what_changed(self):
        already = self._asset(state="missing")
        found = self._asset()
        (already | found).write({"state": "missing"})
        self.assertFalse(self._events(already), "was already missing")
        event = self._events(found)
        self.assertEqual(len(event), 1)
        self.assertEqual(event.from_value, "active")

    def test_marking_missing_carries_the_reason(self):
        """*Why is this asset missing* is the first question anybody asks,
        and until handoff 30 it had nowhere to live."""
        asset = self._asset()
        asset.action_mark_missing(reason="not in the store at handover")
        self.assertEqual(asset.state, "missing")
        event = self._events(asset)
        self.assertEqual(len(event), 1)
        self.assertEqual(event.to_value, "missing")
        self.assertEqual(event.reason, "not in the store at handover")
        self.assertEqual(event.source, "action")

    def test_marking_missing_without_a_reason_still_records_the_change(self):
        asset = self._asset()
        asset.action_mark_missing()
        event = self._events(asset)
        self.assertEqual(len(event), 1)
        self.assertFalse(event.reason)

    def test_a_status_change_in_the_same_write_as_a_move_records_both(self):
        asset = self._asset(location_id=self.room.id)
        asset.write({"state": "in_repair",
                     "location_id": self.elsewhere.id})
        self.assertEqual(len(self._events(asset)), 1)
        self.assertEqual(len(asset.movement_ids), 2)


@tagged("post_install", "-at_install")
class TestAnOpeningValueIsNotAnEvent(EventCase):
    """The deliberate difference from custody and movement, which DO record
    the first custodian and the first placement. Every asset has a `state`
    from birth; recording it would pin every asset ever created for a row
    that says only that it was created."""

    def test_creating_an_asset_writes_no_event(self):
        self.assertFalse(self._events(self._asset()))

    def test_creating_one_with_everything_set_writes_none_either(self):
        asset = self._asset(
            state="in_repair", last_verified_date="2026-01-15",
            grn_reference="GRN-OPEN", purchase_order_reference="PO-OPEN")
        self.assertFalse(self._events(asset))

    def test_an_asset_nothing_has_happened_to_can_be_deleted(self):
        """What writing no opening event buys: created nowhere and
        unassigned, an asset is still an ordinary deletable record."""
        asset = self._asset()
        asset_id = asset.id
        asset.unlink()
        self.env.flush_all()
        self.assertFalse(self.Asset.search([("id", "=", asset_id)]))

    def test_the_first_change_carries_the_opening_value(self):
        """So nothing is lost by not recording it at birth."""
        asset = self._asset(grn_reference="GRN-OPEN")
        asset.write({"grn_reference": "GRN-CORRECTED"})
        self.assertEqual(self._events(asset).from_value, "GRN-OPEN")


@tagged("post_install", "-at_install")
class TestEveryVerificationIsRecorded(EventCase):

    def test_two_checks_on_one_day_are_two_events(self):
        """One overwritten column is exactly what could not say so: the
        second check changes no DATE."""
        asset = self._asset()
        asset.action_verify(notes="sighted, tag intact")
        asset.action_verify()
        events = self._events(asset)
        self.assertEqual(events.mapped("event_type"),
                         ["verified", "verified"])
        today = date.today().isoformat()
        self.assertFalse(events[0].from_value)
        self.assertEqual(events[0].to_value, today)
        self.assertEqual(events[1].from_value, today)
        self.assertEqual(events[1].to_value, today)

    def test_the_actor_is_the_verifier(self):
        asset = self._asset()
        asset.action_verify()
        event = self._events(asset)
        self.assertEqual(event.actor_id, self.env.user)
        self.assertEqual(event.actor_name, self.env.user.name)
        self.assertEqual(event.source, "action")

    def test_the_actor_is_whoever_pressed_it_not_the_superuser(self):
        """The suite runs as the superuser, so `actor == env.user` above
        would also pass on a recorder that always wrote uid 1."""
        Users = self.env["res.users"]
        groups_field = ("group_ids" if "group_ids" in Users._fields
                        else "groups_id")
        checker = Users.create({
            "name": "Event Test Checker", "login": "event-test-checker",
            # `action_verify` posts a message, and `message_post` refuses an
            # author with no address.
            "email": "event-test-checker@example.com",
            groups_field: [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref(
                    "myservice_asset_register.group_asset_manager").id])],
        })
        asset = self._asset()
        asset.with_user(checker).action_verify(notes="sighted")
        event = self._events(asset)
        self.assertEqual(event.actor_id, checker)
        self.assertEqual(event.actor_name, "Event Test Checker")

    def test_the_notes_are_carried_and_the_next_check_does_not_inherit_them(
            self):
        asset = self._asset()
        asset.action_verify(notes="sighted, tag intact")
        asset.action_verify()
        first, second = self._events(asset)
        self.assertEqual(first.notes, "sighted, tag intact")
        self.assertFalse(second.notes)

    def test_a_written_date_is_not_a_verification(self):
        """PATCH, the form, an import. Somebody wrote a DATE; the record
        does not say anybody checked anything."""
        asset = self._asset()
        asset.write({"last_verified_date": "2026-06-01"})
        event = self._events(asset)
        self.assertEqual(len(event), 1)
        self.assertEqual(event.event_type, "verification_date_set")
        self.assertFalse(event.from_value)
        self.assertEqual(event.to_value, "2026-06-01")
        self.assertFalse(event.notes)
        self.assertEqual(event.source, "direct")

    def test_a_written_date_does_not_borrow_the_assets_notes(self):
        asset = self._asset(verification_notes="left by the last verifier")
        asset.write({"last_verified_date": "2026-06-01"})
        self.assertFalse(self._events(asset).notes)

    def test_writing_the_same_date_again_records_nothing(self):
        asset = self._asset()
        asset.write({"last_verified_date": "2026-06-01"})
        asset.write({"last_verified_date": "2026-06-01"})
        self.assertEqual(len(self._events(asset)), 1)

    def test_the_same_date_written_over_a_verifier_is_recorded(self):
        """`write` clears the verifier whenever a date arrives without one —
        the same date included. The asset said "checked by somebody" and now
        says nobody checked it; with no change of DATE the first draft
        recorded nothing, and left a message-log line titled "Verified" for
        an act that removed a verifier."""
        asset = self._asset()
        asset.action_verify()
        today = asset.last_verified_date
        self.assertTrue(asset.last_verified_by)
        asset.write({"last_verified_date": today})
        self.assertFalse(asset.last_verified_by)
        last = self._events(asset)[-1]
        self.assertEqual(last.event_type, "verification_date_set")
        self.assertEqual(last.from_value, last.to_value)

    def test_clearing_the_date_is_recorded(self):
        asset = self._asset()
        asset.write({"last_verified_date": "2026-06-01"})
        asset.write({"last_verified_date": False})
        last = self._events(asset)[-1]
        self.assertEqual(last.event_type, "verification_date_set")
        self.assertEqual(last.from_value, "2026-06-01")
        self.assertFalse(last.to_value)

    def test_a_written_date_after_a_check_says_what_it_replaced(self):
        asset = self._asset()
        asset.action_verify()
        asset.write({"last_verified_date": "2026-06-01"})
        events = self._events(asset)
        self.assertEqual(events.mapped("event_type"),
                         ["verified", "verification_date_set"])
        self.assertEqual(events[1].from_value, date.today().isoformat())

    def test_a_date_write_cannot_claim_to_be_the_button(self):
        """The context is caller-controlled. A PATCH of the date that says
        it came from Verify names nobody as the verifier — `write` has just
        cleared that column — so it is a date that was written, and it is
        not filed under a label only a verification earns."""
        asset = self._asset()
        asset.with_context(cadra_event_source="action").write(
            {"last_verified_date": "2026-06-01"})
        event = self._events(asset)
        self.assertEqual(len(event), 1)
        self.assertEqual(event.event_type, "verification_date_set")
        self.assertEqual(event.source, "direct")

    def test_nor_can_it_by_dating_the_write_today(self):
        asset = self._asset()
        asset.with_context(cadra_event_source="api_verify").write(
            {"last_verified_date": date.today()})
        event = self._events(asset)
        self.assertEqual(event.event_type, "verification_date_set")
        self.assertEqual(event.source, "direct")
        self.assertFalse(asset.last_verified_by)

    def test_nor_by_naming_somebody_else_as_the_verifier(self):
        """The claim is honoured only when the verifier named is the ACTOR.
        Anything else would let one person record another's check."""
        other = self.env["res.users"].create({
            "name": "Event Test Bystander", "login": "event-test-bystander"})
        asset = self._asset()
        asset.with_context(cadra_event_source="action").write({
            "last_verified_date": date.today(),
            "last_verified_by": other.id})
        event = self._events(asset)
        self.assertEqual(event.event_type, "verification_date_set")
        self.assertEqual(event.source, "direct")


@tagged("post_install", "-at_install")
class TestEveryReferenceChangeIsRecorded(EventCase):

    def test_a_changed_grn_records_before_and_after(self):
        asset = self._asset(grn_reference="GRN-2026-0001")
        asset.write({"grn_reference": "GRN-2026-0002"})
        event = self._events(asset)
        self.assertEqual(len(event), 1)
        self.assertEqual(event.event_type, "reference_changed")
        self.assertEqual(event.field_name, "grn_reference")
        self.assertEqual(event.from_value, "GRN-2026-0001")
        self.assertEqual(event.to_value, "GRN-2026-0002")
        self.assertEqual(event.actor_id, self.env.user)
        self.assertFalse(event.reason)

    def test_the_first_value_is_a_change_from_nothing(self):
        asset = self._asset()
        asset.write({"purchase_order_reference": "PO-4500012345"})
        event = self._events(asset)
        self.assertEqual(event.field_name, "purchase_order_reference")
        self.assertFalse(event.from_value)
        self.assertEqual(event.to_value, "PO-4500012345")

    def test_clearing_a_reference_is_recorded(self):
        """A change to one of these is exactly the event somebody would want
        to hide, and blanking it is the bluntest way to."""
        asset = self._asset(grn_reference="GRN-2026-0001")
        asset.write({"grn_reference": False})
        event = self._events(asset)
        self.assertEqual(event.from_value, "GRN-2026-0001")
        self.assertFalse(event.to_value)

    def test_an_unchanged_reference_records_nothing(self):
        asset = self._asset(grn_reference="GRN-2026-0001")
        asset.write({"grn_reference": "GRN-2026-0001"})
        self.assertFalse(self._events(asset))

    def test_an_empty_reference_rewritten_empty_records_nothing(self):
        """`False` and `''` are one value here: nothing, written again."""
        asset = self._asset()
        asset.write({"grn_reference": ""})
        self.assertFalse(self._events(asset))

    def test_two_references_in_one_write_are_two_events(self):
        asset = self._asset()
        asset.write({"grn_reference": "GRN-1",
                     "purchase_order_reference": "PO-1"})
        self.assertEqual(
            sorted(self._events(asset).mapped("field_name")),
            ["grn_reference", "purchase_order_reference"])

    def test_the_sap_number_returned_by_sap_is_recorded(self):
        """INT-07's setter writes through `sudo()` with its own evidence
        context — a writer no route test would reach."""
        asset = self._asset()
        self.assertTrue(asset._set_sap_master(
            {"sap_asset_number": "400000991201"}))
        event = self._events(asset)
        self.assertEqual(len(event), 1)
        self.assertEqual(event.field_name, "sap_asset_number")
        self.assertFalse(event.from_value)
        self.assertEqual(event.to_value, "400000991201")
        self.assertEqual(event.actor_id, self.env.user,
                         "`sudo()` changes what may be done, not who did it")

    def test_a_sap_sync_that_repeats_the_number_records_nothing(self):
        """Every sync sends the number again. One event per sync would bury
        the one change that mattered."""
        asset = self._asset()
        asset._set_sap_master({"sap_asset_number": "400000991202"})
        asset._set_sap_master({"sap_asset_number": "400000991202",
                               "net_book_value": 1500.0})
        self.assertEqual(len(self._events(asset)), 1)

    def test_a_replaced_sap_number_keeps_the_one_it_replaced(self):
        asset = self._asset()
        asset._set_sap_master({"sap_asset_number": "400000991203"})
        asset._set_sap_master({"sap_asset_number": "400000991204"})
        last = self._events(asset)[-1]
        self.assertEqual(last.from_value, "400000991203")
        self.assertEqual(last.to_value, "400000991204")

    def test_the_vendor_is_not_an_event(self):
        """Tracked in the chatter, and deliberately NOT here: the importer
        rewrites it on every re-import, and an append-only table is the
        wrong place to discover that a record is mostly data loading."""
        asset = self._asset(purchase_vendor="Acme Supplies")
        asset.write({"purchase_vendor": "Apex Trading"})
        self.assertFalse(self._events(asset))


@tagged("post_install", "-at_install")
class TestRecordingBeganPerType(EventCase):
    """They share a table and did not necessarily begin together, and a
    shared table is exactly where that is easy to get wrong."""

    def _backdate(self, event, instant):
        # Raw SQL on purpose: `create_date` is the database's transaction
        # clock, which `freeze_time` cannot move, and the model refuses
        # `write` — which is the guarantee, not an obstacle to route around
        # anywhere but here.
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE nrs_asset_event SET create_date = %s WHERE id = %s",
            (instant, event.id))
        self.env.invalidate_all()

    def test_one_kind_beginning_does_not_begin_another(self):
        asset = self._asset()
        asset.write({"state": "in_repair"})
        self._backdate(self._events(asset), "2001-02-03 04:05:06")
        began = datetime(2001, 2, 3, 4, 5, 6)
        self.assertEqual(
            self.Event.recording_began_at("status_changed"), began)
        for other in ("verified", "verification_date_set",
                      "reference_changed"):
            self.assertNotEqual(
                self.Event.recording_began_at(other), began,
                "%s did not begin when status changes did" % other)

    def test_each_kind_keeps_its_own_beginning(self):
        asset = self._asset()
        asset.write({"state": "in_repair"})
        asset.action_verify()
        status = self._events(asset, "status_changed")
        verified = self._events(asset, "verified")
        self._backdate(status, "2001-02-03 04:05:06")
        self._backdate(verified, "2002-03-04 05:06:07")
        self.assertEqual(self.Event.recording_began_at("status_changed"),
                         datetime(2001, 2, 3, 4, 5, 6))
        self.assertEqual(self.Event.recording_began_at("verified"),
                         datetime(2002, 3, 4, 5, 6, 7))

    def test_a_kind_nobody_has_recorded_has_no_beginning(self):
        """None, not the table's oldest row.

        The table is EMPTIED first, by raw SQL, inside this test's
        transaction and rolled back with it. There is no other way to get
        here on a database the HTTP suite has already verified an asset on:
        CI runs that suite first, and its rows are permanent by design.
        """
        self.env.flush_all()
        self.env.cr.execute("DELETE FROM nrs_asset_event")
        self.env.invalidate_all()
        for kind in ("verified", "verification_date_set",
                     "status_changed", "reference_changed"):
            self.assertIsNone(self.Event.recording_began_at(kind))
        asset = self._asset()
        asset.write({"state": "missing"})
        self.assertTrue(self.Event.recording_began_at("status_changed"))
        self.assertIsNone(self.Event.recording_began_at("verified"))
        self.assertIsNone(
            self.Event.recording_began_at("verification_date_set"))
        self.assertIsNone(self.Event.recording_began_at("reference_changed"))


@tagged("post_install", "-at_install")
class TestDisposedIsTerminal(EventCase):
    """The transition table of handoff 30 §B. This class is the
    specification.

    Until it existed a disposed asset could be marked missing — which
    overwrote `disposed` and put it back on the register with a 200 — and
    completing a transfer on one set it `active` without anybody having
    asked. The rule is in `nrs.asset.write`, so these go through the ORM:
    a disabled button closes one door.
    """

    def _disposed(self, **vals):
        """Disposed of by a BARE WRITE, on purpose: the rule is in
        `nrs.asset.write` and has to hold for an asset that got here by any
        door. Since handoff 31 that write also stamps the disposal — a date
        and `decommissioned` — so this fixture is dated, which nothing in
        this class depends on either way. The stamp's own tests are
        `TestADisposalIsStampedThroughAnyDoor`."""
        asset = self._asset(location_id=self.room.id,
                            custodian_id=self.alice.id, **vals)
        asset.write({"state": "disposed"})
        return asset

    # ── nothing leaves `disposed` ────────────────────────────────────

    def test_no_status_follows_disposed(self):
        asset = self._disposed()
        before = len(self._events(asset))
        every_other = [key for key, _label
                       in self.Asset._fields["state"].selection
                       if key != "disposed"]
        # Read off the model, so a status added later is refused here on
        # the day it is added rather than on the day somebody notices.
        self.assertEqual(sorted(every_other),
                         ["active", "in_repair", "missing", "transferred"])
        for state in every_other:
            with self.subTest(state=state):
                with self.assertRaises(UserError):
                    asset.write({"state": state})
                self.assertEqual(asset.state, "disposed")
        self.assertEqual(len(self._events(asset)), before,
                         "a refused change is not an event")

    def test_a_disposed_asset_cannot_be_marked_missing(self):
        """The one report 29 found: a 200, and the asset back on the
        register."""
        asset = self._disposed()
        with self.assertRaises(UserError):
            asset.action_mark_missing(reason="cannot find it")
        self.assertEqual(asset.state, "disposed")

    def test_the_refusal_says_why(self):
        asset = self._disposed()
        with self.assertRaises(UserError) as raised:
            asset.write({"state": "active"})
        self.assertIn("disposed", str(raised.exception))

    def test_nor_under_sudo(self):
        """No way round it, on purpose: every API route writes as sudo."""
        asset = self._disposed()
        with self.assertRaises(UserError):
            asset.sudo().write({"state": "active"})
        self.assertEqual(asset.state, "disposed")

    def test_nor_through_a_context_flag(self):
        """A context is something an RPC caller supplies. The keys this
        module's own recorders read must not open anything."""
        asset = self._disposed()
        with self.assertRaises(UserError):
            asset.with_context(
                cadra_event_append=True, cadra_event_source="action",
                cadra_event_reason="returned from disposal",
            ).write({"state": "active"})

    def test_one_disposed_asset_refuses_the_whole_write(self):
        """Refused BEFORE anything is written, so the live asset beside it
        is untouched too — a refusal that half-happened is not one."""
        disposed = self._disposed()
        live = self._asset()
        with self.assertRaises(UserError):
            (live | disposed).write({"state": "missing"})
        self.assertEqual(live.state, "active")
        self.assertFalse(self._events(live))

    # ── a disposed asset is not moved or handed to anybody ───────────

    def test_a_disposed_asset_cannot_be_moved(self):
        asset = self._disposed()
        with self.assertRaises(UserError):
            asset.write({"location_id": self.elsewhere.id})
        self.assertEqual(asset.location_id, self.room)
        self.assertEqual(len(asset.movement_ids), 1)

    def test_nor_moved_to_nowhere(self):
        asset = self._disposed()
        with self.assertRaises(UserError):
            asset.write({"location_id": False})
        self.assertEqual(asset.location_id, self.room)

    def test_a_disposed_asset_cannot_change_custodian(self):
        asset = self._disposed()
        with self.assertRaises(UserError):
            asset.write({"custodian_id": self.bob.id})
        self.assertEqual(asset.custodian_id, self.alice)
        self.assertEqual(len(asset.custody_ids), 1)

    def test_nor_be_taken_off_its_custodian(self):
        """`myservice_identity.action_mark_retrieved` clears the custodian
        when an employee leaves. A disposed asset keeps whoever held it
        when it was disposed of."""
        asset = self._disposed()
        with self.assertRaises(UserError):
            asset.write({"custodian_id": False})
        self.assertEqual(asset.custodian_id, self.alice)

    def test_completing_a_transfer_on_one_is_refused(self):
        """It used to set the asset `active`, silently."""
        asset = self._disposed()
        transfer = self.env["nrs.asset.transfer"].create({
            "asset_id": asset.id,
            "from_location_id": self.room.id,
            "to_location_id": self.elsewhere.id,
            "to_custodian_id": self.bob.id,
        })
        with self.assertRaises(UserError):
            transfer.action_complete()
        self.assertEqual(asset.state, "disposed")
        self.assertEqual(asset.location_id, self.room)
        self.assertEqual(asset.custodian_id, self.alice)
        self.assertNotEqual(transfer.state, "done",
                            "a transfer marked done for a move that never "
                            "happened — report 28's defect, one model over")

    # ── what stays open ──────────────────────────────────────────────

    def test_naming_the_three_without_changing_them_is_not_refused(self):
        """The Cadra app's edit form re-sends `state` and the location on
        every save. Refusing that would make a disposed asset's notes
        uneditable from the app for a reason nobody could guess."""
        asset = self._disposed()
        events = len(self._events(asset))
        asset.write({
            "state": "disposed",
            "location_id": self.room.id,
            "custodian_id": self.alice.id,
            "notes": "collected by the contractor on the 14th",
        })
        self.assertEqual(asset.notes,
                         "collected by the contractor on the 14th")
        self.assertEqual(len(self._events(asset)), events)
        self.assertEqual(len(asset.movement_ids), 1)
        self.assertEqual(len(asset.custody_ids), 1)

    def test_an_unplaced_unheld_one_may_go_on_saying_so(self):
        """`False` re-sent for an empty field is the same value, not a move
        to nowhere."""
        asset = self._asset()
        asset.write({"state": "disposed"})
        asset.write({"location_id": False, "custodian_id": False,
                     "notes": "never placed"})
        self.assertEqual(asset.notes, "never placed")

    def test_the_paperwork_is_completed_after_the_disposal(self):
        asset = self._disposed()
        asset.write({"disposal_method": "auction",
                     "disposal_reference": "BOARD/2026/041",
                     "disposal_reason": "beyond economic repair"})
        self.assertEqual(asset.disposal_method, "auction")
        self.assertEqual(asset.disposal_reference, "BOARD/2026/041")
        self.assertEqual(asset.state, "disposed")

    def test_a_disposal_can_still_be_approved(self):
        """The approval is recorded AFTER the disposal by design — it
        refuses an asset that is not disposed of."""
        asset = self._disposed()
        asset.action_approve_disposal()
        self.assertEqual(asset.disposal_approved_by, self.env.user)
        self.assertTrue(asset.disposal_approved_date)
        self.assertEqual(asset.state, "disposed")

    def test_a_disposed_asset_can_still_be_verified(self):
        """Not one of the three. Sighting a condemned asset in the yard is
        a fact about it, and changes nothing the rule protects."""
        asset = self._disposed()
        asset.action_verify(notes="awaiting collection")
        self.assertEqual(asset.state, "disposed")
        self.assertEqual(
            self._events(asset)[-1].event_type, "verified")

    def test_a_reference_on_one_can_still_be_corrected_and_is_recorded(self):
        asset = self._disposed(grn_reference="GRN-1")
        asset.write({"grn_reference": "GRN-2"})
        self.assertEqual(self._events(asset)[-1].to_value, "GRN-2")

    # ── the way IN to `disposed` ─────────────────────────────────────

    def test_condemning_records_one_event_naming_who_and_why(self):
        asset = self._asset(location_id=self.room.id)
        # 00:30 on 2 March in Lagos, and still 1 March in UTC — which is
        # what `context_today` answers for a user with no timezone, and
        # every API credential's user has none.
        with freeze_time("2031-03-01 23:30:00"):
            asset.action_condemn(reason="fire damage, beyond repair")
        self.assertEqual(asset.state, "disposed")
        self.assertEqual(asset.condition, "decommissioned")
        self.assertEqual(asset.disposal_date, date(2031, 3, 2),
                         "a Lagos day, the one the register snapshot cuts on")
        self.assertEqual(asset.disposal_reason, "fire damage, beyond repair")
        event = self._events(asset)
        self.assertEqual(len(event), 1,
                         "stamping the date afterwards is not a second event")
        self.assertEqual(event.event_type, "status_changed")
        self.assertEqual(event.from_value, "active")
        self.assertEqual(event.to_value, "disposed")
        self.assertEqual(event.reason, "fire damage, beyond repair")
        # `disposal_executor`, closed going forward: who carried it out.
        self.assertEqual(event.actor_id, self.env.user)
        self.assertEqual(event.actor_name, self.env.user.name)
        self.assertEqual(event.source, "action")

    def test_condemning_without_a_reason_leaves_the_paperwork_alone(self):
        asset = self._asset(disposal_reason="written up beforehand")
        asset.action_condemn()
        self.assertEqual(asset.disposal_reason, "written up beforehand")
        self.assertFalse(self._events(asset).reason)

    def test_condemning_twice_is_not_a_second_disposal(self):
        """`disposed` → `disposed` names the state without changing it."""
        asset = self._asset()
        asset.action_condemn(reason="first")
        asset.action_condemn(reason="second")
        self.assertEqual(len(self._events(asset, "status_changed")), 1)

    def test_a_missing_asset_can_be_disposed_of(self):
        """Written off. Into `disposed` is open from everywhere."""
        asset = self._asset()
        asset.action_mark_missing(reason="not found in two counts")
        asset.action_condemn(reason="written off as lost")
        self.assertEqual(
            [(e.from_value, e.to_value) for e in self._events(asset)],
            [("active", "missing"), ("missing", "disposed")])

    # ── missing is NOT terminal, and nothing else is either ──────────

    def test_a_missing_asset_that_turns_up_is_ordinary(self):
        asset = self._asset()
        asset.action_mark_missing(reason="not in the store")
        asset.with_context(
            cadra_event_reason="found in the annex").write(
                {"state": "active"})
        self.assertEqual(asset.state, "active")
        found = self._events(asset)[-1]
        self.assertEqual(found.from_value, "missing")
        self.assertEqual(found.to_value, "active")
        self.assertEqual(found.reason, "found in the annex")

    def test_marking_found_carries_where_it_turned_up(self):
        """Handoff 31 §C3. The bare write above still works and still
        records a change with whatever reason the context happened to
        carry; `action_mark_found` is the door that takes the sentence as
        an argument, as `action_mark_missing` does for why it went."""
        asset = self._asset()
        asset.action_mark_missing(reason="not in the store")
        asset.action_mark_found(reason="in the annex, tag intact")
        self.assertEqual(asset.state, "active")
        self.assertEqual(
            [(e.from_value, e.to_value, e.reason, e.source)
             for e in self._events(asset, "status_changed")],
            [("active", "missing", "not in the store", "action"),
             ("missing", "active", "in the annex, tag intact", "action")])
        found = self._events(asset)[-1]
        self.assertEqual(found.actor_id, self.env.user)

    def test_marking_found_without_a_reason_still_records_the_change(self):
        """The Odoo button asks for none (GO-LIVE §15.3). The change is the
        fact; a reason nobody gave is not invented."""
        asset = self._asset(state="missing")
        asset.action_mark_found()
        self.assertEqual(asset.state, "active")
        self.assertFalse(self._events(asset).reason)

    def test_marking_found_does_not_verify_the_asset(self):
        """Whoever found it may not be whoever checks it."""
        asset = self._asset(state="missing")
        asset.action_mark_found(reason="turned up")
        self.assertFalse(asset.last_verified_date)
        self.assertFalse(asset.last_verified_by)
        self.assertFalse(self._events(asset, "verified"))

    def test_marking_found_acts_only_on_what_is_missing(self):
        """The route answers 409 before it gets here; this is the same
        answer for the ORM and the Odoo button. Every status that is not
        `missing` is left exactly as it was, with no event — and for
        `disposed` that is the terminal rule's tenth door: `mark found`
        writes `active`, and must not be a way out."""
        for state in ("active", "in_repair", "transferred", "disposed"):
            with self.subTest(state=state):
                asset = self._asset()
                if state != "active":
                    asset.write({"state": state})
                events = len(self._events(asset))
                asset.action_mark_found(reason="it was never lost")
                self.assertEqual(asset.state, state)
                self.assertEqual(len(self._events(asset)), events)

    def test_marking_a_mixed_set_found_touches_only_the_missing_one(self):
        """A list view selects across statuses. The live asset beside the
        missing one must not collect an event saying it was found."""
        missing = self._asset(state="missing")
        live = self._asset()
        (missing | live).action_mark_found(reason="found in the recount")
        self.assertEqual(missing.state, "active")
        self.assertEqual(self._events(missing).reason,
                         "found in the recount")
        self.assertFalse(self._events(live))

    def test_a_route_that_found_it_is_left_standing(self):
        """`POST /assets/<id>/mark-found` declares itself before it calls
        the button; the button must not relabel it `action`."""
        asset = self._asset(state="missing")
        asset.with_context(
            cadra_event_source="api_mark_found").action_mark_found(
                reason="found")
        self.assertEqual(self._events(asset).source, "api_mark_found")

    def test_a_missing_asset_can_be_moved_and_handed_over(self):
        asset = self._asset(location_id=self.room.id,
                            custodian_id=self.alice.id)
        asset.action_mark_missing()
        asset.write({"location_id": self.elsewhere.id,
                     "custodian_id": self.bob.id})
        self.assertEqual(asset.location_id, self.elsewhere)
        self.assertEqual(asset.custodian_id, self.bob)

    def test_a_transferred_missing_asset_has_been_found(self):
        """Completing a transfer sets the asset `active`. On a missing one
        that is a change of status, and it says where it came from."""
        asset = self._asset(location_id=self.room.id)
        asset.action_mark_missing()
        transfer = self.env["nrs.asset.transfer"].create({
            "asset_id": asset.id,
            "from_location_id": self.room.id,
            "to_location_id": self.elsewhere.id,
            "reason": "turned up at the annex",
        })
        transfer.action_complete()
        self.assertEqual(asset.state, "active")
        found = self._events(asset)[-1]
        self.assertEqual((found.from_value, found.to_value),
                         ("missing", "active"))
        self.assertEqual(found.source, "transfer")
        self.assertEqual(found.reason, "turned up at the annex")

    def test_a_transfer_of_an_active_asset_changes_no_status(self):
        asset = self._asset(location_id=self.room.id)
        transfer = self.env["nrs.asset.transfer"].create({
            "asset_id": asset.id,
            "from_location_id": self.room.id,
            "to_location_id": self.elsewhere.id,
        })
        transfer.action_complete()
        self.assertFalse(self._events(asset, "status_changed"))

    def test_repair_and_back_is_allowed_and_recorded(self):
        asset = self._asset()
        asset.write({"state": "in_repair"})
        asset.write({"state": "active"})
        self.assertEqual(
            [(e.from_value, e.to_value) for e in self._events(asset)],
            [("active", "in_repair"), ("in_repair", "active")])

    def test_every_status_but_disposed_can_be_left(self):
        for state in ("active", "in_repair", "transferred", "missing"):
            with self.subTest(state=state):
                asset = self._asset(state=state)
                target = "missing" if state != "missing" else "active"
                asset.write({"state": target})
                self.assertEqual(asset.state, target)

    # ── the two doors `nrs.asset.write` cannot see ───────────────────
    #
    # `location_id` and `custodian_id` are both `ON DELETE SET NULL`, so a
    # delete of the location or of the employee changes the asset WITHOUT a
    # write — and the terminal rule lives in `write`. Found by handoff 30's
    # verification pass, which asked whether the rule held "through any
    # door" and went looking for one.

    def test_the_location_a_disposed_asset_keeps_cannot_be_deleted(self):
        asset = self._disposed()
        with self.assertRaises(UserError) as refused, self.env.cr.savepoint():
            self.room.unlink()
        self.assertIn("Archive the location", str(refused.exception))
        self.assertEqual(asset.location_id, self.room)
        # …and the refusal wrote no "moved to nowhere" row on the way.
        self.assertFalse(self.env["nrs.asset.movement"].search([
            ("asset_id", "=", asset.id), ("source", "=", "location_deleted")]))

    def test_a_parent_of_that_location_cannot_be_deleted_either(self):
        """The cascade takes the children without calling `unlink` on them."""
        building = self.env["generic.location"].create(
            {"name": "Event test building"})
        self.room.parent_id = building
        self._disposed()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            building.unlink()
        self.assertTrue(self.room.exists())

    def test_a_location_holding_only_live_assets_can_still_be_deleted(self):
        asset = self._asset(location_id=self.room.id)
        self.room.unlink()
        self.assertFalse(asset.location_id)

    def test_the_employee_a_disposed_asset_keeps_cannot_be_deleted(self):
        asset = self._disposed()
        with self.assertRaises(UserError) as refused, self.env.cr.savepoint():
            self.alice.unlink()
        self.assertIn("Archive the employee", str(refused.exception))
        self.assertEqual(asset.custodian_id, self.alice)

    def test_deleting_an_employee_is_a_link_in_the_chain(self):
        """Custody's twin of `GenericLocation.unlink`. The database empties
        `custodian_id` itself, so until handoff 30 the chain still said
        somebody held the asset who no longer existed."""
        asset = self._asset(custodian_id=self.alice.id)
        self.alice.unlink()
        self.assertFalse(asset.custodian_id)
        last = self.env["nrs.asset.custody"].search(
            [("asset_id", "=", asset.id)], order="id")[-1]
        self.assertEqual(last.from_custodian_name, "Event Alice")
        self.assertFalse(last.to_custodian_name)
        self.assertEqual(last.source, "direct")
        self.assertIn("deleted", last.reason)

    def test_condemning_a_disposed_asset_over_the_orm_changes_nothing(self):
        """The route answers 409. The ORM and the Odoo button must not do
        what the route refuses: overwrite the reason given at the time,
        with no event to say so."""
        asset = self._asset()
        asset.action_condemn(reason="the reason at the time")
        events = len(self._events(asset))
        asset.action_condemn(reason="a different story")
        self.assertEqual(asset.disposal_reason, "the reason at the time")
        self.assertEqual(len(self._events(asset)), events)


@tagged("post_install", "-at_install")
class TestADisposalIsStampedThroughAnyDoor(EventCase):
    """Handoff 31 §C1. A disposal gets its date and its condition whichever
    way it arrives.

    Until then only `action_condemn` did this, in two overrides — one here
    and one in `myservice_asset_depreciation` — and `/condemn` being the
    proper door did not close the others: a PATCH of `state`, the Odoo form
    and the shell all disposed of an asset and stamped nothing, which is how
    the disposal report came to raise `no_disposal_date` against disposals
    made last week. `nrs.asset._stamp_disposal` is in `nrs.asset.write`,
    beside the recorders and for their reason. These go through a BARE
    write, because that is the door that used to be open; the button's own
    stamp is `test_condemning_records_one_event_naming_who_and_why`.
    """

    def test_a_bare_write_into_disposed_is_dated_and_decommissioned(self):
        asset = self._asset(condition="fair")
        # 00:30 on 2 March in Lagos, and still 1 March in UTC — which is
        # what `context_today` answers for a user with no timezone, and
        # every API credential's user has none.
        with freeze_time("2031-03-01 23:30:00"):
            asset.write({"state": "disposed"})
        self.assertEqual(asset.state, "disposed")
        self.assertEqual(asset.condition, "decommissioned")
        self.assertEqual(asset.disposal_date, date(2031, 3, 2),
                         "a Lagos day, the one the register snapshot cuts on")

    def test_a_condition_sent_with_the_disposal_does_not_survive_it(self):
        """`decommissioned` is what disposed MEANS here. A disposed asset in
        `good` condition is how the condition tiles came to count things
        that are gone."""
        asset = self._asset(condition="good")
        asset.write({"state": "disposed", "condition": "good"})
        self.assertEqual(asset.condition, "decommissioned")

    def test_a_date_the_writer_supplied_is_kept(self):
        """An integration carrying a disposal made elsewhere knows when it
        happened, and this does not."""
        asset = self._asset()
        with freeze_time("2031-03-01 23:30:00"):
            asset.write({"state": "disposed",
                         "disposal_date": "2026-01-31"})
        self.assertEqual(asset.disposal_date, date(2026, 1, 31))
        self.assertEqual(asset.condition, "decommissioned")

    def test_a_date_already_on_the_asset_is_kept(self):
        """Paperwork written up BEFORE the act — the date was agreed at the
        board of survey, and the status follows a week later."""
        asset = self._asset(disposal_date="2026-01-31")
        with freeze_time("2031-03-01 23:30:00"):
            asset.write({"state": "disposed"})
        self.assertEqual(asset.disposal_date, date(2026, 1, 31))

    def test_an_asset_registered_as_already_disposed_gets_no_date(self):
        """NOT on `create`, deliberately. It was disposed of on some earlier
        day this system never saw; stamping today would replace a finding
        the disposal report can show — no date — with a date that is wrong,
        which it cannot. `test_disposal_report.py` depends on this for its
        unplaceable row."""
        with freeze_time("2031-03-01 23:30:00"):
            asset = self._asset(state="disposed", condition="poor")
        self.assertEqual(asset.state, "disposed")
        self.assertFalse(asset.disposal_date)
        self.assertEqual(asset.condition, "poor",
                         "the stamp is the write's; a create is a "
                         "registration and is left as it was sent")

    def test_the_stamp_is_not_a_second_event(self):
        """The stamp re-enters `write` with a condition and a date. Neither
        is a status, so the one change of status is still ONE event — and
        it still carries the reason and the source of the write that caused
        it, not of the stamp that followed."""
        asset = self._asset()
        asset.with_context(
            cadra_event_source="api_write",
            cadra_event_reason="written off").write({"state": "disposed"})
        events = self._events(asset)
        self.assertEqual(len(events), 1)
        self.assertEqual(events.event_type, "status_changed")
        self.assertEqual((events.from_value, events.to_value),
                         ("active", "disposed"))
        self.assertEqual(events.reason, "written off")
        self.assertEqual(events.source, "api_write")

    def test_a_multi_record_write_stamps_each_asset_that_was_disposed(self):
        """…and leaves the one that already was alone: its date is the day
        it was disposed of, not the day somebody re-sent its status."""
        already = self._asset()
        already.write({"state": "disposed", "disposal_date": "2026-01-31"})
        fresh = self._asset()
        other = self._asset(state="missing")
        with freeze_time("2031-03-01 23:30:00"):
            (already | fresh | other).write({"state": "disposed"})
        self.assertEqual(already.disposal_date, date(2026, 1, 31))
        self.assertEqual(fresh.disposal_date, date(2031, 3, 2))
        self.assertEqual(other.disposal_date, date(2031, 3, 2))
        self.assertEqual(
            (fresh | other | already).mapped("condition"),
            ["decommissioned"] * 3)

    def test_resending_disposed_to_an_undated_disposal_does_not_date_it(self):
        """The stamp belongs to the CHANGE into `disposed`. A legacy row —
        disposed, no date — whose status is re-sent by the app's edit form
        must not acquire today's date on the way: that would turn a finding
        into a wrong answer, one save at a time."""
        asset = self._asset(state="disposed")
        self.assertFalse(asset.disposal_date)
        with freeze_time("2031-03-01 23:30:00"):
            asset.write({"state": "disposed", "notes": "saved from the form"})
        self.assertFalse(asset.disposal_date)
        self.assertEqual(asset.notes, "saved from the form")
