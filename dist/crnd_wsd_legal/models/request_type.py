from odoo import models, fields


class RequestType(models.Model):
    _inherit = 'request.type'

    require_terms_and_conditions = fields.Selection(
        selection=[
            ('global', 'Global Default'),
            ('yes', 'Yes'),
            ('no', 'No'),
        ],
        default='global',
        required=True)
    terms_and_conditions_url = fields.Char()
