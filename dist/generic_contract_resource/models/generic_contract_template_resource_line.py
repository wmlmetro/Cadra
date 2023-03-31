import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class GenericContractResourceLine(models.Model):
    _name = 'generic.contract.template.resource.line'
    _inherit = [
        'generic.resource.related.mixin',
    ]
    _description = 'Generic Contract Template Resource Line'

    contract_template_id = fields.Many2one(
        'generic.contract.template', required=True, index=True, readonly=True,
        ondelete='cascade')
