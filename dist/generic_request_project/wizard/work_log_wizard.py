from odoo import models, fields


class WorkLogWizard(models.TransientModel):
    _name = 'work.log.wizard'
    _description = 'Request Wizard: Work Log'

    request_id = fields.Many2one(
        'request.request', 'Request', required=True, ondelete='cascade')
    task_id = fields.Many2one('project.task', 'Task', ondelete='cascade')
    project_id = fields.Many2one(
        'project.project', related='task_id.project_id', readonly=True)
    timesheet_ids = fields.One2many(
        'account.analytic.line',
        related='task_id.timesheet_ids', readonly=False)

    def do_save(self):
        # empty method. no actions required. record will be saved automatically
        # by odoo before this method called.
        return
