from odoo import models, fields


class GenericResourceType(models.Model):
    _inherit = 'generic.resource.type'

    use_generic_locations = fields.Boolean(
        help='If set, then resources of this types could be '
             'placed on generic location.')
