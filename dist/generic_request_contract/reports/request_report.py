from odoo import models, fields


class RequestReport(models.Model):
    _inherit = 'request.report'

    request_contract_id = fields.Many2one(
        'generic.contract', string='Contract', readonly=True)

    def _get_request_fields(self):
        """ Get list of fields to read from request.
            Return: [(request_field, select_as_field)]
        """
        res = super(RequestReport, self)._get_request_fields()
        return res + [
            ('contract_id', 'request_contract_id'),
        ]
