from odoo import models, fields


class GenericEquipmentBrand(models.Model):
    _name = 'generic.equipment.brand'
    _description = 'Generic Equipment Brand'
    _order = 'name'

    name = fields.Char(required=True, index=True)
    vendor_id = fields.Many2one(
        comodel_name='generic.equipment.vendor', index=True)

    active = fields.Boolean(index=True, default=True)

    _sql_constraints = [
        ('unique_check',
         'UNIQUE(vendor_id, name)',
         'Name must be unique per vendor!')
    ]
