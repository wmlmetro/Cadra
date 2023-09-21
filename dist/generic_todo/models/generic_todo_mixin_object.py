import logging

from odoo import fields, models, api

_logger = logging.getLogger(__name__)


class GenericTodoMixinObject(models.AbstractModel):
    _name = 'generic.todo.mixin.object'
    _description = 'Generic Todo MixIn Object'

    generic_todo_ids = fields.One2many(
        'generic.todo', 'res_id',
        string='Todos',
        domain=lambda self: [('res_model', '=', self._name)]
    )

    def _check_all_todo_from_object(self):
        # TODO: to be removed when request migrated to system events
        return all([
            todo.state in ['done', 'canceled']
            for todo in self.generic_todo_ids])

    def check_all_todo_from_object(self):
        # TODO: to be removed when request migrated to system events
        if self._check_all_todo_from_object():
            self._event_all_todos_from_object_completed()

    def _event_all_todos_from_object_completed(self):
        # TODO: to be removed when request migrated to system events
        # Used for override
        return True

    def _add_res_model_by_obj_to_vals(self, vals):
        """ Update 'res_model' field for each todo created on object.
            This is used when todo being created on the object from view,
            for example, when todo created via UI on the task's form view.
        """
        generic_todo_vals = vals.get('generic_todo_ids', False)
        if not generic_todo_vals:
            return vals
        for val in generic_todo_vals:
            if val[0] not in (0, 1):
                continue
            val[2].update({'res_model': self._name})

        return vals

    def action_todos_add_to_end(self, template):
        """
            Add new todos from the specified template after those already in
            the model object.
        """
        self.ensure_one()
        self.write({
            'generic_todo_ids': template._get_vals_lines_tuple()
        })

    def action_todos_rewrite(self, template):
        """
            Deactivate all todos on the object model by setting active = False,
            and add new todos from the specified template.
        """
        self.ensure_one()

        # Deactivating old todos on object
        self.generic_todo_ids.write({'active': False})
        self.write({
            'generic_todo_ids': template._get_vals_lines_tuple()
        })

    def action_todos_clean_all(self):
        """
            Deactivate all todos on the object model, by set active = False
        """
        self.ensure_one()
        self.generic_todo_ids.action_archive()

    def action_hide_canceled_done_todo(self):
        """
            Deactivate all todos on the object model,
            that have the status "Canceled" and "Done" by set active = False
        """
        self.ensure_one()
        self.generic_todo_ids.filtered(
            lambda t: t.state in ['canceled', 'done']
        ).action_archive()

    @api.model_create_multi
    def create(self, vals):
        vals = [self._add_res_model_by_obj_to_vals(v) for v in vals]
        return super(GenericTodoMixinObject, self).create(vals)

    def write(self, vals):
        return super(GenericTodoMixinObject, self).write(
            self._add_res_model_by_obj_to_vals(vals))

    def action_add_template_todo(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_todo.action_todo_wizard_add_template',
            context={
                'default_res_model': self._name,
                'default_res_id': self.id,
            })
