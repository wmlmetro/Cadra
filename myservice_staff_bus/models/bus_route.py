from odoo import models, fields, api, release, _
from odoo.exceptions import ValidationError

# See myservice_asset_register/models/asset.py for why both spellings exist:
# Odoo 19 removed `_sql_constraints` and creates nothing for it.
_ODOO_MAJOR = release.version_info[0]


class BusRoute(models.Model):
    _name = 'bus.route'
    _description = 'Staff Bus Route'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char('Route Name', required=True, tracking=True)
    code = fields.Char('Route Code', required=True, copy=False)
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
    ], default='draft', tracking=True)

    direction = fields.Selection([
        ('morning', 'Morning (To Office)'),
        ('evening', 'Evening (From Office)'),
        ('both', 'Both Directions'),
    ], default='both', required=True)

    frequency = fields.Selection([
        ('daily', 'Daily (Mon–Fri)'),
        ('weekly', 'Weekly'),
        ('custom', 'Custom'),
    ], default='daily')

    origin_location_id = fields.Many2one(
        'generic.location', string='Origin / Start Point',
        help='Starting point of this route')
    destination_location_id = fields.Many2one(
        'generic.location', string='Destination / End Point',
        help='Final destination of this route')

    distance_km = fields.Float('Estimated Distance (km)')
    duration_minutes = fields.Integer('Estimated Duration (min)')
    notes = fields.Text('Route Notes')

    stop_ids = fields.One2many('bus.route.stop', 'route_id', string='Stops')
    stop_count = fields.Integer('Stop Count', compute='_compute_stop_count')

    schedule_ids = fields.One2many('bus.schedule', 'route_id', string='Schedules')
    schedule_count = fields.Integer('Schedule Count', compute='_compute_schedule_count')

    # AI optimisation
    optimization_ids = fields.One2many(
        'bus.route.optimization', 'route_id', string='Optimisation Runs')
    last_optimized = fields.Datetime('Last Optimised', compute='_compute_last_optimized')

    @api.depends('stop_ids')
    def _compute_stop_count(self):
        for r in self:
            r.stop_count = len(r.stop_ids)

    @api.depends('schedule_ids')
    def _compute_schedule_count(self):
        for r in self:
            r.schedule_count = len(r.schedule_ids)

    @api.depends('optimization_ids.date_run')
    def _compute_last_optimized(self):
        for r in self:
            opts = r.optimization_ids.sorted('date_run', reverse=True)
            r.last_optimized = opts[0].date_run if opts else False

    def action_activate(self):
        for r in self:
            if not r.stop_ids:
                raise ValidationError(_('Route must have at least one stop before activation.'))
            r.state = 'active'

    def action_suspend(self):
        self.write({'state': 'suspended'})

    def action_view_stops(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Stops — %s' % self.name,
            'res_model': 'bus.route.stop',
            'view_mode': 'tree,form',
            'domain': [('route_id', '=', self.id)],
            'context': {'default_route_id': self.id},
        }

    def action_view_schedules(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Schedules — %s' % self.name,
            'res_model': 'bus.schedule',
            'view_mode': 'tree,form',
            'domain': [('route_id', '=', self.id)],
            'context': {'default_route_id': self.id},
        }

    if _ODOO_MAJOR >= 19:
        _code_unique = models.Constraint(
            'UNIQUE (code)',
            'Route code must be unique.',
        )
    else:
        _sql_constraints = [
            ('code_unique', 'unique(code)', 'Route code must be unique.')
        ]


class BusRouteStop(models.Model):
    _name = 'bus.route.stop'
    _description = 'Bus Route Stop'
    _order = 'route_id, sequence'

    route_id = fields.Many2one('bus.route', string='Route', required=True, ondelete='cascade')
    name = fields.Char('Stop Name', required=True)
    sequence = fields.Integer('Order', default=10)
    is_terminal = fields.Boolean('Terminal Stop')

    latitude = fields.Float('Latitude', digits=(10, 7))
    longitude = fields.Float('Longitude', digits=(10, 7))
    landmark = fields.Char('Landmark / Description')

    arrival_time = fields.Float('Scheduled Arrival', help='Time as decimal (e.g. 7.5 = 07:30)')
    departure_time = fields.Float('Scheduled Departure')

    avg_boarding = fields.Integer('Avg. Boardings', help='Historical average passengers boarding here')

    @api.constrains('latitude', 'longitude')
    def _check_coordinates(self):
        for s in self:
            if s.latitude and not (-90 <= s.latitude <= 90):
                raise ValidationError(_('Latitude must be between -90 and 90.'))
            if s.longitude and not (-180 <= s.longitude <= 180):
                raise ValidationError(_('Longitude must be between -180 and 180.'))


class BusRouteOptimization(models.Model):
    _name = 'bus.route.optimization'
    _description = 'AI Route Optimisation Run'
    _order = 'date_run desc'

    route_id = fields.Many2one('bus.route', string='Route', required=True, ondelete='cascade')
    date_run = fields.Datetime('Run Date', default=fields.Datetime.now)
    staff_zone_data = fields.Text('Staff Zone Input', help='JSON summary of staff home zones used')
    suggested_stops = fields.Text('Suggested Stops', help='AI-suggested stop list as JSON')
    efficiency_score = fields.Float('Efficiency Score', help='0–100 score vs current route')
    ai_summary = fields.Text('AI Summary')
    status = fields.Selection([
        ('pending', 'Pending Review'),
        ('applied', 'Applied'),
        ('rejected', 'Rejected'),
    ], default='pending')
    applied_by = fields.Many2one('res.users', string='Applied By')
    applied_date = fields.Datetime('Applied Date')

    def action_apply(self):
        self.write({
            'status': 'applied',
            'applied_by': self.env.uid,
            'applied_date': fields.Datetime.now(),
        })
