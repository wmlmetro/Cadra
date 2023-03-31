from odoo import models, _


class ResUsers(models.Model):
    _inherit = 'res.users'

    def request_helper_m2o_info(self):
        """ Technical method, that is used to perepear data for
            m2o_info fields.
        """
        res = super().request_helper_m2o_info()
        if self.employee_ids and len(self.employee_ids) == 1:
            e = self.employee_ids
            if e.job_id:
                res += [{
                    'name': 'employee_ids.job_id',
                    'string': _('Job Position'),
                    'value': e.job_id.display_name,
                }]
            if e.department_id:
                res += [{
                    'name': 'employee_ids.department_id',
                    'string': _('Department'),
                    'value': e.department_id.display_name,
                }]

            if e.parent_id:
                res += [{
                    'name': 'employee_ids.parent_id',
                    'string': _('Manager'),
                    'value': e.parent_id.display_name,
                }]
        return res
