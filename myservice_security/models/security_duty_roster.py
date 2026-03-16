from odoo import models, fields, api
from datetime import datetime


class SecurityDutyRoster(models.Model):
    _name = 'security.duty.roster'
    _description = 'Security Duty Roster'
    _order = 'date desc, shift asc'

    guard_id = fields.Many2one(
        comodel_name='security.guard',
        string='Guard',
        required=True,
        ondelete='cascade',
        index=True,
    )
    location_id = fields.Many2one(
        comodel_name='generic.location',
        string='Assigned Location',
        required=True,
        index=True,
    )
    date = fields.Date(
        string='Duty Date',
        required=True,
        default=fields.Date.today,
        index=True,
    )
    shift = fields.Selection(
        selection=[
            ('morning',   'Morning  06:00–14:00'),
            ('afternoon', 'Afternoon 14:00–22:00'),
            ('night',     'Night  22:00–06:00'),
        ],
        string='Shift',
        required=True,
    )
    status = fields.Selection(
        selection=[
            ('scheduled', 'Scheduled'),
            ('active',    'On Duty'),
            ('completed', 'Completed'),
            ('absent',    'Absent'),
        ],
        string='Status',
        default='scheduled',
        tracking=True,
    )
    check_in  = fields.Datetime(string='Check In')
    check_out = fields.Datetime(string='Check Out')
    notes = fields.Text(string='Notes')
    checkpoint_log = fields.Text(
        string='Checkpoint Log',
        help='Time-stamped checkpoint entries for this shift',
    )

    def action_check_in(self):
        self.write({'status': 'active', 'check_in': fields.Datetime.now()})

    def action_check_out(self):
        self.write({'status': 'completed', 'check_out': fields.Datetime.now()})

    def action_mark_absent(self):
        self.write({'status': 'absent'})

    def action_add_checkpoint(self):
        from datetime import datetime
        ts = datetime.now().strftime('%H:%M')
        existing = self.checkpoint_log or ''
        self.checkpoint_log = f"{existing}\n[{ts}] Checkpoint logged" if existing else f"[{ts}] Checkpoint logged"
