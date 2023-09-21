import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class GenericAssignPolicyRule(models.Model):
    _inherit = 'generic.assign.policy.rule'

    assign_type = fields.Selection(
        selection_add=[('department_manager', 'Department Manager'),
                       ('department_employee', 'Department Employee')],
        ondelete={'department_manager': 'cascade',
                  'department_employee': 'cascade'})
    assign_department_id = fields.Many2one(
        'hr.department', 'Department')
    assign_department_job_id = fields.Many2one('hr.job', string='Job',
                                               ondelete='restrict')
    assign_department_sort_field_id = fields.Many2one(
        'ir.model.fields',
        ondelete='cascade', tracking=True,
        domain=[('model', '=', 'hr.employee'),
                ('store', '=', True)])
    assign_department_sort_direction = fields.Selection(
        selection=[
            ('asc', 'Ascending'),
            ('desc', 'Descending')])
    assign_department_choice_type = fields.Selection(
        selection=[
            ('first', 'First'),
            ('random', 'Random')],
        default='random')
    assign_department_choice_condition_ids = fields.Many2many(
        comodel_name='generic.condition',
        domain=[('model_id.model', '=', 'hr.employee')],
        relation='generic_assign_policy_rel_department_choice_cond_rel')

    @api.onchange('model_id')
    def _onchange_model_id_hr(self):
        for rec in self:
            rec.assign_department_id = False
            rec.assign_department_job_id = False

    @api.onchange('assign_department_id')
    def _onchange_assign_department_id(self):
        for rec in self:
            rec.assign_department_job_id = False

    def _get_assignee_department_manager(self, record, debug_log=None):
        self.ensure_one()
        if self.assign_department_id:
            manger = self.sudo().assign_department_id.manager_id.user_id
            if not manger:
                return False
            return {'user_id': manger.id}
        return False

    def _get_assignee_department_employee__get_employees(
            self, record, debug_log=None):
        employees = self.sudo().assign_department_id.member_ids
        if self.assign_department_job_id:
            employees = employees.filtered(
                lambda d: d.job_id == self.assign_department_job_id)

        if employees and self.assign_department_choice_condition_ids:
            conditions = self.assign_department_choice_condition_ids
            employees = employees.filtered(conditions.check)

        if not employees:
            employees = self.sudo().assign_department_id.manager_id
        return employees

    def _get_assignee_department_employee(self, record, debug_log=None):
        self.ensure_one()
        if self.assign_department_id:
            employees = (
                self._get_assignee_department_employee__get_employees(record))
            if not employees:
                return False

            choice_type = self.assign_department_choice_type or 'random'
            order = None
            if self.sudo().assign_department_sort_field_id:
                order = ("%s %s" % (
                    self.sudo().assign_department_sort_field_id.name,
                    self.sudo().assign_department_sort_direction))

            employee = self._choose_record(employees, choice_type, order)
            if employee:
                return {'user_id': employee.user_id.id}
        return False
