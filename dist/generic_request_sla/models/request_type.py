from odoo import fields, models, api, exceptions, _
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class RequestType(models.Model):
    _inherit = 'request.type'

    sla_rule_ids = fields.One2many(
        'request.sla.rule', 'request_type_id', 'SLA Rules')
    sla_rule_count = fields.Integer(
        compute='_compute_sla_rules_data', store=True, readonly=True,
        compute_sudo=True)
    sla_main_rule_id = fields.Many2one(
        'request.sla.rule', 'Main SLA Rule', store=True, readonly=True,
        compute='_compute_sla_rules_data', compute_sudo=True,
        help="To change, just move required SLA rule "
             "to the top of the list on the SLA Rules page. "
             "Or specify the lowest Sequence on the Rule form.")
    sla_compute_type = fields.Selection(
        [('main_sla_rule', 'Main SLA Rule'),
         ('least_date_worst_status', 'Least Date Worst Status'),
         ('conditional', 'Conditional')],
        default='main_sla_rule')
    sla_rule_condition_ids = fields.One2many(
        'request.sla.rule.condition', 'request_type_id',
        string='SLA Rule Conditions',
        help="Specify generic conditions to decide whether the activity "
             "can be executed.")

    # Notification configuration
    send_default_notification_sla_warn = fields.Boolean(default=True)
    sla_warn_notification_show_request_text = fields.Boolean(default=True)
    sla_warn_notification_show_response_text = fields.Boolean()
    send_default_notification_sla_limit = fields.Boolean(default=True)
    sla_limit_notification_show_request_text = fields.Boolean(default=True)
    sla_limit_notification_show_response_text = fields.Boolean()

    @api.constrains('sla_calendar_id')
    def _check_calendar_rules(self):
        for rec in self:
            if rec.sla_calendar_id:
                continue
            rule_need_calendar = rec.sla_rule_ids.filtered(
                lambda r: (r.compute_time == 'calendar' and
                           not r.sla_calendar_id))
            rule_line_need_calendar = rec.sla_rule_ids.mapped(
                'rule_line_ids').filtered(
                    lambda r: (
                        r.compute_time == 'calendar' and
                        not (r.sla_calendar_id or r.rule_id.sla_calendar_id)
                    )
                )
            if rule_need_calendar or rule_line_need_calendar:
                raise exceptions.ValidationError(_(
                    "Request type '%s' must have Working time, because it "
                    "have SLA rules or at least one from SLA rule lines "
                    "that depend on Working time!") % rec.display_name)

    @api.depends('sla_rule_ids', 'sla_rule_ids.sequence',
                 'sla_rule_ids.active', 'sla_compute_type')
    def _compute_sla_rules_data(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='sla_rule_ids')
        for record in self:
            record.sla_rule_count = mapped_data.get(record.id, 0)
            if not record.sla_rule_ids:
                record.sla_main_rule_id = False
            elif record.sla_compute_type == 'main_sla_rule':
                record.sla_main_rule_id = record.sla_rule_ids.sorted()[0]
            else:
                # SLA Comput type seems to be least_date_worst_status
                record.sla_main_rule_id = False

    def action_show_request_sla_rules(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request_sla.generic_request_sla_rule_action',
            domain=[('request_type_id', '=', self.id)],
            context={'default_request_type_id': self.id},
        )
