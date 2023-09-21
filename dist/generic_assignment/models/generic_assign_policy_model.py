import logging

from odoo import models, fields, api, exceptions, _

from odoo.addons.generic_mixin import post_write
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

_logger = logging.getLogger(__name__)


class GenericAssignPolicyModel(models.Model):
    _name = 'generic.assign.policy.model'
    _inherit = [
        'generic.mixin.track.changes',
    ]
    _description = 'Assignment Policy Model'

    model_id = fields.Many2one(
        'ir.model', string="Odoo Model", required=True, index=True,
        delegate=True, readonly=True, ondelete='cascade')
    assign_user_field_id = fields.Many2one(
        'ir.model.fields', readonly=True,
        ondelete='cascade',
        domain="[('ttype', '=', 'many2one'), ('relation', '=', 'res.users')]")
    assign_policy_ids = fields.One2many(
        'generic.assign.policy', 'assign_model_id', readonly=True)
    assign_policy_count = fields.Integer(
        compute='_compute_assign_policy_count', readonly=True,
        string='Policies', store=False)

    act_assign_id = fields.Many2one(
        'ir.actions.act_window', readonly=True,
        string='Action Assign',
        help='Context action that allows to assign multiple '
             'objects from list view')
    enable_act_assign = fields.Boolean(
        'Enable context assign')

    _sql_constraints = [
        ('model_unique',
         'UNIQUE (model_id)',
         'The model for the assignment policy must be unique.'),
    ]

    @api.depends('assign_policy_ids')
    def _compute_assign_policy_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='assign_policy_ids')
        for record in self:
            record.assign_policy_count = mapped_data.get(record.id, 0)

    @post_write('enable_act_assign')
    def _toggle_context_action_for_target_model(self, changes):
        ActWindow = self.env['ir.actions.act_window'].sudo()
        old_val, new_val = changes['enable_act_assign']
        if new_val and not old_val and not self.sudo().act_assign_id:
            self.act_assign_id = ActWindow.create({
                'name': 'Assign by Policy',
                'binding_model_id': self.sudo().model_id.id,
                'res_model': 'generic.wizard.assign',
                'view_mode': 'form',
                'target': 'new',
                'context': (
                    "{"
                    "'default_assign_model': active_model,"
                    "'default_assign_object_ids': active_ids,"
                    "}"),
            })
        elif old_val and not new_val and self.sudo().act_assign_id:
            self.sudo().act_assign_id.unlink()

    @api.onchange('model_id')
    def _onchange_model_id(self):
        for rec in self:
            rec.assign_user_field_id = False

    @api.constrains('assign_user_field_id', 'model_id')
    def _check_assign_user_field(self):
        for rec in self.sudo():
            model_ok = rec.assign_user_field_id.model_id == rec.model_id
            type_ok = rec.assign_user_field_id.ttype in ('many2one',
                                                         'many2many')
            relation_ok = rec.assign_user_field_id.relation == 'res.users'
            if not all((model_ok, type_ok, relation_ok)):
                raise exceptions.ValidationError(
                    _('Incorrect combination of assign_user_field_id '
                      'and model_id.'))

    def action_assign_policy_view(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_assignment.action_assign_policy',
            context={'default_model_id': self.sudo().model_id.id},
            domain=[('assign_model_id', '=', self.id)])
