from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    request_resource_autocomplete_max_resources = fields.Integer(
        related='company_id.request_resource_autocomplete_max_resources',
        readonly=False)
