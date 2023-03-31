from odoo import models, fields, api


class RequestWizardAssign(models.TransientModel):
    _name = 'request.wizard.assign'
    _description = 'Request Wizard: Assign'

    def _default_user_id(self):
        return self.env.user

    def _default_unsubscribe(self):
        return (
            self.env.user.company_id.request_autoset_unsubscribe_prev_assignee)

    request_ids = fields.Many2many(
        'request.request', string='Requests', required=True)
    user_id = fields.Many2one(
        'res.users', string="User", default=_default_user_id, required=True,
        ondelete='cascade')
    partner_id = fields.Many2one(
        'res.partner', related="user_id.partner_id",
        readonly=True, store=False)
    comment = fields.Text()
    unsubscribe_prev_assignee = fields.Boolean(
        default=_default_unsubscribe,
        string='Unsubscribe previously subscribed')
    # Techical field
    show_field_unsubscribe = fields.Boolean(
        compute='_compute_show_unsubscribe_field')

    @api.onchange('request_ids')
    def _compute_show_unsubscribe_field(self):
        for rec in self:
            rec.show_field_unsubscribe = any([
                bool(r.user_id) for r in rec.request_ids])

    def _prepare_assign(self):
        """ Prepare assign data

            This method have to prepare dict with data to be written to request
        """
        self.ensure_one()
        return {
            'user_id': self.user_id.id,
        }

    def _do_assign_implementation(self, request):
        self.ensure_one()
        request.with_context(
            assign_comment=self.comment
        ).write(self._prepare_assign())

    def _do_assign(self, request):
        prev_assignee = request.user_id
        self._do_assign_implementation(request)
        if self.comment:
            request.message_post(body=self.comment)

        new_assignee = request.user_id
        if (self.unsubscribe_prev_assignee and prev_assignee
                and new_assignee != prev_assignee):
            request._close_mail_activities_for_user(prev_assignee)
            request.message_unsubscribe(
                partner_ids=prev_assignee.partner_id.ids)

    def do_assign(self):
        self.ensure_one()
        self.request_ids.ensure_can_assign()
        for request in self.request_ids:
            self._do_assign(request)
