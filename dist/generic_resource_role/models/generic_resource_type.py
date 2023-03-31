from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m
from .generic_resource_role_link import GenericResourceRoleID


class GenericResourceType(models.Model):
    _inherit = 'generic.resource.type'

    role_ids = fields.One2many(
        'generic.resource.role', 'resource_type_id',
        string="Roles")
    role_count = fields.Integer(
        'Roles', compute='_compute_role_count', readonly=True)

    role_link_ids = fields.One2many(
        'generic.resource.role.link', 'resource_type_id', 'Role links',
        readonly=True)
    role_link_count = fields.Integer(
        'Role links', compute='_compute_role_link_count', readonly=True)

    creator_role_id = fields.Many2one(
        'generic.resource.role', 'Creator Role',
        help='This role will be automatically assigned to resource creator')

    resource_visibility = fields.Selection(
        selection_add=[('role-based', 'Access restricted by roles')],
        default='role-based', ondelete={'role-based': 'cascade'})

    resource_act_manage_roles_id = fields.Many2one(
        'ir.actions.act_window', readonly=True)

    resource_permission_ids = fields.One2many(
        'generic.resource.permission', 'resource_type_id', 'Permissions',
        readonly=True)
    resource_permission_count = fields.Integer(
        'Permissions', compute='_compute_resource_permission_count',
        readonly=True)

    @api.depends('role_ids')
    def _compute_role_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='role_ids')
        for record in self:
            record.role_count = mapped_data.get(record.id, 0)

    @api.depends('role_link_ids')
    def _compute_role_link_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='role_link_ids')
        for record in self:
            record.role_link_count = mapped_data.get(record.id, 0)

    @api.depends('resource_permission_ids')
    def _compute_resource_permission_count(self):
        for rec in self:
            rec.resource_permission_count = len(rec.resource_permission_ids)

    def get_resource_tracking_fields(self):
        res = super(GenericResourceType, self).get_resource_tracking_fields()
        return res | set(self.env['generic.resource.sub.role'].search([
            ('sub_type_id', '=', self.id)]).sudo().mapped('sub_field_id.name'))

    def _get_resource_defaults(self):
        defaults = super(GenericResourceType, self)._get_resource_defaults()
        if self.creator_role_id:
            defaults['resource_role_link_ids'] = [
                (0, 0, {
                    'role_id': GenericResourceRoleID(self.creator_role_id.id),
                    'partner_id': self.env.user.partner_id.id,
                    'date_start': fields.Date.today(),
                })
            ]
        return defaults

    def _create_context_action_for_target_model_single(self):
        if not self.resource_act_manage_roles_id:
            self.resource_act_manage_roles_id = self.env.ref(
                'generic_resource_role.'
                'action_resource_open_wizard_manage_roles'
            ).copy({
                'binding_model_id': self.model_id.id,
            })
        return super(
            GenericResourceType, self
        )._create_context_action_for_target_model_single()

    def unlink(self):
        self.mapped('resource_act_manage_roles_id').unlink()
        return super(GenericResourceType, self).unlink()

    def action_show_related_roles(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_resource_role.generic_resource_role_action_view',
            context={'default_resource_type_id': self.id},
            domain=[('resource_type_id', '=', self.id)])

    def action_show_related_role_links(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_resource_role.generic_resource_role_link_action_view',
            context={'default_resource_type_id': self.id},
            domain=[('resource_type_id', '=', self.id)])

    def action_show_related_permissions(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_resource_role.generic_resource_permission_action_view',
            context={'default_resource_type_id': self.id},
            domain=[('resource_type_id', '=', self.id)])
