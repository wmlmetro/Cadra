from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import uuid


class BusSchedule(models.Model):
    _name = 'bus.schedule'
    _description = 'Staff Bus Schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, departure_time'

    name = fields.Char('Reference', required=True, copy=False,
                       default=lambda self: _('New'))
    date = fields.Date('Date', required=True, default=fields.Date.today, tracking=True)

    route_id = fields.Many2one('bus.route', string='Route', required=True, tracking=True)
    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Bus / Vehicle',
        domain=[('is_staff_bus', '=', True)],
        tracking=True)
    driver_id = fields.Many2one('hr.employee', string='Driver', tracking=True)

    departure_time = fields.Float('Departure Time', required=True,
                                  help='Time as decimal — e.g. 7.5 = 07:30')
    arrival_time = fields.Float('Expected Arrival')

    capacity = fields.Integer('Total Capacity', related='vehicle_id.bus_capacity', store=True)
    booked_seats = fields.Integer('Booked Seats', compute='_compute_bookings', store=True)
    available_seats = fields.Integer('Available Seats', compute='_compute_bookings', store=True)
    occupancy_pct = fields.Float('Occupancy %', compute='_compute_bookings', store=True)

    state = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('boarding', 'Boarding'),
        ('departed', 'Departed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='scheduled', tracking=True)

    manifest_ids = fields.One2many('bus.manifest.line', 'schedule_id', string='Manifest')
    notes = fields.Text('Notes')

    direction = fields.Selection(related='route_id.direction', store=True)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('bus.schedule') or _('New')
        return super().create(vals)

    @api.depends('manifest_ids', 'manifest_ids.state', 'capacity')
    def _compute_bookings(self):
        for s in self:
            confirmed = s.manifest_ids.filtered(
                lambda m: m.state in ('booked', 'checked_in'))
            s.booked_seats = len(confirmed)
            s.available_seats = max(0, (s.capacity or 0) - s.booked_seats)
            s.occupancy_pct = (s.booked_seats / s.capacity * 100) if s.capacity else 0.0

    @api.constrains('vehicle_id', 'date', 'departure_time')
    def _check_vehicle_double_booking(self):
        for s in self:
            if not s.vehicle_id:
                continue
            domain = [
                ('vehicle_id', '=', s.vehicle_id.id),
                ('date', '=', s.date),
                ('departure_time', '=', s.departure_time),
                ('state', 'not in', ['cancelled']),
                ('id', '!=', s.id),
            ]
            if self.search_count(domain):
                raise ValidationError(_(
                    'Bus %s is already scheduled on this route at this time on %s.'
                ) % (s.vehicle_id.name, s.date))

    def action_start_boarding(self):
        self.write({'state': 'boarding'})

    def action_depart(self):
        self.write({'state': 'departed'})

    def action_complete(self):
        self.write({'state': 'completed'})
        # Mark no-shows
        self.mapped('manifest_ids').filtered(
            lambda m: m.state == 'booked').write({'state': 'no_show'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_view_manifest(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Manifest — %s' % self.name,
            'res_model': 'bus.manifest.line',
            'view_mode': 'tree,form',
            'domain': [('schedule_id', '=', self.id)],
            'context': {'default_schedule_id': self.id},
        }

    def departure_time_display(self):
        h = int(self.departure_time)
        m = int((self.departure_time - h) * 60)
        return '%02d:%02d' % (h, m)
