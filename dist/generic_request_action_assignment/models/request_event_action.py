from odoo import models, fields


class RequestStageRouteAction(models.Model):
    _inherit = "request.event.action"

    # Assign related fields
    assign_type = fields.Selection(
        selection_add=[('policy', 'Policy')],
        ondelete={'policy': 'cascade'})
    assign_policy_id = fields.Many2one(
        'generic.assign.policy', ondelete='restrict',
        domain="[('model_id.model', '=', 'request.request')]",
        tracking=True)

    # Mail activity fields
    mail_activity_assign_type = fields.Selection(
        selection_add=[('policy', 'Policy')],
        ondelete={'policy': 'cascade'})
    mail_activity_assign_policy_id = fields.Many2one(
        'generic.assign.policy', ondelete='restrict',
        domain="[('model_id.model', '=', 'request.request')]",
        tracking=True)
    mail_activity_assign_policy_user_id = fields.Many2one(
        'res.users', 'Fallback user',
        help="This user will be assigned to mail activity "
             "if policy returns no users")

    subrequest_assign_policy_id = fields.Many2one(
        'generic.assign.policy',
        'Subrequest assign by policy',
        ondelete='restrict',
        domain="[('model_id.model', '=', 'request.request')]",
        tracking=True)

    def _get_mail_activity_user_id(self, request):
        if self.mail_activity_assign_type == 'policy':
            policy = self.mail_activity_assign_policy_id
            assignee = policy.get_assign_data(request).get('user_id')
            if not assignee:
                assignee = self.mail_activity_assign_policy_user_id.id
            return assignee
        return super(
            RequestStageRouteAction, self
        )._get_mail_activity_user_id(request)

    def _run_assign(self, request, event):
        if self.assign_type == 'policy':
            self.assign_policy_id.do_assign(request)
        return super(RequestStageRouteAction, self)._run_assign(request, event)

    def _run_subrequest_postprocess_subrequest(self, request, event,
                                               subrequest):
        if self.subrequest_assign_policy_id:
            self.subrequest_assign_policy_id.do_assign(subrequest)
        return super(
            RequestStageRouteAction, self
        )._run_subrequest_postprocess_subrequest(request, event, subrequest)
