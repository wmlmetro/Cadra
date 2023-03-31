from odoo import models, fields


class GenericTeamMember(models.Model):
    _inherit = 'generic.team.member'

    assigned_request_count = fields.Integer(
        related="user_id.assigned_request_count",
        readonly=True, store=True,
        string="Assigned Requests Count")
    assigned_request_open_count = fields.Integer(
        related="user_id.assigned_request_open_count",
        readonly=True, store=True,
        string="Assigned Open Requests To User")
    assigned_request_closed_count = fields.Integer(
        related="user_id.assigned_request_closed_count",
        readonly=True, store=True,
        string="Assigned Closed Requests")
