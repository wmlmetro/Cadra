from odoo import models, fields


class AccountInvoice(models.Model):
    _inherit = 'account.move'

    request_id = fields.Many2one(
        'request.request', readonly=True)
