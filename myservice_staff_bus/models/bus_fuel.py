from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class BusFuelLog(models.Model):
    _name = 'bus.fuel.log'
    _description = 'Bus Fuel Log'
    _inherit = ['mail.thread']
    _order = 'date desc'

    name = fields.Char('Reference', compute='_compute_name', store=True)
    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Bus / Vehicle', required=True,
        domain=[('is_staff_bus', '=', True)])
    date = fields.Date('Date', required=True, default=fields.Date.today)

    litres = fields.Float('Litres Filled', required=True, digits=(10, 2))
    cost_per_litre = fields.Float('Cost per Litre (₦)', digits=(10, 2))
    total_cost = fields.Float(
        'Total Cost (₦)', compute='_compute_total_cost', store=True)

    odometer_reading = fields.Float('Odometer Reading (km)')
    prev_odometer = fields.Float('Previous Odometer (km)')
    km_since_last_fill = fields.Float(
        'km Since Last Fill', compute='_compute_km', store=True)
    fuel_efficiency = fields.Float(
        'Fuel Efficiency (km/L)', compute='_compute_km', store=True)

    filled_by = fields.Many2one('hr.employee', string='Filled By')
    station = fields.Char('Filling Station')
    receipt_ref = fields.Char('Receipt No.')
    budget_code = fields.Char('Budget Code')

    approved_by = fields.Many2one('res.users', string='Approved By')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('approved', 'Approved'),
    ], default='draft', tracking=True)

    notes = fields.Text('Notes')

    @api.depends('vehicle_id', 'date')
    def _compute_name(self):
        for r in self:
            r.name = 'FUEL/%s/%s' % (
                r.vehicle_id.license_plate or r.vehicle_id.name or '??',
                r.date or '')

    @api.depends('litres', 'cost_per_litre')
    def _compute_total_cost(self):
        for r in self:
            r.total_cost = r.litres * r.cost_per_litre

    @api.depends('odometer_reading', 'prev_odometer', 'litres')
    def _compute_km(self):
        for r in self:
            km = r.odometer_reading - r.prev_odometer if r.odometer_reading and r.prev_odometer else 0.0
            r.km_since_last_fill = max(0, km)
            r.fuel_efficiency = (km / r.litres) if r.litres and km > 0 else 0.0

    @api.constrains('litres')
    def _check_litres(self):
        for r in self:
            if r.litres <= 0:
                raise ValidationError(_('Litres must be greater than zero.'))

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_approve(self):
        self.write({
            'state': 'approved',
            'approved_by': self.env.uid,
        })

    def action_reset(self):
        self.write({'state': 'draft'})


class BusFuelBudget(models.Model):
    _name = 'bus.fuel.budget'
    _description = 'Monthly Fuel Budget per Bus'

    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Bus', required=True,
        domain=[('is_staff_bus', '=', True)])
    month = fields.Selection([
        ('1','January'),('2','February'),('3','March'),('4','April'),
        ('5','May'),('6','June'),('7','July'),('8','August'),
        ('9','September'),('10','October'),('11','November'),('12','December'),
    ], required=True)
    year = fields.Integer('Year', required=True)
    budget_amount = fields.Float('Budget (₦)', digits=(14, 2))
    actual_amount = fields.Float(
        'Actual Spend (₦)', compute='_compute_actual', store=True)
    variance = fields.Float(
        'Variance (₦)', compute='_compute_actual', store=True)
    utilisation_pct = fields.Float(
        'Utilisation %', compute='_compute_actual', store=True)

    @api.depends('vehicle_id', 'month', 'year')
    def _compute_actual(self):
        FuelLog = self.env['bus.fuel.log']
        for r in self:
            logs = FuelLog.search([
                ('vehicle_id', '=', r.vehicle_id.id),
                ('state', '=', 'approved'),
            ]).filtered(
                lambda l: l.date and
                str(l.date.month) == r.month and
                l.date.year == r.year
            )
            actual = sum(logs.mapped('total_cost'))
            r.actual_amount = actual
            r.variance = r.budget_amount - actual
            r.utilisation_pct = (actual / r.budget_amount * 100) if r.budget_amount else 0.0
