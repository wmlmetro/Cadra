"""A vehicle's service schedule is reset by a SERVICE change, not by any write.

`myservice_fleet_maintenance.request_request.write` ran
`_update_vehicle_after_service()` on every write to a closed maintenance
ticket, whatever the write contained — it did not look at `vals` at all. That
is the same shape of defect handoff 18 fixed in `myservice_request_core.write`
(which branched on `'stage_id' in vals` rather than on the stage changing),
one step further along: no branch at all.

Two of the three fields it writes are idempotent. The third is not:
`manual_next_service_date = False` **destroys an operator's manual override**,
a value somebody deliberately set on the vehicle to say "not on the usual
interval". Any unrelated write to the ticket wiped it.

Handoff 20 made it reachable from a new direction — recording a late
`payment_ref` on a replayed WorkSpace callback is a write to the request where
a replay previously wrote nothing — but every other caller has had it all
along.

Run with:
    odoo -d <db> -u myservice_fleet_maintenance --test-enable \
         --test-tags /myservice_fleet_maintenance --stop-after-init \
         --http-port=8099 --gevent-port=8098
"""
from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestServiceScheduleReset(TransactionCase):

    def setUp(self):
        super().setUp()
        brand = self.env["fleet.vehicle.model.brand"].create({"name": "Cadra Sched"})
        model = self.env["fleet.vehicle.model"].create({
            "name": "Sched Model", "brand_id": brand.id,
        })
        self.vehicle = self.env["fleet.vehicle"].create({
            "model_id": model.id,
            "license_plate": "CADRA-SCHED-1",
            "last_service_date": date(2026, 1, 10),
        })
        closed = self.env["request.stage"].search([("closed", "=", True)], limit=1)
        self.assertTrue(closed, "the tenant has no closed request stage")
        category = self.env["request.category"].search([], limit=1)
        request_type = self.env["request.type"].search([], limit=1)
        self.assertTrue(request_type, "the tenant has no request type")
        vals = {
            "type_id": request_type.id,
            "is_maintenance_ticket": True,
            "vehicle_id": self.vehicle.id,
            "service_completion_date": date(2026, 3, 1),
            "stage_id": closed.id,
        }
        if category:
            vals["category_id"] = category.id
        self.req = self.env["request.request"].create(vals)
        # The create above may already have run the reset; set the override
        # afterwards so the test starts from a known state.
        self.vehicle.write({"manual_next_service_date": date(2027, 6, 30)})

    def test_a_write_that_touches_no_service_field_leaves_the_override_alone(self):
        """The defect, stated as the thing an operator loses.

        `manual_next_service_date` is the one field `_update_vehicle_after_service`
        DESTROYS rather than rewrites, so it is the one this asserts on.
        """
        self.req.write({"name": "an unrelated edit"})
        self.assertEqual(
            self.vehicle.manual_next_service_date, date(2027, 6, 30),
            "an unrelated write to the ticket cleared the vehicle's manual "
            "next-service override")

    def test_the_workflow_payment_ref_write_is_one_of_those(self):
        """The path handoff 20 opened.

        Recording a late `payment_ref` on a replayed callback writes exactly
        one field on the request. If that reached the vehicle, a duplicate
        WorkSpace callback would clear a manual override.
        """
        if "workflow_payment_ref" not in self.req._fields:
            self.skipTest("myservice_workflow is not installed on this tenant")
        self.req.write({"workflow_payment_ref": "PAY-2026-04412"})
        self.assertEqual(
            self.vehicle.manual_next_service_date, date(2027, 6, 30),
            "recording a late payment reference cleared the vehicle's manual "
            "next-service override")

    def test_a_real_service_completion_still_resets_the_schedule(self):
        """The half that matters most.

        A guard that stopped the reset happening at all would be worse than
        the defect: the whole point of the method is that closing a service
        ticket updates the vehicle.
        """
        self.req.write({"service_completion_date": date(2026, 4, 2)})
        self.assertEqual(
            self.vehicle.last_service_date, date(2026, 4, 2),
            "a genuine service completion no longer reaches the vehicle")
        self.assertFalse(
            self.vehicle.manual_next_service_date,
            "a genuine service completion should clear the manual override — "
            "that is what the override is for")

    def test_an_odometer_correction_reaches_the_vehicle_too(self):
        """`service_odometer_reading` is one of the derived-from fields, so a
        correction to it must still propagate."""
        self.req.write({"service_odometer_reading": 84210.0})
        self.assertEqual(self.vehicle.last_service_odometer, 84210.0)
