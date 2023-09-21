import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class GenericContractTemplate(models.Model):
    _inherit = 'generic.contract.template'

    contract_resource_line_ids = fields.One2many(
        'generic.contract.template.resource.line', 'contract_template_id',
        string='Resource Lines')

    def _prepare_contract_values(self, partner, user, date_begin, date_end):
        data = super(
            GenericContractTemplate, self
        )._prepare_contract_values(partner, user, date_begin, date_end)

        contract_resource_line_ids_data = []
        for contract_resource_line in self.contract_resource_line_ids:
            # TODO: prepare values for resource lines (services, roles, etc)
            contract_resource_line_ids_data.append(
                (0, 0, {
                    'resource_id': contract_resource_line.resource_id.id,
                })
            )
        data.update({
            'contract_resource_line_ids': contract_resource_line_ids_data
        })
        return data
