from odoo import models, fields


class GenericSystemEventSource(models.Model):
    _name = 'generic.system.event.category'
    _inherit = ['generic.mixin.name_with_code',
                'generic.mixin.uniq_name_code']
    _order = 'name ASC'
    _description = 'Generic System Event Category'

    event_source_id = fields.Many2one(
        'generic.system.event.source',
        required=False, readonly=True,
        index=True, ondelete='cascade')
