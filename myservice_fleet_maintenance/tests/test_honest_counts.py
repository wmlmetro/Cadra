"""The fleet breakdown sums to its own headline, in the same response.

Handoff 13 A3. `state_counts` and `fuel_counts` were tallied over a 100-row
window and returned NEXT TO `kpis.total`, which is a real count. On any
fleet over 100 vehicles the columns did not add up to the headline in one
payload — and the reasonable conclusion for anyone who summed them is that
the register is wrong, not that the dashboard is.

Seeded past 100 deliberately: below the window the two are identical, which
is why this survived being read.
"""
import json

from odoo.tests import tagged
from odoo.addons.myservice_nrs_base.tests.common import CadraHttpCase


@tagged("post_install", "-at_install")
class TestFleetDashboardCounts(CadraHttpCase):

    #: Past the 100-row window the breakdowns were tallied over.
    VEHICLES = 130

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Brand = cls.env["fleet.vehicle.model.brand"]
        Model = cls.env["fleet.vehicle.model"]
        State = cls.env["fleet.vehicle.state"]

        brand = Brand.create({"name": "H13 Motors"})
        model = Model.create({"name": "H13 Hauler", "brand_id": brand.id})
        cls.states = State.create([{"name": "H13 %s" % label}
                                   for label in ("Running", "Workshop",
                                                 "Grounded")])

        cls.vehicles = cls.env["fleet.vehicle"].create([
            {"model_id": model.id,
             "license_plate": "H13-%04d" % i,
             "state_id": cls.states[i % 3].id,
             "fuel_type": ("diesel", "gasoline", "electric")[i % 3]}
            for i in range(cls.VEHICLES)
        ])
        cls.env.flush_all()

    def _payload(self):
        self.authenticate("admin", "admin")
        response = self.url_open(
            "/myservice/fleet_dashboard/data",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {}}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertNotIn("error", body, body)
        return body["result"]

    def test_the_seed_is_actually_past_the_old_window(self):
        active = self.env["fleet.vehicle"].search_count([("active", "=", True)])
        self.assertGreater(
            active, 100,
            "the breakdowns were tallied over the first 100 rows; a smaller "
            "fleet cannot show the difference")

    def test_the_state_breakdown_sums_to_the_headline(self):
        payload = self._payload()
        self.assertEqual(sum(payload["state_counts"].values()),
                         payload["kpis"]["active"],
                         "the columns and the headline are in one response; "
                         "they have to be the same measurement")

    def test_the_fuel_breakdown_sums_to_the_headline(self):
        payload = self._payload()
        self.assertEqual(sum(payload["fuel_counts"].values()),
                         payload["kpis"]["active"])

    def test_each_state_column_is_the_true_count(self):
        payload = self._payload()
        Vehicle = self.env["fleet.vehicle"]
        for state in self.states:
            self.assertEqual(
                payload["state_counts"].get(state.name),
                Vehicle.search_count([("active", "=", True),
                                      ("state_id", "=", state.id)]))

    def test_the_vehicle_list_stays_a_window_and_says_so_by_being_a_list(self):
        payload = self._payload()
        self.assertEqual(len(payload["vehicles"]), 100)
        self.assertGreater(payload["kpis"]["active"], len(payload["vehicles"]),
                           "the list is a sample; the count is not")
