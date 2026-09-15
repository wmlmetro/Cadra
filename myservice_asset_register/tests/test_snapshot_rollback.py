"""The register as it stood on a past date — and the three ways that lies.

Handoff 16 §B1. A snapshot's whole value is that an auditor can reconcile a
figure against it, so the failures that matter are not "it crashed" but:

    1. **It answers as-of-today while looking as-of-the-date.** A field that
       is not tracked, or is tracked but has no rows for this asset, returns
       today's value — correctly, in the second case, and misleadingly in the
       first. The tests below assert that the two are distinguishable from the
       response: `SNAPSHOT_ROLLED_BACK` / `SNAPSHOT_AS_OF_TODAY` say which
       class a field is in before a row is read, `_fidelity.unknown` says
       which fields are degraded for one row, and `_changed_since` says which
       fields actually moved. A status check would see a 200 and six columns.

    2. **It publishes a translated label where an enum belongs.** Odoo stores
       a Selection's tracking value as `dict(selection)[key]` — the LABEL, in
       whatever language the acting user had. Rolling that back verbatim would
       put "Under Repair" into a `state` field an integrator branches on.

    3. **It writes.** Every route in this API `sudo()`s, and the report reads
       stored computes and the depreciation policy. The write-nothing case
       fingerprints `write_date` on the assets it touched plus the row counts
       of `mail.tracking.value`, `nrs.asset.custody` and `mail.message`, and
       flushes AFTER the run so a pending compute cannot hide until the next
       transaction.

The fixtures do three things by raw SQL, all of them deliberate and none of
them reachable from the engine under test:

  * **`create_date` is written by POSTGRES** (`now() at time zone 'UTC'` in
    the INSERT), so `freeze_time` cannot move it. An asset that has to predate
    the snapshot must be backdated with an UPDATE.
  * **`mail_message.date` is set by Odoo at flush**, so a change that has to
    fall on a chosen side of the cutoff is stamped by id after the write.
  * **`nrs.asset.custody` refuses `write` even under `sudo()`** — by design —
    so a link that has to predate the cutoff is backdated the same way.

And tracking is finalised in `cr.precommit`, not in `write`: without
`_flush_tracking()` no `mail.tracking.value` row exists at all and every test
here passes for the wrong reason. Worse, `nrs.asset.create` calls
`_track_discard()`, which suppresses tracking for that record until the
precommit runs — so a write issued after a create and before a flush produces
NO tracking row. Both are why every fixture flushes between steps.

Run with:
    odoo -d <db> -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register --stop-after-init
"""
from datetime import date, datetime

from odoo.tests import tagged

from odoo.addons.myservice_asset_register.models.asset_snapshot import (
    SNAPSHOT_AS_OF_TODAY,
    SNAPSHOT_NOT_RECOVERABLE,
    SNAPSHOT_ROLLED_BACK,
    snapshot_cutoff,
)
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

# The date every test asks about, and the two sides of its cutoff.
# `snapshot_cutoff(AS_OF)` is 2020-06-30 23:00:00 UTC — the end of 30 June in
# Lagos. Both stamps are hours clear of it so nothing here depends on the
# boundary arithmetic being off by an hour; `TestTheCutoff` tests that
# directly instead.
AS_OF = date(2020, 6, 30)
CREATED_AT = "2020-01-01 08:00:00"
BEFORE_CUTOFF = "2020-03-01 09:00:00"
AFTER_CUTOFF = "2021-03-01 09:00:00"
LATER_STILL = "2022-03-01 09:00:00"


