from odoo import models, fields, api


class GenericTeamMember(models.Model):
    _name = 'generic.team.member'
    _description = 'Generic team member'

    user_id = fields.Many2one(
        'res.users', index=True, required=True, ondelete='cascade')
    team_id = fields.Many2one(
        'generic.team', index=True, required=True, ondelete='cascade')

    # Ported forward from the 15.0 copy in dist/, where `_sql_constraints`
    # was still honoured. Odoo 19 removed it (orm/model_classes.py logs
    # "no longer supported" and creates nothing), so this constraint had
    # silently ceased to exist. crnd-19/ is loaded only by the Odoo 19
    # config, so no version guard is needed here — unlike our own modules,
    # which the 15 stack still loads.
    _user_team_unique = models.Constraint(
        'UNIQUE (user_id, team_id)',
        'User may be added to team only once.',
    )

    @api.depends('user_id.display_name', 'team_id.display_name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = "%s (%s)" % (
                record.user_id.display_name, record.team_id.display_name)
