from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class ResPartner(models.Model):
    _inherit = 'res.partner'

    resource_role_link_ids = fields.One2many(
        'generic.resource.role.link', 'partner_id', 'Resource Roles')
    resource_role_link_count = fields.Integer(
        readonly=True, compute='_compute_resource_role_link_count',
        compute_sudo=True)

    @api.depends('resource_role_link_ids')
    def _compute_resource_role_link_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='resource_role_link_ids', sudo=True)
        for record in self:
            record.resource_role_link_count = mapped_data.get(record.id, 0)

    def action_view_resource_role_links(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_resource_role.generic_resource_role_link_action_view',
            context={'default_partner_id': self.id},
            domain=[('partner_id', '=', self.id)],
        )
