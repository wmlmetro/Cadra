from odoo import models, fields


class RequestEventAction(models.Model):
    _inherit = 'request.event.action'

    # Action Todo
    act_type = fields.Selection(
        selection_add=[('generic-todo', 'Generic Todo')],
        ondelete={'generic-todo': 'cascade'}
    )
    generic_todo_action = fields.Selection(
        selection=[
            ('add-to-end', 'Add To End'),
            ('rewrite', 'Rewrite'),
            ('clean', 'Clean'),
        ])
    generic_todo_template_id = fields.Many2one(
        'generic.todo.template', 'Todo Template', tracking=True)

    def _run_todo_add_to_end(self, request, event):
        # Add todo from template to the end
        request.action_todos_add_to_end(self.generic_todo_template_id)

    def _run_todo_rewrite(self, request, event):
        # Rewrite request todo by todo from template
        request.action_todos_rewrite(self.generic_todo_template_id)

    def _run_todo_clean(self, request, event):
        # Clear all todos from request
        request.action_todos_clean_all()

    def _dispatch(self, request, event):
        if self.act_type == 'generic-todo':
            if self.generic_todo_action == 'add-to-end':
                return self._run_todo_add_to_end(request, event)
            if self.generic_todo_action == 'rewrite':
                return self._run_todo_rewrite(request, event)
            if self.generic_todo_action == 'clean':
                return self._run_todo_clean(request, event)
        return super(RequestEventAction, self)._dispatch(request, event)
