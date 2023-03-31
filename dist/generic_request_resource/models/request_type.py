from odoo import models, fields


class RequestType(models.Model):
    _inherit = 'request.type'

    resource_type_ids = fields.Many2many(
        'generic.resource.type',
        string="Resource types",
        help="Resource types allowed for selection on requests of this type.")
    resource_required = fields.Boolean(
        'Resource is required',
        help='Set this checkbox to make resource field required '
             'on requests of this type')
    resource_invisible = fields.Boolean(
        'Hide resource fields',
        help='Hide resource fields on request form view, '
             'when this type is selected')
