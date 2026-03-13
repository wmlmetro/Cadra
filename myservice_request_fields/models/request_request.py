from odoo import models, fields, api


class RequestRequest(models.Model):
    _inherit = 'request.request'

    # ── Vehicle field (Fleet requests only) ───────────────────────────
    vehicle_id = fields.Many2one(
        comodel_name='fleet.vehicle',
        string='Vehicle',
        index=True,
        tracking=True,
        help='Select the vehicle this request relates to. '
             'Search by name, license plate, chassis number or tag.',
    )

    # ── Location is already on the model (generic_location_id).
    #    We make it required at the view level via attrs, not here,
    #    so existing records are not broken. But we expose a computed
    #    helper so portal templates can check it easily.

    @api.onchange('service_id')
    def _onchange_service_clear_vehicle(self):
        """Clear vehicle when service changes to non-fleet."""
        if self.vehicle_id and not self._is_fleet_service():
            self.vehicle_id = False

    def _is_fleet_service(self):
        """Return True if the current service belongs to Fleet Management group."""
        self.ensure_one()
        if not self.service_id:
            return False
        group = self.service_id.service_group_id
        return group and group.name == 'Fleet Management'
