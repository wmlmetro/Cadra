import logging
import dateutil
import pytz
from odoo import models, fields, api
from odoo.addons.generic_request.tools.jinja import render_jinja_string
from odoo.tools.safe_eval import safe_eval, wrap_module

_logger = logging.getLogger(__name__)


class RequestStageRouteAction(models.Model):
    _inherit = 'request.event.action'

    act_type = fields.Selection(selection_add=[('task', 'Task')],
                                ondelete={'task': 'cascade'})
    task_project_compute_type = fields.Selection(
        string='Compute project as',
        selection=[
            ('fixed', 'Fixed'),
            ('domain', 'Domain'),
            ('python-expression', 'Python expression'),
            ('request', 'From request'),
        ], default='request')
    task_project_id = fields.Many2one('project.project')
    task_project_domain = fields.Text()
    task_project_py_expression = fields.Text()
    task_stage_id = fields.Many2one('project.task.type')
    task_title = fields.Char(
        help="You can use jinja2 placeholders in this field"
    )
    task_description = fields.Html(
        help="You can use jinja2 placeholders in this field"
    )
    task_assign_type = fields.Selection([
        ('user', 'User'),
        ('request-user', "Request's assignee"),
    ])
    task_user_id = fields.Many2one('res.users')

    task_use_request_deadline = fields.Boolean()

    def _run_task_prepare_data(self, request, event):
        project_id = self._run_task_determine_project(request, event)
        res = {
            'project_id': project_id,
            'stage_id': self.task_stage_id.id,
            'request_id': request.id,
            'name': render_jinja_string(
                self.task_title,
                dict(self.env.context,
                     request=request,
                     object=request,
                     event=event)),
            'description': render_jinja_string(
                self.task_description,
                dict(self.env.context,
                     request=request,
                     object=request,
                     event=event)),
        }

        if self.task_assign_type == 'user' and self.task_user_id:
            res['user_ids'] = [(6, 0, self.task_user_id.ids)]
        elif self.task_assign_type == 'request-user':
            res['user_ids'] = [(6, 0, request.user_id.ids)]

        if self.task_use_request_deadline:
            res['date_deadline'] = request.deadline_date
        return res

    def _run_task(self, request, event):
        self.env['project.task'].create(
            self._run_task_prepare_data(request, event))

    def _dispatch(self, request, event):
        if self.act_type == 'task':
            return self._run_task(request, event)
        return super(RequestStageRouteAction, self)._dispatch(request, event)

    @api.onchange('task_project_id')
    def _onchange_project_id(self):
        for record in self:
            record.task_stage_id = False

    @api.onchange('task_project_compute_type')
    def _onchange_task_project_compute_type(self):
        for record in self:
            if record.task_project_compute_type != 'fixed':
                record.task_project_id = False
                record.task_stage_id = False
            if record.task_project_compute_type != 'domain':
                record.task_project_domain = False
            if record.task_project_compute_type != 'python-expression':
                record.task_project_py_expression = False

    def _run_task_get_eval_context(self, request, event):
        mods = ['parser', 'relativedelta', 'rrule', 'tz']
        for mod in mods:
            __import__('dateutil.%s' % mod)
        _datetime = wrap_module(
            __import__('datetime'),
            ['date', 'datetime', 'time', 'timedelta', 'timezone',
             'tzinfo', 'MAXYEAR', 'MINYEAR'])
        _dateutil = wrap_module(dateutil, {
            mod: getattr(dateutil, mod).__all__
            for mod in mods
        })
        _relativedelta = dateutil.relativedelta.relativedelta
        _time = wrap_module(
            __import__('time'), ['time', 'strptime', 'strftime'])
        _timezone = pytz.timezone

        return {
            'uid': self._uid,
            'user': self.env.user,
            'time': _time,
            'datetime': _datetime.datetime,
            'dateutil': _dateutil,
            'relativedelta': _relativedelta,
            'timezone': _timezone,
            'request': request,
            'event': event,
        }

    def _run_task_determine_project_domain(self, request, event):
        context = self._run_task_get_eval_context(request, event)
        domain = safe_eval(self.task_project_domain, context)
        project = self.env['project.project'].search(domain, limit=1)
        if project:
            return project.id
        return False

    def _run_task_determine_project_py_expression(self, request, event):
        context = self._run_task_get_eval_context(request, event)
        context.update({
            'env': self.env,
            'Project': self.env['project.project'],
        })
        result = safe_eval(self.task_project_py_expression, context)
        if (isinstance(result, models.Model) and
                result._name == 'project.project'):
            return result.id
        return False

    def _run_task_determine_project(self, request, event):
        if self.task_project_compute_type == 'fixed':
            return self.task_project_id.id
        if self.task_project_compute_type == 'domain':
            return self._run_task_determine_project_domain(request, event)
        if self.task_project_compute_type == 'python-expression':
            return self._run_task_determine_project_py_expression(
                request, event)
        if self.task_project_compute_type == 'request':
            return request.project_id.id
        return False
