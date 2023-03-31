from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    recent_related_request_period = fields.Integer(
        string='Recent related requests period',
        config_parameter='request.recent_related_request_period')
