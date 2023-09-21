import logging

from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)


class GenericWizardAssign(models.TransientModel):
    _name = 'generic.wizard.assign'
    _description = 'Generic Wizard: Assign'

    def _default_user_id(self):
        return self.env.user

    assign_model_id = fields.Many2one(
        'generic.assign.policy.model', required=True, readonly=True)
    assign_model = fields.Char(
        related='assign_model_id.model_id.model', readonly=True)
    assign_type = fields.Selection(
        [('user', 'User'),
         ('policy', 'Policy')],
        'Type',
        required=True, default='user')
    assign_user_id = fields.Many2one(
        'res.users', 'User', default=_default_user_id)
    assign_policy_id = fields.Many2one('generic.assign.policy', 'Policy')
    assign_comment = fields.Text('Comment')
    unsubscribe_prev_assignee = fields.Boolean(
        string='Unsubscribe previously subscribed')

    @api.model
    def default_get(self, fields_list):
        default = super(GenericWizardAssign, self).default_get(fields_list)
        context = self.env.context
        default_assign_model = context.get('default_assign_model', False)
        default_assign_model_id = context.get('default_assign_model_id', False)
        if (default_assign_model is not False and
                default_assign_model_id is False):
            model = self.sudo().env['ir.model'].search(
                [('model', '=', default_assign_model)])
            assign_model_id = model.assignment_model_ids
            default.update({'assign_model_id': assign_model_id.id})
        return default

    def _close_mail_activities_for_user(self, assign_obj, user):
        self.ensure_one()
        user_activities = self.env['mail.activity'].search([
            ('res_id', '=', assign_obj.id),
            ('res_model', '=', assign_obj._name),
            ('user_id', '=', user.id)
        ])
        for activity in user_activities:
            activity.action_feedback(
                _('Closing this activity because assignee was unsubscribed!'))

    def _unsubscribe_user_from_object(self, assign_obj, user):
        self._close_mail_activities_for_user(assign_obj, user)
        assign_obj.message_unsubscribe(partner_ids=user.partner_id.ids)

    def _do_assign_user(self, assign_obj):
        """ Assign object to user

            :param Record assign_obj: object to be assigned
        """
        field_name = self.sudo().assign_model_id.assign_user_field_id.name
        assign_obj.write({
            field_name: self.assign_user_id.id,
        })

    def _do_assign_policy(self, assign_obj):
        """ Assign object to user

            :param Record assign_obj: object to be assigned
        """
        if self.assign_model_id != self.assign_policy_id.assign_model_id:
            raise exceptions.ValidationError(_(
                "Assign model (%(assign_model)s) must be equal to "
                "policy's assign model %(policy_model)s"
                "") % {
                    'assign_model': self.assign_model_id.model,
                    'policy_model':
                        self.assign_policy_id.assign_model_id.model,
                })

        self.assign_policy_id.do_assign(assign_obj)

    def _do_assign_dispatch(self, assign_obj):
        """ Assign object

            :param Record assign_obj: object to be assigned
        """
        if self.assign_model_id.model != assign_obj._name:
            raise exceptions.ValidationError(_(
                "Assign object's model (%(obj_model)s) must be equal to "
                "policy's assign model %(policy_model)s"
                "") % {
                    'obj_model': assign_obj._name,
                    'policy_model':
                        self.assign_policy_id.assign_model_id.model,
                })

        if self.assign_type == 'user':
            self._do_assign_user(assign_obj)
        elif self.assign_type == 'policy':
            self._do_assign_policy(assign_obj)
        else:
            raise exceptions.UserError(_('Wrong assign type selected'))

    def _do_assign(self, assign_obj):

        prev_assignee = assign_obj[
            self.sudo().assign_model_id.assign_user_field_id.name]
        self._do_assign_dispatch(assign_obj)
        if self.assign_comment and hasattr(assign_obj, 'message_post'):
            assign_obj.message_post(body=self.assign_comment)

        new_assignee = assign_obj[
            self.sudo().assign_model_id.assign_user_field_id.name]
        if (self.unsubscribe_prev_assignee and prev_assignee and
                new_assignee != prev_assignee):
            self._unsubscribe_user_from_object(assign_obj, prev_assignee)

    def do_assign(self):
        self.ensure_one()
        AssignModel = self.env[self.assign_model]
        assign_obj_ids = self.env.context.get('default_assign_object_ids', [])
        for assign_obj_id in assign_obj_ids:
            assign_obj = AssignModel.with_context(
                assign_comment=self.assign_comment).browse(assign_obj_id)
            self._do_assign(assign_obj)

        return True
