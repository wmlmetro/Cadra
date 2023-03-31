from odoo import models, fields


class ResourceType(models.Model):
    _inherit = 'generic.resource.type'

    search_by_field_id = fields.Many2one(
        'ir.model.fields', store=True, ondelete='cascade')
