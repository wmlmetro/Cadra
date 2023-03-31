from odoo import models, fields, api


class GenericResourceRoleLink(models.Model):
    _inherit = 'generic.resource.role.link'

    employee_id = fields.Many2one(
        'hr.employee',
        compute='_compute_employee_id',
        readonly=True, store=True, index=True)

    @api.depends('user_id')
    def _compute_employee_id(self):
        for rec in self:
            if rec.user_id and len(rec.user_id.employee_ids) == 1:
                rec.employee_id = rec.user_id.employee_ids
            else:
                rec.employee_id = False
