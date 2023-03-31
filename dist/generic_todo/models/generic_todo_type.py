from odoo import fields, models, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class GenericTodoType(models.Model):
    _name = 'generic.todo.type'
    _description = 'Generic Todo Type'

    name = fields.Char(index=True, required=True, translate=True)
    active = fields.Boolean(index=True, default=True)

    model_id = fields.Many2one(
        'ir.model', required=True, index=True, auto_join=True,
        domain=[('transient', '=', False),
                ('field_id.name', '=', 'generic_todo_id')],
        string='Todo Model',
        delegate=True, ondelete='cascade')
    todo_ids = fields.One2many(
        'generic.todo', 'todo_type_id', string='Todos')
    todo_count = fields.Integer(compute='_compute_todo_count')

    enable_state_pause = fields.Boolean(default=True)
    enable_state_canceled = fields.Boolean(default=True)

    _sql_constraints = [
        ('model_id_uniq',
         'UNIQUE (model_id)',
         'For each Odoo model only one Todo Type can be created!'),
    ]

    @api.depends('todo_ids')
    def _compute_todo_count(self):
        mapped_data = read_counts_for_o2m(
            records=self, field_name='todo_ids', sudo=True)
        for rec in self:
            rec.todo_count = mapped_data.get(rec.id, 0)

    @api.onchange('model_id')
    def _onchange_model_id(self):
        for rec in self:
            if rec.model_id:
                rec.name = rec.model_id.name

    @api.model
    def get_todo_type_by_model(self, model_name):
        """ Return todo type by model name
        """
        return self.search([
            ('model_id.model', '=', model_name),
        ], limit=1)

    def get_todo_by_id(self, generic_todo_id):
        """
            Returns recordset of todo for res_id from model_id.model.

        :param res_id: int id of related record.
        :return: Recordset of todo model_id.model.
        """
        self.ensure_one()
        return self.env[
            self.sudo().model_id.model
        ].browse(generic_todo_id).exists()

    def action_show_todos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.model_id.name,
            'res_model': self.model_id.model,
            'view_mode': 'tree,form',
            'target': 'current',
            'context': {'default_todo_type_id': self.id},
            'domain': [('todo_type_id', '=', self.id)],
        }
