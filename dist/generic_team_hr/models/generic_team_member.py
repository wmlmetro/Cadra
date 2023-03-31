from odoo import models, fields, api


class GenericTeamMember(models.Model):
    _inherit = 'generic.team.member'

    employee_id = fields.Many2one(
        'hr.employee', string="Employee", compute='_compute_employee',
        readonly=True, store=True, index=True)
    department_id = fields.Many2one(
        'hr.department', string="Department",
        related="employee_id.department_id")
    job_position_id = fields.Many2one(
        'hr.job', string="Job Position", related="employee_id.job_id")

    @api.depends('user_id', 'user_id.employee_ids')
    def _compute_employee(self):
        for rec in self:
            if rec.user_id.employee_ids:
                rec.employee_id = rec.user_id.employee_ids[0]
            else:
                rec.employee_id = False
