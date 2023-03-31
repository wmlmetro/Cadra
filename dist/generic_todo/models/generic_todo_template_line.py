from odoo import fields, models, api


class GenericTodoTemplateLine(models.Model):
    _name = 'generic.todo.template.line'
    _description = 'Generic Todo Template Line'
    _order = 'sequence ASC, id ASC'

    name = fields.Char(index=True, required=True)

    todo_template_id = fields.Many2one(
        'generic.todo.template', index=True)
    todo_type_id = fields.Many2one(
        'generic.todo.type', string="Todo Type",
        required=True, index=True, ondelete='cascade', auto_join=True)
    sequence = fields.Integer(
        default=5, index=True,
        help="Gives the sequence order for Todo Template Line.")

    @api.model
    def _add_missing_default_values(self, values):
        todo_template = values.get('res_model', False)
        todo_lines = self.search([
            ('todo_template_id', '=', todo_template)
        ])

        if todo_lines:
            values['sequence'] = max(s.sequence for s in todo_lines) + 1

        return super()._add_missing_default_values(values)
