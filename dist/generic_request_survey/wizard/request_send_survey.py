import werkzeug

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RequestSendSurvey(models.TransientModel):

    _name = 'request.send.survey'
    _description = "Wizard: Send Request Survey"

    request_id = fields.Many2one(
        'request.request',
        required=True,
        ondelete="cascade",
    )

    # Composer fields
    subject = fields.Char()
    body = fields.Html('Contents', default='', sanitize_style=True)
    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='request_survey_mail_compose_message_ir_attachments_rel',
        column1='wizard_id',
        column2='attachment_id',
        string='Attachments')
    template_id = fields.Many2one(
        'mail.template', 'Use template',
        domain="[('model', '=', 'request.request')]")

    send_author = fields.Boolean(default=True)
    send_creator = fields.Boolean()
    send_assignee = fields.Boolean()
    send_others = fields.Boolean()
    is_author_creator = fields.Boolean(
        default=False,
        compute='_compute_is_author_creator',
    )
    partner_ids = fields.Many2many(
        'res.partner',
        'request_send_survey_res_partner_rel',
        'wizard_id',
        'partner_id',
        string="Partners",
    )

    survey_template_id = fields.Many2one(
        'survey.survey',
        required=True,
    )

    @api.depends('request_id')
    def _compute_is_author_creator(self):
        for rec in self:
            rec.is_author_creator = (rec.request_id.author_id ==
                                     rec.request_id.created_by_id.partner_id)

    @api.onchange('template_id')
    def _onchange_template_id(self):
        """ Update subject and body from selected mail template
        """
        if self.template_id:
            self.update_from_template()

    def update_from_template(self):
        self.ensure_one()
        self.template_id.ensure_one()
        values = self.template_id.generate_email(
            self.request_id.id, fields=['subject', 'body_html'])
        self.subject = values.get('subject')
        self.body = values.get('body')

    def create_response_and_send_mail(self, token, partner_id):
        self.ensure_one()
        Mail = self.env['mail.mail']

        # set url
        url = '%s?%s' % (
            self.survey_template_id.get_start_url(),
            werkzeug.urls.url_encode({
                'answer_token': token,
            })
        )

        # post the message
        values = {
            'model': 'request.request',
            'res_id': self.request_id.id,
            'subject': self.subject,
            'body': self.body.replace("__URL__", url),
            'body_html': self.body.replace("__URL__", url),
            'parent_id': None,
            'auto_delete': False,
        }
        values['recipient_ids'] = [(4, partner_id)]
        Mail.create(values).send()

    def create_token(self, partner_id):
        self.ensure_one()

        partner = self.env['res.partner'].browse(partner_id)
        survey_user_input = self.survey_template_id._create_answer(
            partner=partner,
            request_id=self.request_id.id,
        )
        return survey_user_input.access_token

    def send_mail(self):
        self.ensure_one()
        partners_recipients = set()
        if self.send_author:
            partners_recipients.add(self.request_id.author_id.id)
        if self.send_creator:
            partners_recipients.add(
                self.request_id.created_by_id.partner_id.id)
        if self.send_assignee and self.request_id.user_id:
            partners_recipients.add(self.request_id.user_id.partner_id.id)
        if self.partner_ids and self.send_others:
            partners_recipients.update(self.partner_ids.ids)

        # check if __URL__ is in the text
        if self.body.find("__URL__") < 0:
            raise UserError(
                _("Please add '__URL__' to email content, \
                it will automaticaly be converted into survey url."))
        # check if there are some recipients
        if not partners_recipients:
            raise UserError(_("Please select at least one recipient."))

        for partner_id in partners_recipients:
            token = self.create_token(partner_id)
            self.create_response_and_send_mail(token, partner_id)
        return {'type': 'ir.actions.act_window_close'}
