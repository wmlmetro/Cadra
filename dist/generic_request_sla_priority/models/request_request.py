import logging
from odoo import models

from odoo.addons.generic_request.models.request_request import (
    TRACK_FIELD_CHANGES,
)
from odoo.addons.generic_mixin import post_write


_logger = logging.getLogger(__name__)

TRACK_FIELD_CHANGES.add('priority')


class RequestRequest(models.Model):
    _inherit = 'request.request'

    def _filter_sla_rule_line(self, rule_line):
        if int(rule_line.sudo().priority):
            if not self.priority:
                return False
            if (self.priority !=
                    rule_line.sudo().priority):
                return False
        return super(RequestRequest, self)._filter_sla_rule_line(rule_line)

    @post_write('priority')
    def _update_request_sla_control_lines(self, changes):
        return super(RequestRequest, self)._update_request_sla_control_lines(
            changes
        )
