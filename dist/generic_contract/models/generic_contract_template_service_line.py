import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class GenericContractTemplateServiceLine(models.Model):
    _name = 'generic.contract.template.service.line'
    _inherit = 'generic.service.line'
    _description = 'Generic Contract Service Line'

    contract_template_id = fields.Many2one(
        'generic.contract.template', required=True, index=True, readonly=True,
        ondelete='cascade')

    _sql_constraints = [
        ('contract_template_service_unique',
         'UNIQUE(contract_template_id, service_id)',
         "Binding: contract_template_id and service_id, must be unique!"),
    ]

    def prepare_contract_service_line(self):
        return {
            'service_id': self.service_id.id,
            'service_level_id': self.service_level_id.id
        }
