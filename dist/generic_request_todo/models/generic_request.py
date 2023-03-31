import logging
from odoo import models
from odoo.addons.generic_system_event import on_event

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _name = 'request.request'
    _inherit = [
        'generic.todo.mixin.object',
        'request.request',
    ]

    @on_event('generic-todo-completed', 'generic-todo-canceled',
              event_source='generic.todo')
    def _on_generic_todo_completed_or_cancelled(self, event):
        if event.event_code == 'generic-todo-completed':
            self.trigger_event('request-todo-completed', {})
        elif event.event_code == 'generic-todo-cancelled':
            self.trigger_event('request-todo-cancelled', {})

        # If there are no todo in progress,
        #  assume that all todo were completed.
        # Note, in case when all todo were cancelled,
        # system will generate event for all todo completed.
        if all([t.state in ['done', 'canceled']
                for t in self.generic_todo_ids]):
            self.trigger_event('request-all-todo-completed', {})
