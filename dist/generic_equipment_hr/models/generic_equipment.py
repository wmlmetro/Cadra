from odoo import models, fields


class GenericEquipment(models.AbstractModel):
    _inherit = 'generic.equipment'

    in_use_by_department_id = fields.Many2one('hr.department', index=True)
    in_use_by_employee_id = fields.Many2one('hr.employee', index=True)
