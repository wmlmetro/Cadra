from odoo import fields, models


class RequestSlaRuleCondition(models.Model):
    _name = 'request.sla.rule.condition'
    _inherit = [
        'mail.thread',
    ]
    _order = 'sequence, name'
    _description = 'Request SLA rule Condition'

    name = fields.Char(
        required=True, index=True, translate=True, tracking=True)
    sequence = fields.Integer(
        index=True, default=10, tracking=True,
        help="Conditions with smaller value in this field "
             "will be checked first")
    sla_rule_id = fields.Many2one('request.sla.rule', required=True)
    sla_rule_type_id = fields.Many2one(
        'request.sla.rule.type',
        related="sla_rule_id.sla_rule_type_id", readonly=True)
    request_type_id = fields.Many2one(
        'request.type', 'Request type',
        required=True, index=True, ondelete='cascade',
        tracking=True)
    condition_ids = fields.Many2many(
        comodel_name='generic.condition',
        relation='generic_request_sla_rule_conditions_rel',
        column1='sla_rule_condion_id',
        column2='condition_id',
        string='Conditions',
        help="Specify generic conditions to decide whether the activity "
             "can be executed.")

    description = fields.Text(translate=True)
    active = fields.Boolean(index=True, default=True)
