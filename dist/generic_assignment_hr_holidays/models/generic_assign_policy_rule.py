from odoo import models, fields


class GenericAssignPolicyRule(models.Model):
    _inherit = 'generic.assign.policy.rule'

    assign_user_field_filter_out_leaves = fields.Boolean()
    assign_department_filter_out_leaves = fields.Boolean()

    def _get_assignee_user_field__get_users(self, record):
        users = super(
            GenericAssignPolicyRule, self
        )._get_assignee_user_field__get_users(record)

        if not self.assign_user_field_filter_out_leaves:
            return users

        return users.filtered(
            lambda u: (
                not u.employee_ids or not u.employee_ids[0].is_absent))

    def _get_assignee_department_employee__get_employees(self, record):
        employees = super(
            GenericAssignPolicyRule, self
        )._get_assignee_department_employee__get_employees(record)

        if not self.assign_department_filter_out_leaves:
            return employees

        return employees.filtered(lambda e: not e.is_absent)
