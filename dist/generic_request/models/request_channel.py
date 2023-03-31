import logging
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

_logger = logging.getLogger(__name__)


class RequestChannel(models.Model):
    # pylint: disable=too-many-locals
    _name = "request.channel"
    _description = "Request Channel"
    _inherit = [
        'generic.mixin.name_with_code',
        'generic.mixin.uniq_name_code',
        'generic.mixin.track.changes',
    ]
    _order = 'name, id'

    name = fields.Char(required=True, index=True)
    code = fields.Char()
    active = fields.Boolean(default=True, index=True)

    request_ids = fields.One2many(
        'request.request', 'channel_id', string='Requests')
    request_count = fields.Integer(
        compute='_compute_request_count', readonly=True)

    request_open_count = fields.Integer(
        compute="_compute_request_count", readonly=True)
    request_closed_count = fields.Integer(
        compute="_compute_request_count", readonly=True)
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

    def action_show_all_requests(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            context=dict(
                self.env.context,
                search_default_channel_id=self.id),
            domain=[('channel_id', '=', self.id)])

    def action_show_open_requests(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            context=dict(
                self.env.context,
                search_default_filter_open=1,
                search_default_channel_id=self.id),
            domain=[('channel_id', '=', self.id)])

    def action_show_closed_requests(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            context=dict(
                self.env.context,
                search_default_filter_closed=1,
                search_default_channel_id=self.id),
            domain=[('channel_id', '=', self.id)])

    def action_channel_request_open_today_count(self):
        self.ensure_one()
        today_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('date_created', '>=', today_start),
                ('closed', '=', False),
                ('channel_id', '=', self.id)])

    def action_channel_request_open_last_24h_count(self):
        self.ensure_one()
        yesterday = datetime.now() - relativedelta(days=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('date_created', '>', yesterday),
                ('closed', '=', False),
                ('channel_id', '=', self.id)])

    def action_channel_request_open_week_count(self):
        self.ensure_one()
        week_ago = datetime.now() - relativedelta(weeks=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('date_created', '>', week_ago),
                ('closed', '=', False),
                ('channel_id', '=', self.id)])

    def action_channel_request_open_month_count(self):
        self.ensure_one()
        month_ago = datetime.now() - relativedelta(months=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('date_created', '>', month_ago),
                ('closed', '=', False),
                ('channel_id', '=', self.id)])

    def action_channel_request_closed_today_count(self):
        self.ensure_one()
        today_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            context={'search_default_filter_closed': 1},
            domain=[
                ('date_closed', '>=', today_start),
                ('closed', '=', True),
                ('channel_id', '=', self.id)])

    def action_channel_request_closed_last_24h_count(self):
        self.ensure_one()
        yesterday = datetime.now() - relativedelta(days=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            context={'search_default_filter_closed': 1},
            domain=[
                ('date_closed', '>', yesterday),
                ('closed', '=', True),
                ('channel_id', '=', self.id)])

    def action_channel_request_closed_week_count(self):
        self.ensure_one()
        week_ago = datetime.now() - relativedelta(weeks=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            context={'search_default_filter_closed': 1},
            domain=[
                ('date_closed', '>', week_ago),
                ('closed', '=', True),
                ('channel_id', '=', self.id)])

    def action_channel_request_closed_month_count(self):
        self.ensure_one()
        month_ago = datetime.now() - relativedelta(months=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            context={'search_default_filter_closed': 1},
            domain=[
                ('date_closed', '>', month_ago),
                ('closed', '=', True),
                ('channel_id', '=', self.id)])

    def action_channel_request_deadline_today_count(self):
        self.ensure_one()
        today_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('deadline_date', '>=', today_start),
                ('closed', '=', False),
                ('channel_id', '=', self.id)])

    def action_channel_request_deadline_last_24h_count(self):
        self.ensure_one()
        yesterday = datetime.now() - relativedelta(days=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('deadline_date', '>', yesterday),
                ('closed', '=', False),
                ('channel_id', '=', self.id)])

    def action_channel_request_deadline_week_count(self):
        self.ensure_one()
        week_ago = datetime.now() - relativedelta(weeks=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('deadline_date', '>', week_ago),
                ('closed', '=', False),
                ('channel_id', '=', self.id)])

    def action_channel_request_deadline_month_count(self):
        self.ensure_one()
        month_ago = datetime.now() - relativedelta(months=1)
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('deadline_date', '>', month_ago),
                ('closed', '=', False),
                ('channel_id', '=', self.id)])

    def action_channel_request_unassigned_count(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_stat_request_count',
            domain=[
                ('user_id', '=', False),
                ('channel_id', '=', self.id)])
