import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class GenericContractEvent(models.Model):
    _inherit = 'generic.contract.event'

    # Main package changes
    resource_id = fields.Many2one(
        'generic.resource', readonly=True)
    contract_resource_line_id = fields.Many2one(
        'generic.contract.resource.line', readonly=True)
