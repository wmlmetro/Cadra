from datetime import timedelta
from odoo import models, fields, api
from odoo.exceptions import UserError


SLA_HOURS = {
    'critical': 0.5,
    'high': 2,
    'standard': 4,
    'low': 24,
}


class RequestRequestTriage(models.Model):
    _inherit = 'request.request'

    # ── Triage fields ──
    triage_note = fields.Text('Internal Triage Note')
    assigned_team_id = fields.Many2one(
        'generic.team', string='Assigned Team', tracking=True,
    )
    sla_tier = fields.Selection([
        ('critical', 'Critical — 30 min'),
        ('high', 'High — 2 hours'),
        ('standard', 'Standard — 4 hours'),
        ('low', 'Low — 1 day'),
    ], string='SLA Tier', default='standard')
    sla_deadline = fields.Datetime(
        'SLA Deadline', compute='_compute_sla_deadline', store=True,
    )
    sla_breached = fields.Boolean(
        'SLA Breached', compute='_compute_sla_breached', store=True,
    )
    intake_channel = fields.Selection([
        ('portal', 'Web Portal'),
        ('whatsapp', 'WhatsApp'),
        ('email', 'Email'),
        ('phone', 'Phone'),
        ('walkin', 'Walk-in'),
    ], string='Intake Channel', default='portal')

    # ── Technician work fields ──
    work_log = fields.Text('Work Log')
    parts_used = fields.Char('Parts / Materials Used')
    time_spent_mins = fields.Integer('Time Spent (minutes)')
    resolution_note = fields.Text('Resolution Note')

    # ── Reporter fields (for phone/walk-in intake) ──
    reporter_name = fields.Char('Reporter Name')
    reporter_contact = fields.Char('Reporter Contact')

    # ── Priority shortcut (maps to existing priority field) ──
    priority_display = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Critical'),
    ], string='Display Priority', default='1')

    @api.depends('create_date', 'sla_tier')
    def _compute_sla_deadline(self):
        for rec in self:
            if rec.create_date and rec.sla_tier:
                hours = SLA_HOURS.get(rec.sla_tier, 4)
                rec.sla_deadline = rec.create_date + timedelta(hours=hours)
            else:
                rec.sla_deadline = False

    @api.depends('sla_deadline')
    def _compute_sla_breached(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.sla_breached = bool(rec.sla_deadline and rec.sla_deadline < now)

    def action_assign_and_notify(self):
        self.ensure_one()
        if not self.user_id:
            raise UserError('Please select a technician before assigning.')
        sla_label = dict(self._fields['sla_tier'].selection).get(self.sla_tier, '')
        team_name = self.assigned_team_id.name if self.assigned_team_id else '—'
        self.message_post(
            body='Request assigned to %s (Team: %s). SLA: %s. Note: %s'
                 % (self.user_id.name, team_name, sla_label,
                    self.triage_note or 'None'),
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

    def action_mark_resolved(self):
        self.ensure_one()
        if not self.work_log:
            raise UserError('Please enter a work log before marking as resolved.')
        self.message_post(
            body='Resolved by %s.\nWork done: %s\nParts: %s\nTime: %d min\n'
                 'Resolution: %s'
                 % (self.env.user.name, self.work_log,
                    self.parts_used or 'None', self.time_spent_mins or 0,
                    self.resolution_note or ''),
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )
        closed_stage = self.env['request.stage'].search(
            [('closed', '=', True)], limit=1, order='sequence',
        )
        if closed_stage:
            self.stage_id = closed_stage
