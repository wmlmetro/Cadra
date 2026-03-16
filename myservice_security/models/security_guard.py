from odoo import models, fields, api


class SecurityGuard(models.Model):
    _name = 'security.guard'
    _description = 'Security Guard'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name asc'

    name = fields.Char(string='Full Name', required=True, tracking=True)
    badge_number = fields.Char(
        string='Badge Number', required=True, copy=False, tracking=True)
    partner_id = fields.Many2one(
        comodel_name='res.partner', string='Contact Record', required=True)
    photo = fields.Binary(related='partner_id.image_128', string='Photo')
    phone = fields.Char(related='partner_id.phone', store=True)
    email = fields.Char(related='partner_id.email', store=True)

    home_location_id = fields.Many2one(
        comodel_name='generic.location',
        string='Base Location',
        tracking=True,
    )
    specialisation = fields.Selection(
        selection=[
            ('access',   'Access Control'),
            ('patrol',   'Patrol'),
            ('cctv',     'CCTV Monitoring'),
            ('response', 'Emergency Response'),
            ('dog',      'K9 / Dog Handler'),
            ('all',      'General'),
        ],
        string='Specialisation',
        default='all',
        tracking=True,
    )
    vendor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Security Company / Vendor',
        domain=[('is_company', '=', True)],
    )
    contract_start = fields.Date(string='Contract Start')
    contract_end   = fields.Date(string='Contract End')
    is_active = fields.Boolean(string='Active', default=True, tracking=True)
    notes = fields.Text(string='Notes')

    # Computed
    duty_count = fields.Integer(
        string='Duty Records',
        compute='_compute_duty_count',
    )
    active_duty_id = fields.Many2one(
        comodel_name='security.duty.roster',
        string='Current Duty',
        compute='_compute_active_duty',
    )
    on_duty = fields.Boolean(
        string='On Duty',
        compute='_compute_active_duty',
        store=True,
    )

    @api.depends('duty_count')
    def _compute_duty_count(self):
        for rec in self:
            rec.duty_count = self.env['security.duty.roster'].search_count([
                ('guard_id', '=', rec.id)
            ])

    @api.depends()
    def _compute_active_duty(self):
        from datetime import date
        today = date.today()
        for rec in self:
            active = self.env['security.duty.roster'].search([
                ('guard_id', '=', rec.id),
                ('date', '=', today),
                ('status', '=', 'active'),
            ], limit=1)
            rec.active_duty_id = active
            rec.on_duty = bool(active)

    def action_view_duties(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Duty Roster',
            'res_model': 'security.duty.roster',
            'view_mode': 'list,form',
            'domain': [('guard_id', '=', self.id)],
        }
