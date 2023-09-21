import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class GenericWizardAssign(models.TransientModel):
    _inherit = 'generic.wizard.assign'

    assign_type = fields.Selection(
        selection_add=[('team', 'Team')],
        ondelete={'team': 'cascade'})
    assign_team_id = fields.Many2one(
        'generic.team', 'Team', required=False)
    assign_team_user_id = fields.Many2one(
        'res.users', 'User')

    # Used in view as helper fields for domain
    assign_team_leader_id = fields.Integer(
        related='assign_team_id.leader_id.id')
    assign_team_task_manager_id = fields.Integer(
        related='assign_team_id.task_manager_id.id')

    def _do_assign_team(self, assign_obj):
        field_name_team = self.sudo().assign_model_id.assign_team_field_id.name
        field_name_user = self.sudo().assign_model_id.assign_user_field_id.name
        values = {
            field_name_user: self.assign_team_user_id.id,
        }
        if field_name_team:
            values.update({
                field_name_team: self.assign_team_id.id,
            })
        assign_obj.write(values)

    def _do_assign_user(self, assign_obj):
        # Clean up team, if we want to assign request to user
        field_name_team = self.sudo().assign_model_id.assign_team_field_id.name
        if field_name_team:
            assign_obj.write({field_name_team: False})
        return super(GenericWizardAssign, self)._do_assign_user(assign_obj)

    def _do_assign_dispatch(self, assign_obj):
        if self.assign_type == 'team':
            return self._do_assign_team(assign_obj)
        return super(GenericWizardAssign, self)._do_assign_dispatch(assign_obj)

    @api.onchange('assign_type', 'assign_team_id', 'assign_team_user_id')
    def onchange_assign_type_team(self):
        self.ensure_one()
        team = self.assign_team_id
        if team and not team._check_user_in_team(self.assign_team_user_id):
            self.assign_user_id = False
