from odoo import models, fields, api, _


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    is_staff_bus = fields.Boolean('Staff Bus', default=False,
                                   help='Mark this vehicle as an NRS staff bus')
    bus_capacity = fields.Integer('Seating Capacity',
                                   help='Total number of passenger seats')
    current_route_id = fields.Many2one('bus.route', string='Current Route',
                                        domain=[('state', '=', 'active')])
    roadworthy_expiry = fields.Date('Roadworthiness Expiry')
    insurance_expiry = fields.Date('Insurance Expiry')

    # Computed stats
    fuel_log_ids = fields.One2many('bus.fuel.log', 'vehicle_id', string='Fuel Logs')
    schedule_ids = fields.One2many('bus.schedule', 'vehicle_id', string='Schedules')

    total_fuel_cost_ytd = fields.Float(
        'Fuel Cost YTD (₦)', compute='_compute_fuel_ytd')
    last_fuel_date = fields.Date(
        'Last Fuelled', compute='_compute_fuel_ytd')
    schedules_this_month = fields.Integer(
        'Schedules This Month', compute='_compute_schedule_stats')
    is_roadworthy = fields.Boolean(
        'Roadworthy', compute='_compute_compliance')
    is_insured = fields.Boolean(
        'Insured', compute='_compute_compliance')

    @api.depends('fuel_log_ids', 'fuel_log_ids.total_cost',
                 'fuel_log_ids.state', 'fuel_log_ids.date')
    def _compute_fuel_ytd(self):
        from datetime import date
        year = date.today().year
        for v in self:
            logs = v.fuel_log_ids.filtered(
                lambda l: l.state == 'approved' and l.date and l.date.year == year)
            v.total_fuel_cost_ytd = sum(logs.mapped('total_cost'))
            dated = logs.filtered('date').sorted('date', reverse=True)
            v.last_fuel_date = dated[0].date if dated else False

    @api.depends('schedule_ids', 'schedule_ids.date')
    def _compute_schedule_stats(self):
        from datetime import date
        today = date.today()
        for v in self:
            v.schedules_this_month = len(v.schedule_ids.filtered(
                lambda s: s.date and
                s.date.month == today.month and
                s.date.year == today.year
            ))

    @api.depends('roadworthy_expiry', 'insurance_expiry')
    def _compute_compliance(self):
        from datetime import date
        today = date.today()
        for v in self:
            v.is_roadworthy = bool(v.roadworthy_expiry and v.roadworthy_expiry >= today)
            v.is_insured = bool(v.insurance_expiry and v.insurance_expiry >= today)
