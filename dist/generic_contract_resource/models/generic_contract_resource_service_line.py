import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class GenericContractResourceServiceLine(models.Model):
    _name = 'generic.contract.resource.service.line'
    _inherit = [
        'generic.service.line',
    ]
    _description = 'Generic Contract Resource Service Line'

    contract_resource_line_id = fields.Many2one(
        'generic.contract.resource.line', required=True, index=True,
        ondelete='cascade')

    contract_id = fields.Many2one(
        related='contract_resource_line_id.contract_id',
        required=False, readonly=True, index=True, ondelete='cascade')
    resource_type_id = fields.Many2one(
        related='contract_resource_line_id.resource_type_id',
        required=False, readonly=True, index=True, ondelete='cascade')
    resource_id = fields.Many2one(
        related='contract_resource_line_id.resource_id',
        required=False, readonly=True, index=True, ondelete='cascade')
