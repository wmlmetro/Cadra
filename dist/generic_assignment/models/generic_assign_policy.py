import logging

from odoo import models, fields, api, _, exceptions
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

_logger = logging.getLogger(__name__)


class GenericAssignPolicy(models.Model):
    _name = 'generic.assign.policy'
    _inherit = [
        'mail.thread',
    ]
    _description = 'Assignment Policy'

    name = fields.Char(required=True, index=True, translate=True)
    model_id = fields.Many2one(
        'ir.model', required=True, index=True, ondelete='cascade',
        tracking=True)
    model_name = fields.Char(
        related='model_id.model', readonly=True,
        store=True, index=True)
    assign_model_id = fields.Many2one(
        'generic.assign.policy.model', compute='_compute_assign_model_id',
        readonly=True, index=True, ondelete='set null',
        store=True, tracking=True)
    active = fields.Boolean(
        index=True, default=True, tracking=True)
    rule_ids = fields.One2many(
        'generic.assign.policy.rule', 'policy_id',
        tracking=True)
    rule_count = fields.Integer(
        compute='_compute_rule_count', readonly=True)
    rule_not_unique = fields.Boolean(
        'Rules priority is not unique',
        compute='_compute_rule_unique', readonly=True)
    assign_user_field_id = fields.Many2one(
        'ir.model.fields', related='assign_model_id.assign_user_field_id',
        store=True, readonly=True, ondelete='cascade')
    description = fields.Text(translate=True)

    @api.depends('rule_ids')
    def _compute_rule_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='rule_ids')
        for record in self:
            record.rule_count = mapped_data.get(record.id, 0)

    @api.depends('rule_ids')
    def _compute_rule_unique(self):
        for rec in self:
            sequences = rec.rule_ids.mapped('sequence')
            rec.rule_not_unique = len(sequences) != len(set(sequences))

    @api.depends('model_id', 'model_id.assignment_model_ids')
    def _compute_assign_model_id(self):
        for rec in self:
            rec.assign_model_id = rec.sudo().model_id.assignment_model_ids

    @api.model
    def default_get(self, field_names):
        if self.env.context.get('default_model'):
            model = self.sudo().env['ir.model'].search(
                [('model', '=', self.env.context['default_model'])])
            if len(model) == 1:
                return super(
                    GenericAssignPolicy,
                    self.with_context(default_model_id=model.id)
                ).default_get(field_names)
        return super(GenericAssignPolicy, self).default_get(field_names)

    @api.onchange('model_id')
    def _onchange_model_id(self):
        for record in self:
            record.rule_ids = False

    def get_assignment_fields_info(self):
        self.ensure_one()
        return {
            'user_id': {
                'model': 'res.users',
                'field_name': self.sudo().assign_user_field_id.name,
                'savable': bool(self.sudo().assign_user_field_id),
            },
        }

    def get_assign_data(self, record, debug_log=None):
        self.ensure_one()
        condition_cache = {}
        for rule in self.rule_ids:
            if not rule.condition_ids.check(record, cache=condition_cache):
                rule._debug_log(
                    debug_log, record,
                    "Skipping because rule conditions not pass")
                continue

            assign_data = rule.get_assign_data(record, debug_log=debug_log)
            if assign_data is not False:
                return assign_data
        return False

    def convert_assign_data(self, assign_data, debug_log=None):
        self.ensure_one()
        if not assign_data:
            return {}

        res = {}
        for atype, ainfo in self.get_assignment_fields_info().items():
            if not ainfo['savable'] and assign_data.get(atype):
                raise exceptions.UserError(
                    _("This policy cannot be used to set assignee,"
                      " because policy model is not configured,"
                      " but it could be used to compute assign data"
                      " based on model: %s") % self.assign_model_id.name
                )
            if assign_data.get(atype):
                res[ainfo['field_name']] = assign_data[atype]

        return res

    def do_assign(self, record):
        self.ensure_one()
        assign_data = self.get_assign_data(record)
        value = self.convert_assign_data(assign_data)

        # [15.0 project] Do some post processing to handle many2many fields,
        # like that one in project task
        # TODO: backport this on 12.0
        for field_name, field_val in value.items():
            if not field_val:
                continue
            if (record._fields[field_name].type == 'many2many' and
                    isinstance(field_val, int)):
                value[field_name] = [(6, 0, [field_val])]
        record.write(value)

    def action_assign_policy_rule_view(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_assignment.action_assign_policy_rule',
            context={'default_policy_id': self.id},
            domain=[('policy_id', '=', self.id)])

    def action_show_test_wizard(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_assignment.action_generic_assign_policy_test_wizard_view',
            context={'default_assign_policy_id': self.id})
