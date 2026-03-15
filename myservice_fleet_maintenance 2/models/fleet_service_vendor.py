from odoo import models, fields, api


class FleetServiceVendor(models.Model):
    _name = 'fleet.service.vendor'
    _description = 'Fleet Service Vendor / Mechanic'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name asc'

    name = fields.Char(
        string='Vendor / Workshop Name',
        required=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Contact',
        required=True,
        tracking=True,
        help='Odoo contact record for this vendor (email, phone, address).',
    )
    email = fields.Char(
        related='partner_id.email',
        string='Email',
        readonly=True,
        store=True,
    )
    phone = fields.Char(
        related='partner_id.phone',
        string='Phone',
        readonly=True,
        store=True,
    )
    specialisation = fields.Selection(
        selection=[
            ('all',        'General / All'),
            ('mechanical', 'Mechanical'),
            ('electrical', 'Electrical'),
            ('tyres',      'Tyres & Wheels'),
            ('bodywork',   'Bodywork & Panel'),
            ('ac',         'Air Conditioning'),
            ('transmission', 'Transmission & Gearbox'),
        ],
        string='Specialisation',
        default='all',
        required=True,
        tracking=True,
    )
    location_ids = fields.Many2many(
        comodel_name='generic.location',
        relation='fleet_service_vendor_location_rel',
        column1='vendor_id',
        column2='location_id',
        string='Service Coverage',
        help='States or zones this vendor covers.',
    )
    is_approved = fields.Boolean(
        string='Approved Vendor',
        default=False,
        tracking=True,
    )
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notes')

    vehicle_ids = fields.One2many(
        comodel_name='fleet.vehicle',
        inverse_name='preferred_vendor_id',
        string='Assigned Vehicles',
    )
    vehicle_count = fields.Integer(
        string='Vehicles',
        compute='_compute_vehicle_count',
    )

    @api.depends('vehicle_ids')
    def _compute_vehicle_count(self):
        for rec in self:
            rec.vehicle_count = len(rec.vehicle_ids)

    def action_view_vehicles(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Assigned Vehicles',
            'res_model': 'fleet.vehicle',
            'view_mode': 'list,form',
            'domain': [('preferred_vendor_id', '=', self.id)],
        }
