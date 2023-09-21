from odoo import models


class RequestRequest(models.Model):
    _inherit = "request.request"

    def action_request_assign(self):
        action = super(RequestRequest, self).action_request_assign()
        if self.team_id:
            action['context'].update({
                'default_assign_type': 'team',
                'default_assign_team_id': self.team_id.id,
            })
        return action
