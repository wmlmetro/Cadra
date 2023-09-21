import logging
from datetime import datetime as dtime, date
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, exceptions, _
from odoo.osv import expression
from odoo.tools.safe_eval import wrap_module

from odoo.addons.generic_request.tools.jinja import render_jinja_string
from odoo.addons.generic_request.models.request_request import (
    AVAILABLE_PRIORITIES, AVAILABLE_IMPACTS, AVAILABLE_URGENCIES)

_logger = logging.getLogger(__name__)

DEFAULT_ARCH_BASE = (
    "<?xml version='1.0'?>"
    "\n<t name='' t-name=''>"
    "\n\t<t t-esc='request.request_text'/>"
    "\n\t"
    "\n\t<!-- Variables available: -->"
    "\n\t<!-- <t t-esc='user.name'/> -->"
    "\n\t<!-- <t t-esc='request.name'/> -->"
    "\n\t<!-- <t t-esc='env'/> -->"
    "\n\t<!-- <t t-esc='time'/> -->"
    "\n\t<!-- <t t-esc='datetime'/> -->"
    "\n</t>")


class RequestEventAction(models.Model):
    _name = "request.event.action"
    _inherit = [
        'mail.thread',
    ]
    _description = "Request Event Action"
    _order = 'sequence ASC, name ASC, id ASC'

    def _default_unsubscribe(self):
        return (
            self.env.user.company_id.request_autoset_unsubscribe_prev_assignee)

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(
        index=True, default=5, required=True, tracking=True,
        help="this field is used to determine order, "
             "in which actions will be executed. "
             "Actions with lower value in this field will be called first.")
    active = fields.Boolean(
        index=True, default=True, tracking=True)

    event_type_ids = fields.Many2many(
        comodel_name='generic.system.event.type',
        relation='request_event_action__event_type__rel',
        column1='event_action_id',
        column2='event_type_id',
        string='Events', required=True, index=True,
        help="This action will be called to handle selected events.")
    request_type_id = fields.Many2one(
        'request.type', required=False, index=True,
        ondelete='cascade', auto_join=True, tracking=True)
    route_id = fields.Many2one(
        'request.stage.route', 'Route', required=False, index=True,
        ondelete='cascade', auto_join=True, tracking=True,
        help="Used in case of 'stage-move', 'closed', or 'reopened' events. "
             "If set, then this action will be called only when request moved "
             "by this route. If no route selected, then action will be called "
             "when request moved by any route")

    condition_ids = fields.Many2many(
        'generic.condition', string='Request Conditions',
        help="List here conditions that request should satisfy "
             "to run this action")
    event_condition_ids = fields.Many2many(
        'generic.condition',
        'request_event_action__event_condition__rel',
        'action_id', 'event_condition_id',
        string='Event Conditions')

    # Helper field to be able to use ID of request.request model in views
    helper_request_model_id = fields.Many2one(
        'ir.model', readonly=True, store=False,
        default=lambda self: self.env.ref(
            'generic_request.model_request_request'),
        string='Helper: ID of request model',
        compute_sudo=True, compute='_compute_helper_request_model_id')

    act_type = fields.Selection(
        [('server_action', 'Server Action'),
         ('assign', 'Assign'),
         ('subscribe', 'Subscribe'),
         ('mail_activity', 'Schedule activity'),
         ('send_email', 'Send Email'),
         ('kanban_state', 'Change Kanban state'),
         ('validate', 'Validate Request'),
         ('change_deadline', 'Change Deadline date'),
         ('set_priority', 'Set priority'),
         ('tag', 'Tag'),
         ('subrequest', 'Subrequest')],
        'Type', required=True, index=True, default='server_action',
        tracking=True)
    act_sudo = fields.Boolean(
        'Sudo action', help="Run this action as superuser",
        tracking=True)
    act_sudo_user_id = fields.Many2one(
        'res.users', 'Sudo user', help='Run this action as user',
        tracking=True)

    # Server action
    action_id = fields.Many2one(
        'ir.actions.server', 'Server Action', ondelete='restrict',
        required=False, domain=[('model_name', '=', 'request.request')],
        help="Bind server action to run when this route is used.\n"
             "Following extra variables will be available in context:\n"
             "- request: instance of request been moved\n"
             "- request_route: instance of route that is used to move request",
        tracking=True)

    # Send Email
    send_email_template_id = fields.Many2one(
        'mail.template', 'Email Template', ondelete='restrict',
        domain="[('model_id.model', '=', 'request.request')]",
    )
    send_response_attachments = fields.Boolean(
        'Send response attachments',
        default=False,
        help="Send response attachments, used when request was closed")

    # Action assign
    assign_type = fields.Selection(
        [('user', 'User')], default='user', tracking=True)
    assign_user_id = fields.Many2one(
        'res.users', 'Assign to', tracking=True)
    unsubscribe_prev_assignee = fields.Boolean(
        default=_default_unsubscribe,
        string='Unsubscribe previous assignee')

    # Action subscribe
    subscribe_partner_ids = fields.Many2many(
        'res.partner',
        'request_route_action_subscribe_partner_rel',
        'action_id', 'partner_id', 'Subscribe partners')

    # Action mail
    mail_activity_activity_type_id = fields.Many2one(
        'mail.activity.type', 'Activity Type')
    mail_activity_date_delta_uom = fields.Selection([
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months')
    ], default='days', string='Deadline UoM')
    mail_activity_date_delta_value = fields.Integer(
        'Deadline', default=1)
    mail_activity_assign_type = fields.Selection(
        [('user', 'User'), ('field', 'Field')], default='user',
        string="Activity Assign Type")
    mail_activity_user_id = fields.Many2one('res.users', 'Assigned to')
    mail_activity_user_field_id = fields.Many2one(
        'ir.model.fields',
        domain=[
            ('model', '=', 'request.request'),
            ('relation', '=', 'res.users')],
        string='Assigned to (Field)',
        help='Select field to get assignee for activity')
    mail_activity_summary = fields.Char(
        'Summary', help="You can use jinja2 placeholders in this field"
    )
    mail_activity_note = fields.Html(
        'Note', help="You can use jinja2 placeholders in this field"
    )

    # Action kanban state
    kanban_state = fields.Selection(
        selection="_get_selection_kanban_state",
        string='State',
        default='normal')

    # Action Validate
    validate_condition_ids = fields.Many2many(
        comodel_name='generic.condition',
        relation='generic_request_action_validate_conditions_rel',
        column1='action_id',
        column2='condition_id',
        string='Validate request with conditions',
        help="Request is valid if all conditions listed here were "
             "evaluated to True.")
    validate_event_condition_ids = fields.Many2many(
        comodel_name='generic.condition',
        relation='generic_request_action_validate_event_conditions_rel',
        column1='action_id',
        column2='condition_id',
        string='Validate event with conditions',
        help="Event data is valid if all conditions listed here were "
             "evaluated to True.")
    validate_error_msg = fields.Text(
        string='Validation error message')

    # Action Change the deadline date
    change_deadline_type = fields.Selection(
        selection=[
            ('calendar_days', 'Calendar Days'),
            ('working_days', 'Working Days')], default='calendar_days')
    change_deadline_from = fields.Selection(
        selection=[
            ('now', 'Current date'),
            ('field', 'Field')],
        string='From Date', default='now', tracking=True)
    change_deadline_from_field_date = fields.Many2one(
        'ir.model.fields',
        string='From Field',
        domain=[('ttype', 'in', ('date', 'datetime'))],
        ondelete='cascade', tracking=True)
    change_deadline_calendar_id = fields.Many2one(
        'resource.calendar')
    change_deadline_value = fields.Integer(
        help='Increase the deadline date by the number of days')

    # Priority action configuration
    act_priority_type = fields.Selection([
        ('set', 'Set Priority'),
        ('increase', 'Increase Priority'),
        ('decrease', 'Decrease Priority')])
    act_priority_priority = fields.Selection(
        selection=AVAILABLE_PRIORITIES,
    )
    act_priority_impact = fields.Selection(selection=AVAILABLE_IMPACTS)
    act_priority_urgency = fields.Selection(selection=AVAILABLE_URGENCIES)
    act_priority_priority_modifier = fields.Integer(default=1)
    act_priority_impact_modifier = fields.Integer(default=1)
    act_priority_urgency_modifier = fields.Integer(default=1)
    act_priority_is_priority_complex = fields.Boolean(
        related='request_type_id.complex_priority', readonly=True)

    # Tags action configuration
    tag_add_tag_ids = fields.Many2many(
        'generic.tag',
        'request_event_action_generic_tag_add_tag_ids_rel',
        'action_id', 'tag_id',
        domain=[('model_id.model', '=', 'request.request')])
    tag_remove_tag_ids = fields.Many2many(
        'generic.tag',
        'request_event_action_generic_tag_remove_tag_ids_rel',
        'action_id', 'tag_id',
        domain=[('model_id.model', '=', 'request.request')])

    # Subrequest info
    subrequest_template_id = fields.Many2one(
        'request.creation.template', ondelete='restrict',
        tracking=True)
    subrequest_type_id = fields.Many2one(
        related='subrequest_template_id.request_type_id',
        string='Subrequest type', store=False, readonly=True)
    subrequest_category_id = fields.Many2one(
        related='subrequest_template_id.request_category_id',
        string='Subrequest Category', store=False, readonly=True)
    subrequest_start_stage_id = fields.Many2one(
        related='subrequest_template_id.request_type_id.start_stage_id',
        string='Subrequest stage', store=False, readonly=True)
    subrequest_subscribe_partner_ids = fields.Many2many(
        'res.partner',
        'request_route_action_subrequest_subscribe_partner_rel',
        'action_id', 'partner_id', 'Subrequest subscribe partners')
    subrequest_trigger_route_id = fields.Many2one(
        'request.stage.route', 'Subrequest trigger route',
        ondelete='restrict', tracking=True)
    subrequest_text = fields.Html(
        help="You can use jinja2 placeholders in this field"
    )
    subrequest_text_template_id = fields.Many2one(
        'ir.ui.view', ondelete='restrict', domain=[('type', '=', 'qweb')],
        context={
            'default_type': 'qweb',
            'default_arch_base': DEFAULT_ARCH_BASE},
        tracking=True)
    subrequest_same_author = fields.Boolean()
    subrequest_same_deadline = fields.Boolean()
    subrequest_transfer_field_ids = fields.Many2many(
        comodel_name='ir.model.fields',
        relation='request_act_subrequest_transfer_fields_rel',
        column1='action_id',
        column2='field_id',
        domain=expression.AND([
            [('model', '=', 'request.request')],
            [('ttype', '!=', 'one2many')],
            [('related', '=', False)],
            [('compute', '=', False)],
            expression.OR([
                [('store', '=', True)],
                [('store', '=', False), ('copied', '=', True)],
            ]),
        ]),
        help='List of fields to transfer to subrequesst from parent request.')

    @api.constrains('event_type_ids')
    def check_event_type_ids(self):
        for record in self:
            if not record.event_type_ids:
                raise exceptions.ValidationError(_(
                    "Event types are required!"))

    @api.constrains('request_type_id', 'route_id')
    def check_request_type_and_route(self):
        for record in self:
            if not record.route_id:
                continue
            if record.route_id.request_type_id != record.request_type_id:
                raise exceptions.ValidationError(_(
                    "Wrong combination of route and request type!"))

    @api.constrains('action_id')
    def check_server_action(self):
        for record in self:
            if not record.action_id:
                continue
            if record.action_id.model_id.model != 'request.request':
                raise exceptions.ValidationError(_(
                    "Cannot use server action that is not "
                    "bound to 'request.request' model!"))

    @api.constrains('send_email_template_id')
    def check_send_email_template_id(self):
        for record in self:
            if not record.send_email_template_id:
                continue
            template_model = record.send_email_template_id.model_id.model
            if template_model != 'request.request':
                raise exceptions.ValidationError(_(
                    "Cannot use server action that is not "
                    "bound to 'request.request' model!"))

    @api.constrains('change_deadline_value')
    def check_server_action_change_deadline(self):
        for record in self:
            if (record.act_type == 'change_deadline'
                    and record.change_deadline_value == 0):
                raise exceptions.ValidationError(_(
                    "Cannot use server action in which the value of the"
                    " field 'Change Deadline Value' is '0'!'"))

    @api.constrains('validate_condition_ids', 'validate_event_condition_ids',
                    'validate_error_msg')
    def _check_action_validate_configuraion(self):
        for record in self:
            if record.act_type != 'validate':
                continue
            if not (record.validate_condition_ids or
                    record.validate_event_condition_ids):
                raise exceptions.ValidationError(_(
                    "Validate Request action misconfigured! It is required to "
                    "specify 'Validate with request conditions' or "
                    "'Validate with event conditions fields'!"))

    @api.depends()
    def _compute_helper_request_model_id(self):
        model = self.env.ref('generic_request.model_request_request')
        for record in self:
            record.helper_request_model_id = model

    @api.model
    def _add_missing_default_values(self, values):
        res = super(RequestEventAction, self)._add_missing_default_values(
            values)

        # guess request type based on route, for backward compatability
        if res.get('route_id') and not res.get('request_type_id'):
            raise exceptions.ValidationError(_(
                "Creating action with only route_id is not allowed anymore. "
                "Now it is required to specify request_type_id and "
                "event_type_ids for action."
            ))

        return res

    def _run_assign_dispatch(self, request, event):
        if self.assign_type == 'user':
            request.write({'user_id': self.assign_user_id.id})

    def _run_assign(self, request, event):
        prev_assignee = request.user_id
        self._run_assign_dispatch(request, event)

        new_assignee = request.user_id
        if (self.unsubscribe_prev_assignee and prev_assignee
                and new_assignee != prev_assignee):
            request._close_mail_activities_for_user(prev_assignee)
            request.message_unsubscribe(
                partner_ids=prev_assignee.partner_id.ids)

    def _run_subscribe_get_partner_ids(self, request):
        return self.subscribe_partner_ids.mapped('id')

    def _run_subscribe(self, request, event):
        request.message_subscribe(
            partner_ids=self._run_subscribe_get_partner_ids(request))

    def _run_server_action(self, request, event):
        self.action_id.with_context(
            active_id=request.id,
            active_ids=[request.id],
            active_model='request.request',
            event=event).run()

    def _run_mail_activity_calculate_due_date(self, request):
        uom = self.mail_activity_date_delta_uom
        value = self.mail_activity_date_delta_value
        return dtime.now() + relativedelta(**{uom: value})

    def _get_selection_kanban_state(self):
        return self.env['request.request']._fields['kanban_state'].selection

    def _run_kanban_state(self, request):
        request.write({'kanban_state': self.kanban_state})

    def _get_mail_activity_user_id(self, request):
        if self.mail_activity_assign_type == 'user':
            return self.mail_activity_user_id.id
        if self.mail_activity_assign_type == 'field':
            field = self.mail_activity_user_field_id.name
            return request[field] and request[field].id
        return False

    def _run_mail_activity_prepare_data(self, request, event, user_id):
        due_date = self._run_mail_activity_calculate_due_date(request)
        return {
            'res_id': request.id,
            'res_model_id': self.env.ref(
                'generic_request.model_request_request').id,
            'activity_type_id': self.mail_activity_activity_type_id.id,
            'date_deadline': due_date,
            'user_id': user_id,
            'summary': render_jinja_string(
                self.mail_activity_summary,
                dict(self.env.context,
                     request=request,
                     object=request,
                     event=event)),
            'note': render_jinja_string(
                self.mail_activity_note,
                dict(self.env.context,
                     request=request,
                     object=request,
                     event=event)),
            'automated': True,
        }

    def _run_mail_activity(self, request, event):
        user_id = self._get_mail_activity_user_id(request)
        if user_id:
            request.message_subscribe(
                partner_ids=self.env['res.users'].browse(
                    user_id).partner_id.ids)
            self.env['mail.activity'].create(
                self._run_mail_activity_prepare_data(request, event, user_id))

    def _run_send_email(self, request, event):
        # If checkbox 'Send response attachments' activated,
        # pass response attachments with email attachments through
        # 'email_values'
        email_values = None
        if self.send_response_attachments and request.response_attachment_ids:
            resp_att_ids = request.response_attachment_ids.ids
            tmpl_att_ids = self.send_email_template_id.attachment_ids.ids
            email_values = {
                'attachment_ids': resp_att_ids + tmpl_att_ids,
            }

        self.sudo().send_email_template_id.send_mail(
            request.id, force_send=False, raise_exception=False,
            email_values=email_values)

    def _run_validate_request(self, request, event):
        if not self.validate_condition_ids.check(request):
            raise exceptions.ValidationError(self.validate_error_msg)
        if not self.validate_event_condition_ids.check(event):
            raise exceptions.ValidationError(self.validate_error_msg)

    def _run_change_deadline_date(self, request, event):
        if self.change_deadline_from == 'now':
            datetime_from = fields.Datetime.now()
        if self.change_deadline_from == 'field':
            datetime_from = getattr(
                request,
                self.change_deadline_from_field_date.name
            )
            if not datetime_from:
                datetime_from = fields.Datetime.now()

            # If the specified field is a Date class, then it must be
            # converted to a Datetime class for the plan_days() method
            # to work correctly.
            # Moreover, if the value of change_deadline_value is greater
            # than zero, then you need to specify max.time so that
            # that calculation starts from the next day.
            # If it is less than zero, specify min.time so that
            # te calculation starts from the previous day.
            if isinstance(datetime_from, date):
                if self.change_deadline_value > 0:
                    datetime_from = dtime.combine(
                        datetime_from, dtime.max.time())
                else:
                    datetime_from = dtime.combine(
                        datetime_from, dtime.min.time())
        else:
            raise exceptions.UserError(_(
                "Misconfigured automated action %(action)s! "
                "change_deadline_from cannot be %(value)s"
            ) % {
                'action': self.display_name,
                'value': self.change_deadline_from,
            })

        if self.change_deadline_type == 'calendar_days':
            deadline_datetime = datetime_from + relativedelta(
                days=self.change_deadline_value)
        elif self.change_deadline_type == 'working_days':
            deadline_datetime = self.change_deadline_calendar_id.plan_days(
                days=self.change_deadline_value,
                day_dt=datetime_from)
        else:
            raise exceptions.UserError(_(
                "Misconfigured automated action %(action)s! "
                "change_deadline_type cannot be %(value)s"
            ) % {
                'action': self.display_name,
                'value': self.change_deadline_type,
            })

        # Currently, this action is designed to work with days, not hours,
        # thus, we convert resulted deadline datetime value to date
        # and write it to deadline 'date' field.
        # TODO: May be it have sense to write to
        #       deadline_date_dt field instead?
        request.deadline_date = fields.Date.to_date(deadline_datetime)

    def _run_priority_set_priority(self, request, event):
        if request.is_priority_complex:
            request.impact = self.act_priority_impact
            request.urgency = self.act_priority_urgency
        else:
            request.priority = self.act_priority_priority

    def _run_priority_increase_priority(self, request, event):
        if request.is_priority_complex:
            new_impact = (
                int(request.impact) +
                self.act_priority_impact_modifier)
            request.impact = str(max(0, min(new_impact, 3)))
            new_urgency = (
                int(request.urgency) +
                self.act_priority_urgency_modifier)
            request.urgency = str(max(0, min(new_urgency, 3)))
        else:
            new_priority = (
                int(request.priority) +
                self.act_priority_priority_modifier)
            request.priority = str(max(0, min(new_priority, 5)))

    def _run_priority_decrease_priority(self, request, event):
        if request.is_priority_complex:
            new_impact = (
                int(request.impact) -
                self.act_priority_impact_modifier)
            request.impact = str(min(3, max(new_impact, 0)))
            new_urgency = (
                int(request.urgency) -
                self.act_priority_urgency_modifier)
            request.urgency = str(min(3, max(new_urgency, 0)))
        else:
            new_priority = (
                int(request.priority) -
                self.act_priority_priority_modifier)
            request.priority = str(min(5, max(new_priority, 0)))

    def _run_priority(self, request, event):
        if self.act_priority_type == 'set':
            return self._run_priority_set_priority(request, event)
        if self.act_priority_type == 'increase':
            return self._run_priority_increase_priority(request, event)
        if self.act_priority_type == 'decrease':
            return self._run_priority_decrease_priority(request, event)
        return False

    def _run_tag(self, request, event):
        request.tag_ids -= self.tag_remove_tag_ids
        request.tag_ids += self.tag_add_tag_ids

    def _run_subrequest_prepare_transfer_fields(self, request, event):
        """ Prepare values for fields that have to be transfered from parent
            request to child request
        """
        res = {}
        Request = self.env['request.request']
        for field in self.sudo().subrequest_transfer_field_ids:
            res[field.name] = Request._fields[field.name].convert_to_write(
                request[field.name], request)

        return res

    def _run_subrequest_prepare_data(self, request, event):
        """ Prepare data for subrequest
        """
        res = {
            'parent_id': request.id,
        }

        # Apply template for request_text for subrequest
        if self.subrequest_text_template_id:
            # Evaluation context for Qweb template
            # Wrap modules in context with `wrap_module`
            # TODO: Add tests for this code block, review, may be simplify
            _datetime = wrap_module(
                __import__('datetime'),
                ['date', 'datetime', 'time', 'timedelta', 'timezone',
                 'tzinfo', 'MAXYEAR', 'MINYEAR'])
            _time = wrap_module(
                __import__('time'),
                ['time', 'strptime', 'strftime', 'localtime'])

            val = {
                'user': self.env.user,
                'env': self.env,
                'request': request,
                'time': _time,
                'datetime': _datetime,
            }
            res['request_text'] = self.subrequest_text_template_id._render(val)
        else:
            res['request_text'] = render_jinja_string(
                self.subrequest_text,
                dict(self.env.context,
                     request=request,
                     object=request,
                     event=event),
            )

        # Update author of subrequest if required
        if self.subrequest_same_author:
            res['author_id'] = request.author_id.id

        # Update deadline of subrequest
        if self.subrequest_same_deadline:
            res['deadline_date'] = request.deadline_date

        if self.sudo().subrequest_transfer_field_ids:
            res.update(
                self._run_subrequest_prepare_transfer_fields(request, event)
            )

        return res

    def _run_subrequest_create_subrequest(self, request, event):
        return self.subrequest_template_id.do_create_request(
            self._run_subrequest_prepare_data(request, event))

    def _run_subrequest_postprocess_subrequest(self, request, event,
                                               subrequest):
        subrequest.message_subscribe(
            partner_ids=self.subrequest_subscribe_partner_ids.mapped('id'))

        if self.subrequest_trigger_route_id:
            trigger_route = self.subrequest_trigger_route_id
            if subrequest.stage_id == trigger_route.stage_from_id:
                # Ensure, request was not moved to other stage yet
                subrequest.write({
                    'stage_id': trigger_route.stage_to_id.id,
                })

    def _run_subrequest(self, request, event):
        subrequest = self._run_subrequest_create_subrequest(request, event)
        self._run_subrequest_postprocess_subrequest(
            request, event, subrequest)

    def _dispatch(self, request, event):
        """ Dispatch action and run corresponding method
        """
        # pylint: disable=too-many-return-statements
        if self.act_type == 'server_action' and self.action_id:
            return self._run_server_action(request, event)
        if self.act_type == 'assign':
            return self._run_assign(request, event)
        if self.act_type == 'subscribe':
            return self._run_subscribe(request, event)
        if self.act_type == 'mail_activity':
            return self._run_mail_activity(request, event)
        if self.act_type == 'send_email':
            return self._run_send_email(request, event)
        if self.act_type == 'kanban_state':
            return self._run_kanban_state(request)
        if self.act_type == 'validate':
            return self._run_validate_request(request, event)
        if self.act_type == 'change_deadline':
            return self._run_change_deadline_date(request, event)
        if self.act_type == 'set_priority':
            return self._run_priority(request, event)
        if self.act_type == 'tag':
            return self._run_tag(request, event)
        if self.act_type == 'subrequest' and self.subrequest_template_id:
            return self._run_subrequest(request, event)
        return False

    def _ensure_can_run(self, request, event):
        """ Hook to check if action could be ran

            return: True if action can be ran or False if not
        """
        self.ensure_one()
        if self.condition_ids and not self.condition_ids.check(request):
            return False
        if self.event_condition_ids and not self.event_condition_ids.check(
                event):
            return False
        return True

    def _run(self, request, event):
        if self._ensure_can_run(request, event):
            return self._dispatch(request, event)
        return False

    def run(self, request, event):
        for action in self.with_context(mail_notify_force_send=False):
            if action.act_sudo and not action.act_sudo_user_id:
                # Run action as superuser
                action.sudo()._run(request.sudo(), event.sudo())
            elif action.act_sudo and action.act_sudo_user_id:
                # Run action as specific user
                action.with_user(action.act_sudo_user_id)._run(
                    request.with_user(action.act_sudo_user_id),
                    event.with_user(action.act_sudo_user_id),
                )
            else:
                # Run action as current user
                action._run(request, event)
