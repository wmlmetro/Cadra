from odoo import models, fields
from ..models.request_sla_control import SLA_STATE


class RequestReport(models.Model):
    _inherit = 'request.report'

    # Main SLA Rules
    # TODO: how this show?
    request_sla_warn_date = fields.Datetime('SLA Warn date', readonly=True)
    request_sla_limit_date = fields.Datetime('SLA Limit date', readonly=True)
    request_sla_state = fields.Selection(
        SLA_STATE,
        'SLA State', readonly=True)

    def _get_request_fields(self):
        """ Get list of fields to read from request.
            Return: [(request_field, select_as_field)]
        """
        res = super(RequestReport, self)._get_request_fields()
        return res + [
            ('sla_warn_date', 'request_sla_warn_date'),
            ('sla_limit_date', 'request_sla_limit_date'),
            ('sla_state', 'request_sla_state'),
        ]
