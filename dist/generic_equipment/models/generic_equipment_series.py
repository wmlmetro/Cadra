from odoo import models, fields


class GenericEquipmentSeries(models.Model):
    _name = 'generic.equipment.series'
    _description = 'Generic Equipment Series'
    _order = 'name'

    name = fields.Char(required=True, index=True)
    vendor_id = fields.Many2one(
        comodel_name='generic.equipment.vendor', index=True)
    brand_id = fields.Many2one(
        comodel_name='generic.equipment.brand', index=True)

    active = fields.Boolean(index=True, default=True)

    _sql_constraints = [
        ('unique_check',
         'UNIQUE(vendor_id, brand_id, name)',
         'Name must be unique per vendor and brand!')
    ]
