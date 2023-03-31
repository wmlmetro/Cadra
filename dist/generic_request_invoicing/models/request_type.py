from odoo import models, fields


class RequestType(models.Model):
    _inherit = 'request.type'

    enable_invoicing = fields.Boolean()
    default_timetracking_product_id = fields.Many2one(
        'product.product', domain=[('type', '=', 'service')])
