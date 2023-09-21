import logging
from odoo import models, fields, api

from odoo.addons.generic_mixin import post_create

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = 'request.request'

    mail_source_id = fields.Many2one(
        'request.mail.source', index=True, readonly=True)

    def _notify_get_reply_to(self, default=None, records=None,
                             company=None, doc_names=None):
        res = super(RequestRequest, self)._notify_get_reply_to(
            default=default, records=None,
            company=company, doc_names=None)

        # Update result with aliases from mail source
        aliases = self.sudo().mapped('mail_source_id')._notify_get_reply_to(
            default=default, records=None, company=company, doc_names=None)
        res.update({
            request.id: aliases[request.mail_source_id.id]
            for request in self.sudo()
            if aliases.get(request.mail_source_id.id)
        })
        return res

    def _send_default_notification__get_email_from(self, **kw):
        """ Compute From header for email notification to be sent
        """
        self_sudo = self.sudo()
        if self_sudo.mail_source_id:
            return self_sudo.mail_source_id.get_email_from_address(
                author=self.env.user.partner_id,
                company=self_sudo.company_id)
        return super(
            RequestRequest, self
        )._send_default_notification__get_email_from(**kw)

    @api.model
    def _add_missing_default_values(self, values):
        res = super(RequestRequest, self)._add_missing_default_values(values)

        mail_source = self.sudo().env['ir.config_parameter'].get_param(
            'generic_request_mail.default_mail_source_id')
        if mail_source and not res.get('mail_source_id'):
            res.update({
                'mail_source_id': int(mail_source),
            })
        return res

    @post_create()
    def _after_create_link_source_mail_message(self, changes):
        # If request was create from email, then link that email to created
        # request
        from_message_id = self.env.context.get("from_message_id", False)
        if from_message_id:
            self.env['mail.message'].browse(from_message_id).write({
                'model': 'request.request',
                'res_id': self.id,
                'record_name': self.display_name,
            })

    def _validate_incoming_message(self, msg_dict):
        res = super()._validate_incoming_message(msg_dict)

        msg = self.env['mail.message'].new({
            f: v for f, v in msg_dict.items()
            if f in self.env['mail.message']._fields
        })
        company = self.env.user.company_id
        if not company.request_incoming_mail_validator_ids.check(msg):
            raise ValueError(
                "Cannot create request from email!\n"
                "Reason: Email was not passed validation via conditions!\n"
                "Subject: %s\n"
                "From: %s\n"
                "To: %s\n"
                "Message ID: %s" % (msg_dict.get('subject'),
                                    msg_dict.get('from'),
                                    msg_dict.get('to'),
                                    msg_dict.get('message_id')))
        return res
