import logging
from odoo import models, fields, api, _
from odoo.addons.generic_mixin import post_write
from odoo.addons.generic_mixin.tools.sql import create_sql_view
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m
from odoo.addons.generic_system_event import on_event

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = 'request.request'

    project_id = fields.Many2one('project.project')
    project_task_ids = fields.One2many(
        'project.task', 'request_id',
        string='Tasks', copy=False)
    project_task_count = fields.Integer(
        compute='_compute_project_task_count',
        readonly=True)
    project_task_recursive_ids = fields.Many2manyView(
        comodel_name='project.task',
        relation='request_project_task_recursive_rel_view',
        column1='request_id',
        column2='task_id',
        string='Tasks (Recursive)',
        readonly=True,
    )
    use_subtasks = fields.Boolean(
        related='type_id.use_subtasks',
        readonly=True)
    project_task_timesheet_ids = fields.Many2manyView(
        comodel_name='account.analytic.line',
        relation='request_project_task_timesheet_rel_view',
        column1='request_id',
        column2='timesheet_id',
        string='Task Timesheets',
        readonly=True,
        groups='hr_timesheet.group_hr_timesheet_user',
    )
    use_worklog = fields.Boolean(related='type_id.use_worklog', readonly=True)

    @api.depends('project_task_ids')
    def _compute_project_task_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='project_task_ids')
        for record in self:
            record.project_task_count = mapped_data.get(record.id, 0)

    def init(self):
        res = super().init()
        create_sql_view(
            self._cr, 'request_project_task_recursive_rel_view',
            """
                SELECT pt.request_id AS request_id,
                       pt.id AS task_id
                FROM project_task AS pt
                WHERE pt.request_id IS NOT NULL

                UNION

                SELECT ppt.request_id AS request_id,
                       pt.id AS task_id
                FROM project_task AS pt
                LEFT JOIN project_task AS ppt ON ppt.id = pt.parent_id
                WHERE pt.parent_id IS NOT NULL
                  AND ppt.request_id IS NOT NULL
            """)
        create_sql_view(
            self._cr, 'request_project_task_timesheet_rel_view',
            """
                SELECT pt.request_id AS request_id,
                       aal.id AS timesheet_id
                FROM account_analytic_line AS aal
                LEFT JOIN project_task AS pt ON pt.id = aal.task_id
                WHERE aal.task_id IS NOT NULL
                  AND pt.request_id IS NOT NULL

                UNION

                SELECT ppt.request_id AS request_id,
                       aal.id AS timesheet_id
                FROM account_analytic_line AS aal
                LEFT JOIN project_task AS pt ON pt.id = aal.task_id
                LEFT JOIN project_task AS ppt ON ppt.id = pt.parent_id
                WHERE aal.task_id IS NOT NULL
                  AND pt.parent_id IS NOT NULL
                  AND ppt.request_id IS NOT NULL
            """)
        return res

    @post_write('project_id', 'partner_id')
    def _after_project_id_changed_trigger_event(self, changes):
        if changes.get('project_id', False):
            self.trigger_event('project-changed', {
                'old_project_id': changes['project_id'].old_val.id,
                'new_project_id': changes['project_id'].new_val.id,
            })
            self.timesheet_line_ids._sync_project_timesheet_lines()
        self.timesheet_line_ids._sync_project_timesheet_lines()

    def _prepare_action_related_tasks_context(self):
        self.ensure_one()
        context = {
            'default_request_id': self.id,
            'default_project_id': self.project_id.id,
            'default_name': _("Request %s") % self.name,
            'default_description': self.request_text,
        }
        if self.user_id:
            context['default_user_ids'] = [self.user_id.id]
        return context

    @on_event('stage-changed', event_source='project.task')
    def _on_project_task_stage_changed(self, event):

        old_stage = event.old_stage_id
        new_stage = event.new_stage_id
        self.trigger_event('task-stage-changed', {
            'task_id': event.event_source_record_id,
            'task_old_stage_id': old_stage.id,
            'task_new_stage_id': new_stage.id})
        if not old_stage.fold and new_stage.fold:
            self.trigger_event('task-closed', {
                'task_id': event.event_source_record_id,
                'task_old_stage_id': old_stage.id,
                'task_new_stage_id': new_stage.id})
            if (self.sudo().project_task_ids and
                    all(task.stage_id.fold
                        for task in self.sudo().project_task_ids)):
                self.trigger_event('task-all-tasks-closed', {})

    def action_show_related_tasks(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'project.act_project_project_2_project_task_all',
            context=self._prepare_action_related_tasks_context(),
            domain=[('request_id', '=', self.id)])

    def action_create_task(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_form_action_by_xmlid(
            'project.act_project_project_2_project_task_all',
            context=self._prepare_action_related_tasks_context())

    def action_request_work_log(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request_project.action_wizard_work_log',
            context={'default_request_id': self.id})
