from odoo import fields, models


class GenericResourcePermission(models.Model):
    _name = 'generic.resource.permission'
    _inherit = ['generic.mixin.name_with_code']
    _order = 'name ASC'

    _description = 'Generic Resource Permission'

    description = fields.Text()

    resource_type_id = fields.Many2one(
        'generic.resource.type', string="Resource type",
        required=True, index=True, ondelete='restrict')

    _sql_constraints = [
        ('permission_name_uniq',
         'UNIQUE (resource_type_id, name)',
         'Permission name must be uniq for resource type'),
        ('permission_code_uniq',
         'UNIQUE (resource_type_id, code)',
         'Permission code must be uniq for resource type'),
    ]
