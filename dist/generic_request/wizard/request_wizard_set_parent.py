from odoo import models, fields, api


class RequestWizardSetParent(models.TransientModel):
    _name = 'request.wizard.set.parent'
    _description = 'Request Wizard: Set Parent'

    request_ids = fields.Many2many('request.request', required=True)
    parent_id = fields.Many2one(
        'request.request', 'Parent Request', ondelete='cascade')
    request_text_sample = fields.Text(
        'Parent request text', related='parent_id.request_text_sample')
    author_id = fields.Many2one(
        'res.partner', 'Parent request author',
        related='parent_id.author_id')
    warning_type = fields.Selection(selection=[
        ('one_parent', 'One  parent'),
        ('few_parent', 'Few parent'),
    ], compute='_compute_warning_type')

    def do_set_parent(self):
        self.ensure_one()
        for rec in self.request_ids:
            rec.parent_id = self.parent_id

    @api.depends('request_ids')
    def _compute_warning_type(self):
        for rec in self:
            parent = rec.request_ids.mapped('parent_id')
            if not parent:
                rec.warning_type = False
            elif len(parent) == 1:
                if len(rec.request_ids) == 1:
                    rec.warning_type = False
                else:
                    rec.warning_type = 'one_parent'
            else:
                rec.warning_type = 'few_parent'

    @api.model
    def default_get(self, default_fields):
        request = self.env['request.request'].browse(
            self.env.context.get('active_ids', [])
        )
        parent_id = request.mapped('parent_id')
        if not parent_id:
            default_parent_id = False
        elif len(parent_id) == 1:
            default_parent_id = parent_id[0]
        else:
            default_parent_id = False

        res = super(RequestWizardSetParent, self).default_get(
            default_fields)
        res.update({
            'request_ids': [(6, 0, request.ids)],
            'parent_id': default_parent_id.id if default_parent_id else False,
        })
        return res
