import logging
from odoo import models

from odoo.addons.generic_mixin import post_write

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = 'request.request'

    def _filter_sla_rule_line(self, rule_line):
        if rule_line.sudo().service_level_id:
            if not self.service_level_id:
                return False
            if (self.service_level_id.id !=
                    rule_line.sudo().service_level_id.id):
                return False
        if rule_line.sudo().service_id:
            if not self.service_id:
                return False
            if self.service_id.id != rule_line.sudo().service_id.id:
                return False
        return super(RequestRequest, self)._filter_sla_rule_line(rule_line)

    @post_write('service_id', 'service_level_id')
    def _update_request_sla_control_lines(self, changes):
        return super(RequestRequest, self)._update_request_sla_control_lines(
            changes
        )
