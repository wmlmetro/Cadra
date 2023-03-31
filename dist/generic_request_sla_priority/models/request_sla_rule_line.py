from odoo import models, fields
from odoo.addons.generic_request.models.request_request import (
    AVAILABLE_PRIORITIES
)


class RequestSLAPriority(models.Model):
    _inherit = 'request.sla.rule.line'

    priority = fields.Selection(
        selection=AVAILABLE_PRIORITIES,
        default=False, index=True)
