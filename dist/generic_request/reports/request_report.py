from odoo import models, fields

from odoo.addons.generic_mixin.tools.sql import create_sql_view

from ..constants import (
    AVAILABLE_PRIORITIES,
)


class RequestReport(models.Model):
    _name = 'request.report'
    _inherit = 'generic.mixin.get.action'
    _description = 'Request Report'
    _auto = False
    _order = 'id DESC'

    # Tags
    request_id = fields.Integer(readonly=True)
    request_name = fields.Char(string='Name', readonly=True)
    request_request_text_sample = fields.Text(string='Text')
    request_date_created = fields.Datetime(string='Created', readonly=True)
    request_is_closed = fields.Boolean(string='Is Closed', readonly=True)
    request_closed_by = fields.Many2one(
        comodel_name='res.users',
        string='Closed by',
        readonly=True,
        help='Request was closed by this user')
    request_date_closed = fields.Datetime(string='Closed', readonly=True)
    request_created_by_id = fields.Many2one(
        'res.users', string='Created by', readonly=True,
        help='Request was created by this user')
    request_author_id = fields.Many2one(
        'res.partner', string='Author', readonly=True,
        help='Author of this request')
    request_channel_id = fields.Many2one(
        'request.channel', string='Channel', readonly=True,
        help='Channel of request')

    active = fields.Boolean(readonly=True)

    request_service_id = fields.Many2one(
        'generic.service', string='Service', readonly=True,
        help='Service of request')
    request_category_id = fields.Many2one(
        'request.category', string='Category', readonly=True,
        help='Category of request')
    request_type_id = fields.Many2one(
        'request.type', string='Type', readonly=True,
        help='Type of request')
    request_kind_id = fields.Many2one(
        'request.kind', string='Kind', readonly=True,
        help='Kind of request')
    request_kanban_state = fields.Selection(
        string='Kanban State',
        selection=[
            ('normal', 'In Progress'),
            ('blocked', 'Blocked'),
            ('done', 'Ready for next stage')],
        readonly=True)
    request_stage_type_id = fields.Many2one(
        'request.stage.type', string='Stage Type',
        readonly=True)
    request_stage_id = fields.Many2one(
        'request.stage', string='Stage',
        readonly=True)

    # Assigned to User
    # Assignad to Team
    request_user_id = fields.Many2one(
        'res.users', 'Assigned to user',
        readonly=True,
        help="User responsible for next action on this request.")
    request_is_user_assigned = fields.Boolean(
        string='User Assigned', readonly=True)
    # TODO: Clarify what the meaning should be here.
    # is_assigned_team = fields.Boolean(readonly=True)

    request_deadline_date = fields.Date(string='Deadline', readonly=True)

    request_priority = fields.Selection(
        string='Priority',
        selection=AVAILABLE_PRIORITIES,
        readonly=True,
        help='Actual priority of request')
    request_service_level_id = fields.Many2one(
        'generic.service.level',
        string='Service Level', readonly=True,
        help='Service of request. Used to compute SLA for request.')

    request_company_id = fields.Many2one(
        'res.company', string='Company', readonly=True)
    request_partner_id = fields.Many2one(
        'res.partner', string='Partner', readonly=True,
        help='Partner related to this request')

    planned_amount = fields.Float(
        string='Planned Amount Hours', readonly=True,
        help='The amount of hours planned to work on the request.')
    total_amount = fields.Float(
        string='Total Amount Hours', readonly=True,
        help='The amount of hours spent working on the request.')
    remaining_amount = fields.Float(
        readonly=True, help="Remaining time")

    def _get_request_fields(self):
        """ Get list of fields to read from request.
            Return: [(request_field, select_as_field)]
        """
        return [
            ('name', 'request_name'),
            ('id', 'request_id'),
            ('request_text_sample', 'request_request_text_sample'),
            ('date_created', 'request_date_created'),
            ('date_closed', 'request_date_closed'),
            ('created_by_id', 'request_created_by_id'),
            ('author_id', 'request_author_id'),
            ('channel_id', 'request_channel_id'),
            ('active', 'active'),
            ('closed', 'request_is_closed'),
            ('closed_by_id', 'request_closed_by'),

            ('service_id', 'request_service_id'),
            ('category_id', 'request_category_id'),
            ('type_id', 'request_type_id'),
            ('kind_id', 'request_kind_id'),
            ('kanban_state', 'request_kanban_state'),
            ('stage_type_id', 'request_stage_type_id'),
            ('stage_id', 'request_stage_id'),

            ('user_id', 'request_user_id'),
            ('is_assigned', 'request_is_user_assigned'),
            ('deadline_date_dt', 'request_deadline_date'),
            ('priority', 'request_priority'),
            ('service_level_id', 'request_service_level_id'),
            ('company_id', 'request_company_id'),
            ('partner_id', 'request_partner_id'),

            ('timesheet_planned_amount', 'planned_amount'),
            ('timesheet_amount', 'total_amount'),
            ('timesheet_remaining_amount', 'remaining_amount'),
        ]

    def init(self):
        create_sql_view(
            self.env.cr, self._table,
            """
                SELECT
                    req.id AS id,
                    %(request_fields)s
                FROM request_request AS req
            """ % {
                'request_fields': ", ".join((
                    "%s AS %s" % r for r in self._get_request_fields()
                ))
            })  # nosec

    def action_view_report_requests(self):
        self.ensure_one()
        action = self.get_action_by_xmlid(
            xmlid='generic_request.action_request_window',
            )
        action.update({
            'res_id': self.request_id,
            'views': [(False, 'form')],
        })
        return action
