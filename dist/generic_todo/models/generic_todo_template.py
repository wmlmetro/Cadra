from odoo import fields, models, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class GenericTodoTemplate(models.Model):
    _name = 'generic.todo.template'
    _description = 'Generic Todo Template'

    name = fields.Char(index=True, required=True)

    todo_template_line_ids = fields.One2many(
        'generic.todo.template.line', 'todo_template_id')
    todo_lines_count = fields.Integer(compute='_compute_todo_lines_count')

    @api.depends('todo_template_line_ids')
    def _compute_todo_lines_count(self):
        mapped_data = read_counts_for_o2m(
            records=self, field_name='todo_template_line_ids', sudo=True)
        for rec in self:
            rec.todo_lines_count = mapped_data.get(rec.id, 0)

    def _get_vals_lines(self):
        self.ensure_one()
        vals_list = []
        for line in self.todo_template_line_ids:
            vals = {
                'name': line.name,
                'todo_type_id': line.todo_type_id.id,
            }
            vals_list.append(vals)
        return vals_list

    def _get_vals_lines_tuple(self):
        self.ensure_one()
        vals_list_tuples = []
        for val in self._get_vals_lines():
            vals_list_tuples.append((0, 0, val))
        return vals_list_tuples

    def action_show_todo_template_lines(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_todo.generic_todo_template_line_action',
            context={'default_todo_template_id': self.id},
            domain=[('todo_template_id', '=', self.id)])
