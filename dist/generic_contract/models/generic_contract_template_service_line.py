import logging

from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)


class GenericContractTemplateServiceLine(models.Model):
    _name = 'generic.contract.template.service.line'
    _description = 'Generic Contract Service Line'
    _order = 'service_id ASC, id ASC'

    contract_template_id = fields.Many2one(
        'generic.contract.template', required=True, index=True, readonly=True,
        ondelete='cascade')

    service_id = fields.Many2one(
        'generic.service', index=True, ondelete='restrict')
    service_level_id = fields.Many2one(
        'generic.service.level', index=True, ondelete='restrict')

    _sql_constraints = [
        ('contract_template_service_unique',
         'UNIQUE(contract_template_id, service_id)',
         "Binding: contract_template_id and service_id, must be unique!"),
    ]

    @api.constrains('service_id', 'service_level_id')
    def _ensure_service_id_or_service_level_id(self):
        for rec in self:
            if not rec.service_id and not rec.service_level_id:
                raise exceptions.ValidationError(
                    _('If you don`t want to set the service or service level,'
                      ' unlink this row. You can`t save empty row.'))

    def prepare_contract_service_line(self):
        return {
            'service_id': self.service_id.id,
            'service_level_id': self.service_level_id.id
        }
