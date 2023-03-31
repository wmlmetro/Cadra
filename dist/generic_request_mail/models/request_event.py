from odoo import models


class RequestEvent(models.Model):
    _inherit = "request.event"

    def get_context(self):
        self.ensure_one()
        context = super().get_context()
        context.update({
            'message_id': self.mail_message_id,
        })
        return context
