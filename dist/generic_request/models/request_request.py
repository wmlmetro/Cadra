# pylint:disable=too-many-lines
import json
import logging

from operator import itemgetter
from inspect import getmembers

from datetime import datetime, time
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, tools, _, http, exceptions, SUPERUSER_ID
from odoo.addons.generic_mixin import (
    pre_write, post_write, pre_create, post_create)
from odoo.osv import expression
from odoo.exceptions import ValidationError
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m
from odoo.addons.generic_mixin.tools.sql import create_sql_view
from odoo.addons.generic_system_event import on_event
from ..tools.utils import html2text
from ..constants import (
    TRACK_FIELD_CHANGES,
    REQUEST_TEXT_SAMPLE_MAX_LINES,
    KANBAN_READONLY_FIELDS,
    MAIL_REQUEST_TEXT_TMPL,
    AVAILABLE_PRIORITIES,
    AVAILABLE_IMPACTS,
    AVAILABLE_URGENCIES,
    PRIORITY_MAP,
)
_logger = logging.getLogger(__name__)

KANBAN_READONLY_FIELDS.update(['service_id', 'service_level_id'])
TRACK_FIELD_CHANGES.update(['parent_id', 'service_id', 'service_level_id'])

DEFAULT_SERVICE_LEVEL_GUESSER_PRIORITY = 100


def service_level_guesser(priority=None):
    """ Mark method, to be used to guess service level for request

        Note, that this decorator is not propagated, thus, when
        you need to override the method decorated with this decorator,
        you have to apply this decorator to redefined method too.

        :param int priority: used to order guesser.
            Method with the lowest priority will be called first.
    """
    if priority is not None and not isinstance(priority, int):
        raise AssertionError("priority must be int")

    def decorator(fn):
        fn.__service_level_guesser__ = True
        fn.__service_level_guesser_priority__ = (
            priority
            if priority is not None
            else DEFAULT_SERVICE_LEVEL_GUESSER_PRIORITY)
        return fn
    return decorator


