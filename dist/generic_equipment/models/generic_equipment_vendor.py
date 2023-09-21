from odoo import models, fields


class GenericEquipmentVendor(models.Model):
    _name = 'generic.equipment.vendor'
    _description = 'Generic Equipment Vendor'
    _order = 'name'

    name = fields.Char(required=True, index=True)

    active = fields.Boolean(index=True, default=True)

    _sql_constraints = [
        ('unique_name', 'UNIQUE(name)',
         'Name must be unique')
    ]
