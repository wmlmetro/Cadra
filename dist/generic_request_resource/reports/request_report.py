from odoo import models, fields


class RequestReport(models.Model):
    _inherit = 'request.report'

    request_resource_type_id = fields.Many2one(
        'generic.resource.type', string='Resource type', readonly=True)
    request_resource_id = fields.Many2one(
        'generic.resource', string='Generic resource', readonly=True)

    def _get_request_fields(self):
        """ Get list of fields to read from request.
            Return: [(request_field, select_as_field)]
        """
        res = super(RequestReport, self)._get_request_fields()
        return res + [
            ('resource_type_id', 'request_resource_type_id'),
            ('resource_id', 'request_resource_id'),
        ]
