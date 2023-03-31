from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    request_require_terms_and_conditions = fields.Selection(
        selection=[
            ('yes', 'Yes'),
            ('no', 'No'),
        ],
        default='no',
        required=True)
    request_terms_and_conditions_url = fields.Char()
