import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class GenericAssignPolicyRule(models.Model):
    _inherit = 'generic.assign.policy.rule'

    # TODO: add type "Team Field", that will allow to select team from specific
    #       field of object
    assign_type = fields.Selection(
        selection_add=[
            ('team', 'Team'),
            ('team_leader', 'Team Leader'),
            ('team_member', 'Team Member'),
            ('team_task_manager', 'Team Task Manager'), ],
        ondelete={
            'team': 'cascade',
            'team_leader': 'cascade',
            'team_member': 'cascade',
            'team_task_manager': 'cascade'})
    assign_team_id = fields.Many2one(
        'generic.team', 'Team')
    assign_team_sort_field_id = fields.Many2one(
        'ir.model.fields',
        ondelete='cascade', tracking=True,
        domain=[('model', '=', 'generic.team.member'),
                ('store', '=', True)])
    assign_team_sort_direction = fields.Selection(
        selection=[
            ('asc', 'Ascending'),
            ('desc', 'Descending')])
    assign_team_choice_type = fields.Selection(
        selection=[
            ('first', 'First'),
            ('random', 'Random')],
        default='random')
    assign_team_choice_condition_ids = fields.Many2many(
        comodel_name='generic.condition',
        relation='generic_assign_policy_rel_team_choice_cond_rel')

    @api.onchange('model_id')
    def _onchange_model_id_hr(self):
        for rec in self:
            rec.assign_team_id = False

    def _get_assignee_team_leader(self, record, debug_log=None):
        self.ensure_one()
        if self.assign_team_id:
            leader = self.sudo().assign_team_id.leader_id
            if leader:
                return {
                    'team_id': self.assign_team_id.id,
                    'user_id': leader.id,
                }
        return False

    def _get_assignee_team_member__get_members(self, record, debug_log=None):
        members = self.sudo().assign_team_id.team_member_ids

        if members and self.assign_team_choice_condition_ids:
            conditions = self.assign_team_choice_condition_ids
            members = members.filtered(conditions.check)
        return members

    def _get_assignee_team_member(self, record, debug_log=None):
        self.ensure_one()
        if self.assign_team_id:
            members = self._get_assignee_team_member__get_members(record)
            if not members:
                self._debug_log(
                    debug_log, record,
                    "no related members to call related policy on")
                return False

            # TODO: it may make sense to remove this line of code
            # and add/leave a default value to the field attributes
            choice_type = self.assign_team_choice_type or 'first'
            order = None
            if self.sudo().assign_team_sort_field_id:
                order = ("%s %s" % (
                    self.sudo().assign_team_sort_field_id.name,
                    self.sudo().assign_team_sort_direction))

            member = self._choose_record(members, choice_type, order)
            if member:
                return {
                    'team_id': self.assign_team_id.id,
                    'user_id': member.user_id.id,
                }
        return False

    def _get_assignee_team_task_manager(self, record, debug_log=None):
        self.ensure_one()
        if self.assign_team_id:
            task_manager = self.sudo().assign_team_id.task_manager_id
            if task_manager:
                return {
                    'team_id': self.assign_team_id.id,
                    'user_id': task_manager.id,
                }
        return False

    def _get_assignee_team(self, record, debug_log=None):
        self.ensure_one()
        if self.assign_team_id:
            return {'team_id': self.assign_team_id.id}
        return False