class RequestRequest(models.Model):
    _name = "request.request"
    _inherit = [
        'generic.system.event.source.mixin',
        'mail.thread',
        'mail.activity.mixin',
        'generic.tag.mixin',
        'generic.mixin.get.action',
    ]
    _description = 'Request'
    _order = 'priority DESC, date_created DESC'
    _needaction = True
    _parent_store = True
    _parent_order = 'name'

    name = fields.Char(
        required=True, index=True, readonly=True, default="New", copy=False)
    help_html = fields.Html(
        "Help", related="type_id.help_html", readonly=True)
    category_help_html = fields.Html(
        related='category_id.help_html', readonly=True, string="Category help")
    stage_help_html = fields.Html(
        "Stage help", related="stage_id.help_html", readonly=True)
    instruction_html = fields.Html(
        related='type_id.instruction_html',
        readonly=True, string='Instruction')
    note_html = fields.Html(
        related='type_id.note_html', readonly=True, string="Note")
    active = fields.Boolean(default=True, index=True)

    # Priority
    _priority = fields.Char(
        default='3', readonly=True,
        string='Priority (Technical)')
    priority = fields.Selection(
        selection=AVAILABLE_PRIORITIES,
        tracking=True,
        index=True,
        store=True,
        compute='_compute_priority',
        inverse='_inverse_priority',
        help="Actual priority of request"
    )
    impact = fields.Selection(
        selection=AVAILABLE_IMPACTS,
        index=True
    )
    urgency = fields.Selection(
        selection=AVAILABLE_URGENCIES,
        index=True
    )
    is_priority_complex = fields.Boolean(
        related='type_id.complex_priority', readonly=True)

    # Type and stage related fields
    type_id = fields.Many2one(
        'request.type', 'Type', ondelete='restrict',
        required=True, index=True, tracking=True,
        help="Type of request")
    type_id_domain = fields.Char(
        compute='_compute_service_category_type_domains'
    )
    type_color = fields.Char(related="type_id.color", readonly=True)
    kind_id = fields.Many2one(
        'request.kind', related='type_id.kind_id',
        store=True, index=True, readonly=True,
        help="Kind of request")
    category_id = fields.Many2one(
        'request.category', 'Category', index=True,
        required=False, ondelete="restrict", tracking=True,
        help="Category of request")
    category_id_domain = fields.Char(
        compute='_compute_service_category_type_domains'
    )
    channel_id = fields.Many2one(
        'request.channel', 'Channel', index=True, required=False,
        help="Channel of request")
    stage_id = fields.Many2one(
        'request.stage', 'Stage', ondelete='restrict',
        required=True, index=True, tracking=True, copy=False)
    stage_type_id = fields.Many2one(
        'request.stage.type', related="stage_id.type_id", string="Stage Type",
        index=True, readonly=True, store=True)
    stage_bg_color = fields.Char(
        compute="_compute_stage_colors", string="Stage Background Color")
    stage_label_color = fields.Char(
        compute="_compute_stage_colors")
    last_route_id = fields.Many2one('request.stage.route', 'Last Route')
    closed = fields.Boolean(
        related='stage_id.closed', store=True, index=True, readonly=True)
    can_be_closed = fields.Boolean(
        compute='_compute_can_be_closed', readonly=True)
    is_assigned = fields.Boolean(
        compute="_compute_is_assigned", store=True, readonly=True)

    kanban_state = fields.Selection(
        selection=[
            ('normal', 'In Progress'),
            ('blocked', 'Blocked'),
            ('done', 'Ready for next stage')],
        required=True,
        default='normal',
        tracking=True,
        help="A requests kanban state indicates special"
             " situations affecting it:\n"
             " * Grey is the default situation\n"
             " * Red indicates something is preventing the"
             "progress of this request\n"
             " * Green indicates the request is ready to be pulled"
             "to the next stage")

    # 12.0 compatability. required to generate xmlid for this field
    tag_ids = fields.Many2many()

    # Is this request new (does not have ID yet)?
    # This field could be used in domains in views for True and False leafs:
    # [1, '=', 1] -> True,
    # [0, '=', 1] -> False
    is_new_request = fields.Integer(
        compute='_compute_is_new_request', readonly=True, default=1)

    # UI change restriction fields
    can_change_request_text = fields.Boolean(
        compute='_compute_can_change_request_text', readonly=True,
        compute_sudo=False)
    can_change_assignee = fields.Boolean(
        compute='_compute_can_change_assignee', readonly=True,
        compute_sudo=False)
    can_change_author = fields.Boolean(
        compute='_compute_can_change_author', readonly=True,
        compute_sudo=False)
    can_change_category = fields.Boolean(
        compute='_compute_can_change_category', readonly=True,
        compute_sudo=False)
    can_change_deadline = fields.Boolean(
        compute='_compute_can_change_deadline', readonly=True,
        compute_sudo=False)

    # Request data fields
    request_text = fields.Html(required=True)
    internal_note_text = fields.Html(
        help="Add here internal notes related to this request. "
             "This field is not visible on website.")
    response_text = fields.Html(required=False)
    response_attachment_ids = fields.Many2many(
        'ir.attachment',
        'request_response_attachment_rel',
        'request_id',
        'response_attachment_id',
        'Response Attachments', copy=False)
    request_text_sample = fields.Text(
        compute="_compute_request_text_sample",
        string='Request text', store=True)

    deadline_date = fields.Date(
        string='Deadline',
        compute='_compute_deadline_date',
        inverse='_inverse_deadline_date',
        store=True, index=True,
        tracking=True)
    deadline_date_dt = fields.Datetime(
        string='Deadline (datetime)',
        store=True, index=True,
        tracking=True)
    deadline_format = fields.Selection(related='type_id.deadline_format')
    deadline_state = fields.Selection(selection=[
        ('ok', 'Ok'),
        ('today', 'Today'),
        ('overdue', 'Overdue')], compute='_compute_deadline_state')

    # Keep info about events related to deadline,
    # to avoid sending same event multiple times
    deadline_event_tomorrow_sent = fields.Boolean(readonly=True, default=False)
    deadline_event_today_sent = fields.Boolean(readonly=True, default=False)
    deadline_event_overdue_sent = fields.Boolean(readonly=True, default=False)

    date_created = fields.Datetime(
        'Created', default=fields.Datetime.now, readonly=True, copy=False)
    date_closed = fields.Datetime('Closed', readonly=True, copy=False)
    date_assigned = fields.Datetime('Assigned', readonly=True, copy=False)
    date_moved = fields.Datetime('Moved', readonly=True, copy=False)
    created_by_id = fields.Many2one(
        'res.users', 'Created by', readonly=True, ondelete='restrict',
        default=lambda self: self.env.user, index=True,
        help="Request was created by this user", copy=False)
    moved_by_id = fields.Many2one(
        'res.users', 'Moved by', readonly=True, ondelete='restrict',
        copy=False)
    closed_by_id = fields.Many2one(
        'res.users', 'Closed by', readonly=True, ondelete='restrict',
        copy=False, help="Request was closed by this user")
    partner_id = fields.Many2one(
        'res.partner', 'Partner', index=True, tracking=True,
        ondelete='restrict', help="Partner related to this request")
    author_id = fields.Many2one(
        'res.partner', 'Author', index=True, required=False,
        ondelete='restrict', tracking=True,
        domain=[('is_company', '=', False)],
        default=lambda self: self.env.user.partner_id,
        help="Author of this request")
    user_id = fields.Many2one(
        'res.users', 'Assigned to',
        ondelete='restrict', tracking=True, index=True,
        help="User responsible for next action on this request.")
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.user.company_id)

    # Email support
    email_from = fields.Char(
        'Email', help="Email address of the contact", index=True,
        readonly=True)
    email_cc = fields.Text(
        'Global CC', readonly=True,
        help="These email addresses will be added to the CC field "
             "of all inbound and outbound emails for this record "
             "before being sent. "
             "Separate multiple email addresses with a comma")
    author_name = fields.Char(
        readonly=True,
        help="Name of author based on incoming email")
    author_phone = fields.Char(
        readonly=True,
        help="Phone of author")

    message_discussion_ids = fields.One2many(
        'mail.message', 'res_id', string='Discussion Messages', store=True,
        domain=lambda r: [
            ('subtype_id', '=', r.env.ref('mail.mt_comment').id)])
    original_message_id = fields.Char(
        help='Technical field. '
             'ID of original message that started this request.')
    attachment_ids = fields.One2many(
        'ir.attachment', 'res_id',
        domain=[('res_model', '=', 'request.request')],
        string='Attachments')

    instruction_visible = fields.Boolean(
        compute='_compute_instruction_visible', default=False,
        compute_sudo=False)

    # We have to explicitly set compute_sudo to True to avoid access errors
    activity_date_deadline = fields.Date(compute_sudo=True)

    # Events (deprecated, use generic_event_count instead)
    request_event_ids = fields.One2many(
        'request.event', 'event_source_record_id', 'Events', readonly=True)
    request_event_count = fields.Integer(
        compute='_compute_request_event_count', readonly=True)

    # Timesheets
    timesheet_line_ids = fields.One2many(
        'request.timesheet.line', 'request_id')
    timesheet_planned_amount = fields.Float(
        help="Planned time")
    timesheet_amount = fields.Float(
        compute='_compute_timesheet_line_data',
        readonly=True, store=True,
        help="Time spent")
    timesheet_remaining_amount = fields.Float(
        compute='_compute_timesheet_line_data',
        readonly=True, store=True,
        help="Remaining time")
    timesheet_progress = fields.Float(
        compute='_compute_timesheet_line_data',
        readonly=True, store=True,
        help="Request progress, calculated as the ratio of time spent "
             "to planned time")
    timesheet_start_status = fields.Selection(
        [('started', 'Started'),
         ('not-started', 'Not Started')],
        compute='_compute_timesheet_start_status', readonly=True)
    use_timesheet = fields.Boolean(
        related='type_id.use_timesheet', readonly=True)

    author_related_request_open_count = fields.Integer(
        compute='_compute_related_a_p_request_ids')
    author_related_request_closed_count = fields.Integer(
        compute='_compute_related_a_p_request_ids')

    partner_related_request_open_count = fields.Integer(
        compute='_compute_related_a_p_request_ids')
    partner_related_request_closed_count = fields.Integer(
        compute='_compute_related_a_p_request_ids')

    stage_route_out_json = fields.Char(
        compute='_compute_stage_route_out_json', readonly=True)

    parent_id = fields.Many2one(
        'request.request', 'Parent', index=True,
        ondelete='restrict', readonly=True,
        tracking=True,
        help="Parent request")
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many(
        'request.request', 'parent_id', 'Subrequests', readonly=True)
    child_count = fields.Integer(
        'Subrequest Count', compute='_compute_child_count')

    sec_view_access_partner_ids = fields.Many2manyView(
        comodel_name='res.partner',
        relation='request_access_follower_partner_rel_view',
        column1='request_id',
        column2='partner_id',
        readonly=True,
        copy=False,
        help="Technical field to represent all partners that "
             "follow this request, or its parent request, or any of its child "
             "request. It is used for access-rights checks."
    )

    # Service Fields
    service_id = fields.Many2one(
        'generic.service', string='Service', ondelete='restrict',
        help="Service of request")
    service_id_group = fields.Many2one(
        comodel_name='generic.service.group',
        related='service_id.service_group_id',
        string='Service group', store=True, readonly=True)

    # NOTE: Some notes about service level field
    #       Here it is readonly and is not computed, but we have to
    #       emulate behavior of computed-like field because,
    #       we want to trigger service-level-changed event,
    #       each time this field is changed in database,
    #       but in case of computed fields it is difficult to handle when
    #       the field is changed in database, thus we use in paralled,
    #       onchange methods to compute it in user interface and
    #       @post_write handlers to compute it on actual write to database
    service_level_id = fields.Many2one(
        'generic.service.level', ondelete='restrict',
        string='Service Level', readonly=True,
        help="Service of request. Used to compute SLA for request.")
    can_change_service = fields.Boolean(
        compute='_compute_can_change_service', readonly=True, store=False)

    service_id_domain = fields.Text(
        compute='_compute_service_category_type_domains')

    _sql_constraints = [
        ('name_uniq',
         'UNIQUE (name)',
         'Request name must be unique.'),
    ]

    @property
    def _request_service_level_guessers(self):
        cls = type(self)

        def is_guesser(fn):
            """ Check if fn is function that represents service level guesser.
            """
            if not callable(fn):
                return False
            if getattr(fn, '__service_level_guesser__', False):
                return True
            return False

        guessers = []
        for method_name, __ in getmembers(cls, is_guesser):
            method = getattr(cls, method_name)
            guessers += [
                (method.__service_level_guesser_priority__, method_name)
            ]
        # Sort guessers by priority
        result = [
            g[1] for g in sorted(guessers, key=itemgetter(0))]

        # Memoize guessers on class
        cls._request_service_level_guessers = result
        return result

    @classmethod
    def _get_service_level_dependency_fields(cls):
        """ Return list of fields that have to trigger service level
            recomputation.
            Could be extended by other addons

            This list is used to trigger onchange handler that will recompute
            service level in UI when at least one of mentioned fields changed.
        """
        return ['author_id', 'partner_id']

    @classmethod
    def _init_constraints_onchanges(cls):
        # Overloading this method to dynamically create onchange handler with
        # dynamically computed fields. This is required to be able to add
        # dependency fields in other addons.
        cls._onchange_update_service_level._onchange = tuple(
            cls._get_service_level_dependency_fields())

        # Reset momoized list of guessers
        cls._request_service_level_guessers = (
            RequestRequest._request_service_level_guessers)
        return super(RequestRequest, cls)._init_constraints_onchanges()

    def _get_service_level(self):
        """ Get service level for this request.
            This is the core method, that will be called from various places
            to compute service level for request.
        """
        self.ensure_one()
        for guesser in self._request_service_level_guessers:
            service_level = getattr(self, guesser)()
            if service_level:
                return service_level
        return self.env['generic.service.level'].browse()

    @api.model
    def default_get(self, fields_list):
        res = super(RequestRequest, self).default_get(fields_list)

        channel_id = self._guess_default_channel()
        if channel_id:
            res.update({'channel_id': channel_id})
        if 'parent_id' in fields_list:
            parent = self._context.get('generic_request_parent_id')
            res.update({'parent_id': parent})

        return res

    def _guess_default_channel(self):
        path = http.request.httprequest.path if http.request else False

        self_sudo = self.sudo()

        # Define default channel, that will be assigned, when others
        # are inactive or deleted
        default = self_sudo.env.ref(
            'generic_request.request_channel_other', raise_if_not_found=False)

        # Try to define an active specified channel
        channel = None
        if path and path.startswith('/web') or path == '/web':
            channel = self_sudo.env.ref(
                'generic_request.request_channel_web',
                raise_if_not_found=False)
        elif path and path.startswith('/xmlrpc') or path == '/xmlrpc':
            channel = self_sudo.env.ref(
                'generic_request.request_channel_api',
                raise_if_not_found=False)
        elif path and path.startswith('/jsonrpc') or path == '/jsonrpc':
            channel = self_sudo.env.ref(
                'generic_request.request_channel_api',
                raise_if_not_found=False)

        # If nothing specified active channels found,
        # try to assign the default one or, at least
        # (when default also inactive) return False
        if channel and channel.active:
            return channel.id
        return default.id if default and default.active else False

    @service_level_guesser(priority=1000)
    def _get_service_level__from_parther_author(self):
        if self.partner_id:
            return self.partner_id.service_level_id
        return self.author_id.service_level_id

    @api.depends('deadline_date', 'date_closed')
    def _compute_deadline_state(self):
        now = datetime.now().date()
        for rec in self:
            date_deadline = fields.Date.from_string(
                rec.deadline_date) if rec.deadline_date else False
            date_closed = fields.Date.from_string(
                rec.date_closed) if rec.date_closed else False
            if not date_deadline:
                rec.deadline_state = False
                continue

            if date_closed:
                if date_closed <= date_deadline:
                    rec.deadline_state = 'ok'
                else:
                    rec.deadline_state = 'overdue'
            else:
                if date_deadline > now:
                    rec.deadline_state = 'ok'
                elif date_deadline < now:
                    rec.deadline_state = 'overdue'
                elif date_deadline == now:
                    rec.deadline_state = 'today'

    @api.depends('deadline_date_dt')
    def _compute_deadline_date(self):
        for record in self:
            if record.deadline_date_dt:
                record.deadline_date = record.deadline_date_dt.date()
            else:
                record.deadline_date = False

    def _inverse_deadline_date(self):
        # On attempt to write to deadline_date, we have to automatically
        # convert it to datetime, and deadline_date will be computed via
        # compute method.

        # TODO: Think about handling edge cases. But, it seems that in case
        #       of dates, odoo does not automatically handles timezones.
        #       For example, take a look at table below
        # UTC Date time             | local datetime            | timezone
        # 2023-07-20 09:21:38+00:00 | 2023-07-19 22:21:38-11:00 | Pacific/Samoa
        # 2023-07-20 09:21:38+00:00 | 2023-07-20 12:21:38+03:00 | Europe/Kyiv
        for record in self:
            if record.type_id.deadline_format == 'date':
                if record.deadline_date:
                    record.deadline_date_dt = datetime.combine(
                        record.deadline_date, time.max)
                else:
                    record.deadline_date_dt = False

    @api.depends('stage_id', 'stage_id.type_id')
    def _compute_stage_colors(self):
        for rec in self:
            rec.stage_bg_color = rec.stage_id.res_bg_color
            rec.stage_label_color = rec.stage_id.res_label_color

    @api.depends('stage_id.route_out_ids.stage_to_id.closed')
    def _compute_can_be_closed(self):
        for record in self:
            record.can_be_closed = any((
                r.close for r in record.stage_id.route_out_ids))

    @api.depends('request_event_ids')
    def _compute_request_event_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='request_event_ids', sudo=True)
        for record in self:
            record.request_event_count = mapped_data.get(record.id, 0)

    @api.depends()
    def _compute_is_new_request(self):
        for record in self:
            record.is_new_request = int(not bool(record.id))

    def _hook_can_change_request_text(self):
        self.ensure_one()
        return not self.closed

    def _hook_can_change_assignee(self):
        self.ensure_one()
        return not self.closed

    def _hook_can_change_category(self):
        self.ensure_one()
        return self.stage_id == self.type_id.sudo().start_stage_id

    def _hook_can_change_deadline(self):
        self.ensure_one()
        return not self.closed

    def _hook_can_change_author(self):
        self.ensure_one()
        return self.stage_id == self.type_id.sudo().start_stage_id

    @api.depends('type_id', 'stage_id', 'user_id',
                 'partner_id', 'created_by_id', 'category_id', 'tag_ids')
    def _compute_can_change_request_text(self):
        for rec in self:
            rec.can_change_request_text = rec._hook_can_change_request_text()

    @api.depends('type_id', 'stage_id', 'user_id',
                 'partner_id', 'created_by_id', 'category_id', 'tag_ids')
    def _compute_can_change_assignee(self):
        for rec in self:
            rec.can_change_assignee = rec._hook_can_change_assignee()

    @api.depends('type_id', 'type_id.start_stage_id', 'stage_id',
                 'user_id', 'partner_id', 'created_by_id', 'request_text',
                 'category_id', 'tag_ids')
    def _compute_can_change_author(self):
        for record in self:
            if not self.env.user.has_group(
                    'generic_request.group_request_user_can_change_author'):
                record.can_change_author = False
            else:
                record.can_change_author = record._hook_can_change_author()

    @api.depends('type_id', 'type_id.start_stage_id', 'stage_id', 'tag_ids')
    def _compute_can_change_category(self):
        for record in self:
            record.can_change_category = record._hook_can_change_category()

    @api.depends('type_id', 'type_id.start_stage_id', 'stage_id',
                 'deadline_date', 'category_id', 'tag_ids')
    def _compute_can_change_deadline(self):
        for record in self:
            record.can_change_deadline = record._hook_can_change_deadline()

    @api.depends('request_text')
    def _compute_request_text_sample(self):
        for request in self:
            text_list = html2text(request.request_text).splitlines()
            result = []
            while len(result) <= REQUEST_TEXT_SAMPLE_MAX_LINES and text_list:
                line = text_list.pop(0)
                line = line.lstrip('#').strip()
                if not line:
                    continue
                result.append(line)
            request.request_text_sample = "\n".join(result)

    @api.depends('user_id')
    def _compute_instruction_visible(self):
        for rec in self:
            rec.instruction_visible = (
                (
                    self.env.user == rec.user_id or
                    self.env.user.id == SUPERUSER_ID or
                    self.env.user.has_group(
                        'generic_request.group_request_manager')
                ) and (
                    rec.instruction_html and
                    rec.instruction_html != '<p><br></p>'
                )
            )

    @api.depends('type_id')
    def _compute_is_priority_complex(self):
        for rec in self:
            rec.is_priority_complex = rec.sudo().type_id.complex_priority

    @api.depends('_priority', 'impact', 'urgency')
    def _compute_priority(self):
        for rec in self:
            if rec.is_priority_complex:
                rec.priority = str(
                    PRIORITY_MAP[int(rec.impact)][int(rec.urgency)])
            else:
                rec.priority = rec._priority

    @api.depends('user_id')
    def _compute_is_assigned(self):
        for rec in self:
            rec.is_assigned = bool(rec.user_id)

    # When priority is complex, it is computed from impact and urgency
    # We do not need to write it directly from the field
    def _inverse_priority(self):
        for rec in self:
            if not rec.is_priority_complex:
                rec._priority = rec.priority

    @api.depends('author_id', 'partner_id')
    def _compute_related_a_p_request_ids(self):
        for record in self:
            # TODO: Possibly, optimize with SQL, because there are cases
            #       when there are a lot of requests for single
            #       partner or author.
            # Usually this will be called on request form view and thus
            # computed only for one record. So, it will lead only to 4
            # search_counts per request to compute stat
            if record.id and record.author_id:
                record.update({
                    'author_related_request_open_count':
                        self.sudo().search_count([
                            ('author_id', '=', record.author_id.id),
                            ('closed', '=', False),
                            ('id', '!=', record.id)]),
                    'author_related_request_closed_count':
                        self.sudo().search_count([
                            ('author_id', '=', record.author_id.id),
                            ('closed', '=', True),
                            ('id', '!=', record.id)]),
                })
            else:
                record.update({
                    'author_related_request_open_count': 0,
                    'author_related_request_closed_count': 0,
                })

            if record.id and record.partner_id:
                record.update({
                    'partner_related_request_open_count': self.search_count(
                        [('partner_id', '=', record.partner_id.id),
                         ('closed', '=', False),
                         ('id', '!=', record.id)]),
                    'partner_related_request_closed_count': self.search_count(
                        [('partner_id', '=', record.partner_id.id),
                         ('closed', '=', True),
                         ('id', '!=', record.id)]),
                })
            else:
                record.update({
                    'partner_related_request_open_count': 0,
                    'partner_related_request_closed_count': 0,
                })

    @api.depends('timesheet_line_ids', 'timesheet_line_ids.amount',
                 'timesheet_planned_amount')
    def _compute_timesheet_line_data(self):
        for rec in self:
            timesheet_amount = 0.0
            for line in rec.timesheet_line_ids:
                timesheet_amount += line.amount
            rec.timesheet_amount = timesheet_amount

            if rec.timesheet_planned_amount:
                rec.timesheet_remaining_amount = (
                    rec.timesheet_planned_amount - timesheet_amount)
                rec.timesheet_progress = (
                    100.0 * (timesheet_amount / rec.timesheet_planned_amount))
            else:
                rec.timesheet_remaining_amount = 0.0
                rec.timesheet_progress = 0.0

    @api.depends('timesheet_line_ids', 'timesheet_line_ids.date_start',
                 'timesheet_line_ids.date_end')
    def _compute_timesheet_start_status(self):
        TimesheetLines = self.env['request.timesheet.line']
        domain = expression.AND([
            TimesheetLines._get_running_lines_domain(),
            [('request_id', 'in', self.ids)],
        ])
        grouped = self.env["request.timesheet.line"].read_group(
            domain=domain,
            fields=["id", 'request_id'],
            groupby=['request_id'],
        )
        lines_per_record = {
            group['request_id'][0]: group["request_id_count"]
            for group in grouped
        }

        for record in self:
            if lines_per_record.get(record.id, 0) > 0:
                record.timesheet_start_status = 'started'
            else:
                record.timesheet_start_status = 'not-started'

    @api.depends('stage_id', 'service_id', 'category_id', 'type_id', 'tag_ids')
    def _compute_stage_route_out_json(self):
        for rec in self:
            routes = []
            for route in rec.stage_id.route_out_ids:
                try:
                    route._ensure_can_move(rec)
                except exceptions.AccessError:  # pylint: disable=except-pass
                    # We have to ignore routes that cannot be used
                    # to move request
                    pass
                except exceptions.UserError:
                    # In case of user error, we have to log this error,
                    # and make this route not available for user.
                    _logger.warning(
                        "Cannot check availability of route %s, skipping...",
                        route.display_name, exc_info=True)
                else:
                    # Add route to those allowed to move
                    if route.name:
                        route_name = route.name
                    else:
                        route_name = route.stage_to_id.name
                    routes += [{
                        'id': route.id,
                        'name': route_name,
                        'stage_to_id': route.stage_to_id.id,
                        'close': route.close,
                        'btn_style': route.button_style,
                    }]

            rec.stage_route_out_json = json.dumps({'routes': routes})

    @api.depends('child_ids')
    def _compute_child_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='child_ids')
        for record in self:
            record.child_count = mapped_data.get(record.id, 0)

    @api.depends('is_new_request', 'type_id', 'category_id', 'service_id')
    def _compute_service_category_type_domains(self):
        """ Compute domains for service_id, category_id, service_id fields in
            request. Later this domains will be handled in js.
        """

        for record in self:
            record.service_id_domain = record._get_service_id_domain()
            record.category_id_domain = record._get_category_id_domain()
            record.type_id_domain = record._get_type_id_domain()

    def _hook_can_change_service(self):
        self.ensure_one()
        return self.stage_id == self.type_id.sudo().start_stage_id

    @api.depends('type_id', 'type_id.start_stage_id', 'stage_id')
    def _compute_can_change_service(self):
        for record in self:
            record.can_change_service = record._hook_can_change_service()

    @api.model
    def init(self):
        res = super().init()

        # Making this view to improve performance on
        # access rights check for requests.
        create_sql_view(
            self._cr, 'request_access_follower_partner_rel_view',
            """
                SELECT mf.res_id AS request_id,
                    mf.partner_id AS partner_id
                FROM mail_followers AS mf
                WHERE mf.res_model = 'request.request'
                  AND mf.partner_id IS NOT NULL
                UNION
                SELECT rr.id AS request_id,
                       mf.partner_id AS partner_id
                FROM request_request AS rr
                LEFT JOIN mail_followers  AS mf ON (
                    mf.res_model = 'request.request' AND
                    mf.partner_id IS NOT NULL AND
                    mf.res_id = rr.parent_id)
                WHERE rr.parent_id IS NOT NULL
                UNION
                SELECT rr.parent_id AS request_id,
                       mf.partner_id AS partner_id
                FROM request_request AS rr
                LEFT JOIN mail_followers  AS mf ON (
                    mf.res_model = 'request.request' AND
                    mf.partner_id IS NOT NULL AND
                    mf.res_id = rr.id)
                WHERE rr.parent_id IS NOT NULL
            """)
        return res

    @api.constrains('parent_id')
    def _recursion_constraint(self):
        if not self._check_recursion():
            raise ValidationError(_(
                'Error! You cannot create recursive requests.'))

    def _create_update_from_type(self, r_type, vals):
        vals = dict(vals)
        # Name update
        if vals.get('name') == "###new###":
            # To set correct name for request generated from mail aliases
            # See code `mail.models.mail_thread.MailThread.message_new` - it
            # attempts to set name if it is empty. So we pass special name in
            # our method overload, and handle it here, to keep all request name
            # related logic in one place
            vals['name'] = False
        if not vals.get('name') and r_type.sequence_id:
            vals['name'] = r_type.sudo().sequence_id.next_by_id()
        elif not vals.get('name'):
            vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                'request.request.name')

        # Update stage
        if r_type.start_stage_id:
            vals['stage_id'] = r_type.start_stage_id.id
        else:
            raise exceptions.ValidationError(_(
                "Cannot create request of type '%(type_name)s':"
                " This type have no start stage defined!"
            ) % {'type_name': r_type.name})

        # Set default priority
        if r_type.sudo().complex_priority:
            if not vals.get('impact'):
                vals['impact'] = r_type.sudo().default_impact
            if not vals.get('urgency'):
                vals['urgency'] = r_type.sudo().default_urgency
        else:
            if not vals.get('priority'):
                vals['priority'] = r_type.sudo().default_priority

        return vals

    @api.model
    def _add_missing_default_values(self, values):
        if values.get('created_by_id') and 'author_id' not in values:
            # This is required to be present before super call, because
            # 'author_id' has its own default value, and unless it is set
            # explicitly, original default value (partner of current user)
            # will be used.
            create_user = self.env['res.users'].sudo().browse(
                values['created_by_id'])
            values = dict(
                values,
                author_id=create_user.partner_id.id)
        res = super(RequestRequest, self)._add_missing_default_values(values)

        if res.get('author_id') and 'partner_id' not in values:
            author = self.env['res.partner'].browse(res['author_id'])
            if author.commercial_partner_id != author:
                res['partner_id'] = author.commercial_partner_id.id
        return res

    @api.model_create_multi
    def create(self, values):
        values_to_write = []
        for vals in values:
            if vals.get('type_id', False):
                # TODO: rewrite as pre_create hook instead.
                values_to_write += [
                    self._create_update_from_type(
                        self.env['request.type'].browse(vals['type_id']),
                        vals),
                ]
            else:
                values_to_write += [vals]

        self_ctx = self.with_context(mail_create_nolog=False)
        requests = super(RequestRequest, self_ctx).create(values_to_write)

        # This is needed to avoid creation of requests with wrong parent by
        # accident. For example, in case of following situation:
        # - We have automated action, that will be triggered when
        #   request is created. This action have to create another request,
        #   based on this request (just created).
        # - If we have in context 'generic_request_parent_id', then this new
        #   request will be created with same parent.
        # To avoid this, we have to clean context after request was created.
        if self.env.context.get('generic_request_parent_id'):
            new_ctx = dict(self.env.context)
            new_ctx.pop('generic_request_parent_id')
            requests = requests.with_env(requests.env(context=new_ctx))

        self.env['res.partner'].invalidate_cache(fnames=['request_ids'])
        return requests

    def unlink(self):
        res = super().unlink()
        # Cleanup cache on unlink
        self.env['res.partner'].invalidate_cache(fnames=['request_ids'])
        return res

    def _get_generic_tracking_fields(self):
        """ Compute list of fields that have to be tracked
        """
        # TODO: Do we need it? it seems that we have migrated most of code to
        # use pre/post_write decorators
        return super(
            RequestRequest, self
        )._get_generic_tracking_fields() | TRACK_FIELD_CHANGES

    def _get_service_id_domain(self):
        """ This method must return domain for 'service_id_domain' field in
            request.
            This method could be overridden in other addons.

            Also, if new dependency added to domain, then such dependency have
            to be added also to _compute_service_category_type_domains method.
        """
        self.ensure_one()
        classifier_domain = []
        if not self.is_new_request:
            classifier_domain = expression.AND([
                classifier_domain,
                [('type_id', '=', self.type_id.id)], ])

        classifiers = self.env['request.classifier'].search(classifier_domain)
        service_id_domain = [('id', 'in', classifiers.mapped(
            'service_id').ids)]
        return service_id_domain

    def _get_category_id_domain(self):
        """ This method must return domain for 'category_id_domain'
            field in request. This method could be overridden in other addons.
        """
        # If no service selected, search only classifiers without service
        classifier_domain = [
            ('service_id', '=', self.service_id.id),
        ]
        if not self.is_new_request:
            classifier_domain = expression.AND([
                classifier_domain,
                [('type_id', '=', self.type_id.id)],
            ])
        classifiers = self.env['request.classifier'].search(
            classifier_domain)
        category_id_domain = [
            ('id', 'in', classifiers.mapped('category_id').ids)]
        return category_id_domain

    def _get_type_id_domain(self):
        """ This method must return domain for 'type_id_domain'
            field in request. This method could be overridden in other addons.
        """
        start_domain = [('start_stage_id', '!=', False)]

        # domain resolution for type_id depending on category_id
        category_type_domain = (
            [('category_id', '=', self.category_id.id)]
            if self.category_id
            else [('category_id', '=', False)])

        # domain resolution for type_id depending on service_id
        service_type_domain = (
            [('service_id', '=', self.service_id.id)]
            if self.service_id
            else [('service_id', '=', False)])

        # find the records in classifier by domains mentioned above
        classifier_domain = expression.AND(
            [category_type_domain, service_type_domain])
        classifiers = self.env['request.classifier'].search(
            classifier_domain)
        classifier_type_ids = classifiers.mapped('type_id').ids

        record_domain = expression.AND(
            [start_domain, [('id', 'in', classifier_type_ids)]])
        return record_domain

    @pre_write('active')
    def _before_active_changed(self, changes):
        if self.env.user.id == SUPERUSER_ID:
            return
        if not self.env.user.has_group(
                'generic_request.group_request_manager_can_archive_request'):
            raise exceptions.AccessError(_(
                "Operation change active is not allowed!"))

    @pre_write('type_id')
    def _before_type_id_changed(self, changes):
        raise exceptions.ValidationError(_(
            'It is not allowed to change request type'))

    @pre_create('user_id')
    @pre_write('user_id')
    def _before_user_id_changed(self, changes):
        if changes['user_id'].new_val:
            return {'date_assigned': fields.Datetime.now()}
        return {'date_assigned': False}

    @pre_write('stage_id')
    def _before_stage_id_changed(self, changes):
        Route = self.env['request.stage.route']
        old_stage, new_stage = changes['stage_id']
        route = Route.ensure_route(self, new_stage.id)

        vals = {}
        vals['last_route_id'] = route.id
        vals['date_moved'] = fields.Datetime.now()
        vals['moved_by_id'] = self.env.user.id

        if not old_stage.closed and new_stage.closed:
            vals['date_closed'] = fields.Datetime.now()
            vals['closed_by_id'] = self.env.user.id
        elif old_stage.closed and not new_stage.closed:
            vals['date_closed'] = False
            vals['closed_by_id'] = False
        return vals

    @post_write('stage_id')
    def _after_stage_id_changed(self, changes):
        old_stage, new_stage = changes['stage_id']
        event_data = {
            'route_id': self.last_route_id.id,
            'old_stage_id': old_stage.id,
            'new_stage_id': new_stage.id,
        }
        if new_stage.closed and not old_stage.closed:
            self.trigger_event('closed', event_data)
        elif old_stage.closed and not new_stage.closed:
            self.trigger_event('reopened', event_data)
        else:
            self.trigger_event('stage-changed', event_data)

    @post_write('user_id')
    def _after_user_id_changed(self, changes):
        old_user, new_user = changes['user_id']
        event_data = {
            'old_user_id': old_user.id,
            'new_user_id': new_user.id,
            'assign_comment': self.env.context.get('assign_comment', False)
        }
        if not old_user and new_user:
            self.trigger_event('assigned', event_data)
        elif old_user and new_user:
            self.trigger_event('reassigned', event_data)
        elif old_user and not new_user:
            self.trigger_event('unassigned', event_data)

    @post_write('partner_id', 'author_id')
    def _after_partner_author_changed_invalidate_cache(self, changes):
        self.env['res.partner'].invalidate_cache(fnames=['request_ids'])

    @post_write('request_text')
    def _after_request_text_changed(self, changes):
        self.trigger_event('changed', {
            'old_text': changes['request_text'][0],
            'new_text': changes['request_text'][1]})

    @post_write('category_id')
    def _after_category_id_changed(self, changes):
        self.trigger_event('category-changed', {
            'old_category_id': changes['category_id'][0].id,
            'new_category_id': changes['category_id'][1].id,
        })

    @post_write('author_id')
    def _after_author_id_changed(self, changes):
        self.trigger_event('author-changed', {
            'old_author_id': changes['author_id'][0].id,
            'new_author_id': changes['author_id'][1].id,
        })

    @post_write('partner_id')
    def _after_partner_id_changed(self, changes):
        self.trigger_event('partner-changed', {
            'old_partner_id': changes['partner_id'][0].id,
            'new_partner_id': changes['partner_id'][1].id,
        })

    @post_write('priority', 'impact', 'urgency')
    def _after_priority_changed(self, changes):
        if 'priority' in changes:
            self.trigger_event('priority-changed', {
                'old_priority': changes['priority'][0],
                'new_priority': changes['priority'][1]})
        if 'impact' in changes:
            old, new = changes['impact']
            old_priority = str(
                PRIORITY_MAP[int(old)][int(self.urgency)])
            new_priority = str(
                PRIORITY_MAP[int(new)][int(self.urgency)])
            self.trigger_event('priority-changed', {
                'old_priority': old_priority,
                'new_priority': new_priority})
            self.trigger_event('impact-changed', {
                'old_impact': old,
                'new_impact': new})
        if 'urgency' in changes:
            old, new = changes['urgency']
            old_priority = str(
                PRIORITY_MAP[int(self.impact)][int(old)])
            new_priority = str(
                PRIORITY_MAP[int(self.impact)][int(new)])
            self.trigger_event('priority-changed', {
                'old_priority': old_priority,
                'new_priority': new_priority})
            self.trigger_event('urgency-changed', {
                'old_urgency': old,
                'new_urgency': new})

    @pre_create('deadline_date')
    def _before_create_convert_deadline_date_to_date_time(self, changes):
        # This is needed to avoid generation of 'deadline_changed' event
        # during request creation.
        # Because deadline_date is compute + inverse, then after record is
        # created, inverse method will be called to automatically convert
        # provided deadline_date to deadline_date_dt.
        # So, we do this conversion in pre-create hook, thus inverse method
        # will not need to be called.
        old_date, new_date = changes['deadline_date']
        if not old_date and new_date:
            return {
                'deadline_date_dt': datetime.combine(new_date, time.max),
            }
        return {}

    # Use as trigger 'deadline_date_dt' field instead of 'deadline_date'
    # in this method as well,
    # as it was previously not triggered when only the time changed
    # but the date remained the same.
    @post_write('deadline_date_dt')
    def _after_deadline_changed(self, changes):
        old_datetime, new_datetime = changes['deadline_date_dt']
        new_date = new_datetime.date() if new_datetime else False
        current_datetime = fields.Datetime.now()
        current_date = current_datetime.date()
        self.trigger_event('deadline-changed', {
            'old_deadline': old_datetime,
            'new_deadline': new_datetime,
        })

        # Update event sent status on request
        # By default cleanup info about events already triggered.
        event_status = {
            'deadline_event_tomorrow_sent': False,
            'deadline_event_today_sent': False,
            'deadline_event_overdue_sent': False,
        }
        if new_datetime and not self.closed:
            # Immediately trigger deadline-related date-based events
            # if needed. We do not trigger events on already closed request
            if new_date == current_date and new_datetime > current_datetime:
                self.trigger_event('deadline-today')
                event_status['deadline_event_today_sent'] = True
            elif new_date == current_date and new_datetime < current_datetime:
                self.trigger_event('deadline-overdue')
                event_status['deadline_event_overdue_sent'] = True
            elif new_date < current_date:
                self.trigger_event('deadline-overdue')
                event_status['deadline_event_overdue_sent'] = True
            elif new_date == current_date + relativedelta(days=1):
                self.trigger_event('deadline-tomorrow')
                event_status['deadline_event_tomorrow_sent'] = True
        self.write(event_status)

    @post_write('kanban_state')
    def _after_kanban_state_changed(self, changes):
        self.trigger_event('kanban-state-changed', {
            'old_kanban_state': changes['kanban_state'].old_val,
            'new_kanban_state': changes['kanban_state'].new_val})

    @post_write('active')
    def _after_active_changed(self, changes):
        # TODO: Use record archived-unarchived global events,
        #       or remove this completely and provide migration.
        __, new_active = changes['active']
        if new_active:
            event_code = 'request-unarchived'
        else:
            event_code = 'request-archived'
        self.trigger_event(event_code, {'request_active': event_code})

    def _creation_subtype(self):
        """ Determine mail subtype for request creation message/notification
        """
        return self.env.ref('generic_request.mt_request_created')

    @post_write('parent_id')
    def _after_parent_changed_trigger_request_event(self, changes):
        old, new = changes['parent_id']
        event_data = {
            'parent_old_id': old.id,
            'parent_new_id': new.id,
        }
        self.trigger_event('parent-request-changed', event_data)

    @post_write('stage_id')
    def _after_stage_id_changed_trigger_request_event(self, changes):
        old, new = changes['stage_id']
        parent_event_data = {
            'parent_route_id': self.last_route_id.id,
            'parent_old_stage_id': old.id,
            'parent_new_stage_id': new.id,
        }
        for child in self.child_ids:
            child.trigger_event(
                'parent-request-stage-changed', parent_event_data)
            if (not old.closed and new.closed):
                child.trigger_event(
                    'parent-request-closed', parent_event_data)

        if self.parent_id:
            subrequest_event_data = {
                'subrequest_id': self.id,
                'subrequest_old_stage_id': old.id,
                'subrequest_new_stage_id': new.id,
            }
            self.parent_id.trigger_event(
                'subrequest-stage-changed', subrequest_event_data)
            if (not old.closed and new.closed):
                self.parent_id.trigger_event(
                    'subrequest-closed', subrequest_event_data)

                # Here parent has at least one subrequest (self), so we do not
                # need to check if parent has subrequests.
                child_reqs = self.parent_id.sudo().child_ids
                if all(sr.stage_id.closed for sr in child_reqs):
                    self.parent_id.trigger_event(
                        'subrequest-all-subrequests-closed', {})

    @post_write('service_id')
    def _after_service_changed__trigger_event(self, changes):
        if 'service_id' in changes:
            old_service, new_service = changes['service_id']
            self.trigger_event('service-changed', {
                'old_service_id': old_service.id,
                'new_service_id': new_service.id,
            })

    @post_create()
    @post_write('author_id', 'partner_id')
    def _update_service_level_on_write(self, changes):
        self.service_level_id = self._get_service_level()

    @post_write('service_level_id')
    def _after_service_level_id_changed__trigger_event(self, changes):
        self.trigger_event('service-level-changed', {
            'old_service_level_id': changes['service_level_id'][0].id,
            'new_service_level_id': changes['service_level_id'][1].id,
        })

    def _track_subtype(self, init_values):
        """ Give the subtypes triggered by the changes on the record according
        to values that have been updated.

        :param init_values: the original values of the record;
                            only modified fields are present in the dict
        :type init_values: dictionary
        :returns: a subtype xml_id or False if no subtype is triggered
        """
        self.ensure_one()
        if 'stage_id' in init_values:
            init_stage = init_values['stage_id']
            if init_stage and init_stage != self.stage_id and \
                    self.stage_id.closed and not init_stage.closed:
                return self.env.ref('generic_request.mt_request_closed')
            if init_stage and init_stage != self.stage_id and \
                    not self.stage_id.closed and init_stage.closed:
                return self.env.ref('generic_request.mt_request_reopened')
            if init_stage != self.stage_id:
                return self.env.ref('generic_request.mt_request_stage_changed')

        return self.env.ref('generic_request.mt_request_updated')

    @api.onchange('type_id')
    def onchange_type_id(self):
        """ Set default stage_id
        """
        for request in self:
            if request.type_id and request.type_id.start_stage_id:
                request.stage_id = request.type_id.start_stage_id
            else:
                request.stage_id = self.env['request.stage'].browse([])

            # Set default priority
            if not request.is_priority_complex:
                request.priority = request.type_id.default_priority
            else:
                request.impact = request.type_id.default_impact
                request.urgency = request.type_id.default_urgency

            # Set default text for request
            if self.env.context.get('default_request_text'):
                continue
            if request.type_id and request.type_id.default_request_text \
                    not in (False, '<p><br></p>'):
                request.request_text = request.type_id.default_request_text

    @api.onchange('category_id', 'type_id', 'service_id', 'is_new_request')
    def _onchange_category_type(self):
        classifier = self.env['request.classifier']

        # Clear type if it does not exist
        # for the selected category in classifier
        if self.type_id and self.category_id and self.is_new_request:
            if not classifier.get_classifiers(
                    category=self.category_id.id,
                    request_type=self.type_id.id,
                    limit=1):
                self.type_id = False

        # Clear type if it does not exist
        # without category in classifier
        elif self.type_id and not self.category_id and self.is_new_request:
            if not classifier.get_classifiers(
                    category=False,
                    request_type=self.type_id.id,
                    limit=1):
                self.type_id = False

        # Clear category if it does not exist
        # for the selected service in classifier
        if self.category_id and self.service_id:
            if not classifier.get_classifiers(
                    service=self.service_id,
                    category=self.category_id,
                    limit=1):
                self.category_id = False

        # Clear category if it does not exist
        # without a service in classifiers
        elif self.category_id and not self.service_id:
            if not classifier.get_classifiers(
                    service=False,
                    category=self.category_id,
                    limit=1):
                self.category_id = False

        # Clear type if it does not exist
        # for the selected service in classifier
        if self.service_id and self.is_new_request:
            if not classifier.get_classifiers(
                    service=self.service_id,
                    request_type=self.type_id,
                    limit=1):
                self.type_id = None

    @api.onchange('author_id')
    def _onchange_author_id(self):
        for rec in self:
            if rec.author_id:
                rec.partner_id = self.author_id.parent_id
            else:
                rec.partner_id = False

    def _onchange_update_service_level(self):
        """ Onchange method, that will be called to automatically
            compute service level, allowing to change it in future
        """
        self.service_level_id = self._get_service_level()

    @api.model
    def fields_view_get(self, view_id=None, view_type='form',
                        toolbar=False, submenu=False):
        result = super(RequestRequest, self).fields_view_get(
            view_id=view_id, view_type=view_type,
            toolbar=toolbar, submenu=submenu)

        # Make type_id and stage_id readonly for kanban mode.
        # this is required to disable kanban drag-and-drop features for this
        # fields, because changing request type or request stage in this way,
        # may lead to broken workflow for requests (no routes to move request
        # to next stage)
        if view_type == 'kanban':
            for rfield in KANBAN_READONLY_FIELDS:
                if rfield in result['fields']:
                    result['fields'][rfield]['readonly'] = True
        return result

    def ensure_can_assign(self):
        for record in self:
            if not record.can_change_assignee:
                raise exceptions.UserError(_(
                    "You can not assign this (%(request)s) request"
                ) % {'request': record.display_name})

    def action_request_assign(self):
        self.ensure_can_assign()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_wizard_assign',
            context={'default_request_ids': [(6, 0, self.ids)]})

    def action_request_assign_to_me(self):
        self.ensure_can_assign()
        self.write({'user_id': self.env.user.id})

    # Default notifications
    def _send_default_notification__get_email_from(self, **kw):
        """ To be overloaded to change 'email_from' field for notifications
        """
        return False

    def _send_default_notification__get_context(self, event):
        """ Compute context for default notification
        """
        values = event.get_context()
        values['company'] = self.company_id
        return values

    def _send_default_notification__get_msg_params(self, **kw):
        return dict(
            composition_mode='mass_mail',
            # TODO: Make auto-delete configurable
            auto_delete=True,
            auto_delete_message=False,
            parent_id=False,  # override accidental context defaults
            # Use mt_note, because otherwise,
            # message will be sent to all subscribers
            subtype_id=self.env.ref('mail.mt_note').id,
            **kw,
        )

    def _send_default_notification__send(self, template, partners,
                                         event, **kw):
        """ Send default notification

            :param str template: XMLID of template to use for notification
            :param Recordset partners: List of partenrs that have to receive
                                       this notification
            :param Recordset event: Single record of 'request.event'
            :param function lazy_subject: function (self) that have to return
                                          translated string for subject
                                          for notification
        """
        values_g = self._send_default_notification__get_context(event)
        message_data_g = self._send_default_notification__get_msg_params(**kw)
        email_from = self._send_default_notification__get_email_from(**kw)
        if email_from:
            message_data_g['email_from'] = email_from

        # In order to handle translatable subjects, we use specific argument:
        # lazy_subject, which is function that receives 'self' and returns
        # string.
        lazy_subject = message_data_g.pop('lazy_subject', None)

        for partner in partners.sudo():
            # Skip partners without emails to avoid errors
            if not partner.email:
                continue
            values = dict(
                values_g,
                partner=partner,
            )

            # Prepare base context for this notification
            # We have to use sudo, because otherwise external users
            # will not be able to create request (
            # that requires to send notification)
            self_ctx = self.sudo()

            # Remove default author from context.
            # This is required to fix bug in generic_request_crm:
            # when user create new request from lead, and there is default
            # author specified in context, then all notification messages use
            # that author as author of message. This way customer notification
            # has customer as author. Next block of code have to fix
            # this issue.
            if self_ctx.env.context.get('default_author_id'):
                new_ctx = dict(self_ctx.env.context)
                new_ctx.pop('default_author_id')
                self_ctx = self_ctx.with_env(self_ctx.env(context=new_ctx))

            if partner.lang:
                self_ctx = self_ctx.with_context(lang=partner.lang)
            message_data = dict(
                message_data_g,
                partner_ids=[(4, partner.id)],
                values=values)
            if lazy_subject:
                message_data['subject'] = lazy_subject(self_ctx)

            self_ctx.message_post_with_view(
                template,
                **message_data)

    @on_event('record-created')
    def _send_default_notification_created(self, event):
        # if created request has parent,
        # send the event message to parent in any case
        # regardless of request type notification setting
        if self.parent_id:
            log_note = 'Subrequest <a href="%s">%s</a> of type <i>%s</i> ' \
                       'has been created. ' \
                       % (self.get_mail_url(), self.name, self.type_id.name)
            self.parent_id._message_log(body=log_note)

        if not self.sudo().type_id.send_default_created_notification:
            return

        self._send_default_notification__send(
            'generic_request.message_request_created__author',
            self.sudo().author_id,
            event,
            lazy_subject=lambda self: _(
                "Request %(request)s successfully created!"
            ) % {'request': self.name},
        )

    @on_event('assigned', 'reassigned')
    def _send_default_notification_assigned(self, event):
        # if assigned request has parent,
        # send the event message to parent in any case
        # regardless of request type notification setting
        if self.parent_id:
            log_note = 'Subrequest <a href="%s">%s</a> assigned to: %s. ' \
                       % (self.get_mail_url(), self.name, self.user_id.name)
            self.parent_id._message_log(body=log_note)

        if not self.sudo().type_id.send_default_assigned_notification:
            return

        self._send_default_notification__send(
            'generic_request.message_request_assigned__assignee',
            event.sudo().new_user_id.partner_id,
            event,
            lazy_subject=lambda self: _(
                "You have been assigned to request %(request)s!"
            ) % {'request': self.name},
        )

    @on_event('closed')
    def _send_default_notification_closed(self, event):
        # if closed request has parent,
        # send the event message to parent in any case
        # regardless of request type notification setting
        if self.parent_id:
            log_note = 'Subrequest <a href="%s">%s</a> has been closed. ' \
                       % (self.get_mail_url(), self.name)
            if self.response_text:
                log_note += '<br> %s' % self.response_text
            self.parent_id._message_log(body=log_note)

        if not self.sudo().type_id.send_default_closed_notification:
            return

        self._send_default_notification__send(
            'generic_request.message_request_closed__author',
            self.sudo().author_id,
            event,
            lazy_subject=lambda self: _(
                "Your request %(request)s has been closed!"
            ) % {'request': self.name},
            attachment_ids=[(6, 0, self.response_attachment_ids.ids)],
        )

    @on_event('reopened')
    def _send_default_notification_reopened(self, event):
        # if reopened request has parent,
        # send the event message to parent in any case
        # regardless of request type notification setting
        if self.parent_id:
            log_note = 'Subrequest <a href="%s">%s</a> has been reopened. ' \
                       % (self.get_mail_url(), self.name)
            self.parent_id._message_log(body=log_note)

        if not self.sudo().type_id.send_default_reopened_notification:
            return

        self._send_default_notification__send(
            'generic_request.message_request_reopened__author',
            self.sudo().author_id,
            event,
            lazy_subject=lambda self: _(
                "Your request %(request)s has been reopened!"
            ) % {'request': self.name},
        )

    def trigger_event(self, event_type_code, event_data_vals=None):
        # Set `request_id` for all events.
        # This is needed for backward compatibility,
        # but may be removed in future
        if event_data_vals is None:
            vals = {'request_id': self.id}
        else:
            vals = dict(event_data_vals, request_id=self.id)
        return super().trigger_event(event_type_code, event_data_vals=vals)

    def get_mail_url(self, pid=None):
        """ Get request URL to be used in mails

            :param int pid: ID of partner. reserver for portal usage
        """
        return "/mail/view/request/%s" % self.id

    def _notify_get_groups(self, *args, **kwargs):
        """ Use custom url for *button_access* in notification emails
        """
        self.ensure_one()
        groups = super(RequestRequest, self)._notify_get_groups(
            *args, **kwargs)

        view_title = _('View Request')
        # TODO: generate separate link for each partner
        access_link = self.get_mail_url()

        # pylint: disable=unused-variable
        for group_name, group_method, group_data in groups:
            group_data['button_access'] = {
                'title': view_title,
                'url': access_link,
            }

        return groups

    def _message_auto_subscribe_followers(self, updated_values,
                                          default_subtype_ids):
        res = super(RequestRequest, self)._message_auto_subscribe_followers(
            updated_values, default_subtype_ids)

        if updated_values.get('author_id'):
            author = self.env['res.partner'].browse(
                updated_values['author_id'])
            if author.active:
                res.append((
                    author.id, default_subtype_ids, False))
        return res

    def _message_auto_subscribe_notify(self, partner_ids, template):
        # Disable sending mail to assigne, when request was assigned.
        # Custom notification will be sent, see _after_user_id_changed method
        # pylint: disable=useless-super-delegation
        return super(
            RequestRequest,
            self.with_context(mail_auto_subscribe_no_notify=True)
        )._message_auto_subscribe_notify(partner_ids, template)

    def _find_emails_from_msg(self, msg):
        """ Find emais from email message.
            Check 'to' and 'cc' fields

            :return: List of emails
        """
        # TODO: do we need to parse 'to' header here?
        return tools.email_split(
            (msg.get('to') or '') + ',' + (msg.get('cc') or ''))

    def _get_or_create_partner_from_email(self, email, force_create=False):
        """ This method will try to find partner by email.
            And if "force_create" is set to True, then it will try to create
            new partner (contact) for this email
        """
        partner_ids = self._mail_find_partner_from_emails(
            [email], force_create=force_create)
        if partner_ids:
            return partner_ids[0].id
        return False

    @api.model
    def _ensure_email_from_is_not_alias(self, msg_dict):
        """ Check that email is not come from alias.

            This needed to protect from infinite loops.
            If email come to odoo from alias managed by odoo,
            then it seems that there is going on something strage.
        """
        __, from_email = (
            self.env['res.partner']._parse_partner_name(msg_dict['from'])
            if msg_dict.get('from')
            else (False, False)
        )
        email_addr, email_domain = from_email.split('@')

        alias_domain = self.sudo().env["ir.config_parameter"].get_param(
            "mail.catchall.domain")
        if not alias_domain:
            # If alias domain is no configured, then assume that everything is
            # ok
            return
        if alias_domain.lower().strip() != email_domain.lower().strip():
            # If email come from different domain then everything seems to be
            # ok
            return

        check_domain = [
            ('alias_name', 'ilike', email_addr),
        ]
        if self.env['mail.alias'].search(check_domain, limit=1):
            raise ValueError(
                "Cannot create request from email sent from alias '%s'!\n"
                "Possible infinite loop, thus this email will be skipped!\n"
                "Subject: %s\n"
                "From: %s\n"
                "To: %s\n"
                "Message ID: %s" % (from_email,
                                    msg_dict.get('subject'),
                                    msg_dict.get('from'),
                                    msg_dict.get('to'),
                                    msg_dict.get('message_id')))

    def _validate_incoming_message(self, msg_dict):
        """ Validate incoming message, and if it is not acceptable,
            then raise error.

            This method could be overriden in third-party modules
            to provide extra validation options.
        """
        self._ensure_email_from_is_not_alias(msg_dict)

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """ Overrides mail_thread message_new that is called by the mailgateway
            through message_process.
            This override updates the document according to the email.
        """
        self._validate_incoming_message(msg_dict)
        company = self.env.user.company_id
        Partner = self.env['res.partner']
        defaults = dict(custom_values) if custom_values is not None else {}

        # Ensure we have message_id
        if not msg_dict.get('message_id'):
            msg_dict['message_id'] = self.env['mail.message']._get_message_id(
                msg_dict)

        # Compute default request text
        request_text = MAIL_REQUEST_TEXT_TMPL % {
            'subject': msg_dict.get('subject', _("No Subject")),
            'body': msg_dict.get('body', ''),
        }

        author_name, author_email = (
            Partner._parse_partner_name(msg_dict['from'])
            if msg_dict.get('from')
            else (False, False)
        )

        # Update defaults with partner and created_by_id if possible
        defaults.update({
            'name': "###new###",  # Spec name to avoid using subj as req name
            'request_text': request_text,
            'original_message_id': msg_dict['message_id'],
            'email_from': author_email,
            'email_cc': msg_dict.get('cc', ''),
        })
        author_id = msg_dict.get('author_id')

        # Create author from email if needed
        create_author = company.request_mail_create_author_contact_from_email
        if not author_id and create_author:
            author_id = self._get_or_create_partner_from_email(
                msg_dict['from'], force_create=True)
            if author_id:
                msg_dict['author_id'] = author_id

        if author_id:
            author = self.env['res.partner'].browse(author_id)
            defaults['author_id'] = author.id
            # TODO: May be we have to rely on autodetection of partner?
            #       (without explicitly setting it here)
            defaults['partner_id'] = author.commercial_partner_id.id
            if len(author.user_ids) == 1:
                defaults['created_by_id'] = author.user_ids[0].id
        else:
            author = False
            defaults['author_id'] = False
            defaults['partner_id'] = False
            defaults['author_name'] = author_name
        channel_mail = self.env.ref(
            'generic_request.request_channel_email',
            raise_if_not_found=False)
        if channel_mail and channel_mail.sudo().active:
            defaults['channel_id'] = channel_mail.id

        request = super(RequestRequest, self).message_new(
            msg_dict, custom_values=defaults)

        # Find partners from emails (cc) and subscribe them if needed
        partner_ids = request._mail_find_partner_from_emails(
            self._find_emails_from_msg(msg_dict),
            force_create=company.request_mail_create_cc_contact_from_email)
        partner_ids = [p.id for p in partner_ids if p]

        if author:
            request.message_subscribe([author.id])

        # Subscribe partners if needed
        if partner_ids and company.request_mail_auto_subscribe_cc_contacts:
            request.message_subscribe(partner_ids)
        return request

    def message_update(self, msg, update_vals=None):
        # Subscribe partners found in received email
        email_list = self._find_emails_from_msg(msg)
        company = self.env.user.company_id

        # contacts mentioned in cc
        partner_ids = self._mail_find_partner_from_emails(
            email_list,
            force_create=company.request_mail_create_cc_contact_from_email)
        partner_ids = [p.id for p in partner_ids if p]
        if partner_ids and company.request_mail_auto_subscribe_cc_contacts:
            self.message_subscribe(partner_ids)

        return super(RequestRequest, self).message_update(
            msg, update_vals=update_vals)

    def request_add_suggested_recipients(self, recipients):
        for record in self:
            if record.author_id:
                reason = _('Author')
                record._message_add_suggested_recipient(
                    recipients, partner=record.author_id, reason=reason)
            elif record.email_from:
                record._message_add_suggested_recipient(
                    recipients,
                    email="%s <%s>" % (record.author_name, record.email_from),
                    reason=_('Author Email'))
            if (record.email_cc and
                    self.env.user.company_id.request_mail_suggest_global_cc):
                for email in tools.email_split(record.email_cc):
                    record._message_add_suggested_recipient(
                        recipients, email=email,
                        reason=_('Global CC'))
            if (record.partner_id and
                    self.env.user.company_id.request_mail_suggest_partner):
                reason = _('Partner')
                record._message_add_suggested_recipient(
                    recipients, partner=record.partner_id, reason=reason)

    def _message_get_suggested_recipients(self):
        recipients = super(
            RequestRequest, self
        )._message_get_suggested_recipients()
        try:
            self.request_add_suggested_recipients(recipients)
        except exceptions.AcccessError:  # pylint: disable=except-pass
            pass
        return recipients

    def _message_post_after_hook(self, message, msg_vals, *args, **kwargs):
        # Overridden to add update request text with data from original message
        # This is required to make images display correctly,
        # because usualy, in emails, image's src looks liks:
        #     src="cid:ii_151b51a290ed6a91"
        if self and self.original_message_id == message.message_id:
            # We have to add this processing only in case when request is
            # created from email, and in this case, this method is called on
            # recordset with single record
            self.with_context(
                mail_notrack=True,
            ).write({
                'request_text': MAIL_REQUEST_TEXT_TMPL % {
                    'subject': message.subject,
                    'body': message.body,
                },
                'original_message_id': False,
            })

        return super(RequestRequest, self)._message_post_after_hook(
            message, msg_vals, *args, **kwargs
        )

    def _close_mail_activities_for_user(self, user):
        self.ensure_one()
        user_activities = self.env['mail.activity'].search([
            ('res_id', '=', self.id),
            ('res_model', '=', self._name),
            ('user_id', '=', user.id)
        ])
        for activity in user_activities:
            activity.action_feedback(
                _('Closing this activity because assignee was unsubscribed!'))

    def _mail_track(self, tracked_fields, initial):
        # This method is overriden to adjusts the tracked fields in the
        # request by removing either
        # 'deadline_date' or 'deadline_date_dt' (both with tracking=True)
        # from tracked_fields, based on the datetime format configured for
        # the request type.
        deadline_format = self.type_id.deadline_format
        if deadline_format == 'date':
            tracked_fields.pop('deadline_date_dt', None)
        elif deadline_format == 'datetime':
            tracked_fields.pop('deadline_date', None)
        changes, tracking_value_ids = super()._mail_track(tracked_fields,
                                                          initial)
        return changes, tracking_value_ids

    def api_move_request(self, route_id):
        """ This method could be used to move request via specified route.
            In case of specified route is closing route, then it will return
            dictionary that describes action to open request's closing wizard.

            :param int route_id: ID for request's route to move request.
        """
        self.ensure_one()
        route = self.env['request.stage.route'].browse(route_id)
        if route in self.stage_id.route_out_ids:
            if route.close:
                return self.env[
                    'generic.mixin.get.action'
                ].get_action_by_xmlid(
                    'generic_request.action_request_wizard_close',
                    context={
                        'default_request_id': self.id,
                        'default_close_route_id': route_id,
                        'name_only': True,
                    })
            self.stage_id = route.stage_to_id.id
            return None

        raise exceptions.UserError(_(
            "Cannot move request (%(request)s) by this route (%(route)s)"
        ) % {
            'request': self.name,
            'route': route.display_name,
        })

    @api.model
    def _scheduler_check_deadlines(self):
        """ Check deadline dates and trigger events:
            - Deadline Tomorrow
            - Deadline Today
            - Deadline Overdue
            if needed
        """
        current_datetime = fields.Datetime.now()
        today_date = current_datetime.date()
        today_dt_begin = datetime.combine(today_date, time.min)
        today_dt_end = datetime.combine(today_date, time.max)

        tomorrow_date = today_date + relativedelta(days=1)
        tomorrow_dt_begin = datetime.combine(tomorrow_date, time.min)
        tomorrow_dt_end = datetime.combine(tomorrow_date, time.max)

        requests_deadline_tomorrow = self.sudo().search([
            ('closed', '=', False),
            ('deadline_date_dt', '>=', tomorrow_dt_begin),
            ('deadline_date_dt', '<=', tomorrow_dt_end),
            ('deadline_event_tomorrow_sent', '=', False)])
        requests_deadline_today = self.sudo().search([
            ('closed', '=', False),
            ('deadline_date_dt', '<=', today_dt_end),
            ('deadline_date_dt', '>=', current_datetime),
            ('deadline_event_today_sent', '=', False)])
        requests_deadline_today_overdue = self.sudo().search([
            ('closed', '=', False),
            ('deadline_date_dt', '>=', today_dt_begin),
            ('deadline_date_dt', '<', current_datetime),
            ('deadline_event_overdue_sent', '=', False)])
        requests_deadline_yesterday = self.sudo().search([
            ('closed', '=', False),
            ('deadline_date_dt', '<', today_dt_begin),
            ('deadline_event_overdue_sent', '=', False)])
        for request in requests_deadline_tomorrow:
            request.trigger_event('deadline-tomorrow')
            request.deadline_event_tomorrow_sent = True
        for request in requests_deadline_today:
            request.trigger_event('deadline-today')
            request.deadline_event_today_sent = True
        for request in requests_deadline_today_overdue:
            request.trigger_event('deadline-overdue')
            request.deadline_event_overdue_sent = True
        for request in requests_deadline_yesterday:
            request.trigger_event('deadline-overdue')
            request.deadline_event_overdue_sent = True

    def _request_timesheet_get_defaults(self):
        """ This method supposed to be overridden in other modules,
            to provide some additional default values for timesheet lines.
        """
        return {
            'request_id': self.id,
        }

    def action_close_request(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_wizard_close',
            context={
                'default_request_id': self.id,
                'name_only': True,
            })

    def action_start_work(self):
        self.ensure_one()
        TimesheetLines = self.env['request.timesheet.line']
        running_lines = TimesheetLines._find_running_lines()
        if running_lines:
            return self.env['generic.mixin.get.action'].get_action_by_xmlid(
                'generic_request.action_request_wizard_stop_work',
                context={
                    'default_timesheet_line_id': running_lines[0].id,
                    'request_timesheet_start_request_id': self.id,
                })

        data = self._request_timesheet_get_defaults()
        data['date_start'] = fields.Datetime.now()
        timesheet_line = TimesheetLines.create(data)
        self.trigger_event('timetracking-start-work', {
            'timesheet_line_id': timesheet_line.id,
        })
        return False

    def action_stop_work(self):
        self.ensure_one()
        TimesheetLines = self.env['request.timesheet.line']
        running_lines = TimesheetLines._find_running_lines()
        if running_lines:
            return self.env['generic.mixin.get.action'].get_action_by_xmlid(
                'generic_request.action_request_wizard_stop_work',
                context={'default_timesheet_line_id': running_lines[0].id})
        return False

    def action_request_view_timesheet_lines(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_timesheet_line',
            context={'default_request_id': self.id},
            domain=[('request_id', '=', self.id)],
        )

    def action_show_related_author_requests_closed(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            domain=[('author_id', '=', self.author_id.id),
                    ('id', '!=', self.id)],
            context={
                'search_default_filter_closed': 1,
            })

    def action_show_related_author_requests_opened(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            domain=[('author_id', '=', self.author_id.id),
                    ('id', '!=', self.id)],
            context={
                'search_default_filter_open': 1,
            })

    def action_show_related_partner_requests_closed(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            domain=[('partner_id', '=', self.partner_id.id),
                    ('id', '!=', self.id)],
            context={
                'search_default_filter_closed': 1,
            })

    def action_show_related_partner_requests_opened(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            domain=[('partner_id', '=', self.partner_id.id),
                    ('id', '!=', self.id)],
            context={
                'search_default_filter_open': 1,
            })

    def action_open_parent(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "request.request",
            "name": "Parent Request",
            "view_mode": "form",
            "target": "new",
            "res_id": self.parent_id.id
        }

    def action_button_show_subrequests(self):
        action = self.get_action_by_xmlid(
            'generic_request.action_request_window',
            context={'generic_request_parent_id': self.id,
                     'search_default_filter_open': True},
            domain=[('parent_id', '=', self.id)],
        )
        action.update({
            'name': _('Subrequests'),
            'display_name': _('Subrequests'),
        })
        return action

    def action_request_request_diagram(self):
        self.ensure_one()
        current_stage_id = self.stage_id.id
        highlight_color = self.sudo().type_id.current_stage_highlight_color
        action = self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_type_window',
            name=_('Workflow: %(request_name)s') % {
                'request_name': self.display_name,
            },
            context={'highlight_node_id': current_stage_id,
                     'highlight_node_color': highlight_color,
                     'diagram_readonly': True},
        )
        action.update({
            'res_model': 'request.type',
            'res_id': self.type_id.id,
            'views': [(False, 'diagram_plus')],
        })
        return action
