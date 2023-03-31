from odoo import models, fields, api, exceptions, _


class RequestWizardAssign(models.TransientModel):
    _inherit = 'request.wizard.assign'

    team_id = fields.Many2one(
        'generic.team', string="Team")

    user_id = fields.Many2one(
        'res.users',
        string="User", default=False, required=False)

    def _prepare_assign(self):
        """ Prepare assign data

            This method have to prepare dict with data to be written to request
        """
        res = super(RequestWizardAssign, self)._prepare_assign()
        res['team_id'] = self.team_id.id
        return res

    @api.onchange('team_id')
    def _onchange_team_if_user_not_member(self):
        if self.team_id and self.user_id:
            if not self.team_id._check_user_in_team(self.user_id):
                self.user_id = False
        if self.team_id:
            return {
                'domain': {
                    'user_id': [('generic_team_ids.id', '=', self.team_id.id)],
                },
            }
        return {'domain': {'user_id': []}}

    @api.onchange('user_id')
    def _onchange_no_team_if_user_not_member(self):
        if self.team_id and self.user_id:
            if not self.team_id._check_user_in_team(self.user_id):
                self.team_id = False

    @api.constrains('user_id', 'team_id')
    def _check_assigned_user_in_team(self):
        for rec in self:
            if rec.user_id and rec.team_id:
                if not rec.team_id._check_user_in_team(rec.user_id):
                    raise exceptions.ValidationError(_(
                        "User '%(user)s' is not a member of team '%(team)s'."
                    ) % {
                        'user': rec.user_id.display_name,
                        'team': rec.team_id.display_name,
                    })
