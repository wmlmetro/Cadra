"""A warranty on an asset — handoff 34.

Three things are promised, and each class below is one of them:

    1. **The answer and the working.** A start date and a duration derive the
       expiry; an expiry sent beside them that says anything else is refused,
       not overwritten; half a basis is refused; an expiry derived from a
       basis goes with it.
    2. **Three states, judged on a Lagos day.** Under warranty through the
       expiry day, expired after it, and *no warranty recorded* where nothing
       is — and the filter on the state returns exactly the rows that publish
       it, because a count that is not its filter is this repository's most
       repeated defect.
    3. **A change is an event, and a warranty is not the asset's health.** A
       change to any of the five fields is an append-only `warranty_changed`
       row; creating an asset with a warranty writes none; and nothing about
       a warranty moves the asset's state, condition or verification.

Run with:
    odoo -d <db> -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register --stop-after-init --workers=0
"""
from datetime import date, datetime

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import freeze_time
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

from ..models.asset import WARRANTY_MAX_MONTHS, warranty_expiry_of


class WarrantyCase(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Asset = self.env["nrs.asset"]
        self.Event = self.env["nrs.asset.event"]
        self.category = self.env["nrs.asset.category"].create(
            {"name": "Warranty test category"})

    def _asset(self, **vals):
        return self.Asset.create(dict(
            {"name": "Warranty test asset", "category_id": self.category.id},
            **vals))

    def _events(self, asset):
        return self.Event.search([
            ("asset_id", "=", asset.id),
            ("event_type", "=", "warranty_changed")], order="id")


@tagged("post_install", "-at_install")
class TestWarrantyBasis(WarrantyCase):

    def test_a_start_and_a_duration_derive_the_expiry(self):
        asset = self._asset(warranty_start_date="2026-03-12",
                            warranty_months=24)
        self.assertEqual(asset.warranty_expiry, date(2028, 3, 12))

    def test_a_short_month_clamps_rather_than_overflowing(self):
        self.assertEqual(warranty_expiry_of(date(2024, 1, 31), 1),
                         date(2024, 2, 29))
        self.assertEqual(warranty_expiry_of(date(2024, 2, 29), 24),
                         date(2026, 2, 28))

    def test_a_duration_without_a_start_is_refused(self):
        with self.assertRaises(ValidationError):
            self._asset(warranty_months=24)

    def test_a_start_without_a_duration_is_refused(self):
        with self.assertRaises(ValidationError):
            self._asset(warranty_start_date="2026-03-12")

    def test_a_duration_out_of_range_is_refused(self):
        for months in (0.5, -3, WARRANTY_MAX_MONTHS + 1, True, "two years"):
            with self.subTest(months=months), \
                    self.assertRaises(ValidationError):
                self._asset(warranty_start_date="2026-03-12",
                            warranty_months=months)

    def test_a_contradicting_expiry_is_refused_not_overwritten(self):
        with self.assertRaises(ValidationError):
            self._asset(warranty_start_date="2026-03-12", warranty_months=24,
                        warranty_expiry="2029-03-12")
        asset = self._asset(warranty_start_date="2026-03-12",
                            warranty_months=24)
        with self.assertRaises(ValidationError):
            asset.write({"warranty_expiry": "2030-01-01"})
        self.assertEqual(asset.warranty_expiry, date(2028, 3, 12))

    def test_the_same_expiry_sent_again_is_accepted(self):
        """A form re-sends what it displayed; that contradicts nothing."""
        asset = self._asset(warranty_start_date="2026-03-12",
                            warranty_months=24, warranty_expiry="2028-03-12")
        asset.write({"warranty_months": 24, "warranty_expiry": "2028-03-12"})
        self.assertEqual(asset.warranty_expiry, date(2028, 3, 12))

    def test_changing_the_duration_moves_the_expiry(self):
        asset = self._asset(warranty_start_date="2026-03-12",
                            warranty_months=24)
        asset.write({"warranty_months": 36})
        self.assertEqual(asset.warranty_expiry, date(2029, 3, 12))

    def test_a_bare_expiry_is_still_accepted(self):
        asset = self._asset(warranty_expiry="2027-06-30")
        self.assertEqual(asset.warranty_expiry, date(2027, 6, 30))
        self.assertFalse(asset.warranty_start_date)
        self.assertFalse(asset.warranty_months)

    def test_a_derived_expiry_goes_with_its_basis(self):
        asset = self._asset(warranty_start_date="2026-03-12",
                            warranty_months=24)
        asset.write({"warranty_start_date": False, "warranty_months": False})
        self.assertFalse(asset.warranty_expiry)

    def test_clearing_the_basis_while_naming_an_expiry_keeps_that_date(self):
        asset = self._asset(warranty_start_date="2026-03-12",
                            warranty_months=24)
        asset.write({"warranty_start_date": False, "warranty_months": False,
                     "warranty_expiry": "2028-01-01"})
        self.assertEqual(asset.warranty_expiry, date(2028, 1, 1))

    def test_a_write_to_several_assets_resolves_each_against_its_own_start(
            self):
        one = self._asset(warranty_start_date="2026-01-01",
                          warranty_months=12)
        two = self._asset(warranty_start_date="2026-06-01",
                          warranty_months=12)
        (one | two).write({"warranty_months": 36})
        self.assertEqual(one.warranty_expiry, date(2029, 1, 1))
        self.assertEqual(two.warranty_expiry, date(2029, 6, 1))

    def test_everything_is_optional(self):
        asset = self._asset()
        self.assertFalse(asset.warranty_expiry)
        self.assertEqual(asset.warranty_status, "none")
        asset.write({"warrantor": "Dell Nigeria Ltd"})
        self.assertEqual(asset.warranty_status, "none")


@tagged("post_install", "-at_install")
class TestWarrantyStatus(WarrantyCase):

    def test_the_three_states(self):
        with freeze_time("2026-09-22 12:00:00"):
            under = self._asset(warranty_expiry="2026-09-22")
            expired = self._asset(warranty_expiry="2026-09-21")
            none = self._asset()
            self.assertEqual(under.warranty_status, "under_warranty")
            self.assertEqual(expired.warranty_status, "expired")
            self.assertEqual(none.warranty_status, "none")

    def test_the_day_is_a_lagos_day(self):
        """23:30 UTC on the 21st is 00:30 on the 22nd in Lagos. A warranty
        that ran through the 21st has expired there — in UTC it has not,
        and that is the one-hour-a-night error report 29 found."""
        asset = self._asset(warranty_expiry="2026-09-21")
        with freeze_time(datetime(2026, 9, 21, 23, 30)):
            asset.invalidate_recordset(["warranty_status"])
            self.assertEqual(asset.warranty_status, "expired")
            self.assertIn(asset, self.Asset.search(
                [("warranty_status", "=", "expired")]))

    def test_the_filter_returns_exactly_the_rows_that_publish_the_state(self):
        with freeze_time("2026-09-22 12:00:00"):
            self._asset(warranty_expiry="2027-01-01")
            self._asset(warranty_expiry="2025-01-01")
            self._asset()
            everything = self.Asset.search([])
            for state in ("under_warranty", "expired", "none"):
                with self.subTest(state=state):
                    found = self.Asset.search(
                        [("warranty_status", "=", state)])
                    self.assertEqual(
                        found,
                        everything.filtered(
                            lambda a: a.warranty_status == state))
                    # And the negation is the rest of the register — no row
                    # is in neither, which is how 282 assets once went missing.
                    rest = self.Asset.search(
                        [("warranty_status", "!=", state)])
                    self.assertEqual(found | rest, everything)
                    self.assertFalse(found & rest)


@tagged("post_install", "-at_install")
class TestWarrantyEvents(WarrantyCase):

    def test_an_asset_created_with_a_warranty_writes_no_event(self):
        asset = self._asset(warranty_start_date="2026-03-12",
                            warranty_months=24, warrantor="Dell",
                            warranty_reference="WC-1")
        self.assertFalse(self._events(asset))
        # And so it is not pinned: an INT-03 receipt carrying a warranty
        # leaves an asset that can still be deleted.
        asset.unlink()

    def test_a_change_is_recorded_with_its_before_and_after(self):
        asset = self._asset(warranty_start_date="2026-03-12",
                            warranty_months=24, warrantor="Dell")
        asset.write({"warranty_months": 36, "warrantor": "HP"})
        rows = {e.field_name: (e.from_value, e.to_value)
                for e in self._events(asset)}
        self.assertEqual(rows, {
            "warranty_months": ("24", "36"),
            "warranty_expiry": ("2028-03-12", "2029-03-12"),
            "warrantor": ("Dell", "HP"),
        })

    def test_a_write_that_changes_nothing_records_nothing(self):
        asset = self._asset(warranty_start_date="2026-03-12",
                            warranty_months=24)
        asset.write({"warranty_months": 24,
                     "warranty_start_date": "2026-03-12"})
        self.assertFalse(self._events(asset))

    def test_the_event_cannot_be_altered(self):
        asset = self._asset(warranty_expiry="2027-01-01")
        asset.write({"warranty_expiry": "2028-01-01"})
        event = self._events(asset)
        self.assertEqual(len(event), 1)
        with self.assertRaises(UserError):
            event.write({"to_value": "2030-01-01"})
        with self.assertRaises(UserError):
            event.unlink()

    def test_a_warranty_event_cannot_name_a_reference(self):
        asset = self._asset()
        with self.assertRaises(UserError):
            self.Event._record(asset, "warranty_changed",
                               field_name="grn_reference",
                               from_value="a", to_value="b")
        with self.assertRaises(UserError):
            self.Event._record(asset, "reference_changed",
                               field_name="warranty_months",
                               from_value="1", to_value="2")


@tagged("post_install", "-at_install")
class TestWarrantyIsNotTheAssetsHealth(WarrantyCase):

    def test_an_expired_warranty_moves_nothing_about_the_asset(self):
        asset = self._asset(condition="good", state="active")
        before = (asset.state, asset.condition, asset.is_verified)
        asset.write({"warranty_expiry": "2001-01-01"})
        self.assertEqual(asset.warranty_status, "expired")
        self.assertEqual(
            (asset.state, asset.condition, asset.is_verified), before)
        self.assertFalse(self.Event.search([
            ("asset_id", "=", asset.id),
            ("event_type", "!=", "warranty_changed")]))

    def test_a_disposed_assets_warranty_paperwork_can_still_be_written(self):
        asset = self._asset()
        asset.write({"state": "disposed"})
        asset.write({"warranty_reference": "WC-archived"})
        self.assertEqual(asset.warranty_reference, "WC-archived")
