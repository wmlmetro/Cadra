from odoo import fields, models


class AccountInvoice(models.Model):
    _inherit = 'account.move'

    generic_contract_id = fields.Many2one(
        'generic.contract', string='Contract', index=True, ondelete="cascade")
