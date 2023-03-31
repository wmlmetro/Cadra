from odoo import models, fields


class RequestEvent(models.Model):
    _inherit = 'request.event'

    task_id = fields.Many2one('project.task')

    task_old_stage_id = fields.Many2one('project.task.type', readonly=True)
    task_new_stage_id = fields.Many2one('project.task.type', readonly=True)

    old_project_id = fields.Many2one('project.project', readonly=True)
    new_project_id = fields.Many2one('project.project', readonly=True)
