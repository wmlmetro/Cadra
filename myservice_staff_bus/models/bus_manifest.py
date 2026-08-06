from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import uuid
import hashlib


class BusManifestLine(models.Model):
    _name = 'bus.manifest.line'
    _description = 'Staff Bus Booking / Manifest Line'
    _inherit = ['mail.thread']
    _order = 'schedule_id, boarding_stop_sequence'

    schedule_id = fields.Many2one(
        'bus.schedule', string='Schedule', required=True, ondelete='cascade')
    employee_id = fields.Many2one(
        'hr.employee', string='Staff Member', required=True)
    department_id = fields.Many2one(related='employee_id.department_id', store=True)

    boarding_stop_id = fields.Many2one(
        'bus.route.stop', string='Boarding Stop',
        domain="[('route_id', '=', parent.route_id)]")
    alighting_stop_id = fields.Many2one(
        'bus.route.stop', string='Alighting Stop',
        domain="[('route_id', '=', parent.route_id)]")
    boarding_stop_sequence = fields.Integer(
        related='boarding_stop_id.sequence', store=True)

    booking_ref = fields.Char('Booking Reference', copy=False)
    qr_data = fields.Char('QR Code Data', copy=False)

    booking_date = fields.Datetime('Booked On', default=fields.Datetime.now)
    check_in_time = fields.Datetime('Check-in Time')
    checked_in_by = fields.Many2one('res.users', string='Checked In By')

    state = fields.Selection([
        ('booked', 'Booked'),
        ('checked_in', 'Checked In'),
        ('no_show', 'No Show'),
        ('cancelled', 'Cancelled'),
    ], default='booked', tracking=True)

    notes = fields.Text('Notes')

    # Computed from schedule
    route_id = fields.Many2one(related='schedule_id.route_id', store=True)
    date = fields.Date(related='schedule_id.date', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._generate_booking_ref()
        return records

    def _generate_booking_ref(self):
        for r in self:
            if not r.booking_ref:
                raw = '%s-%s-%s' % (r.schedule_id.id, r.employee_id.id, uuid.uuid4().hex[:6])
                r.booking_ref = 'BUS-%s' % raw.upper()[:12]
                r.qr_data = hashlib.md5(r.booking_ref.encode()).hexdigest()[:16].upper()

    @api.constrains('schedule_id', 'employee_id')
    def _check_duplicate_booking(self):
        for line in self:
            domain = [
                ('schedule_id', '=', line.schedule_id.id),
                ('employee_id', '=', line.employee_id.id),
                ('state', 'not in', ['cancelled']),
                ('id', '!=', line.id),
            ]
            if self.search_count(domain):
                raise ValidationError(_(
                    '%s is already booked on this schedule.'
                ) % line.employee_id.name)

    @api.constrains('schedule_id')
    def _check_capacity(self):
        for line in self:
            sched = line.schedule_id
            if sched.capacity and sched.booked_seats > sched.capacity:
                raise ValidationError(_(
                    'This bus is fully booked. No available seats on %s.'
                ) % sched.name)

    def action_check_in(self):
        for r in self:
            if r.state != 'booked':
                raise ValidationError(_('Only booked passengers can be checked in.'))
            r.write({
                'state': 'checked_in',
                'check_in_time': fields.Datetime.now(),
                'checked_in_by': self.env.uid,
            })

    def action_cancel(self):
        self.write({'state': 'cancelled'})
