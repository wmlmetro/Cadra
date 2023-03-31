import logging
from odoo import fields, models, api, exceptions, _

_logger = logging.getLogger(__name__)


SLA_COMPUTE_TIME = [
    ('absolute', 'Absolute time'),
    ('calendar', 'Working time'),
]

SLA_ASSIGNED = [
    ('none', 'None'),
    ('yes', 'Yes'),
    ('no', 'No'),
]


class RequestSlaRule(models.Model):
    _name = 'request.sla.rule'
    _inherit = [
        'mail.thread',
        'generic.mixin.name_with_code',
    ]
    _description = 'Request SLA rule'
    _order = 'sequence, name'

    # Defined in generic.mixin.name_with_code
    name = fields.Char(tracking=True)
    code = fields.Char(tracking=True)

    sequence = fields.Integer(
        required=True, index=True, default=5,
        help='Sequence determines position of this rule '
             'in the list on the SLA Rules page.\n'
             'The lower the sequence, the higher the position.\n'
             'The first active SLA Rule in the list will be the Main '
             'SLA Rule for this type of request.')
    sla_rule_type_id = fields.Many2one(
        'request.sla.rule.type', index=True, required=True,
        tracking=True, ondelete='restrict',
        string='SLA Rule type',
        help='Global type of SLA Rule\n'
             'It is used to group SLA Rules (e.g. for reporting)')
    request_type_id = fields.Many2one(
        'request.type', 'Request type',
        required=True, index=True,
        ondelete='cascade', readonly=True,
        tracking=True)
    request_stage_ids = fields.Many2many(
        'request.stage', string='Stages',
        tracking=True,
        help='This SLA Rule will be active on selected stages')
    assigned = fields.Selection(
        SLA_ASSIGNED, required=True, default='none',
        tracking=True,
        help='1) None - SLA Rule will be active at this stage(s) '
             'regardless of assignment\n'
             '2) Yes - SLA Rule will activate at this stage(s) '
             'if responsible person is assigned\n'
             '3) No - SLA Rule will be active if no responsible '
             'person is assigned')
    compute_time = fields.Selection(
        SLA_COMPUTE_TIME, required=True, default='absolute',
        tracking=True,
        help='Time calculating method\nIf "Working time" is selected, '
             'it must be configured: Request Type Form -> SLA Tab')
    warn_time = fields.Float(tracking=True,
                             help='Time before the warning shows up')
    limit_time = fields.Float(required=True, tracking=True,
                              help='Total time after which SLA will Fail')
    rule_line_ids = fields.One2many(
        'request.sla.rule.line', 'sla_rule_id', 'Specific Rules')
    active = fields.Boolean(index=True, default=True)

    sla_calendar_id = fields.Many2one(
        'resource.calendar', string="Working time")

    kanban_state_normal = fields.Boolean(
        default=False, string='Kanban State In Progress',
        help='If selected, the rule is active'
             ' when kanban state is "In Progress"')
    kanban_state_blocked = fields.Boolean(
        default=False, string='Kanban State Paused',
        help='If selected, the rule is active'
             ' when kanban state is "Blocked"')
    kanban_state_done = fields.Boolean(
        default=False, string='Kanban State Ready',
        help='If selected, the rule is active'
             ' when kanban state is "Ready for next stage"')

    _sql_constraints = [
        ('check_limit_time_gt_0',
         'CHECK (limit_time > 0)',
         'Limit time must be greater that zero'),
        ('check_warn_time_gte_0',
         'CHECK (warn_time >= 0)',
         'Warn time must be greater or equal zero'),
        ('check_limit_time_gt_warn_time',
         'CHECK (limit_time > warn_time)',
         'Limit time must be greater than Warn time'),
        ('name_uniq',
         'UNIQUE (request_type_id, code)',
         'SLA Rule code must be unique for each request type'),
    ]

    @api.constrains('compute_time', 'sla_calendar_id')
    def _check_calendar_rules(self):
        for rec in self:
            if rec.compute_time != 'calendar':
                continue
            if not (rec.sla_calendar_id or
                    rec.request_type_id.sla_calendar_id):
                raise exceptions.ValidationError(_(
                    "Cannot set compute time to Working time, because "
                    "request SLA rule '%s' have no configured Working time!"
                    "") % rec.name)

    @api.onchange('request_type_id')
    def onchange_set_default_sequence(self):
        for rec in self:
            rules = rec.request_type_id.sla_rule_ids.filtered(
                lambda r: r.id is not rec.id)
            if rules:
                rec.sequence = max(s.sequence for s in rules) + 1

    @api.onchange('sla_rule_type_id')
    def onchange_rule_type_update_name_code(self):
        for rec in self:
            rec.name = rec.sla_rule_type_id.name
            rec.code = rec.sla_rule_type_id.code
