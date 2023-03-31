from odoo import models, fields


class FetchmailServer(models.Model):
    _inherit = 'fetchmail.server'

    request_creation_template_id = fields.Many2one(
        'request.creation.template')
