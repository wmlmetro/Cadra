from odoo import models, fields


class RequestRequest(models.Model):
    _inherit = 'request.request'

    api_endpoint_id = fields.Many2one(
        'request.api.endpoint', index=True, readonly=True)
