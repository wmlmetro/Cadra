from odoo import models, fields


class RequestAPIEndpoint(models.Model):
    _inherit = 'request.api.endpoint'

    on_success = fields.Selection(selection_add=[
        ('redirect_to_req', 'Redirect on Request Page'),
    ], ondelete={'redirect_to_req': 'cascade'})
