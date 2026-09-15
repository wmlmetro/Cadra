"""`get_fleet_command()` answers what it can, and says what it could not.

Handoff 13 A4. `get_fleet_command()` returned `len(vendors)` where
`vendors` is a deliberate six-row sample, so the KPI maxed out at 6 while
`get_kpis()` counted the same quantity correctly. Two endpoints, two
answers, one question — and the wrong one is the one on the fleet page.

Handoff 15 (`TestFleetCommandPanels` below). Two more panels of the same
method were reading fields that do not exist — `lg.service_id` on a service
log, `insurance_expiration_date` on a vehicle — into bare `except: pass`
handlers, so Recent Maintenance and Compliance Alerts had been empty on every
tenant since the day they were written. An empty panel is not a visible
failure, which is the whole reason they lasted: a tenant with no service logs
produces byte-identical output. So these tests SEED the rows the panels are
supposed to find, and assert on the panel that names a failure rather than on
one that swallows it.

A `TransactionCase`: these are model methods and touch no `request`.
"""
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase


@tagged("post_install", "-at_install")
class TestVendorCount(CadraTransactionCase):

    #: More than the six-row sample, so the old ceiling is visible.
    APPROVED = 9
    UNAPPROVED = 4

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Vendor = cls.env["fleet.service.vendor"]
        Partner = cls.env["res.partner"]
        cls.baseline_approved = Vendor.search_count([("is_approved", "=", True)])
        # `partner_id` is required on the vendor: it is where the contact
        # details live.
        Vendor.create(
            [{"name": "H13 Approved %d" % i, "is_approved": True,
              "partner_id": Partner.create({"name": "H13 A%d" % i}).id}
             for i in range(cls.APPROVED)]
            + [{"name": "H13 Pending %d" % i, "is_approved": False,
                "partner_id": Partner.create({"name": "H13 P%d" % i}).id}
               for i in range(cls.UNAPPROVED)])
        cls.env.flush_all()

    def test_the_kpi_is_the_count_and_not_the_size_of_the_sample(self):
        payload = self.env["myservice.dashboard"].get_fleet_command()

        true_count = self.env["fleet.service.vendor"].search_count(
            [("is_approved", "=", True)])
        self.assertEqual(payload["kpis"]["vendors"], true_count)
        self.assertGreater(
            payload["kpis"]["vendors"], 6,
            "this is the assertion the old code failed: it answered 6")
        self.assertEqual(len(payload["vendors"]), 6,
                         "the sample stays a sample — it is a list")

    def test_the_vendor_sample_is_not_silently_empty(self):
        """It was, on every tenant, always.

        The row builder read `v.state_id`, and `fleet.service.vendor` has no
        such field — its columns are name, partner_id, email, phone,
        specialisation, is_approved, active, notes. The AttributeError went
        into a bare `except Exception: pass`, so the list came back empty
        and the web client showed "No approved vendors yet" to tenants that
        had them. `kpis.vendors` was `len()` of that list, so it was not
        capped at six: it was zero.
        """
        payload = self.env["myservice.dashboard"].get_fleet_command()
        self.assertTrue(
            payload["vendors"],
            "approved vendors exist in this transaction; an empty sample "
            "means the row builder raised and was swallowed again")
        for row in payload["vendors"]:
            self.assertIn("state", row)
            self.assertTrue(row["name"])

    def test_the_two_endpoints_give_the_same_answer(self):
        """`get_kpis()` already counted this correctly. The point of the fix
        is that they stop disagreeing."""
        fleet = self.env["myservice.dashboard"].get_fleet_command()
        kpis = self.env["myservice.dashboard"].get_kpis()
        self.assertEqual(fleet["kpis"]["vendors"], kpis["vendors"]["approved"])

    def test_an_unapproved_vendor_is_not_counted_as_approved(self):
        """The KPI is labelled "Approved Vendors" in the web client, so a
        pending vendor must not inflate it."""
        payload = self.env["myservice.dashboard"].get_fleet_command()
        self.assertEqual(payload["kpis"]["vendors"],
                         self.baseline_approved + self.APPROVED)


