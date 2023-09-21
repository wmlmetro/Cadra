from odoo import models, fields


class GenericEquipmentCategory(models.Model):
    _name = 'generic.equipment.category'
    _inherit = [
        'generic.mixin.name_with_code',
        'generic.mixin.uniq_name_code',
        'generic.mixin.parent.names',
    ]
    _description = 'Generic Equipment Category'
    _order = 'name ASC'
    _parent_name = 'parent_id'
    _parent_order = 'name'
    _parent_store = True

    parent_id = fields.Many2one(
        'generic.equipment.category', 'Parent Category',
        index=True, ondelete='restrict')
    parent_path = fields.Char(index=True)
    active = fields.Boolean(index=True, default=True)
