import logging
from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)


class RequestStageRouteAction(models.Model):
    _inherit = 'request.event.action'

    act_type = fields.Selection(selection_add=[('survey', 'Survey')],
                                ondelete={'survey': 'cascade'})
    survey_template_id = fields.Many2one('survey.survey')
    survey_send_author = fields.Boolean(default=True)
    survey_send_creator = fields.Boolean()
    survey_send_assignee = fields.Boolean()
    survey_send_others = fields.Boolean()
    survey_partner_ids = fields.Many2many(
        'res.partner',
        'request_event_action_survey_partner_ids_rel',
        'action_id',
        'partner_id',
        string="Partners",
    )
    survey_email_template_id = fields.Many2one(
        'mail.template', ondelete='restrict',
        domain="[('model_id.model', '=', 'request.request')]",
    )

    @api.constrains('survey_email_template_id')
    def _check_url_in_survey_email_template(self):
        for record in self:
            if not record.survey_email_template_id:
                continue
            if "__URL__" not in record.survey_email_template_id.body_html:
                raise exceptions.UserError(
                    _("Please add '__URL__' to email content, \
                    it will automaticaly be converted into survey URL.")
                )

    def _send_survey_prepare_data(self):
        res = {
            'survey_template_id': self.survey_template_id.id,
            'send_author': self.survey_send_author,
            'send_assignee': self.survey_send_assignee,
            'send_creator': self.survey_send_creator,
            'send_others': self.survey_send_others,
            'partner_ids': [(6, 0, self.survey_partner_ids.ids)],
            'template_id': self.survey_email_template_id.id,
        }
        return res

    def _run_send_survey(self, request):
        ctx = request.action_send_request_survey()['context']
        wiz = self.env['request.send.survey'].with_context(**ctx).create(
            self._send_survey_prepare_data())
        wiz.update_from_template()
        wiz.send_mail()

    def _dispatch(self, request, event):
        if self.act_type == 'survey':
            return self._run_send_survey(request)
        return super(RequestStageRouteAction, self)._dispatch(request, event)
