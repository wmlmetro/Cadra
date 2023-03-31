from odoo import models, fields


class AccountInvoice(models.Model):
    _inherit = 'account.move.line'

    request_invoice_line_id = fields.Many2one(
        'request.invoice.line', readonly=True)
