import logging
from datetime import timedelta

from odoo import fields, models, api

from .request_sla_rule import SLA_COMPUTE_TIME, SLA_ASSIGNED

_logger = logging.getLogger(__name__)

SLA_STATE = [
    ('ok', 'Ok'),
    ('warning', 'Warning'),
    ('failed', 'Failed'),
]


class RequestSlaControl(models.Model):
    _name = 'request.sla.control'
    _description = 'Request SLA Control'
    _order = 'sla_active'

    sla_rule_id = fields.Many2one(
        'request.sla.rule', 'SLA Rule', required=True,
        readonly=True, ondelete='cascade')
    sla_rule_type_id = fields.Many2one(
        'request.sla.rule.type', index=True, string='SLA Rule type',
        related='sla_rule_id.sla_rule_type_id', store=True)
    sla_rule_code = fields.Char(
        related='sla_rule_id.code', store=False, string='SLA Rule Code')
    active = fields.Boolean(
        related='sla_rule_id.active', index=True, store=True, readonly=True)
    request_id = fields.Many2one(
        'request.request', 'Request', required=True,
        index=True, readonly=True, ondelete='cascade')
    date = fields.Datetime(
        related='request_id.date_created', store=True, index=True)
    request_type_id = fields.Many2one(
        'request.type', 'Request type', readonly=True,
        related='request_id.type_id', store=True)
    request_category_id = fields.Many2one(
        'request.category', readonly=True,
        related='request_id.category_id', store=True)
    sla_active = fields.Boolean(
        index=True, readonly=True, default=False)
    sla_active_date = fields.Datetime(
        required=False, readonly=True,
        default=fields.Datetime.now)
    sla_state = fields.Selection(
        SLA_STATE, index=True, required=True, readonly=True, default='ok')

    # Time computation rule data
    assigned = fields.Selection(
        SLA_ASSIGNED, required=True)
    calendar_id = fields.Many2one('resource.calendar', 'Working time')
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

    compute_time = fields.Selection(
        SLA_COMPUTE_TIME,
        required=True, default='absolute')
    warn_time = fields.Float(readonly=True)
    limit_time = fields.Float(readonly=True)

    sla_log_ids = fields.Many2many(
        'request.sla.log', readonly=True, store=False,
        compute='_compute_sla_log_lines')
    sla_log_count = fields.Integer(
        compute='_compute_sla_log_lines', readonly=True)

    # Time computation
    total_time = fields.Float(
        readonly=True, store=True,
        compute='_compute_total_time',
        help="Total time request was in state described by SLA rule")
    warn_date = fields.Datetime(
        index=True, readonly=True, default=False,
        compute='_compute_warn_limit_dates', store=True)
    limit_date = fields.Datetime(
        index=True, readonly=True, default=False,
        compute='_compute_warn_limit_dates', store=True)

    # User responsible for this line
    user_id = fields.Many2one(
        'res.users', store=True, string='Responsible User',
        compute='_compute_sla_user',
        help="Last user responsible for this SLA control line")

    _sql_constraints = [
        ('request_rule_uniq',
         'UNIQUE (request_id, sla_rule_id)',
         'Request and SLA Rule must be unique for each SLA Control line.'),
    ]

    def _is_log_line_satisfy_this_rule(self, log_line):
        """ Check if specified log line satisfy this SLA rule
        """
        # pylint: disable=too-many-return-statements
        self.ensure_one()
        # TODO: save rule stages on SLA Control line
        sla_stage_ids = self.sla_rule_id.request_stage_ids
        if self.assigned == 'no' and log_line.assignee_id:
            return False
        if self.assigned == 'yes' and not log_line.assignee_id:
            return False
        if sla_stage_ids and log_line.stage_id not in sla_stage_ids:
            return False
        if self.kanban_state_normal and log_line.kanban_state != 'normal':
            return False
        if self.kanban_state_done and log_line.kanban_state != 'done':
            return False
        if self.kanban_state_blocked and log_line.kanban_state != 'blocked':
            return False
        return True

    @api.depends('request_id.sla_log_ids')
    def _compute_sla_log_lines(self):
        for rec in self:
            sla_log_lines = self.env['request.sla.log'].browse([])
            for log_line in rec.request_id.sla_log_ids:
                if rec._is_log_line_satisfy_this_rule(log_line):
                    sla_log_lines |= log_line
            rec.sla_log_ids = sla_log_lines
            rec.sla_log_count = len(sla_log_lines)

    @api.depends('request_id.sla_log_ids', 'request_id.user_id',
                 'compute_time')
    def _compute_total_time(self):
        for record in self:
            total_time = 0
            for log_line in record.sla_log_ids:
                if record.compute_time == 'absolute':
                    total_time += log_line.time_spent_total
                else:  # 'calendar' time
                    total_time += log_line.get_time_spent_calendar(
                        record.calendar_id)
            record.total_time = total_time

    @api.depends('request_id.sla_log_ids', 'request_id.user_id',
                 'request_id.stage_id', 'sla_active')
    def _compute_sla_user(self):
        for record in self:
            user_id = False
            if record.sla_active:
                user_id = record.request_id.user_id
            else:
                for log_line in record.sla_log_ids:
                    if log_line.assignee_id:
                        user_id = log_line.assignee_id
                        break
            record.user_id = user_id

    @api.depends('sla_active', 'sla_active_date', 'warn_time', 'limit_time',
                 'compute_time')
    def _compute_warn_limit_dates(self):
        for record in self:
            if record.sla_active:
                dt_active = fields.Datetime.from_string(record.sla_active_date)
                rtime_warn = record.warn_time - record.total_time
                rtime_limit = record.limit_time - record.total_time
                if record.compute_time == 'absolute':
                    dt_warn = dt_active + timedelta(hours=rtime_warn)
                    dt_limit = dt_active + timedelta(hours=rtime_limit)
                else:   # 'calendar' time
                    dt_warn = record.calendar_id.plan_hours(
                        rtime_warn,
                        day_dt=dt_active,
                        compute_leaves=True)
                    dt_limit = record.calendar_id.plan_hours(
                        rtime_limit,
                        day_dt=dt_active,
                        compute_leaves=True)

                record.update({
                    'warn_date': fields.Datetime.to_string(dt_warn),
                    'limit_date': fields.Datetime.to_string(dt_limit),
                })
            else:
                record.update({
                    'warn_date': False,
                    'limit_date': False,
                })

    def name_get(self):
        result = []
        for record in self:
            rec_name = u"%(rule)s [%(request)s]" % {
                'rule': record.sla_rule_id.name,
                'request': record.request_id.name,
            }
            result.append((record.id, rec_name))
        return result

    def _is_active(self):
        """ Check if this sla control line is active
        """
        self.ensure_one()

        # TODO: copy stage on sla_control, to be indepenendt of SLA rule.
        #       this will allow apply SLA changes only to new requests

        # Is active by stage?
        if not self.sla_rule_id.request_stage_ids:
            # Not rule stages
            sla_stage_active = True
        elif self.request_id.stage_id in self.sla_rule_id.request_stage_ids:
            # Stage in Rule stages
            sla_stage_active = True
        else:
            # Stage not in rule stages
            sla_stage_active = False

        # Is active by assigned state?
        if self.assigned == 'yes':
            sla_assigned_active = bool(self.request_id.user_id)
        elif self.assigned == 'no':
            sla_assigned_active = not bool(self.request_id.user_id)
        else:
            # Assigned is 'none'
            sla_assigned_active = True

        # Is active by kanban state?
        kanban_state = self.request_id.kanban_state
        if not (self.kanban_state_normal or
                self.kanban_state_done or
                self.kanban_state_blocked):
            # Kanban state does not matter
            sla_kanban_state_active = True
        elif self.kanban_state_normal and kanban_state == 'normal':
            sla_kanban_state_active = True
        elif self.kanban_state_done and kanban_state == 'done':
            sla_kanban_state_active = True
        elif self.kanban_state_blocked and kanban_state == 'blocked':
            sla_kanban_state_active = True
        else:
            sla_kanban_state_active = False

        return (
            sla_stage_active and
            sla_assigned_active and
            sla_kanban_state_active
        )

    def _trigger_sla_event(self, event_type, sla_state):
        """ Trigger SLA event on request
        """
        self.request_id.trigger_event(
            event_type, {
                'sla_state': sla_state,
                'sla_control_line_id': self.id,
                'sla_rule_id': self.sla_rule_id.id,
            })

    def _sla_update_state(self):
        """ Update SLA state of rule according to total_time spent on request
            Usualy called after stage change.
        """
        new_sla_state = None
        if self.sla_state == 'ok' and self.total_time > self.warn_time:
            new_sla_state = 'warning'
        if (self.sla_state in ('ok', 'warning') and
                self.total_time > self.limit_time):
            new_sla_state = 'failed'

        # Update SLA State
        if new_sla_state:
            self.write({'sla_state': new_sla_state})

        # Trigger SLA Events
        if new_sla_state == 'warning':
            self._trigger_sla_event('sla_warning', 'warning')
        if new_sla_state == 'failed':
            self._trigger_sla_event('sla_failed', 'failed')

    def _sla_activate(self):
        """ Activate SLA control line
        """
        self.ensure_one()
        self.write({
            'sla_active': True,
            'sla_active_date': fields.Datetime.now(),
        })

    def _sla_deactivate(self):
        """ Deactivate SLA control line
        """
        self.ensure_one()
        self.write({
            'sla_active': False,
            'sla_active_date': False,
        })

    def _trigger_active(self):
        """ Activate or deactivate SLA Control line

            Only active lines track time.
            If line is not active it will not track time
        """
        for record in self:
            control_active = record._is_active()
            if not record.sla_active and control_active:
                record._sla_activate()
            elif record.sla_active and not control_active:
                record._sla_deactivate()

            record._sla_update_state()

    @api.model
    def _scheduler_update_sla_state(self):
        # Search records according condition  warn_date <= now < limit_date
        sla_warning = self.search([
            ('sla_active', '=', True),
            ('sla_state', '=', 'ok'),
            ('warn_date', '<=', fields.Datetime.now()),
            ('limit_date', '>', fields.Datetime.now()),
        ])
        # Search records according condition  limit_date <= now
        sla_failed = self.search([
            ('sla_active', '=', True),
            ('sla_state', 'in', ('ok', 'warning')),
            ('limit_date', '<=', fields.Datetime.now()),
        ])

        # Update SLA state for control lines
        sla_warning.write({'sla_state': 'warning'})
        sla_failed.write({'sla_state': 'failed'})

        # Trigger SLA Events
        for rec in sla_warning:
            rec._trigger_sla_event('sla_warning', 'warning')
        for rec in sla_failed:
            rec._trigger_sla_event('sla_failed', 'failed')

    def action_show_related_sla_log_lines(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request_sla_log.action_request_sla_log_view__tree_first',
            domain=[('id', 'in', self.sla_log_ids.ids)],
        )
