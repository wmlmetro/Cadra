from odoo import models
from odoo.addons.generic_mixin import pre_write, post_write


class RequestRequest(models.Model):
    _inherit = 'request.request'

    def _prepare_sla_log_vals(self):
        vals = super(RequestRequest, self)._prepare_sla_log_vals()
        vals['team_id'] = self.team_id.id
        return vals

    @pre_write('team_id')
    def _generate_request_sla_log_line(self, changes):
        return super(RequestRequest, self)._generate_request_sla_log_line(
            changes)

    def _prepare_sla_control_line(self, rule):
        vals = super(RequestRequest, self)._prepare_sla_control_line(rule)
        vals['assigned_team'] = rule.assigned_team
        return vals

    @post_write('team_id')
    def _post_write_trigger_sla_rule_active(self, changes):
        return super()._post_write_trigger_sla_rule_active(changes)
