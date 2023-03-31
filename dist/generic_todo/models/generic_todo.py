import logging

from odoo import models, fields, api

from odoo.addons.generic_mixin import generate_proxy_decorator
from odoo.addons.generic_mixin import post_create, post_write, pre_write
from odoo.addons.generic_mixin.tools.generic_m2o import generic_m2o_get

_logger = logging.getLogger(__name__)


NEW_BG_COLOR = 'rgba(224,133,123,1)'
IN_PROGRESS_BG_COLOR = 'rgba(82,136,192,1)'
DONE_BG_COLOR = 'rgba(114,179,166,1)'
LINE_LABEL_COLOR = 'rgba(255,255,255,1)'

# todo_proxy decorator, that have to be used to mark methods that have
# to be added to todo implementation model.
todo_proxy = generate_proxy_decorator('__generic_todo_proxy__')


class GenericTodo(models.Model):
    _name = 'generic.todo'
    _description = 'Generic Todo'
    _inherit = [
        'generic.mixin.delegation.interface',
        'generic.mixin.proxy.methods',
        'generic.system.event.source.mixin',
    ]
    _log_access = False
    _order = 'sequence ASC, id ASC'

    _generic_mixin_proxy_methods__dest_model = (
        'generic.todo.mixin.implementation')
    _generic_mixin_proxy_methods__link_field = 'generic_todo_id'
    _generic_mixin_proxy_methods__method_attr = '__generic_todo_proxy__'

    _generic_mixin_implementation_model_field = 'todo_implementation_model'
    _generic_mixin_implementation_id_field = 'todo_implementation_res_id'

    name = fields.Char(required=True, index=True)

    user_id = fields.Many2one('res.users', string='Responsible', index=True)

    active = fields.Boolean(index=True, default=True, tracking=True)

    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('in_progress', 'In Progress'),
            ('paused', 'Paused'),
            ('canceled', 'Canceled'),
            ('done', 'Done')], default='new',
        required=True, index=True, readonly=True)

    res_model = fields.Char(
        store=True, string="Related Model", readonly=True, index=True)
    res_id = fields.Many2oneReference(
        string="Related Document", index=True, readonly=True,
        model_field='res_model')

    todo_type_id = fields.Many2one(
        'generic.todo.type', string="Todo Type",
        required=True, index=True, ondelete='cascade', auto_join=True)
    todo_implementation_model_id = fields.Many2one(
        'ir.model',
        related='todo_type_id.model_id',
        required=True, index=True, ondelete='cascade')
    todo_implementation_model = fields.Char(
        related='todo_type_id.model_id.model',
        readonly=True, store=True,
        compute_sudo=True, index=True)
    todo_implementation_res_id = fields.Many2oneReference(
        string="Todo Implementation",
        required=False, store=True, readonly=True,
        model_field='todo_implementation_model')

    date_created = fields.Datetime(
        'Created', default=fields.Datetime.now,
        index=True, required=True, readonly=True, copy=False)
    date_started = fields.Datetime(readonly=True, copy=False)
    date_completed = fields.Datetime(readonly=True, copy=False)
    date_last_action = fields.Datetime(readonly=True, copy=False)

    sequence = fields.Integer(
        default=5, index=True,
        help="Gives the sequence order for Todo.")

    _sql_constraints = [
        ('unique_model', 'UNIQUE(todo_type_id, todo_implementation_res_id)',
         'Todo Implementation instance must be unique')
    ]

    @pre_write('state')
    def _before_state_changed_log_last_action(self, changes):
        res = {
            'date_last_action': fields.Datetime.now(),
        }
        if changes['state'].new_val == 'in_progress' and not self.date_started:
            res['date_started'] = fields.Datetime.now()
        elif changes['state'].new_val == 'done':
            res['date_completed'] = fields.Datetime.now()
        return res

    @post_write('state', priority=40)
    def _after_state_changed_trigger_events(self, changes):
        event_data = {
            'old_state': changes['state'].old_val,
            'new_state': changes['state'].new_val,
        }
        self.trigger_event('generic-todo-state-changed', event_data)
        if changes['state'].new_val == 'canceled':
            self.trigger_event('generic-todo-canceled', event_data)
        elif changes['state'].new_val == 'done':
            self.trigger_event('generic-todo-completed', event_data)

    @post_create()
    @post_write('state', 'active')
    def _after_state_and_active_changed(self, changes):
        # TODO: to be removed when request migrated to system events
        #       could be reimplemented completely on system events
        if self.todo_object:
            self.todo_object.check_all_todo_from_object()

    def unlink(self):
        # This need for checking todos on objects after deleting todos
        # This could trigger event all-todo-done in other modules.
        # TODO: possibly rewrite this via event handlers
        objects = []
        for rec in self:
            objects.append((rec.res_model, rec.res_id))
        res = super().unlink()

        objects = list(set(objects))

        for obj in objects:
            object_id = self.env[obj[0]].browse(obj[1])
            if object_id:
                object_id.check_all_todo_from_object()
        return res

    @api.model
    def _add_missing_default_values(self, values):
        model = values.get('res_model', False)
        res_id = values.get('res_id', False)

        # TODO: Use readgroup to find max sequence
        #       Do nothing if there is no model nor res_id
        todos = self.search([
            ('res_model', '=', model),
            ('res_id', '=', res_id),
        ])

        if todos:
            values['sequence'] = max(s.sequence for s in todos) + 1

        return super()._add_missing_default_values(values)

    @api.model
    def create(self, vals):
        if not self.env.context.get(
                '_generic_todo__do_not_autocreate_implementation'):
            # By default, always create implementation for todo
            # automatically. For example, in case, when todo
            # being created via UI.
            todo_type = self.env['generic.todo.type'].browse(
                vals['todo_type_id'])
            model = todo_type.sudo().model_id.model
            return self.env[model].create(vals).generic_todo_id

        return super().create(vals)

    @property
    def todo_implementation(self):
        """ Property to easily access implementation of this generic todo
        """
        return generic_m2o_get(
            self,
            field_res_model='todo_implementation_model',
            field_res_id='todo_implementation_res_id'
        )

    @property
    def todo_object(self):
        """ Property to easily access object of this generic todo
        """
        return generic_m2o_get(
            self,
            field_res_model='res_model',
            field_res_id='res_id'
        )

    @todo_proxy
    def action_todo_activate(self):
        self.ensure_one()
        self.active = True

    @todo_proxy
    def action_todo_deactivate(self):
        self.ensure_one()
        self.active = False

    @todo_proxy
    def action_start_work(self):
        self.ensure_one()
        return self.todo_implementation._action_generic_todo_start()

    @todo_proxy
    def action_pause_work(self):
        self.ensure_one()
        if self.todo_type_id.enable_state_pause:
            return self.todo_implementation._action_generic_todo_paused()
        return None

    @todo_proxy
    def action_cancel_work(self):
        self.ensure_one()
        if self.todo_type_id.enable_state_canceled:
            return self.todo_implementation._action_generic_todo_canceled()
        return None

    @todo_proxy
    def action_complete_work(self):
        self.ensure_one()
        return self.todo_implementation._action_generic_todo_completed()

    @todo_proxy
    def action_open_todo_object(self):
        """ Open todo implementation object
        """
        res = self.todo_implementation.get_formview_action()
        res.update({
            'target': 'new',
            'flags': {'mode': 'readonly'},
        })
        return res

    @todo_proxy
    def action_show_related_system_events(self):
        return super().action_show_related_system_events()
