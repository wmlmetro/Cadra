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

    def write(self, vals):
        res = super().write(vals)
        # When ticket is closed, update vehicle last service date
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
