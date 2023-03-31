import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = 'request.request'

    crm_lead_id = fields.Many2one('crm.lead', string='Lead', readonly=False)
