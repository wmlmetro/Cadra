from odoo import api, fields, models, exceptions, _
from .request_sla_rule import SLA_COMPUTE_TIME


class RequestSlaRuleLine(models.Model):
    _name = 'request.sla.rule.line'
    _description = 'Request SLA Rule Line'
    _order = 'sequence'

    sequence = fields.Integer(
        required=True, index=True, default=5)
    category_ids = fields.Many2many(
        'request.category', string='Request Categories')
    request_channel_ids = fields.Many2many(
        'request.channel', string="Request Channels"
    )
    sla_rule_id = fields.Many2one(
        'request.sla.rule', 'SLA Rule', required=True,
        index=True, readonly=True)
    compute_time = fields.Selection(
        SLA_COMPUTE_TIME, required=True)
    request_type_id = fields.Many2one(
        'request.type', related='sla_rule_id.request_type_id')
    warn_time = fields.Float(tracking=True)
    limit_time = fields.Float(required=True, tracking=True)
    sla_calendar_id = fields.Many2one(
        'resource.calendar', string="Working time")

    @api.constrains('compute_time', 'sla_calendar_id')
    def _check_calendar_rules(self):
        for rec in self:
            if rec.compute_time != 'calendar':
                continue
            if not (rec.sla_calendar_id or
                    rec.sla_rule_id.sla_calendar_id or
                    rec.request_type_id.sla_calendar_id):
                raise exceptions.ValidationError(_(
                    "Cannot set compute time to Working time, because "
                    "request SLA Rule Line '%s' have no configured "
                    "Working time!") % rec.display_name)

    @api.onchange('sla_rule_id', 'category_ids', 'request_type_id')
    def _onchange_filter_categories(self):
        self.ensure_one()
        for category in self.category_ids:
            if category._origin not in self.request_type_id.category_ids:
                self.category_ids -= category

        return {
            'domain': {
                'category_ids': [
                    ('request_type_ids', 'in', self.request_type_id.id),
                ],
            },
        }
