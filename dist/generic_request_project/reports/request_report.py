from odoo import models, fields


class RequestReport(models.Model):
    _inherit = 'request.report'

    request_project_id = fields.Many2one(
        'project.project', string='Project', readonly=True)

    def _get_request_fields(self):
        """ Get list of fields to read from request.
            Return: [(request_field, select_as_field)]
        """
        res = super(RequestReport, self)._get_request_fields()
        return res + [
            ('project_id', 'request_project_id'),
        ]
