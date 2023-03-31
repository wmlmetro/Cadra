import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class ProjectEventData(models.Model):
    _name = 'project.task.event.data'
    _description = 'Project Event Data'
    _inherit = 'generic.system.event.data.mixin'

    old_deadline = fields.Date()
    new_deadline = fields.Date()

    old_stage_id = fields.Many2one('project.task.type')
    new_stage_id = fields.Many2one('project.task.type')
