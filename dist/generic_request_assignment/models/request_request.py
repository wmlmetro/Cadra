from odoo import models


class RequestRequest(models.Model):
    _inherit = "request.request"

    def action_request_assign(self):
        self.ensure_can_assign()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_assignment.action_assignment_wizard_assign',
            context={
                'default_assign_model': self._name,
                'default_assign_object_ids': self.ids,
            })
