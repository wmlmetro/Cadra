from odoo import models


class GenericEquipmentSimple(models.Model):
    _name = 'generic.equipment.simple'
    _description = 'Generic Equipment Simple'
    _inherit = [
        'generic.equipment',
    ]
