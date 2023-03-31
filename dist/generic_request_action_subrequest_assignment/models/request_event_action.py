from odoo import models, fields


class RequestStageRouteAction(models.Model):
    _inherit = "request.event.action"

    subrequest_assign_policy_id = fields.Many2one(
        'generic.assign.policy',
        'Subrequest assign by policy',
        ondelete='restrict',
        domain="[('model_id.model', '=', 'request.request')]",
        tracking=True)

    def _run_subrequest_postprocess_subrequest(self, request, event,
                                               subrequest):
        if self.subrequest_assign_policy_id:
            self.subrequest_assign_policy_id.do_assign(subrequest)
        return super(
            RequestStageRouteAction, self
        )._run_subrequest_postprocess_subrequest(request, event, subrequest)