class SnapshotCase(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Asset = self.env["nrs.asset"]
        self.Custody = self.env["nrs.asset.custody"]
        self.category = self.env["nrs.asset.category"].create(
            {"name": "Snapshot test category"})
        Employee = self.env["hr.employee"]
        self.alice = Employee.create({"name": "Snapshot Alice"})
        self.bob = Employee.create({"name": "Snapshot Bob"})
        self.carol = Employee.create({"name": "Snapshot Carol"})
        Location = self.env["generic.location"]
        self.place_a = Location.create({"name": "Snapshot location A"})
        self.place_b = Location.create({"name": "Snapshot location B"})

    # ── Fixture plumbing ─────────────────────────────────────────────

    def _flush_tracking(self):
        """Force the tracking values into existence.

        Odoo 19 registers `_track_finalize` on `cr.precommit`, so a tracked
        write produces no `mail.tracking.value` row until the cursor flushes.
        A `TransactionCase` never commits, so without this every rollback test
        would see an empty history and pass by reporting today's values.
        """
        self.env.flush_all()
        self.env.cr.flush()

    def _mark(self):
        """The highest message id right now, so the next step's messages can
        be identified and stamped without touching anybody else's."""
        self.env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM mail_message")
        return self.env.cr.fetchone()[0]

    def _stamp_after(self, mark, when):
        """Move every `nrs.asset` chatter message written since `mark`."""
        self._flush_tracking()
        self.env.cr.execute(
            "UPDATE mail_message SET date = %s "
            " WHERE id > %s AND model = 'nrs.asset'",
            (when, mark))
        self.env.invalidate_all()

    def _backdate_creation(self, asset, when=CREATED_AT):
        """`create_date` comes from Postgres, so this is the only way."""
        self._flush_tracking()
        self.env.cr.execute(
            "UPDATE nrs_asset SET create_date = %s WHERE id = %s",
            (when, asset.id))
        self.env.invalidate_all()

    def _backdate_links(self, asset, when):
        """Backdate this asset's custody links.

        `nrs.asset.custody.write` raises unconditionally — that is the model's
        entire point — so a link that has to sit before the cutoff can only be
        placed there from outside the ORM. This is fixture construction, not a
        thing the engine can do.
        """
        self._flush_tracking()
        self.env.cr.execute(
            "UPDATE nrs_asset_custody SET changed_at = %s WHERE asset_id = %s",
            (when, asset.id))
        self.env.invalidate_all()

    def _asset(self, **vals):
        """An asset that existed on `AS_OF`, with its tracking window open."""
        asset = self.Asset.create(dict(
            {"name": "Snapshot subject", "category_id": self.category.id},
            **vals))
        # Flush before anything else touches it: `create` discards tracking
        # for the record until the precommit runs, so a write issued before
        # this line records nothing at all.
        self._flush_tracking()
        self._backdate_creation(asset)
        return asset

    def _row(self, asset, as_of=AS_OF):
        rows = asset.snapshot_at(as_of)
        self.assertIn(asset.id, rows,
                      "the asset should be in the register on %s" % as_of)
        return rows[asset.id]


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheCutoff(SnapshotCase):
    """"As it stood on 31 March" is a sentence spoken in Lagos."""

    def test_the_cutoff_is_the_end_of_the_day_in_lagos(self):
        """WAT is a fixed UTC+01:00 and Nigeria has never observed daylight
        saving, so the end of 31 March locally is 23:00 UTC on 31 March. Both
        `mail_message.date` and `custody.changed_at` are naive UTC, which is
        the space this has to land in."""
        self.assertEqual(snapshot_cutoff(date(2026, 3, 31)),
                         datetime(2026, 3, 31, 23, 0, 0))

    def test_the_cutoff_accepts_a_string(self):
        self.assertEqual(snapshot_cutoff("2026-03-31"),
                         datetime(2026, 3, 31, 23, 0, 0))

    def test_a_change_after_the_local_midnight_is_not_in_the_snapshot(self):
        """23:30 UTC on 31 March is 00:30 on 1 April in Lagos. Stated as a
        test because it is the one consequence of the choice that will
        surprise somebody."""
        cutoff = snapshot_cutoff(date(2026, 3, 31))
        self.assertGreater(datetime(2026, 3, 31, 23, 30), cutoff)


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestRollback(SnapshotCase):

    def test_a_change_after_the_date_rolls_back(self):
        asset = self._asset(condition="good")
        mark = self._mark()
        asset.write({"condition": "poor"})
        self._stamp_after(mark, AFTER_CUTOFF)

        row = self._row(asset)
        self.assertEqual(row["condition"], "good")
        self.assertIn("condition", row.get("_changed_since", []))

    def test_a_field_with_no_change_returns_todays_value(self):
        """No recorded change means today's value IS the value at the date.

        This is a sound answer, not a degraded one — which is precisely why
        `_changed_since` has to exist: without it this row is byte-identical
        to one whose field was never tracked at all.
        """
        asset = self._asset(condition="good", name="Never renamed")
        mark = self._mark()
        asset.write({"condition": "poor"})
        self._stamp_after(mark, AFTER_CUTOFF)

        row = self._row(asset)
        self.assertEqual(row["name"], "Never renamed")
        self.assertNotIn("name", row.get("_changed_since", []))

    def test_a_change_before_the_date_keeps_todays_value(self):
        asset = self._asset(condition="good")
        mark = self._mark()
        asset.write({"condition": "poor"})
        self._stamp_after(mark, BEFORE_CUTOFF)

        row = self._row(asset)
        self.assertEqual(row["condition"], "poor")
        self.assertNotIn("condition", row.get("_changed_since", []))

    def test_only_the_earliest_change_after_the_date_counts(self):
        """Two changes after the date roll back to the value before the
        FIRST of them, not the second. A reverse replay that stops at the
        newest row reports the second-to-last value as history."""
        asset = self._asset(condition="good")
        mark = self._mark()
        asset.write({"condition": "fair"})
        self._stamp_after(mark, AFTER_CUTOFF)
        mark = self._mark()
        asset.write({"condition": "poor"})
        self._stamp_after(mark, LATER_STILL)

        self.assertEqual(self._row(asset)["condition"], "good")

    def test_a_selection_rolls_back_to_a_technical_key(self):
        """Odoo writes `dict(selection)[key]` into `old_value_char` — the
        TRANSLATED LABEL. Publishing that verbatim would put "Under Repair"
        into a `state` field that Vendra and the SPA branch on."""
        asset = self._asset(state="active")
        mark = self._mark()
        asset.write({"state": "in_repair"})
        self._stamp_after(mark, AFTER_CUTOFF)

        row = self._row(asset)
        self.assertEqual(row["state"], "active")
        keys = {
            key for key, _label
            in self.Asset.fields_get(["state"], ["selection"])
            ["state"]["selection"]
        }
        self.assertIn(row["state"], keys,
                      "a rolled-back Selection must be a technical key")

    def test_an_unmappable_selection_label_is_published_and_flagged(self):
        """A row written under a language this deployment no longer carries,
        or naming an option since removed, cannot be mapped back to a key.
        Guessing one would put an unknown value into a published enum, so the
        label is published as-is and the row says the field is degraded."""
        asset = self._asset(condition="good")
        mark = self._mark()
        asset.write({"condition": "poor"})
        self._stamp_after(mark, AFTER_CUTOFF)
        self.env.cr.execute(
            """
            UPDATE mail_tracking_value mtv
               SET old_value_char = 'Estado desconocido'
              FROM ir_model_fields f, mail_message m
             WHERE f.id = mtv.field_id
               AND m.id = mtv.mail_message_id
               AND f.model = 'nrs.asset' AND f.name = 'condition'
               AND m.model = 'nrs.asset' AND m.res_id = %s
            """, (asset.id,))
        self.env.invalidate_all()

        row = self._row(asset)
        self.assertEqual(row["condition"], "Estado desconocido")
        self.assertIn("condition", row["_fidelity"]["unknown"])

    def test_a_many2one_carries_the_name_recorded_at_the_time(self):
        """The record may have been renamed since. A snapshot should read as
        it read, so the name in the tracking row wins over the name today."""
        asset = self._asset(location_id=self.place_a.id)
        mark = self._mark()
        asset.write({"location_id": self.place_b.id})
        self._stamp_after(mark, AFTER_CUTOFF)
        self.place_a.write({"name": "Renamed long afterwards"})
        self._flush_tracking()

        row = self._row(asset)
        self.assertEqual(row["location_id"]["id"], self.place_a.id)
        self.assertEqual(row["location_id"]["name"], "Snapshot location A")

    def test_an_empty_many2one_rolls_back_to_none(self):
        """Odoo writes `(0, '')` for an empty many2one. Read as an id of 0
        that would be a dangling reference; read as missing it would silently
        become today's value."""
        asset = self._asset()
        mark = self._mark()
        asset.write({"location_id": self.place_b.id})
        self._stamp_after(mark, AFTER_CUTOFF)

        self.assertIsNone(self._row(asset)["location_id"])

    def test_a_date_field_rolls_back(self):
        """There is no `old_value_date` column: Odoo stores a Date in
        `old_value_datetime` at midnight. Reading the wrong column returns
        None and the field silently reports today's value."""
        asset = self._asset(last_verified_date=date(2019, 5, 5))
        mark = self._mark()
        asset.write({"last_verified_date": date(2022, 1, 1)})
        self._stamp_after(mark, AFTER_CUTOFF)

        self.assertEqual(self._row(asset)["last_verified_date"], "2019-05-05")

    def test_dates_are_published_as_iso_strings_either_way(self):
        """The rolled-back path and the unchanged path must agree on shape,
        or a consumer needs two branches for one column."""
        changed = self._asset(last_verified_date=date(2019, 5, 5))
        mark = self._mark()
        changed.write({"last_verified_date": date(2022, 1, 1)})
        self._stamp_after(mark, AFTER_CUTOFF)
        untouched = self._asset(last_verified_date=date(2019, 5, 5))

        self.assertEqual(self._row(changed)["last_verified_date"],
                         self._row(untouched)["last_verified_date"])

    def test_renaming_a_location_is_not_reported_as_a_move(self):
        """`_changed_since` compares many2ones by id. Comparing the published
        dicts would report a rename as a relocation — the finding an auditor
        chases first and the one that is not there."""
        asset = self._asset(location_id=self.place_a.id)
        self.place_a.write({"name": "Renamed, not moved"})
        self._flush_tracking()

        self.assertNotIn("location_id",
                         self._row(asset).get("_changed_since", []))


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestExistence(SnapshotCase):

    def test_an_asset_created_after_the_date_is_not_in_the_register(self):
        """It was not on the register that day. A row for it is a fabrication,
        and an auditor reconciling a count would carry it forward."""
        newborn = self.Asset.create(
            {"name": "Created long after", "category_id": self.category.id})
        self._flush_tracking()

        self.assertEqual(newborn.snapshot_at(AS_OF), {},
                         "an asset created after the date must not appear")
        found = self.Asset.search(
            self.Asset.snapshot_existence_domain(AS_OF) +
            [("id", "=", newborn.id)])
        self.assertFalse(found)

    def test_an_asset_created_before_the_date_is_in_the_register(self):
        oldie = self._asset()
        self.assertIn(oldie.id, oldie.snapshot_at(AS_OF))
        found = self.Asset.search(
            self.Asset.snapshot_existence_domain(AS_OF) +
            [("id", "=", oldie.id)])
        self.assertEqual(found, oldie)

    def test_a_mixed_page_returns_only_the_assets_that_existed(self):
        oldie = self._asset()
        newborn = self.Asset.create(
            {"name": "Created long after", "category_id": self.category.id})
        self._flush_tracking()

        rows = (oldie | newborn).snapshot_at(AS_OF)
        self.assertEqual(set(rows), {oldie.id})

    def test_a_deleted_asset_is_named_as_unrecoverable(self):
        """The snapshot is a LOWER BOUND on the register's size, and the
        response has to say so — an auditor reconciling a count against a
        silently truncated one produces a discrepancy that is ours."""
        self.assertIn("deleted_assets",
                      self.Asset.snapshot_fidelity()["not_recoverable"])
        self.assertIn("deleted_assets",
                      self.Asset.snapshot_fidelity()["notes"])


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestCustodyBeatsTracking(SnapshotCase):
    """`custodian_id` is the one field with a history that cannot be deleted.

    `mail.tracking.value` hangs off `mail.message`, so anybody who can delete
    a message can delete the evidence. `nrs.asset.custody` raises on `write`
    and `unlink` even under `sudo()`. Where the chain reaches, it wins.
    """

    def _chained_asset(self):
        """alice (pre-cutoff) → bob (pre-cutoff) → carol (post-cutoff).

        So the answer on `AS_OF` is bob, from BOTH branches of the resolver:
        the earliest link after the cutoff names bob as its `from`, and the
        last link before the cutoff names bob as its `to`.
        """
        asset = self._asset(custodian_id=self.alice.id)
        mark = self._mark()
        asset.write({"custodian_id": self.bob.id})
        self._stamp_after(mark, BEFORE_CUTOFF)
        self._backdate_links(asset, BEFORE_CUTOFF)

        mark = self._mark()
        asset.write({"custodian_id": self.carol.id})
        self._stamp_after(mark, AFTER_CUTOFF)
        self.env.cr.execute(
            "UPDATE nrs_asset_custody SET changed_at = %s "
            " WHERE asset_id = %s AND to_custodian_id = %s",
            (AFTER_CUTOFF, asset.id, self.carol.id))
        self.env.invalidate_all()
        return asset

    def test_the_custodian_at_the_date_comes_from_the_chain(self):
        asset = self._chained_asset()
        row = self._row(asset)

        self.assertEqual(row["custodian_id"]["id"], self.bob.id)
        self.assertEqual(row["custodian_id"]["name"], "Snapshot Bob")
        self.assertNotEqual(row["custodian_id"]["id"], asset.custodian_id.id,
                            "carol holds it today; bob held it on the date")

    def test_the_answer_matches_the_chain_it_came_from(self):
        """Read the chain independently and agree with it. If the two ever
        disagree the snapshot is inventing custody, which is the one thing
        an append-only record exists to make impossible."""
        asset = self._chained_asset()
        cutoff = snapshot_cutoff(AS_OF)
        links = self.Custody.search(
            [("asset_id", "=", asset.id)], order="changed_at, id")
        after = links.filtered(lambda l: l.changed_at >= cutoff)
        self.assertTrue(after, "fixture should straddle the cutoff")

        self.assertEqual(self._row(asset)["custodian_id"]["id"],
                         after[0].from_custodian_id.id)

    def test_the_chain_answers_even_when_the_tracking_values_are_gone(self):
        """Delete the chatter evidence — which any user who can delete a
        message can do — and the answer must be unchanged. This is the whole
        argument for `nrs.asset.custody` existing, expressed as a test."""
        asset = self._chained_asset()
        self.env.cr.execute(
            """
            DELETE FROM mail_tracking_value mtv
             USING ir_model_fields f, mail_message m
             WHERE f.id = mtv.field_id
               AND m.id = mtv.mail_message_id
               AND f.model = 'nrs.asset' AND f.name = 'custodian_id'
               AND m.model = 'nrs.asset' AND m.res_id = %s
            """, (asset.id,))
        self.env.invalidate_all()

        self.assertEqual(self._row(asset)["custodian_id"]["id"], self.bob.id)

    def test_a_chain_entirely_before_the_date_stands(self):
        asset = self._asset(custodian_id=self.alice.id)
        mark = self._mark()
        asset.write({"custodian_id": self.bob.id})
        self._stamp_after(mark, BEFORE_CUTOFF)
        self._backdate_links(asset, BEFORE_CUTOFF)

        row = self._row(asset)
        self.assertEqual(row["custodian_id"]["id"], self.bob.id)
        self.assertNotIn("custodian_id", row.get("_fidelity", {})
                         .get("unknown", []))

    def test_the_recorded_name_survives_the_employee_being_deleted(self):
        """A many2one to a deleted employee goes null. Without the snapshotted
        name the append-only row could still be emptied of its content from
        outside the model, and the snapshot would report an empty custodian
        where there was one."""
        asset = self._chained_asset()
        self.bob.unlink()
        self._flush_tracking()
        self.env.invalidate_all()

        self.assertEqual(self._row(asset)["custodian_id"]["name"],
                         "Snapshot Bob")

    def test_no_history_at_all_says_unknown_rather_than_today(self):
        """No custody link, no tracking row of any date, and somebody holds
        it today. The custodian shown is today's, and the row says so.

        Three of eight tenants have no chain at all and `nrs19` has one link
        against 11,878 assets, so this is not a corner case — it is what most
        of the estate looks like. An auditor told the record is silent can
        work with it; one shown today's custodian under a historical heading
        cannot.
        """
        asset = self._asset()
        # Set the custodian by SQL: writing it through the ORM is exactly what
        # creates the link this test needs to be absent.
        self.env.cr.execute(
            "UPDATE nrs_asset SET custodian_id = %s WHERE id = %s",
            (self.alice.id, asset.id))
        self.env.invalidate_all()

        row = self._row(asset)
        self.assertFalse(self.Custody.search_count(
            [("asset_id", "=", asset.id)]), "fixture should have no chain")
        self.assertIn("custodian_id", row["_fidelity"]["unknown"])
        self.assertEqual(row["custodian_id"]["id"], self.alice.id,
                         "today's custodian is still published, but flagged")

    def test_no_custodian_and_no_history_is_not_flagged(self):
        """Nobody holds it and nothing ever moved. That is an answer, not a
        gap — flagging it would make `unknown` mean 'this asset exists'."""
        asset = self._asset()
        row = self._row(asset)
        self.assertIsNone(row["custodian_id"])
        self.assertNotIn("custodian_id",
                         row.get("_fidelity", {}).get("unknown", []))


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestValue(SnapshotCase):
    """Depreciation is the one thing INT-10 §2.5 could already answer."""

    def setUp(self):
        super().setUp()
        self.has_depreciation = "depreciation_method" in self.Asset._fields

    def test_the_value_block_is_always_present(self):
        row = self._row(self._asset())
        self.assertIn("value", row)
        self.assertEqual(
            set(row["value"]),
            {"accumulated_depreciation", "book_value", "state"})

    def test_an_erp_managed_asset_has_no_value_history(self):
        """`value_at` returns `(None, None, 'erp_managed')` — an external
        system owns the figures and Cadra has never held a history for them.
        Publishing a zero would be a number an auditor could reconcile."""
        if not self.has_depreciation:
            self.skipTest("myservice_asset_depreciation is not installed")
        asset = self._asset()
        asset.write({
            "use_category_policy": False,
            "depreciation_method": "erp_managed",
        })
        self._flush_tracking()

        row = self._row(asset)
        self.assertIsNone(row["value"]["accumulated_depreciation"])
        self.assertIsNone(row["value"]["book_value"])
        self.assertIn("value", row["_fidelity"]["unknown"])

    def test_a_method_that_moved_after_the_date_flags_the_value(self):
        """Only `depreciation_method` is tracked; the cost basis, life,
        salvage and start date it is computed FROM are read as they stand
        today. Where the method itself moved after the date, the figures are
        not the figures that policy would have produced, and the row says so
        rather than presenting them as historical."""
        if not self.has_depreciation:
            self.skipTest("myservice_asset_depreciation is not installed")
        asset = self._asset(acquisition_cost=1200.0)
        mark = self._mark()
        asset.write({
            "use_category_policy": False,
            "depreciation_method": "straight_line",
            "useful_life_months": 12,
        })
        # Stamp the SETUP write too. Leaving it at "now" would put it after
        # the cutoff as well, and the rollback would then resolve against
        # whichever of the two carried the earlier timestamp — which is the
        # fixture accidentally testing the ordering rather than the flag.
        self._stamp_after(mark, BEFORE_CUTOFF)
        mark = self._mark()
        asset.write({"depreciation_method": "none"})
        self._stamp_after(mark, AFTER_CUTOFF)

        row = self._row(asset)
        self.assertEqual(row["depreciation_method"], "straight_line")
        self.assertIn("value", row["_fidelity"]["as_of_today"])


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheReportWritesNothing(SnapshotCase):
    """An acceptance criterion of handoff 16, and it is not obvious.

    The engine reads stored computes (`depreciable_cost`, `salvage_value`) and
    calls into the depreciation module; `_apply_depreciation()` one letter
    away WRITES the figures onto every record it touches. A report that
    quietly repairs what it finds can never honestly report zero.
    """

    def _fingerprint(self, assets):
        self.env.flush_all()
        self.env.invalidate_all()
        return {
            "write_date": {a.id: a.write_date for a in assets},
            "tracking":
                self.env["mail.tracking.value"].sudo().search_count([]),
            "custody": self.Custody.sudo().search_count([]),
            "messages": self.env["mail.message"].sudo().search_count([]),
        }

    def test_a_snapshot_moves_nothing(self):
        moved = self._asset(condition="good", custodian_id=self.alice.id,
                            location_id=self.place_a.id)
        mark = self._mark()
        moved.write({"condition": "poor", "location_id": self.place_b.id,
                     "custodian_id": self.bob.id})
        self._stamp_after(mark, AFTER_CUTOFF)
        still = self._asset()
        assets = moved | still

        before = self._fingerprint(assets)
        rows = assets.snapshot_at(AS_OF)
        self.assertEqual(len(rows), 2, "the fixture should have produced rows")
        # Flush AFTER the run: a stored compute the report left pending would
        # otherwise not be written until the next transaction, and this test
        # would pass while the write happened moments later.
        after = self._fingerprint(assets)

        self.assertEqual(before, after,
                         "snapshot_at must not write anything")

    def test_the_fidelity_block_moves_nothing(self):
        asset = self._asset()
        before = self._fingerprint(asset)
        self.Asset.snapshot_fidelity()
        self.Asset.snapshot_existence_domain(AS_OF)
        self.assertEqual(before, self._fingerprint(asset))


# ═════════════════════════════════════════════════════════════════════
@tagged("post_install", "-at_install")
class TestTheFidelityContract(SnapshotCase):
    """The lists are the report's real output — handoff 16 asks for them by
    name. A field that quietly falls out of one is the defect."""

    def _tracked_field_names(self):
        """From the LIVE registry, not from a grep.

        A `related=` field inherits `tracking` from its target with no
        `tracking=` of its own, so a source scan misses `tag_label_state`
        (`related='physical_tag_id.label_state'`) and `active_tag_number`
        (`related='active_tag_id.name'`) — between them the largest tracked
        field in the estate, at 11,934 rows on `nrs19`. This is the guard
        that catches the next one.
        """
        return set(self.env["ir.model.fields"].search([
            ("model", "=", "nrs.asset"),
            ("tracking", ">", 0),
        ]).mapped("name"))

    def test_every_tracked_field_is_rolled_back(self):
        missing = self._tracked_field_names() - set(SNAPSHOT_ROLLED_BACK)
        self.assertFalse(
            missing,
            "these fields on nrs.asset carry tracking and therefore have a "
            "history the snapshot is silently not using: %s. Add them to "
            "SNAPSHOT_ROLLED_BACK, or move them to SNAPSHOT_AS_OF_TODAY with "
            "a note saying why rolling them back is unsound."
            % sorted(missing))

    def test_nothing_is_rolled_back_without_a_history(self):
        """The other direction. A field in `SNAPSHOT_ROLLED_BACK` that is not
        tracked would return today's value under a historical heading — the
        exact failure the whole module exists to prevent."""
        tracked = self._tracked_field_names()
        untracked = [f for f in SNAPSHOT_ROLLED_BACK
                     if f in self.Asset._fields and f not in tracked]
        self.assertFalse(
            untracked,
            "claimed as-of-the-date but carries no tracking: %s" % untracked)

    def test_no_field_is_in_two_classes(self):
        rolled = set(SNAPSHOT_ROLLED_BACK)
        today = set(SNAPSHOT_AS_OF_TODAY)
        unrecoverable = set(SNAPSHOT_NOT_RECOVERABLE)
        self.assertFalse(rolled & today)
        self.assertFalse(rolled & unrecoverable)
        self.assertFalse(today & unrecoverable)

    def test_the_as_of_today_fields_really_have_no_history(self):
        tracked = self._tracked_field_names()
        wrong = [f for f in SNAPSHOT_AS_OF_TODAY if f in tracked]
        self.assertFalse(
            wrong,
            "published as as-of-today although it is tracked and could be "
            "rolled back: %s" % wrong)

    def test_the_fidelity_block_only_names_fields_this_tenant_has(self):
        """A field belonging to an uninstalled module is an absent column, not
        a degraded answer, and saying "as of the date" about it would be its
        own small lie."""
        fidelity = self.Asset.snapshot_fidelity()
        for fname in fidelity["rolled_back"] + fidelity["as_of_today"]:
            self.assertIn(fname, self.Asset._fields)

    def test_every_row_carries_every_declared_field(self):
        fidelity = self.Asset.snapshot_fidelity()
        row = self._row(self._asset())
        for fname in fidelity["rolled_back"] + fidelity["as_of_today"]:
            self.assertIn(fname, row,
                          "%s is declared in the fidelity block and missing "
                          "from the row" % fname)

    def test_nothing_not_recoverable_is_published_in_a_row(self):
        """Named, and deliberately not shown. Publishing today's figure beside
        historical ones invites a reconciliation that cannot be right."""
        row = self._row(self._asset())
        for fname in SNAPSHOT_NOT_RECOVERABLE:
            self.assertNotIn(fname, row)

    def test_fidelity_keys_are_absent_when_the_row_is_sound(self):
        """`_fidelity` present only when non-empty, so its presence is the
        signal. A block that is always there gets skipped by every reader."""
        if "depreciation_method" not in self.Asset._fields:
            # With no depreciation module every row legitimately carries
            # `_fidelity.unknown: ['value']`, so there is no sound row to
            # test against on this deployment.
            self.skipTest("myservice_asset_depreciation is not installed")
        asset = self._asset(condition="good")
        mark = self._mark()
        asset.write({"condition": "poor"})
        self._stamp_after(mark, AFTER_CUTOFF)
        row = self._row(asset)
        self.assertNotIn("_fidelity", row)

    def test_the_notes_explain_every_topic_that_needs_one(self):
        notes = self.Asset.snapshot_fidelity()["notes"]
        for topic in ("cutoff", "rolled_back", "as_of_today",
                      "not_recoverable", "tracking", "custodian_id", "value",
                      "deleted_assets"):
            self.assertTrue(notes.get(topic),
                            "no note for %s" % topic)
