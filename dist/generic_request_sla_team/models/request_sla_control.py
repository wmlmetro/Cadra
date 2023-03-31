from odoo import models, fields


class RequestSlaControl(models.Model):

    _inherit = 'request.sla.control'

    assigned_team = fields.Selection(
        required=True,
        selection=[('none', 'None'), ('yes', 'Yes'), ('no', 'No')],
        default='none',
    )

    def _is_log_line_satisfy_this_rule(self, log_line):
        """ Check if specified log line satisfy this SLA rule
        """
        self.ensure_one()
        if self.assigned_team == 'no' and log_line.team_id:
            return False
        if self.assigned_team == 'yes' and not log_line.team_id:
            return False
        return super(RequestSlaControl, self)._is_log_line_satisfy_this_rule(
            log_line)

    def _is_active(self):
        # Is active by assigned team state?
        if self.assigned_team == 'yes' and not self.request_id.team_id:
            return False
        if self.assigned_team == 'no' and self.request_id.team_id:
            return False
        return super(RequestSlaControl, self)._is_active()
