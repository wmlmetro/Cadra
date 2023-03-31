import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class GenericTodoEventData(models.Model):
    _name = 'generic.todo.event.data'
    _description = 'Generic Todo Event Data'
    _inherit = 'generic.system.event.data.mixin'

    # Change state event fields
    old_state = fields.Selection(
        selection='_get_selection_todo_state', readonly=True)
    new_state = fields.Selection(
        selection='_get_selection_todo_state', readonly=True)

    def _get_selection_todo_state(self):
        return self.env['generic.todo']._fields['state'].selection
