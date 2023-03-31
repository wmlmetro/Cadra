import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class TodoWizardAddTemplate(models.TransientModel):
    _name = 'todo.wizard.add.template'
    _description = 'TodoWizardAddTemplate'

    res_model = fields.Char(
        store=True, string="Related Model", readonly=True, index=True)
    res_id = fields.Many2oneReference(
        string='Related Document', index=True, readonly=True,
        model_field='res_model')
    todo_template_id = fields.Many2one(
        'generic.todo.template')

    todo_wizard_add_template_line_ids = fields.One2many(
        'todo.wizard.add.template.line', 'todo_wizard_add_template_id')

    # Technical field, used in domain for hide fields and buttons
    # on wizard view, when no records in todo_wizard_add_template_line_ids,
    # because using
    # attrs="{
    #     'invisible': [('todo_wizard_add_template_line_ids', '=', False)]}"
    # instead
    # attrs="{'invisible': [('edit_mode', '=', False)]}"
    # has no effect
    edit_mode = fields.Boolean(default=False)

    @api.onchange('todo_wizard_add_template_line_ids')
    def _compute_edit_mode(self):
        for rec in self:
            if not bool(rec.todo_wizard_add_template_line_ids):
                rec.edit_mode = False

    def _get_vals_tuple_todo(self):
        lines = self.todo_wizard_add_template_line_ids.filtered(
            lambda line: line.to_add)

        lines = lines.sorted()
        vals_list_tuples = []
        for line in lines:
            vals = (0, 0, {
                'name': line.name,
                'todo_type_id': line.todo_type_id.id,
            })
            vals_list_tuples.append(vals)
        return vals_list_tuples

    def action_load_template(self):
        self.ensure_one()
        # Add [0] for cases
        # where self.todo_wizard_add_template_line_ids is empty
        max_seq = max(
            [0] +
            [li.sequence for li in self.todo_wizard_add_template_line_ids]
        )
        for vals_line in self.todo_template_id._get_vals_lines():
            max_seq += 1
            vals = {
                'todo_wizard_add_template_id': self.id,
                'sequence': max_seq,
            }
            vals.update(vals_line)

            self.env['todo.wizard.add.template.line'].create(vals)

        # Use this variant code,
        # self.env['todo.wizard.add.template.line'].create(vals)
        # where we create each line separatelly

        # instead

        # vals_list.append(vals)
        # self.write({
        #     'todo_wizard_add_template_line_ids':
        #         self._get_vals_tuple_todo(vals_list),
        # })
        # where we can create all lines by 1 write()
        # because the autocomputed 'sequence' added to thin new lines
        # is not correct

        if self.todo_wizard_add_template_line_ids:
            self.edit_mode = True
        return {
            'type': 'ir.actions.client',
            'tag': 'crnd_act_view_reload',
        }

    def action_clear_lines(self):
        self.ensure_one()
        self.todo_wizard_add_template_line_ids.unlink()
        self.write({
            'edit_mode': False
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'crnd_act_view_reload',
        }

    def do_add_todo_lines(self):
        self.ensure_one()
        object_model = self.env[self.res_model].browse(self.res_id)

        object_model.write({
            'generic_todo_ids': self._get_vals_tuple_todo()
        })

    def do_overwrite_todo_lines(self):
        """
            Deactivate all todos on the object model by setting active = False,
            and add new todos from the wizard lines.
        """
        self.ensure_one()
        object_model = self.env[self.res_model].browse(self.res_id)

        # Deactivating old todos on object
        object_model.generic_todo_ids.action_archive()

        object_model.write({
            'generic_todo_ids': self._get_vals_tuple_todo()
        })


class TodoWizardAddTemplateLine(models.TransientModel):
    _name = 'todo.wizard.add.template.line'
    _description = 'Todo Wizard Add Template Line'
    _order = 'sequence ASC, id ASC'

    name = fields.Char(required=True)
    todo_type_id = fields.Many2one(
        'generic.todo.type', string="Todo Type",
        required=True, index=True, ondelete='cascade', auto_join=True)
    sequence = fields.Integer(
        required=True, readonly=False,
        help="Gives the sequence order for Todo Template Line.")
    to_add = fields.Boolean(
        help='Apply this line to model', default=True, index=True)

    todo_wizard_add_template_id = fields.Many2one(
        'todo.wizard.add.template')
