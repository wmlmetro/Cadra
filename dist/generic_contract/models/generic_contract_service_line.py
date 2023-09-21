import logging

from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)


class GenericContractServiceLine(models.Model):
    _name = 'generic.contract.service.line'
    _description = 'Generic Contract Service Line'
    _order = 'service_id ASC, id ASC'

    contract_id = fields.Many2one(
        'generic.contract', required=True, index=True, readonly=True,
        ondelete='cascade', auto_join=True)
    contract_state = fields.Selection(
        related='contract_id.state', readonly=True,
        store=True, index=True)

    service_id = fields.Many2one(
        'generic.service', index=True, ondelete='restrict')
    service_level_id = fields.Many2one(
        'generic.service.level', index=True, ondelete='restrict')

    date_added = fields.Datetime()

    _sql_constraints = [
        ('contract_service_unique',
         'UNIQUE(contract_id, service_id)',
         "Binding: contract_id and service_id, must be unique!"),
    ]

    @api.constrains('service_id', 'service_level_id')
    def _ensure_service_id_or_service_level_id(self):
        for rec in self:
            if not rec.service_id and not rec.service_level_id:
                raise exceptions.ValidationError(
                    _('If you don`t want to set the service or service level,'
                      ' unlink this row. You can`t save empty row.'))
