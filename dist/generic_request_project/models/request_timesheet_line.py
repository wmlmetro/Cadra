import logging

from odoo import models

from odoo.addons.generic_mixin import post_create, post_write

_logger = logging.getLogger(__name__)


class RequestTimesheetLine(models.Model):
    _inherit = ['request.timesheet.line']

    def _prepare_project_timesheet_line_data(self):
        res = {
            'req_timesheet_line_id': self.id,
            'project_id': self.request_id.project_id.id,
            'date': self.date,
            'partner_id': self.request_id.partner_id.id,
            'unit_amount': self.amount,
        }

        if self.description:
            res['name'] = "%s: %s" % (
                self.activity_id.name, self.description)
        else:
            res['name'] = self.activity_id.name

        if len(self.user_id.employee_ids) == 1:
            res['employee_id'] = self.user_id.employee_ids.id
        else:
            res['user_id'] = self.user_id.id

        return res

    def _sync_project_timesheet_single_line(self):
        self.ensure_one()
        if not self.request_id.project_id:
            need_mirror_line = False
        elif not self.request_id.project_id.allow_timesheets:
            need_mirror_line = False
        elif self.amount == 0:
            need_mirror_line = False
        else:
            need_mirror_line = True

        aal = self.env['account.analytic.line'].search(
            [('req_timesheet_line_id', '=', self.id)])
        # NOTE: This if implements following matrix:
        #
        #       | has aal    | need_mirror_line | operation         |
        #       |------------|------------------|-------------------|
        #       | exists     | True             | update aal        |
        #       | exists     | False            | remove aal        |
        #       | not exists | True             | create new aal    |
        #       | not exists | False            | do nothing        |
        if aal and need_mirror_line:
            aal.write(self._prepare_project_timesheet_line_data())
        elif aal and not need_mirror_line:
            aal.unlink()
        elif not aal and need_mirror_line:
            self.env['account.analytic.line'].create(
                self._prepare_project_timesheet_line_data())

    def _sync_project_timesheet_lines(self):
        for rtl in self:
            if not self.user_has_groups(
                    'hr_timesheet.group_hr_timesheet_user'):
                # If current user has no access to timesheets, we have to
                # register them as superuser to avoid access rights errors
                rtl = rtl.sudo()

            rtl._sync_project_timesheet_single_line()

    @post_create()
    @post_write('request_id', 'date', 'amount', 'activity_id',
                'description', 'user_id')
    def _post_create_write_sync_project_timesheets(self, changes):
        self._sync_project_timesheet_lines()

    def unlink(self):
        self.env['account.analytic.line'].search(
            [('req_timesheet_line_id', 'in', self.ids)]).unlink()
        res = super(RequestTimesheetLine, self).unlink()
        return res
