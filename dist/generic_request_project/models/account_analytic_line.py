import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    req_timesheet_line_id = fields.Many2one(
        'request.timesheet.line', ondelete='cascade', index=True)
    request_id = fields.Many2one(
        'request.request', ondelete='cascade',
        related='req_timesheet_line_id.request_id',
        store=True, index=True)
