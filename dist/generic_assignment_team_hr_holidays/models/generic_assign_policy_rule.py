from odoo import models, fields


class GenericAssignPolicyRule(models.Model):
    _inherit = 'generic.assign.policy.rule'

    assign_team_member_filter_out_leaves = fields.Boolean()

    def _get_assignee_team_member__get_members(self, record):
        members = super(
            GenericAssignPolicyRule, self
        )._get_assignee_team_member__get_members(record)

        if not self.assign_team_member_filter_out_leaves:
            return members

        return members.filtered(
            lambda m: (
                not m.employee_id or not m.employee_id.is_absent))