@tagged("post_install", "-at_install")
class TestFleetCommandPanels(CadraTransactionCase):
    """The panels either answer or admit they did not.

    Handoff 15. `get_fleet_command()` is a seven-panel aggregator served both
    to the Odoo web client and to `GET /api/v1/dashboard/fleet-command`, and
    three of its panels sat behind bare `except: pass`. Two of the three were
    raising on every call, on every tenant, forever — the same defect twice,
    written the same day, in the same function as the `v.state_id` one handoff
    13 found.

    What makes this class necessary rather than nice: `[]` from a swallowed
    AttributeError and `[]` from a tenant with nothing to show are the same
    bytes. A test that does not create a row cannot tell them apart, and
    neither could anybody looking at the dashboard.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "H15 Motors"})
        model = cls.env["fleet.vehicle.model"].create(
            {"name": "H15 Runner", "brand_id": brand.id})
        cls.vehicle = cls.env["fleet.vehicle"].create({
            "model_id": model.id,
            "license_plate": "H15-0001",
        })
        # Core `fleet` ships its service types as module data, so one is
        # normally there to be found; it is only created as a fallback, and
        # then with `name` alone, because the model's other columns have moved
        # between Odoo versions and this test has no opinion about them.
        service_type = cls.env["fleet.service.type"].search([], limit=1)
        if not service_type:
            service_type = cls.env["fleet.service.type"].create(
                {"name": "H15 General Service"})
        # `vehicle_id` and `service_type_id` are the model's required columns.
        # `vendor_id` here is a `res.partner`, NOT the `fleet.service.vendor`
        # of the vendors panel — two different models, one word.
        cls.service_log = cls.env["fleet.vehicle.log.services"].create({
            "vehicle_id": cls.vehicle.id,
            "service_type_id": service_type.id,
            "description": "H15 brake pads",
            "amount": 42000.0,
            "date": fields.Date.today(),
        })
        cls.env.flush_all()

    def _payload(self):
        return self.env["myservice.dashboard"].get_fleet_command()

    def test_the_recent_maintenance_panel_is_not_silently_empty(self):
        """This is the test that would have caught `lg.service_id`.

        `fleet.vehicle.log.services` has no such field, so the FIRST row of the
        loop raised AttributeError, the bare `except: pass` ate it, and the
        partially-built list was discarded with it. Every tenant that had any
        service log at all saw an empty Recent Maintenance panel and read it as
        "nothing serviced lately".

        The row created in `setUpClass` is what gives the assertion teeth: on
        an empty table the old code and the new one return the same `[]`.
        """
        payload = self._payload()

        self.assertTrue(
            payload["recent_maint"],
            "a service log exists in this transaction; an empty panel means "
            "the row builder raised and was swallowed again")
        for row in payload["recent_maint"]:
            self.assertTrue(
                row["service"],
                "`service_type_id` is required on the model, so this key "
                "cannot legitimately be blank — a blank one means the "
                "expression behind it stopped resolving")
            self.assertIn("vehicle", row)
            self.assertIn("date", row)

    def test_the_compliance_domain_resolves(self):
        """Compliance Alerts counted `insurance_expiration_date` on
        `fleet.vehicle`, a field that exists on no version of the model and
        nowhere in this repo outside the throwaway patch file it was copied
        from. Odoo's domain parser rejects an unknown field, the bare
        `except: pass` ate that, and the panel showed nothing — a permanent
        zero indistinguishable from good news.

        The assertion is that the DOMAIN resolves, not that the count is
        non-zero: a healthy tenant may legitimately have no expiring contract,
        and a test that demanded one would be asserting the fixture rather than
        the fix.
        """
        Vehicle = self.env["fleet.vehicle"]
        for field_name in ("contract_renewal_overdue", "contract_renewal_due_soon"):
            # Raises on this line if the field is not searchable — which is
            # exactly what the old field name did, inside a handler.
            self.assertIsInstance(
                Vehicle.search_count([(field_name, "=", True)]), int,
                "%s must be a searchable field on fleet.vehicle" % field_name)

        payload = self._payload()
        self.assertIsInstance(payload["compliance"], list)
        self.assertNotIn(
            "compliance", payload.get("_warnings", {}).get("unavailable", []),
            "the panel reported itself unavailable on a healthy tenant")

    def test_a_failed_panel_is_named_and_the_others_still_answer(self):
        """`_warnings.unavailable` is the point of the change: the aggregator
        keeps serving the six panels that worked, and the seventh stops being
        an empty list that reads as an answer.

        The failure is forced as narrowly as possible — `fleet.service.vendor`
        is touched by exactly one panel of this method — so what is asserted is
        the containment, not just the key.
        """
        vendor_cls = type(self.env["fleet.service.vendor"])
        with patch.object(vendor_cls, "search_count",
                          side_effect=RuntimeError("H15 forced panel failure")):
            payload = self._payload()

        self.assertEqual(
            payload.get("_warnings", {}).get("unavailable"), ["vendors"],
            "the panel that failed has to be named, and only that one")
        self.assertEqual(
            payload["vendors"], [],
            "the placeholder stays a placeholder — `_warnings` is what makes "
            "it readable as one")
        # The other six panels are unaffected. Without this, a change that
        # turned any panel failure into a blank payload would still pass.
        self.assertTrue(
            payload["recent_maint"],
            "one broken panel must not take out the six that worked")
        self.assertGreaterEqual(payload["kpis"]["total"], 1)
        self.assertIsInstance(payload["by_status"], list)
        self.assertIn("unassigned", payload["driver_stats"])

    def test_nothing_is_named_unavailable_when_nothing_failed(self):
        """The key's ABSENCE has to carry meaning, or a client cannot use its
        presence. A `_warnings` block on a healthy tenant would make it noise,
        and noise is how the empty panels survived in the first place."""
        payload = self._payload()

        self.assertNotIn(
            "_warnings", payload,
            "nothing in this fixture should fail: %r"
            % (payload.get("_warnings"),))

    def test_the_kpi_numbers_are_numbers(self):
        """`idle` and `vendors` are the two KPIs on this payload that come from
        somewhere other than a plain `search_count` on the vehicle table —
        `idle` from a service-log subquery, `vendors` from the block that used
        to be `len()` of a swallowed list. Both are rendered as figures by the
        web client, so a `None` or a string would surface as a broken card
        rather than as an error anyone could act on.
        """
        kpis = self._payload()["kpis"]

        for key in ("idle", "vendors"):
            self.assertIn(key, kpis)
            self.assertIsInstance(kpis[key], int, "%s is rendered as a figure" % key)
            self.assertGreaterEqual(kpis[key], 0)
