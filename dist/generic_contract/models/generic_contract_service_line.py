import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class GenericContractServiceLine(models.Model):
    _name = 'generic.contract.service.line'
    _inherit = 'generic.service.line'
    _description = 'Generic Contract Service Line'
    _order = 'service_id ASC, id ASC'

    contract_id = fields.Many2one(
        'generic.contract', required=True, index=True, readonly=True,
        ondelete='cascade', auto_join=True)
    contract_state = fields.Selection(
        related='contract_id.state', readonly=True,
        store=True, index=True)
    date_added = fields.Datetime()

    _sql_constraints = [
        ('contract_service_unique',
         'UNIQUE(contract_id, service_id)',
         "Binding: contract_id and service_id, must be unique!"),
    ]
