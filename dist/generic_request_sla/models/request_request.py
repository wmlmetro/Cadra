import logging

from odoo import fields, models, api, _

from odoo.addons.generic_mixin import post_write
from odoo.addons.generic_system_event import on_event

from .request_sla_control import SLA_STATE

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = 'request.request'

    sla_control_ids = fields.One2many(
        'request.sla.control', 'request_id', 'SLA Controls', readonly=True,
        copy=False)

    # SLA state related fields
    sla_state = fields.Selection(
        SLA_STATE,
        'SLA State',
        compute='_compute_sla_state',
        compute_sudo=True,
        readonly=True,
        store=True,
        index=True)
    sla_user_id = fields.Many2one(
        'res.users',
        compute='_compute_sla_state',
        compute_sudo=True,
        readonly=True,
        store=True,
        string='SLA Responsible User')
    sla_warn_date = fields.Datetime(
        'SLA Warn date',
        compute='_compute_sla_state',
        compute_sudo=True,
        index=True,
        store=True)
    sla_limit_date = fields.Datetime(
        'SLA Limit date',
        compute='_compute_sla_state',
        compute_sudo=True,
        index=True,
        store=True)

    @api.depends('sla_control_ids', 'sla_control_ids.sla_state',
                 'sla_control_ids.sla_active',
                 'sla_control_ids.sla_rule_id.sequence',
                 'type_id.sla_compute_type',
                 'tag_ids')
    def _compute_sla_state(self):
        # TODO: need to optimise this method
        # pylint: disable=too-many-branches
        for record in self:
            if not record.sla_control_ids:
                record.update({
                    'sla_state': False,
                    'sla_warn_date': False,
                    'sla_limit_date': False,
                    'sla_user_id': False,
                })
                continue
            sla_control = False
            if record.type_id.sla_compute_type == 'main_sla_rule':
                sla_control = record.sla_control_ids.filtered(
                    lambda r: r.sla_rule_id == record.type_id.sla_main_rule_id)
            if record.type_id.sla_compute_type == 'conditional':
                sla_rule_conditions = (
                    record.type_id.sla_rule_condition_ids.sorted())
                for rule_cond in sla_rule_conditions:
                    if (not rule_cond.condition_ids
                            or rule_cond.condition_ids.check(record)):
                        sla_control = record.sla_control_ids.filtered(
                            lambda r: r.sla_rule_id == rule_cond.sla_rule_id)
                        break
                if not sla_control:
                    record.update({
                        'sla_state': False,
                        'sla_warn_date': False,
                        'sla_limit_date': False,
                        'sla_user_id': False,
                    })
                    continue

            if sla_control:
                record.update({
                    'sla_state': sla_control.sla_state,
                    'sla_warn_date': sla_control.warn_date,
                    'sla_limit_date': sla_control.limit_date,
                    'sla_user_id': sla_control.user_id,
                })
                continue

            # TODO: refactor this. Below is the computation for case when
            #       sla_compute_type is 'least_date_worst_status'
            sla_state = False
            sla_warn_date = False
            sla_limit_date = False
            for sc in record.sla_control_ids:
                # Set worst state (failed, warning, ok)
                if sc.sla_state == 'failed':
                    sla_state = 'failed'
                elif sc.sla_state == 'warning' and sla_state != 'failed':
                    sla_state = 'warning'
                elif sc.sla_state == 'ok' and sla_state not in ('failed',
                                                                'warning'):
                    sla_state = 'ok'

                if not sla_warn_date:
                    sla_warn_date = sc.warn_date
                elif sc.warn_date and sla_warn_date > sc.warn_date:
                    sla_warn_date = sc.warn_date

                if not sla_limit_date:
                    sla_limit_date = sc.limit_date
                elif sc.limit_date and sla_limit_date > sc.limit_date:
                    sla_limit_date = sc.limit_date

            record.update({
                'sla_state': sla_state,
                'sla_warn_date': sla_warn_date,
                'sla_limit_date': sla_limit_date,
                'sla_user_id': False,
            })

    def _filter_sla_rule_line(self, rule_line):
        """ Check if specified sla rule line is applicable for this request
        """
        # pylint: disable=too-many-return-statements
        # pylint: disable=too-many-branches
        if rule_line.sudo().service_level_id:
            if not self.service_level_id:
                return False
            if (self.service_level_id.id !=
                    rule_line.sudo().service_level_id.id):
                return False
        if rule_line.sudo().service_id:
            if not self.service_id:
                return False
            if self.service_id.id != rule_line.sudo().service_id.id:
                return False
        if rule_line.sudo().category_ids:
            if not self.category_id:
                return False
            if self.category_id.id not in rule_line.sudo().category_ids.ids:
                return False
        if rule_line.sudo().request_channel_ids:
            if not self.channel_id:
                return False
            if self.channel_id not in rule_line.sudo().request_channel_ids:
                return False
        if int(rule_line.sudo().priority):
            if not self.priority:
                return False
            if self.priority != rule_line.sudo().priority:
                return False
        if rule_line.sudo().tag_id:
            if not self.tag_ids:
                return False
            if rule_line.sudo().tag_id not in self.tag_ids:
                return False
        return True

    def _get_sla_rule_line(self, rule):
        """ Get SLA Rule line to be applied to this request.

            :param rule: single record of 'request.sla.rule'
            :return: single record of 'request.sla.rule.line'
        """
        for rule_line in rule.rule_line_ids:
            if self._filter_sla_rule_line(rule_line):
                return rule_line
        return False

    def _prepare_sla_control_line(self, rule):
        warn_time, limit_time = rule.warn_time, rule.limit_time
        if rule.sudo().sla_calendar_id:
            calendar_id = rule.sudo().sla_calendar_id.id
        else:
            calendar_id = rule.request_type_id.sudo().sla_calendar_id.id
        return {
            'sla_rule_id': rule.id,
            'warn_time': warn_time,
            'limit_time': limit_time,
            'assigned': rule.assigned,
            'compute_time': rule.compute_time,
            'calendar_id': calendar_id,
            'kanban_state_normal': rule.kanban_state_normal,
            'kanban_state_blocked': rule.kanban_state_blocked,
            'kanban_state_done': rule.kanban_state_done,
        }

    def _set_request_sla_control_lines(self):
        """ Add SLA control lines to this request
        """
        sla_control_data = []

        # Create sla control lines for request
        for rule in self.type_id.sla_rule_ids:
            line_data = self._prepare_sla_control_line(rule)
            sla_control_data.append((0, 0, line_data))

        self.write({
            'sla_control_ids': sla_control_data,
        })
        return True

    @post_write('category_id', 'channel_id', 'service_id',
                'service_level_id', 'priority', 'tag_ids', priority=8)
    def _update_request_sla_control_lines(self, changes):
        """ Update warn and limit times for SLA Control Lines of this request
        """
        for control_line in self.sla_control_ids:
            rule = control_line.sla_rule_id
            rline = self._get_sla_rule_line(rule)
            if rline and rline.sla_calendar_id:
                calendar = rline.sla_calendar_id
            elif rule.sla_calendar_id:
                calendar = rule.sla_calendar_id
            else:
                calendar = control_line.request_type_id.sla_calendar_id
            data = {'calendar_id': calendar.id}
            if rline:
                data.update({
                    'warn_time': rline.warn_time,
                    'limit_time': rline.limit_time,
                    'compute_time': rline.compute_time,
                })
            else:
                data.update({
                    'warn_time': rule.warn_time,
                    'limit_time': rule.limit_time,
                    'compute_time': rule.compute_time,
                })
            control_line.write(data)
            control_line._sla_update_state()

    @post_write('stage_id', 'user_id', 'kanban_state', priority=8)
    def _post_write_trigger_sla_rule_active(self, changes):
        """ Activate or deactivate SLA control lines when
            one of fields that represent request state changed
        """
        self.sla_control_ids._trigger_active()

    @on_event('sla_warning')
    def _send_default_notification_sla_warning(self, event):
        """ Send default notification for SLA warning.

            Send only if it is main SLA rule and it has responsible user
        """
        if not self.sudo().type_id.send_default_notification_sla_warn:
            return
        if event.sla_rule_id != self.type_id.sla_main_rule_id:
            return
        if event.sla_control_line_id.assigned not in ('yes', 'none'):
            return
        if not event.sla_control_line_id.user_id:
            return

        self._send_default_notification__send(
            'generic_request_sla.message_request_sla_warning',
            event.sudo().sla_control_line_id.sudo().user_id.partner_id,
            event,
            lazy_subject=lambda self: _(
                "Warning! Your request %s reached SLA Warning date!"
            ) % self.name,
        )

    @on_event('sla_failed')
    def _send_default_notification_sla_failed(self, event):
        """ Send default notification for SLA limit.

            Send only if it is main SLA rule and it has responsiible user
        """
        if not self.sudo().type_id.send_default_notification_sla_limit:
            return
        if event.sla_rule_id != self.type_id.sla_main_rule_id:
            return
        if event.sla_control_line_id.assigned not in ('yes', 'none'):
            return
        if not event.sla_control_line_id.user_id:
            return

        self._send_default_notification__send(
            'generic_request_sla.message_request_sla_failed',
            event.sudo().sla_control_line_id.user_id.partner_id,
            event,
            lazy_subject=lambda self: _(
                "Warning! Your request %s reached SLA Limit date!"
            ) % self.name,
        )

    @api.model_create_multi
    def create(self, vals):
        requests = super().create(vals)
        for request in requests:
            request._set_request_sla_control_lines()
            request._update_request_sla_control_lines({})
        requests.mapped('sla_control_ids')._trigger_active()
        return requests

    def get_sla_control_by_code(self, code):
        """ This method could be used to obtain instance of SLA Control
            by provided code of SLA Rule Type

            This method could be used in email templates if user needs to get
            some SLA info for specific control line (rule)

            :param str code: Code of sla rule type
        """
        self.ensure_one()
        return self.sla_control_ids.filtered(
            lambda r: r.sla_rule_code == code)
