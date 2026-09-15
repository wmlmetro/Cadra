"""fleet.vehicle.maintenance_status — a stored enum that reads the clock.

maintenance_status is computed from today's date, but its @api.depends names
only the schedule fields. Nothing in the database moves when a service date
passes, so a vehicle that is overdue keeps reading 'ok' until somebody edits
the schedule — which is the one thing an overdue vehicle's record does not get.

That makes it worse than a flag that fails to turn on: it is a WRONG value on
a published enum. It is serialised as data.maintenance_status by
GET /api/v1/fleet/vehicles and it drives the fleet dashboard's OK / Due Soon /
Overdue tiles and its "needs attention" list.

The tests below move the clock and run the cron. They never write to the
vehicle — a test that pokes an input would only prove the dependency graph
works, which was never in doubt.

Run with:
    odoo -d <db> -u myservice_fleet_maintenance --test-enable \\
         --test-tags /myservice_fleet_maintenance --stop-after-init \\
         --http-port=8099 --gevent-port=8098
"""
from datetime import date

from odoo.tests import tagged
from odoo.tests.common import freeze_time
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase


@tagged("post_install", "-at_install")
class TestMaintenanceStatusRefresh(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Vehicle = self.env["fleet.vehicle"]
        brand = self.env["fleet.vehicle.model.brand"].create({"name": "Cadra Test"})
        self.vehicle_model = self.env["fleet.vehicle.model"].create({
            "name": "Test Model",
            "brand_id": brand.id,
        })

    def _vehicle(self, last_service_date, **vals):
        base = {
            "model_id": self.vehicle_model.id,
            "license_plate": "CADRA-TEST",
            "last_service_date": last_service_date,
            # Explicit rather than relying on the field defaults, so a change
            # to the defaults cannot silently move the boundaries under test.
            "service_interval_days": 90,
            "alert_before_days": 7,
            "service_interval_km": 0,
            "alert_before_km": 0,
        }
        base.update(vals)
        return self.Vehicle.create(base)

    def _status_in_the_column(self, vehicle):
        """What the dashboard's search_count and the API serialiser see."""
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT maintenance_status FROM fleet_vehicle WHERE id = %s",
            (vehicle.id,))
        return self.env.cr.fetchone()[0]

    # ── the defect ───────────────────────────────────────────────────────────

    def test_an_overdue_vehicle_still_reads_ok_until_the_cron_runs(self):
        """The whole bug in one test.

        Nothing is written between the two blocks — only the date changes. The
        middle assertion pins the wrong value on purpose: if someone deletes
        the cron, this test must fail rather than quietly pass.
        """
        with freeze_time("2026-01-01"):
            vehicle = self._vehicle(date(2026, 1, 1))
            self.assertEqual(vehicle.next_service_date, date(2026, 4, 1))
            self.assertEqual(self._status_in_the_column(vehicle), "ok")

        with freeze_time("2026-04-02"):
            self.assertEqual(
                self._status_in_the_column(vehicle), "ok",
                "the stored enum cannot correct itself — that is the defect")

            self.Vehicle._cron_refresh_maintenance_status()

            self.assertEqual(vehicle.maintenance_status, "overdue")
            self.assertEqual(self._status_in_the_column(vehicle), "overdue")

    def test_a_vehicle_inside_the_alert_window_reads_due_soon_after_the_cron(self):
        """The lead time is the whole point of alert_before_days: a fleet
        manager is meant to see the vehicle BEFORE it goes overdue, and that
        transition is entirely a function of the date."""
        with freeze_time("2026-01-01"):
            vehicle = self._vehicle(date(2026, 1, 1))
            self.assertEqual(self._status_in_the_column(vehicle), "ok")

        # next service 2026-04-01, seven days' lead time.
        with freeze_time("2026-03-26"):
            self.assertEqual(self._status_in_the_column(vehicle), "ok")
            self.Vehicle._cron_refresh_maintenance_status()
            self.assertEqual(self._status_in_the_column(vehicle), "due_soon")

    def test_a_vehicle_with_no_schedule_is_left_alone(self):
        """Every fleet.vehicle row on every tenant is 'no_schedule' today,
        because none has a last service date. The cron must not invent a status
        for a vehicle nobody has scheduled."""
        with freeze_time("2026-01-01"):
            vehicle = self._vehicle(False)
            self.assertEqual(self._status_in_the_column(vehicle), "no_schedule")

        with freeze_time("2027-01-01"):
            self.Vehicle._cron_refresh_maintenance_status()
            self.assertEqual(self._status_in_the_column(vehicle), "no_schedule")

    def test_the_refresh_covers_an_archived_vehicle(self):
        """A stored status is wrong the moment an archived vehicle comes back,
        and skipping it saves nothing."""
        with freeze_time("2026-01-01"):
            vehicle = self._vehicle(date(2026, 1, 1))
            vehicle.active = False
            self.assertEqual(self._status_in_the_column(vehicle), "ok")

        with freeze_time("2026-04-02"):
            self.Vehicle._cron_refresh_maintenance_status()
            self.assertEqual(self._status_in_the_column(vehicle), "overdue")

    # ── the production wiring ────────────────────────────────────────────────

    def test_the_refresh_cron_exists_and_resolves_to_the_method(self):
        """A cron whose method does not exist is the defect handoff 08 found in
        two live tenants. Asserting the xmlid, the model and the call string
        together is what makes a rename fail here rather than at 00:05."""
        cron = self.env.ref(
            "myservice_fleet_maintenance.ir_cron_fleet_refresh_maintenance_status")
        self.assertTrue(cron.active)
        self.assertEqual(cron.model_id.model, "fleet.vehicle")
        self.assertEqual(cron.ir_actions_server_id.code.strip(),
                         "model._cron_refresh_maintenance_status()")
        self.assertTrue(hasattr(self.Vehicle, "_cron_refresh_maintenance_status"))

    def test_the_refresh_is_scheduled_ahead_of_the_ticket_raising_cron(self):
        """_cron_check_preventive_maintenance decides what to raise a ticket for
        by reading maintenance_status, so it must not run on the value the
        refresh is about to correct. ir.cron orders ready jobs by
        failure_count, priority, id."""
        refresh = self.env.ref(
            "myservice_fleet_maintenance.ir_cron_fleet_refresh_maintenance_status")
        tickets = self.env.ref(
            "myservice_fleet_maintenance.ir_cron_fleet_preventive_maintenance")
        self.assertLess(refresh.priority, tickets.priority)
