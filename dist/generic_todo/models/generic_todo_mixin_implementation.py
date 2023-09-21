import logging

from odoo import fields, models, api

_logger = logging.getLogger(__name__)


class GenericTodoMixinImplementation(models.AbstractModel):
    _name = 'generic.todo.mixin.implementation'
    _description = 'Generic Todo MixIn Implementation'
    _inherit = [
        'generic.mixin.track.changes',
        'generic.mixin.delegation.implementation',
        'generic.system.event.handler.mixin',
    ]

    generic_todo_id = fields.Many2one(
        'generic.todo', index=True, auto_join=True,
        required=True, delegate=True, ondelete='cascade',
        string="Generic Todo")

    _sql_constraints = [
        ('unique_todo_id', 'UNIQUE(generic_todo_id)',
         'Todo Implementation must be unique')
    ]

    @api.model
    def _add_missing_default_values(self, values):
        res = super()._add_missing_default_values(values)

        if not res.get('todo_type_id'):
            res['todo_type_id'] = self.env[
                'generic.todo.type'
            ].get_todo_type_by_model(self._name).id
        return res

    @api.model_create_multi
    def create(self, vals):
        # Pass additional context to notify base object, that there is no
        # need to create implementation for this todo,
        # because it will be created automatically
        return super(
            GenericTodoMixinImplementation,
            self.with_context(
                _generic_todo__do_not_autocreate_implementation=True)
        ).create(vals)

    def _action_generic_todo_start(self):
        if self.generic_todo_id.state in ['new', 'paused']:
            self.generic_todo_id.state = 'in_progress'

    def _action_generic_todo_paused(self):
        if self.generic_todo_id.state == 'in_progress':
            self.generic_todo_id.state = 'paused'

    def _action_generic_todo_canceled(self):
        if self.generic_todo_id.state == 'in_progress':
            self.generic_todo_id.state = 'canceled'

    def _action_generic_todo_completed(self):
        if self.generic_todo_id.state == 'in_progress':
            self.generic_todo_id.state = 'done'
