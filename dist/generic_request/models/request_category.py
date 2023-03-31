from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class RequestCategory(models.Model):
    # pylint: disable=too-many-locals
    _name = "request.category"
    _inherit = [
        'generic.mixin.parent.names',
        'generic.mixin.name_with_code',
        'generic.mixin.track.changes',
        'mail.thread',
    ]
    _description = "Request Category"
    _order = 'sequence, name'

    _parent_name = "parent_id"
    _parent_store = True
    _parent_order = 'name'

    # Defined in generic.mixin.name_with_code
    name = fields.Char()
    code = fields.Char()

    parent_id = fields.Many2one(
        'request.category', 'Parent', index=True, ondelete='cascade')
    parent_path = fields.Char(index=True)

    active = fields.Boolean(default=True, index=True)

    description = fields.Text(translate=True)
    help_html = fields.Html(translate=True)

    # Access rignts
    access_group_ids = fields.Many2many(
        'res.groups', string='Access groups',
        help="If user belongs to one of groups specified in this field,"
             " then he will be able to select this category during request"
             " creation, even if this category is not published."
    )

    # Stat
    request_ids = fields.One2many(
        'request.request', 'category_id', 'Requests', readonly=True)
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

    request_type_ids = fields.Many2many(
        'request.type',
        'request_type_category_rel', 'category_id', 'type_id',
        string="Request types")
    request_type_count = fields.Integer(
        compute='_compute_request_type_count')
    sequence = fields.Integer(index=True, default=5)
    color = fields.Integer()  # for many2many_tags widget

    service_ids = fields.Many2many(
        'generic.service', 'service_category_rel',
        'category_id', 'service_id', string='Service')

    _sql_constraints = [
        ('name_uniq',
         'UNIQUE (parent_id, name)',
         'Category name must be unique.'),
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

    @api.depends('request_type_ids')
    def _compute_request_type_count(self):
        for record in self:
            record.request_type_count = len(record.request_type_ids)

    def action_category_request_open_today_count(self):
        self.ensure_one()
        today_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('date_created', '>=', today_start),
                ('closed', '=', False),
                ('category_id', '=', self.id)])

    def action_category_request_open_last_24h_count(self):
        self.ensure_one()
        yesterday = datetime.now() - relativedelta(days=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('date_created', '>', yesterday),
                ('closed', '=', False),
                ('category_id', '=', self.id)])

    def action_category_request_open_week_count(self):
        self.ensure_one()
        week_ago = datetime.now() - relativedelta(weeks=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('date_created', '>', week_ago),
                ('closed', '=', False),
                ('category_id', '=', self.id)])

    def action_category_request_open_month_count(self):
        self.ensure_one()
        month_ago = datetime.now() - relativedelta(months=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('date_created', '>', month_ago),
                ('closed', '=', False),
                ('category_id', '=', self.id)])

    def action_category_request_closed_today_count(self):
        self.ensure_one()
        today_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            context={'search_default_filter_closed': 1},
            domain=[
                ('date_closed', '>=', today_start),
                ('closed', '=', True),
                ('category_id', '=', self.id)])

    def action_category_request_closed_last_24h_count(self):
        self.ensure_one()
        yesterday = datetime.now() - relativedelta(days=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            context={'search_default_filter_closed': 1},
            domain=[
                ('date_closed', '>', yesterday),
                ('closed', '=', True),
                ('category_id', '=', self.id)])

    def action_category_request_closed_week_count(self):
        self.ensure_one()
        week_ago = datetime.now() - relativedelta(weeks=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            context={'search_default_filter_closed': 1},
            domain=[
                ('date_closed', '>', week_ago),
                ('closed', '=', True),
                ('category_id', '=', self.id)])

    def action_category_request_closed_month_count(self):
        self.ensure_one()
        month_ago = datetime.now() - relativedelta(months=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            context={'search_default_filter_closed': 1},
            domain=[
                ('date_closed', '>', month_ago),
                ('closed', '=', True),
                ('category_id', '=', self.id)])

    def action_category_request_deadline_today_count(self):
        self.ensure_one()
        today_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('deadline_date', '>=', today_start),
                ('closed', '=', False),
                ('category_id', '=', self.id)])

    def action_category_request_deadline_last_24h_count(self):
        self.ensure_one()
        yesterday = datetime.now() - relativedelta(days=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('deadline_date', '>', yesterday),
                ('closed', '=', False),
                ('category_id', '=', self.id)])

    def action_category_request_deadline_week_count(self):
        self.ensure_one()
        week_ago = datetime.now() - relativedelta(weeks=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('deadline_date', '>', week_ago),
                ('closed', '=', False),
                ('category_id', '=', self.id)])

    def action_category_request_deadline_month_count(self):
        self.ensure_one()
        month_ago = datetime.now() - relativedelta(months=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('deadline_date', '>', month_ago),
                ('closed', '=', False),
                ('category_id', '=', self.id)])

    def action_category_request_unassigned_count(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('user_id', '=', False),
                ('category_id', '=', self.id)],
        )
