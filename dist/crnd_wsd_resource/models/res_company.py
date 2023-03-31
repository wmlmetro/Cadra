from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    request_resource_autocomplete_max_resources = fields.Integer(
        default=10)
