from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class GenericResourceRoleType(models.Model):
    _name = 'generic.resource.role.type'
    _description = 'Resource Role Type'
    _inherit = [
        'generic.mixin.no.unlink',
        'generic.mixin.data.updatable',
    ]

    name = fields.Char(
        index=True, required=True, translate=True)
    code = fields.Char(
        index=True, required=True,
        help="ASCII only short code for role type.")
    active = fields.Boolean(
        index=True, default=True)

    role_ids = fields.One2many(
        'generic.resource.role', 'role_type_id', 'Roles')
    role_count = fields.Integer(
        'Roles', compute='_compute_role_count', readonly=True)

    @api.depends('role_ids')
    def _compute_role_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='role_ids')
        for record in self:
            record.role_count = mapped_data.get(record.id, 0)

    _sql_constraints = [
        ('name_uniq',
         'UNIQUE (name)',
         'Role type name must be unique.'),
        ('code_ascii_only',
         r"CHECK (code ~ '^[a-zA-Z0-9\-_]*$')",
         'Role type code must be ascii only'),
    ]
