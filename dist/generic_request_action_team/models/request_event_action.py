from odoo import models, fields


class RequestEventAction(models.Model):
    _inherit = "request.event.action"

    # Action assign
    assign_type = fields.Selection(
        selection_add=[('team', 'Team')])
    assign_team_id = fields.Many2one(
        'generic.team', 'Assign to Team', tracking=True)

    def _run_assign_team(self, request):
        request.write({
            'team_id': self.sudo().assign_team_id.id,
        })

    def _run_assign_dispatch(self, request, event):
        if self.assign_type == 'team':
            self._run_assign_team(request)
        return super()._run_assign_dispatch(request, event)
