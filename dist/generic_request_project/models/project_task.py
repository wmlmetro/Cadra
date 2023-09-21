import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)


class ProjectTask(models.Model):
    _name = 'project.task'
    _inherit = ['project.task']

    request_ids = fields.Many2many(
        'request.request',
        relation='request_request_project_task_rel',
        column1='request_id', column2='project_task_id',
        string='Requests (Deprecated)',
        help="This field is deprecated! Do not use it. If you still need it, "
             "then contact us (CR&D)",
        )
    request_id = fields.Many2one(
        'request.request',
        help="Request this task is related to")
    request_service_id = fields.Many2one(
        related='request_id.service_id',
        string="Request Service",
        store=True, ondelete='restrict', readonly=True)
    request_category_id = fields.Many2one(
        related='request_id.category_id',
        string="Request Category",
        store=True, ondelete='restrict', readonly=True)
    request_type_id = fields.Many2one(
        related='request_id.type_id',
        string="Request Type",
        store=True, ondelete='restrict', readonly=True)

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS | {'request_ids', 'request_id'}

    def action_subtask(self):
        # Redefine this method to not propagate creation of subtask bound to
        # same request as task
        res = super(ProjectTask, self).action_subtask()
        if res.get('default_request_id'):
            del res['default_request_id']
        return res

    def _get_generic_tracking_fields(self):
        """ Compute list of fields that have to be tracked
        """
        return super(
            ProjectTask, self
        )._get_generic_tracking_fields() | {'stage_id'}
