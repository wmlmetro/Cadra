from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    request_require_terms_and_conditions = fields.Selection(
        related='company_id.request_require_terms_and_conditions',
        readonly=False,
        string='Require Terms and Conditions',
    )
    request_terms_and_conditions_url = fields.Char(
        related='company_id.request_terms_and_conditions_url',
        readonly=False,
        string="Terms and Conditions URL")
