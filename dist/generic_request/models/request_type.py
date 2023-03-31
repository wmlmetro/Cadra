from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m
from .request_request import (AVAILABLE_PRIORITIES,
                              AVAILABLE_IMPACTS,
                              AVAILABLE_URGENCIES)


class RequestType(models.Model):
    # pylint: disable=too-many-locals
    _name = "request.type"
    _inherit = [
        'mail.thread',
        'generic.mixin.name_with_code',
        'generic.mixin.track.changes',
    ]
    _description = "Request Type"
    _order = 'name, id'

    name = fields.Char(copy=False)
    code = fields.Char(copy=False)
    kind_id = fields.Many2one('request.kind', index=True)
    active = fields.Boolean(default=True, index=True)
    description = fields.Text(translate=True)
    note_html = fields.Html(
        translate=True,
        help="Short note about request type, that will"
             " be displayed just before request text.")
    instruction_html = fields.Html(translate=True)
    default_request_text = fields.Html(translate=True)
    help_html = fields.Html(translate=True)
    category_ids = fields.Many2many(
        'request.category',
        'request_type_category_rel', 'type_id', 'category_id',
        'Categories', required=False, index=True)

    tag_category_ids = fields.Many2many(
        'generic.tag.category', 'request_type_tag_category_rel',
        'type_id', 'category_id', string='Tag Categories',
        domain=[('model_id.model', '=', 'request.request')],
        help='Restrict available tags for requests of this type '
             'by these categories')

    # Priority configuration
    complex_priority = fields.Boolean(
        default=False,
        help="When creating request, users select "
             "Impact and Urgency of request. Priority "
             "will be automatically computed depending on "
             "these parameters"
    )
    default_priority = fields.Selection(
        selection=AVAILABLE_PRIORITIES,
        default='3'
    )
    default_impact = fields.Selection(
        selection=AVAILABLE_IMPACTS,
        default='2'
    )
    default_urgency = fields.Selection(
        selection=AVAILABLE_URGENCIES,
        default='2'
    )

    # Stages
    stage_ids = fields.One2many(
        'request.stage', 'request_type_id', string='Stages', copy=True)
    stage_count = fields.Integer(
        compute='_compute_stage_count', readonly=True)
    start_stage_id = fields.Many2one(
        'request.stage', ondelete='set null',
        compute='_compute_start_stage_id', readonly=True, store=True,
        help="The initial stage for new requests of this type. To change, "
             "on the Stages page, click the crossed arrows icon and drag "
             "the desired stage to the top of the list.")
    color = fields.Char(default='rgba(240,240,240,1)')

    # Routes
    route_ids = fields.One2many(
        'request.stage.route', 'request_type_id',
        string='Stage Routes')
    route_count = fields.Integer(
        'Routes', compute='_compute_route_count', readonly=True)

    sequence_id = fields.Many2one(
        'ir.sequence', 'Sequence', ondelete='restrict',
        help="Use this sequence to generate names for requests for this type")

    # Access rignts
    access_group_ids = fields.Many2many(
        'res.groups', string='Access groups',
        help="If user belongs to one of groups specified in this field,"
             " then he will be able to select this type during request"
             " creation, even if this category is not published."
    )
    # Requests
    request_ids = fields.One2many(
        'request.request', 'type_id', 'Requests', readonly=True, copy=False)
    request_count = fields.Integer(
        'All Requests', compute='_compute_request_count', readonly=True)
    request_open_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="Open Requests")
    request_closed_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="Closed Requests")
    # Open requests
    request_open_today_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="New Requests For Today")
    request_open_last_24h_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="New Requests For Last 24 Hour")
    request_open_week_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="New Requests For Week")
    request_open_month_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="New Requests For Month")
    # Closed requests
    request_closed_today_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="Closed Requests For Today")
    request_closed_last_24h_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="Closed Requests For Last 24 Hour")
    request_closed_week_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="Closed Requests For Week")
    request_closed_month_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="Closed Requests For Month")
    # Deadline requests
    request_deadline_today_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="Deadline Requests For Today")
    request_deadline_last_24h_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="Deadline Requests For Last 24 Hour")
    request_deadline_week_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="Deadline Requests For Week")
    request_deadline_month_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="Deadline Requests For Month")
    # Unassigned requests
    request_unassigned_count = fields.Integer(
        compute="_compute_request_count", readonly=True,
        string="Unassigned Requests")

    # Notification Settins
    send_default_created_notification = fields.Boolean(default=True)
    created_notification_show_request_text = fields.Boolean(default=True)
    created_notification_show_response_text = fields.Boolean(default=False)
    send_default_assigned_notification = fields.Boolean(default=True)
    assigned_notification_show_request_text = fields.Boolean(default=True)
    assigned_notification_show_response_text = fields.Boolean(default=False)
    send_default_closed_notification = fields.Boolean(default=True)
    closed_notification_show_request_text = fields.Boolean(default=True)
    closed_notification_show_response_text = fields.Boolean(default=True)
    send_default_reopened_notification = fields.Boolean(default=True)
    reopened_notification_show_request_text = fields.Boolean(default=True)
    reopened_notification_show_response_text = fields.Boolean(default=False)

    # Timesheets
    use_timesheet = fields.Boolean()
    timesheet_activity_ids = fields.Many2many(
        comodel_name='request.timesheet.activity',
        relation='request_type__timesheet_activity__rel',
        column1='request_type_id',
        column2='activity_id')

    service_ids = fields.Many2many(
        'generic.service', 'generic_service_request_type_rel',
        'type_id', 'service_id', string='Service')

    _sql_constraints = [
        ('name_uniq',
         'UNIQUE (name)',
         'Name must be unique.'),
        ('code_uniq',
         'UNIQUE (code)',
         'Code must be unique.'),
    ]

    @api.depends('request_ids')
    def _compute_request_count(self):
        now = datetime.now()
        today_start = now.replace(
            hour=0, minute=0, second=0, microsecond=0)
        yesterday = now - relativedelta(days=1)
        week_ago = now - relativedelta(weeks=1)
        month_ago = now - relativedelta(months=1)
        mapped_data_all = read_counts_for_o2m(
            records=self,
            field_name='request_ids')
        mapped_data_closed = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('closed', '=', True)])
        mapped_data_open = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('closed', '=', False)])
        mapped_data_open_today = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('date_created', '>=', today_start),
                    ('closed', '=', False)])
        mapped_data_open_last_24h = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('date_created', '>', yesterday),
                    ('closed', '=', False)])
        mapped_data_open_week = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('date_created', '>', week_ago),
                    ('closed', '=', False)])
        mapped_data_open_month = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('date_created', '>', month_ago),
                    ('closed', '=', False)])
        mapped_data_closed_today = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('date_closed', '>=', today_start),
                    ('closed', '=', True)])
        mapped_data_closed_24h = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('date_closed', '>', yesterday),
                    ('closed', '=', True)])
        mapped_data_closed_week = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('date_closed', '>', week_ago),
                    ('closed', '=', True)])
        mapped_data_closed_month = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('date_closed', '>', month_ago),
                    ('closed', '=', True)])
        mapped_deadline_today = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('deadline_date', '>=', today_start),
                    ('closed', '=', False)])
        mapped_deadline_24 = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('deadline_date', '>', yesterday),
                    ('closed', '=', False)])
        mapped_deadline_week = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('deadline_date', '>', week_ago),
                    ('closed', '=', False)])
        mapped_deadline_month = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('deadline_date', '>', month_ago),
                    ('closed', '=', False)])
        mapped_unassigned = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('user_id', '=', False)])
        for record in self:
            record.request_count = mapped_data_all.get(record.id, 0)
            record.request_closed_count = mapped_data_closed.get(record.id, 0)
            record.request_open_count = mapped_data_open.get(record.id, 0)

            # Open requests
            record.request_open_today_count = mapped_data_open_today.get(
                record.id, 0)
            record.request_open_last_24h_count = mapped_data_open_last_24h.get(
                record.id, 0)
            record.request_open_week_count = mapped_data_open_week.get(
                record.id, 0)
            record.request_open_month_count = mapped_data_open_month.get(
                record.id, 0)

            # Closed requests
            record.request_closed_today_count = mapped_data_closed_today.get(
                record.id, 0)
            record.request_closed_last_24h_count = mapped_data_closed_24h.get(
                record.id, 0)
            record.request_closed_week_count = mapped_data_closed_week.get(
                record.id, 0)
            record.request_closed_month_count = mapped_data_closed_month.get(
                record.id, 0)

            # Deadline requests
            record.request_deadline_today_count = mapped_deadline_today.get(
                record.id, 0)
            record.request_deadline_last_24h_count = mapped_deadline_24.get(
                record.id, 0)
            record.request_deadline_week_count = mapped_deadline_week.get(
                record.id, 0)
            record.request_deadline_month_count = mapped_deadline_month.get(
                record.id, 0)

            # Unassigned requests
            record.request_unassigned_count = mapped_unassigned.get(
                record.id, 0)

    @api.depends('stage_ids')
    def _compute_stage_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='stage_ids')
        for record in self:
            record.stage_count = mapped_data.get(record.id, 0)

    @api.depends('route_ids')
    def _compute_route_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='route_ids')
        for record in self:
            record.route_count = mapped_data.get(record.id, 0)

    @api.depends('stage_ids', 'stage_ids.sequence',
                 'stage_ids.request_type_id')
    def _compute_start_stage_id(self):
        """ Compute start stage for requests of this type
            using following logic:

            - stages have field 'sequence'
            - stages are ordered by value of this field.
            - it is possible from ui to change stage order by dragging them
            - get first stage for stages related to this type

        """
        for rtype in self:
            if rtype.stage_ids:
                rtype.start_stage_id = rtype.stage_ids.sorted(
                    key=lambda r: r.sequence)[0]
            else:
                rtype.start_stage_id = False

    def _create_default_stages_and_routes(self):
        self.ensure_one()
        stage_new = self.env['request.stage'].create({
            'name': _('New'),
            'code': 'new',
            'request_type_id': self.id,
            'sequence': 5,
            'type_id': self.env.ref(
                'generic_request.request_stage_type_draft').id,
        })
        stage_close = self.env['request.stage'].create({
            'name': _('Closed'),
            'code': 'close',
            'request_type_id': self.id,
            'sequence': 10,
            'closed': True,
            'type_id': self.env.ref(
                'generic_request.request_stage_type_closed_ok').id,
        })
        self.env['request.stage.route'].create({
            'name': _('Close'),
            'stage_from_id': stage_new.id,
            'stage_to_id': stage_close.id,
            'request_type_id': self.id,
        })

    @api.model
    def create(self, vals):
        r_type = super(RequestType, self).create(vals)

        if not r_type.start_stage_id and self.env.context.get(
                'create_default_stages'):
            r_type._create_default_stages_and_routes()

        return r_type

    def action_create_default_stage_and_routes(self):
        self._create_default_stages_and_routes()

    def action_request_type_diagram(self):
        self.ensure_one()
        action = self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_type_window',
            name=_('Workflow: %(type_name)s') % {
                'type_name': self.display_name,
            },
            context={'default_request_type_id': self.id},
        )
        action.update({
            'res_model': 'request.type',
            'res_id': self.id,
            'views': [(False, 'diagram_plus'), (False, 'form')],
        })
        return action

    def action_type_request_open_today_count(self):
        self.ensure_one()
        today_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('date_created', '>=', today_start),
                ('closed', '=', False),
                ('type_id', '=', self.id)])

    def action_type_request_open_last_24h_count(self):
        self.ensure_one()
        yesterday = datetime.now() - relativedelta(days=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('date_created', '>', yesterday),
                ('closed', '=', False),
                ('type_id', '=', self.id)])

    def action_type_request_open_week_count(self):
        self.ensure_one()
        week_ago = datetime.now() - relativedelta(weeks=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('date_created', '>', week_ago),
                ('closed', '=', False),
                ('type_id', '=', self.id)])

    def action_type_request_open_month_count(self):
        self.ensure_one()
        month_ago = datetime.now() - relativedelta(months=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('date_created', '>', month_ago),
                ('closed', '=', False),
                ('type_id', '=', self.id)])

    def action_type_request_closed_today_count(self):
        self.ensure_one()
        today_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            context={'search_default_filter_closed': 1},
            domain=[
                ('date_closed', '>=', today_start),
                ('closed', '=', True),
                ('type_id', '=', self.id)])

    def action_type_request_closed_last_24h_count(self):
        self.ensure_one()
        yesterday = datetime.now() - relativedelta(days=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            context={'search_default_filter_closed': 1},
            domain=[
                ('date_closed', '>', yesterday),
                ('closed', '=', True),
                ('type_id', '=', self.id)])

    def action_type_request_closed_week_count(self):
        self.ensure_one()
        week_ago = datetime.now() - relativedelta(weeks=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            context={'search_default_filter_closed': 1},
            domain=[
                ('date_closed', '>', week_ago),
                ('closed', '=', True),
                ('type_id', '=', self.id)])

    def action_type_request_closed_month_count(self):
        self.ensure_one()
        month_ago = datetime.now() - relativedelta(months=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            context={'search_default_filter_closed': 1},
            domain=[
                ('date_closed', '>', month_ago),
                ('closed', '=', True),
                ('type_id', '=', self.id)])

    def action_type_request_deadline_today_count(self):
        self.ensure_one()
        today_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('deadline_date', '>=', today_start),
                ('closed', '=', False),
                ('type_id', '=', self.id)])

    def action_type_request_deadline_last_24h_count(self):
        self.ensure_one()
        yesterday = datetime.now() - relativedelta(days=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('deadline_date', '>', yesterday),
                ('closed', '=', False),
                ('type_id', '=', self.id)])

    def action_type_request_deadline_week_count(self):
        self.ensure_one()
        week_ago = datetime.now() - relativedelta(weeks=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('deadline_date', '>', week_ago),
                ('closed', '=', False),
                ('type_id', '=', self.id)])

    def action_type_request_deadline_month_count(self):
        self.ensure_one()
        month_ago = datetime.now() - relativedelta(months=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('deadline_date', '>', month_ago),
                ('closed', '=', False),
                ('type_id', '=', self.id)])

    def action_type_request_unassigned_count(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('user_id', '=', False),
                ('type_id', '=', self.id)])
