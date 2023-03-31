import logging

from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

_logger = logging.getLogger(__name__)


class GenericContractResourceLine(models.Model):
    _inherit = 'generic.contract.resource.line'

    resource_role_link_ids = fields.One2many(
        'generic.resource.role.link', 'doc_id', string='Role Links',
        domain=[('doc_model', '=', 'generic.contract.resource.line')])
    resource_role_link_count = fields.Integer(
        'Roles', compute='_compute_resource_role_link_count', readonly=True)

    @api.depends('resource_role_link_ids')
    def _compute_resource_role_link_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='resource_role_link_ids')
        for record in self:
            record.resource_role_link_count = mapped_data.get(record.id, 0)

    @api.onchange('resource_type_id', 'resource_res_id')
    def _onchange_resource(self):
        # for unlink resource_role_link_ids without loosing context
        # standard method unlink() looses context
        vals = super(GenericContractResourceLine, self)._onchange_resource()
        resource_role_links = [
            (2, role_id) for role_id in self.resource_role_link_ids.ids]
        vals['value'].update({
            'resource_role_link_ids': resource_role_links
        })
        return vals

    def action_view_contract_resource_line_role_links(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_resource_role.generic_resource_role_link_action_view',
            context=dict(
                self.env.context,
                default_resource_type_id=self.resource_type_id.id,
                default_resource_res_id=self.resource_res_id,
                default_partner_id=self.contract_partner_id.id,
                default_doc_model=self._name,
                default_doc_id=self.id,
            ),
            domain=[('id', 'in', self.resource_role_link_ids.ids)])
