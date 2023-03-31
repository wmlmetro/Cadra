from odoo import models


class RequestRequest(models.Model):
    _inherit = 'request.request'

    def _hook_can_change_service(self):
        if self.sudo().type_id.change_service_condition_ids:
            return self.sudo().type_id.change_service_condition_ids.with_user(
                self.env.user).check(self)
        return super(RequestRequest, self)._hook_can_change_service()
