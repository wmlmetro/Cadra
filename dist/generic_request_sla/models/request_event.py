from odoo import models, fields
from .request_sla_control import SLA_STATE


class RequestEvent(models.Model):
    _inherit = 'request.event'

    sla_state = fields.Selection(SLA_STATE, readonly=True)
    sla_control_line_id = fields.Many2one('request.sla.control', readonly=True)
    sla_rule_id = fields.Many2one('request.sla.rule', readonly=True)
    sla_rule_type_id = fields.Many2one(
        'request.sla.rule.type',
        related='sla_rule_id.sla_rule_type_id', readonly=True)
