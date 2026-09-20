"""Where a thing has been — the record, and what it is worth nothing without.

The same two guarantees as the chain of custody, for the same reasons, and a
third that custody did not need:

    1. Every change of `location_id` produces exactly one row, whoever made it.
    2. A row, once written, cannot be changed or removed by anybody.
    3. A change the DATABASE makes — not the ORM — is recorded too.

The first is the one handoff 27 measured the absence of: on `nrs19`, 1,146
tracked changes of location against ONE transfer row, because only `POST
/assets/<id>/move` and a completed transfer wrote a row at all. So these go
through the ORM, as `test_custody_chain.py` does, and not through any route.

The third exists because `nrs_asset.location_id` is `ON DELETE SET NULL` and
`generic_location.parent_id` is `ON DELETE CASCADE`: deleting a building
empties the location of every asset in every room beneath it, in one
statement, with no `write` and no tracking row. No search of the Python finds
that writer. It was found by reading the foreign key.

Run with:
    odoo -d <db> -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register --stop-after-init
"""
from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase


class MovementCase(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Asset = self.env["nrs.asset"]
        self.Movement = self.env["nrs.asset.movement"]
        self.category = self.env["nrs.asset.category"].create(
            {"name": "Movement test category"})
        Location = self.env["generic.location"]
        self.building = Location.create({"name": "Movement test building"})
        self.room = Location.create({"name": "Movement test room",
                                     "parent_id": self.building.id})
        self.elsewhere = Location.create({"name": "Movement test elsewhere"})
        self.alice = self.env["hr.employee"].create({"name": "Movement Alice"})

    def _asset(self, **vals):
        return self.Asset.create(dict(
            {"name": "Movement test asset", "category_id": self.category.id},
            **vals))

    def _moves(self, asset):
        return self.Movement.search([("asset_id", "=", asset.id)], order="id")


@tagged("post_install", "-at_install")
class TestMovementAppendOnly(MovementCase):

    def _a_move(self):
        asset = self._asset(location_id=self.room.id)
        return asset, self._moves(asset)

    def test_a_row_cannot_be_edited(self):
        _, moves = self._a_move()
        with self.assertRaises(UserError):
            moves.write({"reason": "rewritten"})

    def test_a_row_cannot_be_edited_with_sudo(self):
        """The administrator is refused too. That is the whole point."""
        _, moves = self._a_move()
        with self.assertRaises(UserError) as raised:
            moves.sudo().write({"to_location_id": self.elsewhere.id})
        self.assertIn("sudo", str(raised.exception))

    def test_a_row_cannot_be_deleted(self):
        _, moves = self._a_move()
        with self.assertRaises(UserError):
            moves.unlink()

    def test_a_row_cannot_be_deleted_with_sudo(self):
        _, moves = self._a_move()
        with self.assertRaises(UserError):
            moves.sudo().unlink()

    def test_a_row_cannot_be_written_by_hand(self):
        """Not by ACL — by the model. One bad ACL line must not reach it."""
        asset = self._asset()
        with self.assertRaises(UserError):
            self.Movement.sudo().create({
                "asset_id": asset.id, "to_location_id": self.room.id,
                "moved_at": "2020-01-01 00:00:00"})

    def test_deleting_the_asset_is_refused(self):
        """`restrict`, not `cascade`: `nrs.asset.transfer` cascades, and that
        is half of why a transfer row was never evidence."""
        asset, _ = self._a_move()
        self.env.flush_all()
        with self.assertRaises(Exception), self.env.cr.savepoint():
            asset.unlink()
            self.env.flush_all()

    def test_duplicating_an_asset_does_not_copy_its_moves(self):
        asset, _ = self._a_move()
        asset.write({"location_id": self.elsewhere.id})
        self.assertEqual(len(self._moves(asset)), 2)
        # NOT a bare `copy()`: that fails on every asset today, before it
        # reaches anything of ours — `asset_tag` is copied and then collides
        # with the one-active-tag rule (`asset_tag._check_unique_active`).
        # Pre-existing, reported in handoff 28, and not what is under test.
        twin = asset.copy({"asset_tag": False, "asset_code": False})
        moves = self._moves(twin)
        # One row: the twin's own beginning, where it was created.
        self.assertEqual(len(moves), 1)
        self.assertFalse(moves.from_location_id)
        self.assertEqual(moves.to_location_id, self.elsewhere)


@tagged("post_install", "-at_install")
class TestEveryMoveIsRecorded(MovementCase):

    def test_an_asset_created_at_a_location_begins_there(self):
        asset = self._asset(location_id=self.room.id)
        move = self._moves(asset)
        self.assertEqual(len(move), 1)
        self.assertFalse(move.from_location_id)
        self.assertFalse(move.from_location_name)
        self.assertEqual(move.to_location_id, self.room)
        self.assertEqual(move.moved_by_id, self.env.user)
        self.assertEqual(move.moved_by_name, self.env.user.name)

    def test_an_asset_created_nowhere_has_no_row(self):
        self.assertFalse(self._moves(self._asset()))

    def test_a_plain_write_is_recorded(self):
        """The quiet door: PATCH, the form, a shell. No transfer, no route."""
        asset = self._asset(location_id=self.room.id)
        asset.write({"location_id": self.elsewhere.id})
        moves = self._moves(asset)
        self.assertEqual(len(moves), 2)
        self.assertEqual(moves[1].from_location_id, self.room)
        self.assertEqual(moves[1].to_location_id, self.elsewhere)
        self.assertEqual(moves[1].source, "direct")
        self.assertFalse(moves[1].transfer_id, "a move is not always a "
                         "transfer, and none is invented for one that had none")

    def test_the_full_path_is_recorded_not_the_leaf(self):
        asset = self._asset(location_id=self.room.id)
        self.assertEqual(self._moves(asset).to_location_name,
                         self.room.display_name)
        self.assertIn("Movement test building",
                      self._moves(asset).to_location_name)

    def test_writing_the_same_location_records_nothing(self):
        asset = self._asset(location_id=self.room.id)
        asset.write({"location_id": self.room.id})
        self.assertEqual(len(self._moves(asset)), 1)

    def test_a_write_that_does_not_name_the_location_records_nothing(self):
        asset = self._asset(location_id=self.room.id)
        asset.write({"name": "renamed", "custodian_id": self.alice.id})
        self.assertEqual(len(self._moves(asset)), 1)

    def test_a_multi_record_write_records_only_what_moved(self):
        here = self._asset(location_id=self.elsewhere.id)
        there = self._asset(location_id=self.room.id)
        (here | there).write({"location_id": self.elsewhere.id})
        self.assertEqual(len(self._moves(here)), 1, "was already there")
        self.assertEqual(len(self._moves(there)), 2)

    def test_clearing_the_location_is_a_move_to_nowhere(self):
        asset = self._asset(location_id=self.room.id)
        asset.write({"location_id": False})
        last = self._moves(asset)[-1]
        self.assertEqual(last.from_location_id, self.room)
        self.assertFalse(last.to_location_id)
        self.assertFalse(last.to_location_name)

    def test_custody_and_location_in_one_write_record_one_of_each(self):
        asset = self._asset(location_id=self.room.id)
        asset.write({"location_id": self.elsewhere.id,
                     "custodian_id": self.alice.id})
        self.assertEqual(len(self._moves(asset)), 2)
        self.assertEqual(len(asset.custody_ids), 1)

    def test_renaming_a_location_does_not_rewrite_where_an_asset_was(self):
        asset = self._asset(location_id=self.elsewhere.id)
        self.elsewhere.write({"name": "Movement test RENAMED"})
        self.assertIn("elsewhere", self._moves(asset).to_location_name)


@tagged("post_install", "-at_install")
class TestTheSourceAndTheTransfer(MovementCase):

    def test_a_declared_source_and_reason_are_carried(self):
        asset = self._asset(location_id=self.room.id)
        asset.with_context(
            cadra_movement_source="api_move",
            cadra_movement_reason="floor reorganisation",
        ).write({"location_id": self.elsewhere.id})
        last = self._moves(asset)[-1]
        self.assertEqual(last.source, "api_move")
        self.assertEqual(last.reason, "floor reorganisation")

    def test_a_completed_transfer_is_linked_and_labelled(self):
        asset = self._asset(location_id=self.room.id)
        transfer = self.env["nrs.asset.transfer"].create({
            "asset_id": asset.id,
            "from_location_id": self.room.id,
            "to_location_id": self.elsewhere.id,
            "reason": "handed to the annex",
        })
        transfer.action_complete()
        last = self._moves(asset)[-1]
        self.assertEqual(last.source, "transfer")
        self.assertEqual(last.transfer_id, transfer)
        self.assertEqual(last.transfer_reference, transfer.name)
        self.assertEqual(last.reason, "handed to the annex")

    def test_the_reference_survives_the_transfer_being_deleted(self):
        """The transfer is a document an asset manager can delete. The move
        is a fact, and must outlive its paperwork."""
        asset = self._asset(location_id=self.room.id)
        transfer = self.env["nrs.asset.transfer"].create({
            "asset_id": asset.id,
            "from_location_id": self.room.id,
            "to_location_id": self.elsewhere.id,
        })
        transfer.action_complete()
        reference = transfer.name
        transfer.unlink()
        self.env.invalidate_all()
        last = self._moves(asset)[-1]
        self.assertFalse(last.transfer_id)
        self.assertEqual(last.transfer_reference, reference)

    def test_nothing_writes_a_reconstruction_yet(self):
        """The label exists at the source before any backfill does."""
        values = dict(self.Movement._fields["source"].selection)
        self.assertIn("tracking_backfill", values)
        self.assertFalse(self.Movement.search_count(
            [("source", "=", "tracking_backfill")]))


@tagged("post_install", "-at_install")
class TestTheDatabaseMovesThingsToo(MovementCase):

    def test_deleting_a_location_records_every_asset_in_it(self):
        asset = self._asset(location_id=self.elsewhere.id)
        name = self.elsewhere.display_name
        self.elsewhere.unlink()
        self.env.invalidate_all()
        self.assertFalse(asset.location_id, "the foreign key emptied it")
        last = self._moves(asset)[-1]
        self.assertEqual(last.source, "location_deleted")
        self.assertEqual(last.from_location_name, name)
        self.assertFalse(last.to_location_name)

    def test_deleting_a_building_records_the_assets_in_its_rooms(self):
        """`parent_id` cascades in the database; the ORM never calls `unlink`
        on the room, so the building's `unlink` has to look beneath itself."""
        asset = self._asset(location_id=self.room.id)
        self.building.unlink()
        self.env.invalidate_all()
        self.assertFalse(asset.location_id)
        self.assertEqual(self._moves(asset)[-1].source, "location_deleted")
        self.assertIn("Movement test room",
                      self._moves(asset)[-1].from_location_name)

    def test_an_asset_somewhere_else_is_not_touched(self):
        bystander = self._asset(location_id=self.elsewhere.id)
        self.building.unlink()
        self.assertEqual(len(self._moves(bystander)), 1)


@tagged("post_install", "-at_install")
class TestAVerifierTheRecordDoesNotHave(MovementCase):
    """Not about location — about the same rule, found beside it."""

    def test_a_date_that_arrives_alone_clears_the_old_verifier(self):
        asset = self._asset()
        asset.action_verify()
        self.assertEqual(asset.last_verified_by, self.env.user)
        asset.write({"last_verified_date": "2026-06-01"})
        self.assertFalse(
            asset.last_verified_by,
            "verified in June, by somebody who checked nothing in June")

    def test_a_date_that_arrives_with_a_verifier_keeps_it(self):
        asset = self._asset()
        asset.action_verify(notes="sighted")
        self.assertEqual(asset.last_verified_by, self.env.user)
        self.assertEqual(asset.verification_notes, "sighted")

    def test_a_note_less_verification_does_not_inherit_the_last_ones_notes(self):
        asset = self._asset()
        asset.action_verify(notes="first check")
        asset.action_verify()
        self.assertFalse(asset.verification_notes)

    def test_a_refused_location_delete_leaves_no_row(self):
        """The rows are written before `super().unlink()` checks anything."""
        asset = self._asset(location_id=self.elsewhere.id)
        self.env["nrs.asset.transfer"].create({     # restricts the delete
            "asset_id": asset.id,
            "from_location_id": self.elsewhere.id,
            "to_location_id": self.room.id})
        self.env.flush_all()
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.elsewhere.unlink()
                self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(asset.location_id, self.elsewhere)
        self.assertEqual(len(self._moves(asset)), 1,
                         "a location that is still there, recorded deleted")


@tagged("post_install", "-at_install")
class TestTheFormSavesWhatItShows(MovementCase):

    def test_the_readonly_location_carries_force_save(self):
        """Odoo's web client drops a readonly field from the save unless it
        carries `force_save` (`record.js`, `_getChanges`). The form fills
        `location_id` from the room onchange and then, without this, threw it
        away — showing a new Location and storing the old one."""
        view = self.env.ref("myservice_asset_register.view_nrs_asset_form",
                            raise_if_not_found=False)
        if not view:
            view = self.env["ir.ui.view"].search(
                [("model", "=", "nrs.asset"), ("type", "=", "form"),
                 ("inherit_id", "=", False)], limit=1)
        arch = etree.fromstring(
            self.Asset.get_view(view.id, "form")["arch"])
        fields = arch.xpath("//field[@name='location_id']")
        self.assertTrue(fields, "the form no longer shows location_id at all")
        for field in fields:
            # ANY readonly attribute — a literal or an expression — and not
            # only the literal "1", which would let this pass vacuously the
            # day somebody writes `readonly="state == 'disposed'"`.
            if field.get("readonly") not in (None, "0", "False"):
                self.assertEqual(
                    field.get("force_save"), "1",
                    "a readonly location_id without force_save is discarded "
                    "on save")


@tagged("post_install", "-at_install")
class TestTheImporterDoesNotMoveThingsToNowhere(MovementCase):
    """An UPDATE line used to write `location_id` unconditionally, so a blank
    cell — or a name with a typo, which `ilike` resolves to nothing — wrote
    `False` and moved the asset to nowhere. Since the recorder, that mistake
    would also be permanent."""

    def _update(self, asset, location_text):
        session = self.env["nrs.asset.import"].create({
            "name": "movement test import", "source": "excel",
            "state": "validated"})
        line = self.env["nrs.asset.import.line"].create({
            "import_id": session.id, "status": "update",
            "asset_code": asset.asset_code, "asset_name": asset.name,
            "category": self.category.name, "location": location_text,
            "raw_line": "{}"})
        session.action_import()
        return line

    def test_a_blank_location_leaves_the_asset_where_it_is(self):
        asset = self._asset(location_id=self.room.id)
        line = self._update(asset, "")
        self.assertEqual(line.status, "imported", line.status_note)
        self.assertEqual(asset.location_id, self.room)
        self.assertEqual(len(self._moves(asset)), 1)

    def test_a_location_that_matches_nothing_says_so_and_moves_nothing(self):
        asset = self._asset(location_id=self.room.id)
        line = self._update(asset, "No Such Place Anywhere 9f3a")
        self.assertEqual(asset.location_id, self.room)
        self.assertEqual(len(self._moves(asset)), 1)
        self.assertIn("matched no location", line.status_note or "")

    def test_a_location_that_is_found_still_moves_the_asset(self):
        asset = self._asset(location_id=self.room.id)
        self._update(asset, "Movement test elsewhere")
        self.assertEqual(asset.location_id, self.elsewhere)
        self.assertEqual(self._moves(asset)[-1].source, "direct")
