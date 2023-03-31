from odoo import fields, models, api
from odoo.osv import expression


class RequestSlaRuleLine(models.Model):
    _inherit = 'request.sla.rule.line'

    service_id = fields.Many2one(
        'generic.service', index=True)
    service_level_id = fields.Many2one(
        'generic.service.level', index=True)

    @api.onchange(
        'service_id', 'category_ids', 'sla_rule_id', 'request_type_id')
    def _onchange_filter_categories(self):
        res = super(RequestSlaRuleLine, self)._onchange_filter_categories()
        if not self.service_id:
            return res

        for category in self.category_ids:
            if category._origin not in self.service_id.category_ids:
                self.category_ids -= category

        res['domain']['category_ids'] = expression.AND([
            res['domain']['category_ids'],
            [('service_ids', 'in', self.service_id.id)]
        ])
        return res
