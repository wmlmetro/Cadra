from odoo import models, fields


class RequestEvent(models.Model):
    _inherit = 'request.event'

    old_resource_id = fields.Many2one('generic.resource', readonly=True)
    new_resource_id = fields.Many2one('generic.resource', readonly=True)
