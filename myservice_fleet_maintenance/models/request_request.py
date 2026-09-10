from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = 'request.request'

    is_maintenance_ticket = fields.Boolean(
        string='Maintenance Ticket',
        default=False,
        help='Set automatically when ticket is created by the maintenance cron.',
    )
    service_completion_date = fields.Date(
        string='Service Completion Date',
        tracking=True,
    )
    service_odometer_reading = fields.Float(
        string='Odometer at Service (km)',
        digits=(10, 1),
        tracking=True,
    )
    service_vendor_id = fields.Many2one(
        comodel_name='fleet.service.vendor',
        string='Service Vendor',
        tracking=True,
    )
    service_notes = fields.Text(
        string='Service Notes',
    )

    #: The fields the vehicle's service schedule is DERIVED from. A write
    #: that touches none of them cannot change the derivation, so it has no
    #: business re-running it.
    _SERVICE_SCHEDULE_INPUTS = frozenset({
        'stage_id', 'service_completion_date', 'service_odometer_reading',
        'vehicle_id', 'is_maintenance_ticket',
    })

    def write(self, vals):
        """Reset the vehicle's schedule when a SERVICE INPUT changed.

        This ran on EVERY write to a maintenance request, whatever the write
        contained — the same shape of defect handoff 18 fixed in
        `myservice_request_core.write`, which branched on `'stage_id' in vals`
        rather than on the stage changing. Here it was one step worse: it did
        not even look at `vals`.

        That was not harmless. `_update_vehicle_after_service` sets
        `manual_next_service_date = False`, so any write at all to a closed
        maintenance ticket **destroyed an operator's manual next-service
        override** — a value somebody had deliberately set on the vehicle. The
        other two fields it writes are idempotent; this one is not.

        Handoff 20 made it reachable from a new direction: recording a late
        `payment_ref` on a replayed WorkSpace callback is now a write to the
        request where previously a replay wrote nothing, so a duplicate
        callback on a closed fleet ticket would have cleared the override. The
        callback is the caller that made it visible; the defect is here, and
        every other caller — a bulk edit, an import, a chatter-triggered
        write — has had it all along.

        Scoping to the derived-from fields is the narrowest honest rule: if
        none of them moved, the schedule this method computes cannot have
        changed.
        """
        touched = self._SERVICE_SCHEDULE_INPUTS & set(vals)
        res = super().write(vals)
        if not touched:
            return res
        for rec in self:
            if (rec.is_maintenance_ticket and
                    rec.vehicle_id and
                    rec.stage_id.closed and
                    rec.service_completion_date):
                rec._update_vehicle_after_service()
        return res

    def _update_vehicle_after_service(self):
        """Reset vehicle maintenance schedule after service is completed."""
        self.ensure_one()
        vehicle = self.vehicle_id
        if not vehicle:
            return
        vals = {
            'last_service_date': self.service_completion_date or fields.Date.today(),
        }
        if self.service_odometer_reading:
            vals['last_service_odometer'] = self.service_odometer_reading
        # Clear manual override
        vals['manual_next_service_date'] = False
        vehicle.sudo().write(vals)
        _logger.info(
            "Vehicle %s service schedule reset after ticket %s closed",
            vehicle.name, self.name
        )
