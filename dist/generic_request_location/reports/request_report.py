from odoo import models, fields


class RequestReport(models.Model):
    _inherit = 'request.report'

    request_generic_location_id = fields.Many2one(
        'generic.location', 'Location', readonly=True)

    def _get_request_fields(self):
        """ Get list of fields to read from request.
            Return: [(request_field, select_as_field)]
        """
        res = super(RequestReport, self)._get_request_fields()
        return res + [
            ('generic_location_id', 'request_generic_location_id'),
        ]
