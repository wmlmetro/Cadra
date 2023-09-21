import logging

from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)


class GenericContractResourceServiceLine(models.Model):
    _name = 'generic.contract.resource.service.line'
    _description = 'Generic Contract Resource Service Line'
    _order = 'service_id ASC, id ASC'

    contract_resource_line_id = fields.Many2one(
        'generic.contract.resource.line', required=True, index=True,
        ondelete='cascade')

    contract_id = fields.Many2one(
        related='contract_resource_line_id.contract_id',
        required=False, readonly=True, index=True, ondelete='cascade')

    service_id = fields.Many2one(
        'generic.service', index=True, ondelete='restrict')
    service_level_id = fields.Many2one(
        'generic.service.level', index=True, ondelete='restrict')

    resource_type_id = fields.Many2one(
        related='contract_resource_line_id.resource_type_id',
        required=False, readonly=True, index=True, ondelete='cascade')
    resource_id = fields.Many2one(
        related='contract_resource_line_id.resource_id',
        required=False, readonly=True, index=True, ondelete='cascade')

    @api.constrains('service_id', 'service_level_id')
    def _ensure_service_id_or_service_level_id(self):
        for rec in self:
            if not rec.service_id and not rec.service_level_id:
                raise exceptions.ValidationError(
                    _('If you don`t want to set the service or service level,'
                      ' unlink this row. You can`t save empty row.'))
