"""`kpis.vendors` counts vendors, not the sample beside it.

Handoff 13 A4. `get_fleet_command()` returned `len(vendors)` where
`vendors` is a deliberate six-row sample, so the KPI maxed out at 6 while
`get_kpis()` counted the same quantity correctly. Two endpoints, two
answers, one question — and the wrong one is the one on the fleet page.

A `TransactionCase`: these are model methods and touch no `request`.
"""
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestVendorCount(TransactionCase):

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
