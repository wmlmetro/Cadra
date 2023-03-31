from odoo import models, fields, api


class HREmployee(models.Model):
    _inherit = 'hr.employee'

    related_request_count = fields.Integer(
        'All Requests',
        compute='_compute_employee_requests_count'
    )

    @api.depends('user_id')
    def _compute_employee_requests_count(self):
        for employee in self:
            if employee.user_id:
                employee.related_request_count = self.env[
                    'request.request'].search_count(
                        ['|', '|', ['created_by_id', '=', employee.user_id.id],
                         ['author_id', '=', employee.user_id.partner_id.id],
                         ['user_id', '=', employee.user_id.id]])
            else:
                employee.related_request_count = False

    def action_show_related_requests(self):
        self.ensure_one()
        if self.user_id:
            return self.env['generic.mixin.get.action'].get_action_by_xmlid(
                'generic_request.action_request_window',
                domain=['|', '|', ['created_by_id', '=', self.user_id.id],
                        ['author_id', '=', self.user_id.partner_id.id],
                        ['user_id', '=', self.user_id.id]],
                context=dict(
                    self.env.context,  # ask
                    default_created_by_id=self.user_id.id,
                    default_author_id=self.user_id.partner_id.id,
                    default_user_id=self.user_id.id
                ))
        return None
