from odoo import models, fields


class RequestEvent(models.Model):
    _inherit = 'request.event'

    # Assign related events
    old_team_id = fields.Many2one('generic.team', readonly=True)
    new_team_id = fields.Many2one('generic.team', readonly=True)

    def get_context(self):
        self.ensure_one()
        context = super().get_context()
        context.update({
            'old_team': self.old_team_id,
            'new_team': self.new_team_id,
        })
        return context
