"""ORM-level behaviour of depreciation policy inheritance.

The arithmetic is covered by tests/test_depreciation_engine.py (pure Python, no
database) and the HTTP surface by tests/test_depreciation.py. What is left, and
what these cover, is behaviour that only exists inside the ORM: how policy flows
from category to asset, and how constraints interact with that.

Run with:
    odoo -d <db> -u myservice_asset_depreciation --test-enable \\
         --test-tags /myservice_asset_depreciation --stop-after-init
"""
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import freeze_time
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase


@tagged("post_install", "-at_install")
class TestPolicyInheritance(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Asset = self.env["nrs.asset"]
        self.Category = self.env["nrs.asset.category"]

    def _category(self, **policy):
        vals = {"name": "Test Category", "code": "TESTCAT"}
        vals.update(policy)
        return self.Category.create(vals)

    def _asset(self, category, **vals):
        base = {"name": "Test Asset", "category_id": category.id}
        base.update(vals)
        return self.Asset.create(base)

    # ── The regression this file exists for ──────────────────────────────────

    def test_declining_balance_category_flows_down_without_tripping_its_own_constraint(self):
        """Regression: policy was applied one field at a time, so the method
        landed before the rate and _check_asset_depreciation_policy rejected a
        policy that is actually valid. Only declining-balance categories hit it,
        which is why it survived until a tenant had one."""
        cat = self._category(
            depreciation_method="declining_balance",
            useful_life_months=48,
            declining_rate=33.3,
        )
        asset = self._asset(cat, acquisition_cost=100000.0)

        self.assertEqual(asset.depreciation_method, "declining_balance")
        self.assertEqual(asset.useful_life_months, 48)
        self.assertEqual(asset.declining_rate, 33.3)

        # And again on an existing asset, which is the path the backfill takes.
        other = self._asset(cat, acquisition_cost=50000.0)
        other.write({"use_category_policy": False, "depreciation_method": "none"})
        other.write({"use_category_policy": True})
        self.assertEqual(other.depreciation_method, "declining_balance")
        self.assertEqual(other.declining_rate, 33.3)

    # ── Inheritance and override ─────────────────────────────────────────────

    def test_straight_line_category_flows_down_on_create(self):
        cat = self._category(depreciation_method="straight_line",
                             useful_life_months=60, salvage_rate=10.0)
        asset = self._asset(cat, acquisition_cost=1200000.0)
        self.assertEqual(asset.depreciation_method, "straight_line")
        self.assertEqual(asset.useful_life_months, 60)
        self.assertEqual(asset.salvage_value, 120000.0)

    def test_per_asset_override_survives_a_category_resync(self):
        cat = self._category(depreciation_method="straight_line",
                             useful_life_months=60)
        asset = self._asset(cat, acquisition_cost=1200000.0)
        asset.write({"use_category_policy": False, "useful_life_months": 12})

        asset._sync_policy_from_category()

        self.assertEqual(asset.useful_life_months, 12,
                         "an opted-out asset must keep its own policy")

    def test_changing_the_category_repoints_a_following_asset(self):
        sl = self._category(depreciation_method="straight_line", useful_life_months=60)
        db = self.Category.create({
            "name": "Other", "code": "OTHER",
            "depreciation_method": "declining_balance",
            "useful_life_months": 36, "declining_rate": 20.0,
        })
        asset = self._asset(sl, acquisition_cost=100000.0)
        asset.write({"category_id": db.id})
        self.assertEqual(asset.depreciation_method, "declining_balance")
        self.assertEqual(asset.declining_rate, 20.0)

    # ── ERP-managed ──────────────────────────────────────────────────────────

    def test_erp_managed_figures_are_never_overwritten_by_a_recompute(self):
        """NRS spec §6.2 — Cadra reads but does not compute."""
        cat = self._category(depreciation_method="straight_line", useful_life_months=60)
        asset = self._asset(cat, acquisition_cost=1000000.0,
                            acquisition_date="2020-01-01")
        asset.write({"use_category_policy": False,
                     "depreciation_method": "erp_managed"})
        asset.write({"accumulated_depreciation": 250000.0,
                     "current_book_value": 750000.0})

        asset._apply_depreciation()

        self.assertEqual(asset.accumulated_depreciation, 250000.0)
        self.assertEqual(asset.current_book_value, 750000.0)
        self.assertEqual(asset.depreciation_state, "erp_managed")
        self.assertEqual(asset.get_depreciation_schedule(), [])

    def test_cron_skips_erp_managed_assets(self):
        cat = self._category(depreciation_method="straight_line", useful_life_months=60)
        asset = self._asset(cat, acquisition_cost=1000000.0)
        asset.write({"use_category_policy": False,
                     "depreciation_method": "erp_managed",
                     "accumulated_depreciation": 111.0})
        self.Asset._cron_recompute_depreciation()
        self.assertEqual(asset.accumulated_depreciation, 111.0)

    # ── Start date provenance ────────────────────────────────────────────────

    def test_start_date_falls_back_and_records_its_source(self):
        cat = self._category(depreciation_method="straight_line", useful_life_months=60)

        acq = self._asset(cat, acquisition_cost=1.0, acquisition_date="2021-03-04")
        self.assertEqual(str(acq.depreciation_start_date), "2021-03-04")
        self.assertEqual(acq.depreciation_start_source, "acquisition")
        self.assertFalse(acq.depreciation_start_is_estimated)

        pur = self._asset(cat, acquisition_cost=1.0, purchase_date="2021-05-06")
        self.assertEqual(str(pur.depreciation_start_date), "2021-05-06")
        self.assertEqual(pur.depreciation_start_source, "purchase")

        none = self._asset(cat, acquisition_cost=1.0)
        self.assertEqual(none.depreciation_start_source, "created")
        self.assertTrue(none.depreciation_start_is_estimated,
                        "an inferred date must be flagged for backfill")

    def test_a_manual_start_date_is_not_re_resolved(self):
        cat = self._category(depreciation_method="straight_line", useful_life_months=60)
        asset = self._asset(cat, acquisition_cost=1.0)
        asset.write({"depreciation_start_date": "2019-01-01"})
        self.assertEqual(asset.depreciation_start_source, "manual")

        asset.write({"acquisition_date": "2022-07-07"})

        self.assertEqual(str(asset.depreciation_start_date), "2019-01-01")
        self.assertEqual(asset.depreciation_start_source, "manual")

    def test_clearing_a_manual_start_date_hands_control_back(self):
        cat = self._category(depreciation_method="straight_line", useful_life_months=60)
        asset = self._asset(cat, acquisition_cost=1.0, acquisition_date="2022-02-02")
        asset.write({"depreciation_start_date": "2019-01-01"})
        self.assertEqual(asset.depreciation_start_source, "manual")

        asset.write({"depreciation_start_date": False})

        self.assertEqual(str(asset.depreciation_start_date), "2022-02-02")
        self.assertEqual(asset.depreciation_start_source, "acquisition")

    # ── Validation ───────────────────────────────────────────────────────────

    def test_declining_balance_without_a_rate_is_rejected(self):
        cat = self._category(depreciation_method="straight_line", useful_life_months=60)
        asset = self._asset(cat, acquisition_cost=1.0)
        with self.assertRaises(ValidationError):
            asset.write({"use_category_policy": False,
                         "depreciation_method": "declining_balance",
                         "declining_rate": 0.0})

    def test_a_category_cannot_be_declining_balance_without_a_rate(self):
        with self.assertRaises(ValidationError):
            self._category(depreciation_method="declining_balance",
                           useful_life_months=48)

    def test_salvage_rate_is_bounded(self):
        with self.assertRaises(ValidationError):
            self._category(depreciation_method="straight_line",
                           useful_life_months=48, salvage_rate=140.0)

    # ── Disposal ─────────────────────────────────────────────────────────────

    def test_condemning_an_asset_stops_the_clock(self):
        cat = self._category(depreciation_method="straight_line",
                             useful_life_months=600)
        # A 50-year life so the board certainly runs past today — condemning
        # stamps disposal_date with today's date, and a schedule that already
        # ended would have nothing left to truncate.
        asset = self._asset(cat, acquisition_cost=1200000.0,
                            acquisition_date="2020-01-31")
        before = len(asset.get_depreciation_schedule())

        asset.action_condemn()

        self.assertEqual(asset.state, "disposed")
        self.assertTrue(asset.disposal_date, "disposal_date must be stamped")
        self.assertLess(len(asset.get_depreciation_schedule()), before)
        self.assertEqual(asset.depreciation_state, "disposed")

    def test_a_disposal_by_a_bare_write_stops_the_clock_too(self):
        """This module used to override `action_condemn` to stamp the date,
        because depreciation must stop on the day of disposal. Handoff 31
        deleted that override: the REGISTER stamps the date now, underneath
        every writer of `state`, and this module is owed the recompute only
        because `disposal_date` is a depreciation input and the stamp is a
        `write`. That is a dependency between two modules that nothing
        states in code, so it is stated here — through the door the old
        override never covered: a write of `state` and nothing else, which
        is what `PATCH {"state": "disposed"}` and the Odoo form send.
        """
        cat = self._category(depreciation_method="straight_line",
                             useful_life_months=600)
        asset = self._asset(cat, acquisition_cost=1200000.0,
                            acquisition_date="2020-01-31")
        before = len(asset.get_depreciation_schedule())

        asset.write({"state": "disposed"})

        self.assertTrue(asset.disposal_date, "disposal_date must be stamped")
        self.assertLess(len(asset.get_depreciation_schedule()), before)
        self.assertEqual(asset.depreciation_state, "disposed")

    def test_a_disposal_at_lagos_midnight_still_reads_disposed(self):
        """The two tests above, pinned at the one hour a night they were red.

        `nrs.asset._stamp_disposal` writes `disposal_date` as the LAGOS day
        (`snapshot_today`); `_apply_depreciation` used to measure `as_of`
        with `context_today` — the UTC day for a user with no timezone,
        which every API credential's user and the test runner's superuser
        are. Between 23:00 and 24:00 UTC the stamp is TOMORROW relative to
        `as_of`, the engine's `as_of >= disposal_date` check misses, and —
        because disposal truncates the schedule, so every remaining period
        has already ended — the state falls through to `fully_depreciated`.
        That is report 36's `'fully_depreciated' != 'disposed'`, red for
        one hour a night and green the other twenty-three, which is how it
        ran through six handoffs' suites unseen. The clock is frozen inside
        the window so this cannot depend on when the suite runs.
        """
        cat = self._category(depreciation_method="straight_line",
                             useful_life_months=600)
        asset = self._asset(cat, acquisition_cost=1200000.0,
                            acquisition_date="2020-01-31")
        with freeze_time("2026-01-15 23:30:00"):
            asset.action_condemn()
            # The premise, asserted so it cannot rot: the register stamps
            # the Lagos day, which at 23:30 UTC is already the 16th.
            self.assertEqual(asset.disposal_date, date(2026, 1, 16))
            self.assertEqual(asset.state, "disposed")
            self.assertEqual(asset.depreciation_state, "disposed")

    # ── Report ───────────────────────────────────────────────────────────────

    def test_report_excludes_erp_managed_from_the_backfill_queue(self):
        """Regression: needs_start_date counted erp_managed assets, whose start
        date Cadra never uses. On NRS that reported 11,878 instead of 0."""
        cat = self._category(depreciation_method="straight_line", useful_life_months=60)
        asset = self._asset(cat, acquisition_cost=1000.0)  # no date -> inferred
        self.assertTrue(asset.depreciation_start_is_estimated)

        domain = [("id", "=", asset.id)]
        self.assertEqual(
            self.Asset.get_depreciation_report(domain)["needs_start_date"], 1)

        asset.write({"use_category_policy": False,
                     "depreciation_method": "erp_managed"})
        self.assertEqual(
            self.Asset.get_depreciation_report(domain)["needs_start_date"], 0)
