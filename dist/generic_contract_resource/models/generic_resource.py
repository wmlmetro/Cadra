from odoo import models, fields, api
from odoo.addons.generic_resource.tools.utils import resource_proxy


class GenericResource(models.Model):
    _inherit = 'generic.resource'

    resource_contract_ids = fields.Many2manyView(
        comodel_name='generic.contract',
        relation='generic_contract_resource_line',
        column1='resource_id',
        column2='contract_id',
        readonly=True)
    resource_contract_count = fields.Integer(
        compute='_compute_resource_contract_count', readonly=True)

    @api.depends('resource_contract_ids')
    def _compute_resource_contract_count(self):
        for record in self:
            record.resource_contract_count = len(record.resource_contract_ids)

    @resource_proxy
    def action_show_resource_contracts(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            "generic_contract.generic_contract_action",
            domain=[('contract_resource_line_ids.resource_id', '=', self.id)])
