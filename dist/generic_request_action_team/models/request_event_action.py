from odoo import models, fields, api, exceptions, _


class RequestEventAction(models.Model):
    _inherit = "request.event.action"

    # Action assign
    assign_type = fields.Selection(
        selection_add=[('team', 'Team')])
    assign_team_id = fields.Many2one(
        'generic.team', 'Assign to Team', tracking=True)
    assign_team_user_id = fields.Many2one(
        'res.users', 'Assign to team member', tracking=True)

    @api.constrains('assign_team_user_id', 'assign_team_id')
    def _check_assign_team__user_in_team(self):
        for rec in self:
            if not (rec.assign_team_user_id and rec.assign_team_id):
                continue
            if not rec.assign_team_id._check_user_in_team(
                    rec.assign_team_user_id):
                raise exceptions.ValidationError(_(
                    "User '%(user)s' is not a member of team '%(team)s'."
                ) % {
                    'user': rec.assign_team_user_id.display_name,
                    'team': rec.assign_team_id.display_name,
                })

    def _run_assign_team(self, request):
        request.write({
            'team_id': self.sudo().assign_team_id.id,
            'user_id': self.sudo().assign_team_user_id.id,
        })

    def _run_assign_dispatch(self, request, event):
        if self.assign_type == 'team':
            self._run_assign_team(request)
        return super()._run_assign_dispatch(request, event)
