import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class GenericContractEvent(models.Model):
    _name = 'generic.contract.event'
    _description = 'Generic Contract Event'
    _inherit = 'generic.system.event.data.mixin'

    # Assign event fields
    old_user_id = fields.Many2one('res.users', readonly=True)
    new_user_id = fields.Many2one('res.users', readonly=True)
