from odoo import models, fields, api
from odoo.osv import expression

from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m
from odoo.addons.crnd_web_m2o_info_widget import helper_get_many2one_info_data


class ResUsers(models.Model):
    _inherit = 'res.users'

    assigned_request_ids = fields.One2many(
        'request.request', 'user_id', readonly=True,
        string="Assigned Requests To User")
    created_request_ids = fields.One2many(
        'request.request', 'created_by_id', readonly=True,
        string="Created Requests By User")

    # Assigned requests stat (stored)
    assigned_request_count = fields.Integer(
        compute="_compute_request_stored_fields", readonly=True, store=True,
        string="Assigned Requests Count")
    assigned_request_open_count = fields.Integer(
        compute="_compute_request_stored_fields", readonly=True, store=True,
        string="Assigned Open Requests To User")
    assigned_request_closed_count = fields.Integer(
        compute="_compute_request_stored_fields", readonly=True, store=True,
        string="Assigned Closed Requests")

    # Requests stat (non-stored)
    created_request_count = fields.Integer(
        compute="_compute_request_non_stored_fields",
        readonly=True, store=False,
        string="Created Requests")
    authored_request_count = fields.Integer(
        compute="_compute_request_non_stored_fields",
        readonly=True, store=False,
        string="Authored Requests")
    total_request_count = fields.Integer(
        compute='_compute_request_non_stored_fields',
        readonly=True, store=False,
        string="Total Requests")
    # This is technical field used to display the total count of requests
    # on res.users form in statbutton
    statbutton_total_request_count = fields.Integer(
        compute='_compute_request_non_stored_fields',
        readonly=True, store=False)
    total_request_open_count = fields.Integer(
        compute='_compute_request_non_stored_fields',
        readonly=True, store=False,
        string="Total Open Requests")
    total_request_closed_count = fields.Integer(
        compute='_compute_request_non_stored_fields',
        readonly=True, store=False,
        string="Total Closed Requests")

    @api.depends('assigned_request_ids', 'assigned_request_ids.closed',
                 'created_request_ids', 'created_request_ids.closed')
    def _compute_request_stored_fields(self):
        assigned_map = read_counts_for_o2m(
            records=self,
            field_name='assigned_request_ids',
            sudo=True)
        assigned_open_map = read_counts_for_o2m(
            records=self,
            field_name='assigned_request_ids',
            domain=[('closed', '=', False)],
            sudo=True)
        assigned_closed_map = read_counts_for_o2m(
            records=self,
            field_name='assigned_request_ids',
            domain=[('closed', '=', True)],
            sudo=True)
        for record in self:
            record.assigned_request_count = assigned_map.get(record.id, 0)
            record.assigned_request_open_count = assigned_open_map.get(
                record.id, 0)
            record.assigned_request_closed_count = assigned_closed_map.get(
                record.id, 0)

    @api.depends('assigned_request_ids', 'assigned_request_ids.closed',
                 'created_request_ids', 'created_request_ids.closed',
                 'partner_id.request_by_author_ids',
                 'partner_id.request_by_partner_ids.closed',
                 'partner_id.request_by_author_ids',
                 'partner_id.request_by_partner_ids.closed',)
    def _compute_request_non_stored_fields(self):
        RequestRequest = self.env['request.request']
        for record in self:
            record.created_request_count = RequestRequest.search_count([
                ('created_by_id', '=', record.id),
            ])
            record.authored_request_count = RequestRequest.search_count([
                ('author_id', '=', record.partner_id.id),
            ])
            record.total_request_count = RequestRequest.search_count([
                '|', '|', '|',
                ('created_by_id', '=', record.id),
                ('user_id', '=', record.id),
                ('author_id', '=', record.partner_id.id),
                ('partner_id', '=', record.partner_id.id),
            ])
            record.statbutton_total_request_count = record.total_request_count
            record.total_request_open_count = RequestRequest.search_count([
                ('closed', '=', False),
                '|', '|', '|',
                ('created_by_id', '=', record.id),
                ('user_id', '=', record.id),
                ('author_id', '=', record.partner_id.id),
                ('partner_id', '=', record.partner_id.id),
            ])
            record.total_request_closed_count = RequestRequest.search_count([
                ('closed', '=', True),
                '|', '|', '|',
                ('created_by_id', '=', record.id),
                ('user_id', '=', record.id),
                ('author_id', '=', record.partner_id.id),
                ('partner_id', '=', record.partner_id.id),
            ])

    def action_show_related_requests(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            domain=expression.OR([
                [('created_by_id', 'in', self.ids)],
                [('user_id', 'in', self.ids)],
                [('partner_id', 'in', self.partner_id.ids)],
                [('author_id', 'in', self.partner_id.ids)],
            ]),
            context=dict(
                self.env.context,
                default_partner_id=self.partner_id.commercial_partner_id.id,
                default_author_id=self.partner_id.id,
            ))

    def _request_helper_m2o_info_get_fields(self):
        """ Find list of fields, that have to be displayed as user info
            on request form view in 'm2o_info' fields.

            Could be overridden by third-party modules.
        """
        return [
            'name', 'commercial_company_name', 'website',
            'email', 'phone', 'mobile'
        ]

    def request_helper_m2o_info(self):
        """ Technical method, that is used to perepear data for
            m2o_info fields.
        """
        return helper_get_many2one_info_data(
            self,
            self._request_helper_m2o_info_get_fields())
