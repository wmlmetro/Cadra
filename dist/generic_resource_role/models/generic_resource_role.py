from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class GenericResourceRole(models.Model):
    _name = 'generic.resource.role'
    _description = 'Resource Role'
    _inherit = [
        'generic.mixin.data.updatable',
    ]

    name = fields.Char(
        index=True, required=True, translate=True)
    active = fields.Boolean(index=True, default=True)

    role_type_id = fields.Many2one(
        'generic.resource.role.type', required=True,
        index=True, string='Role type', ondelete='restrict')
    role_code = fields.Char(
        related="role_type_id.code", store=True, index=True, readonly=True)
    resource_type_id = fields.Many2one(
        'generic.resource.type', required=True,
        index=True, string="Resource type", ondelete='restrict')

    can_write = fields.Boolean(index=True)
    can_unlink = fields.Boolean(index=True)
    can_manage_roles = fields.Boolean(index=True)

    role_link_ids = fields.One2many(
        'generic.resource.role.link', 'role_id', string='Role links')
    role_link_count = fields.Integer(
        'Role links', compute='_compute_role_link_count', readonly=True)

    sub_role_ids = fields.One2many(
        'generic.resource.sub.role', 'master_role_id', string='Sub Roles')
    sub_role_count = fields.Integer(
        compute='_compute_sub_role_count', readonly=True)

    resource_permission_ids = fields.Many2many(
        comodel_name='generic.resource.permission',
        relation='generic_resource_role_permission_rel',
        column1='role_id',
        column2='permission_id',
        string='Resource Permissions',
    )

    @api.depends('role_link_ids')
    def _compute_role_link_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='role_link_ids')
        for record in self:
            record.role_link_count = mapped_data.get(record.id, 0)

    @api.depends('sub_role_ids')
    def _compute_sub_role_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='sub_role_ids')
        for record in self:
            record.sub_role_count = mapped_data.get(record.id, 0)

    @api.onchange('role_type_id')
    def onchange_role_type_id(self):
        for record in self:
            record.name = record.role_type_id.name

    @api.onchange('resource_type_id')
    def onchange_resource_type_id(self):
        for record in self:
            record.resource_permission_ids = False

    def action_show_sub_roles(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_resource_role.action_generic_resource_sub_role_view',
            domain=[('master_role_id', '=', self.id)],
            context={'default_master_role_id': self.id},
        )

    def action_show_role_links(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_resource_role.generic_resource_role_link_action_view',
            domain=[('role_id', '=', self.id)],
            context={
                'default_role_id': self.id,
                'default_resource_type_id': self.resource_type_id.id,
            },
        )
