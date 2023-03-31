from odoo import models, fields, api


class RequestEventAction(models.Model):
    _inherit = "request.event.action"

    # Action assing
    assign_type = fields.Selection(
        selection_add=[('department_manager', 'Department Manager'),
                       ('department_employee', 'Department Employee')],
        ondelete={'department_manager': 'cascade',
                  'department_employee': 'cascade'})

    # assign_<assign_type>_<field>
    assign_department_id = fields.Many2one(
        'hr.department', 'Department', tracking=True)
    assign_department_job_id = fields.Many2one(
        'hr.job', string='Job', ondelete='restrict',
        tracking=True)

    # Action subscribe
    subscribe_department_ids = fields.Many2many(
        'hr.department',
        'request_route_action_subscribe_department_rel',
        'action_id', 'department_id', 'Subscribe departments')

    @api.onchange('assign_department_id')
    def onchange_assign_department_id(self):
        """ Clear assign_department_job_id
        """
        for rec in self:
            rec.assign_department_job_id = False

    def _run_assign_department_manager(self, request):
        request.write({
            'user_id': self.sudo().assign_department_id.manager_id.user_id.id,
        })

    def _run_assign_department_employee(self, request):
        employees = self.sudo().assign_department_id.member_ids
        if self.assign_department_job_id:
            employees = employees.filtered(
                lambda d: d.job_id == self.assign_department_job_id)
        users = employees.mapped('user_id')

        if not users:
            users = self.sudo().assign_department_id.manager_id.user_id

        if not users:
            return

        # Find first user that have minimum requests assigned or closed
        self.env.cr.execute("""
            SELECT res_users.id AS uid
            FROM res_users
            LEFT JOIN request_request AS request_open
                   ON (res_users.id = request_open.user_id
                       AND
                       request_open.closed = False)
            LEFT JOIN request_request AS request_closed
                   ON (res_users.id = request_closed.user_id
                       AND
                       request_closed.closed = True)
            WHERE res_users.active = True
              AND res_users.id IN %(user_ids)s
            GROUP BY res_users.id
            ORDER BY count(request_open.id) ASC,
                     count(request_closed.id) ASC
            LIMIT 1
        """, {
            'user_ids': tuple(users.ids),
        })
        user_id = self.env.cr.fetchone()  # returns tuple(user_id) or None
        user_id = user_id[0] if user_id else False

        request.write({
            'user_id': user_id,
        })

    def _run_assign(self, request, event):
        if self.assign_type == 'department_manager':
            self._run_assign_department_manager(request)
        elif self.assign_type == 'department_employee':
            self._run_assign_department_employee(request)
        return super(RequestEventAction, self)._run_assign(request, event)

    def _run_subscribe_get_partner_ids(self, request):
        partner_ids = super(RequestEventAction,
                            self)._run_subscribe_get_partner_ids(request)
        partner_ids += self.sudo().subscribe_department_ids.mapped(
            'manager_id').mapped('user_id').mapped('partner_id').mapped('id')
        partner_ids += self.sudo().subscribe_department_ids.mapped(
            'member_ids').mapped('user_id').mapped('partner_id').mapped('id')
        return list(set(partner_ids))
