from odoo import models, fields


class RequestType(models.Model):
    _inherit = 'request.type'

    send_default_assigned_team_notification = fields.Boolean(
        default=True)
    assigned_team_notification_show_request_text = fields.Boolean(
        default=True)
    assigned_team_notification_show_response_text = fields.Boolean(
        default=True)
