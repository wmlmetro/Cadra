from odoo import fields, models, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class RequestSlaRuleType(models.Model):
    _name = 'request.sla.rule.type'
    _inherit = [
        'mail.thread',
        'generic.mixin.name_with_code',
        'generic.mixin.uniq_name_code',
    ]
    _description = 'Request SLA rule type'

    # Defined in generic.mixin.name_with_code
    name = fields.Char(tracking=True)
    code = fields.Char(tracking=True)

    description = fields.Text(translate=True)
    active = fields.Boolean(index=True, default=True)

    sla_rule_ids = fields.One2many(
        'request.sla.rule', 'sla_rule_type_id', string='SLA Rules')
    sla_rule_count = fields.Integer(
        compute='_compute_sla_rule_count', readonly=True)

    @api.depends('sla_rule_ids')
    def _compute_sla_rule_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='sla_rule_ids')
        for record in self:
            record.sla_rule_count = mapped_data.get(record.id, 0)
