import logging

from odoo import api, _
from odoo.addons.generic_request.tests.common import RequestCase

_logger = logging.getLogger(__name__)


class TestRequestSendSettings(RequestCase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestSendSettings, cls).setUpClass()

        cls.env['ir.config_parameter'].set_param(
            "mail.catchall.domain", "example.com")
        cls.mail_source = cls.env.ref(
            'generic_request_mail.demo_request_mail_source')

        cls.partner_1 = cls.env['res.partner'].with_context(
            mail_create_nolog=True,
            mail_create_nosubscribe=True,
            mail_notrack=True,
            no_reset_password=True,
        ).create({
            'name': 'Valid Lelitre',
            'email': 'valid.lelitre@agrolait.com',
        })

        # Collect sent emails as list of tuples (mail_server_id, message) where
        # message is dict with mail message data to be sent to smtp server.
        cls._sent_emails = []

        # Patch send mail method to save message info before sending
        @api.model
        def send_email(self, message, mail_server_id=None, smtp_server=None,
                       smtp_port=None, smtp_user=None, smtp_password=None,
                       smtp_encryption=None, smtp_debug=False,
                       smtp_session=None):
            cls._sent_emails.append(
                (mail_server_id, message)
            )
            return message['Message-Id']
        cls.env['ir.mail_server']._patch_method('send_email', send_email)

    @classmethod
    def tearDownClass(cls):
        # Remove mocks
        cls.env['ir.mail_server']._revert_method('send_email')
        return super(TestRequestSendSettings, cls).tearDownClass()

    def setUp(self):
        super(TestRequestSendSettings, self).setUp()
        # Clean up saved emails before start new test
        self._sent_emails.clear()

    def test_request_mailing_config_no_mail_source_on_request(self):
        # If mail source is not specified on request,
        # then all messages have to go in standard way:
        # sent via user's email
        request = self.env['request.request'].with_context(
            mail_notify_force_send=True,
        ).with_user(self.request_manager).create({
            'author_id': self.partner_1.id,
            'type_id': self.simple_type.id,
            'request_text': 'Test Request',
        })
        self.assertFalse(request.mail_source_id)

        self.assertEqual(len(self._sent_emails), 1)
        last_mail_srv, last_mail_msg = self._sent_emails[-1]
        self.assertFalse(last_mail_srv)
        self.assertEqual(
            last_mail_msg['From'],
            'Demo Request Manager <demo-request-manager@demo.demo>')
        self.assertEqual(
            last_mail_msg['Reply-To'],
            'YourCompany <catchall@example.com>')
        self.assertEqual(
            last_mail_msg['To'],
            '"Valid Lelitre" <valid.lelitre@agrolait.com>')

        request.with_context(
            mail_notify_force_send=True
        ).message_post(
            body=_("Test Message"),
            subtype_id=self.env.ref('mail.mt_comment').id)
        self.assertEqual(len(self._sent_emails), 2)
        last_mail_srv, last_mail_msg = self._sent_emails[-1]
        self.assertFalse(last_mail_srv)
        self.assertEqual(
            last_mail_msg['From'],
            'Demo Request Manager <demo-request-manager@demo.demo>')
        self.assertEqual(
            last_mail_msg['Reply-To'],
            'YourCompany <catchall@example.com>')
        self.assertEqual(
            last_mail_msg['To'],
            '"Valid Lelitre" <valid.lelitre@agrolait.com>')

    def test_request_mailing_config_default_mail_source_on_request(self):
        # If default mail source configured, then it have to be automatically
        # set on created requests, and also, if mailsource selected,
        # then mailsource address have to be set as 'email_from' header for all
        # messages
        self.env['ir.config_parameter'].set_param(
            'generic_request_mail.default_mail_source_id',
            self.mail_source.id)

        request = self.env['request.request'].with_context(
            mail_notify_force_send=True,
        ).with_user(self.request_manager).create({
            'author_id': self.partner_1.id,
            'type_id': self.simple_type.id,
            'request_text': 'Test Request',
        })
        self.assertEqual(request.mail_source_id, self.mail_source)

        self.assertEqual(len(self._sent_emails), 1)
        last_mail_srv, last_mail_msg = self._sent_emails[-1]
        self.assertFalse(last_mail_srv)
        self.assertEqual(
            last_mail_msg['From'],
            'YourCompany Demo Requests '
            '<demo-requests@example.com>')
        self.assertEqual(
            last_mail_msg['Reply-To'],
            'YourCompany Demo Requests '
            '<demo-requests@example.com>')
        self.assertEqual(
            last_mail_msg['To'],
            '"Valid Lelitre" <valid.lelitre@agrolait.com>')

        request.with_context(
            mail_notify_force_send=True
        ).message_post(
            body=_("Test Message"),
            subtype_id=self.env.ref('mail.mt_comment').id)
        self.assertEqual(len(self._sent_emails), 2)
        last_mail_srv, last_mail_msg = self._sent_emails[-1]
        self.assertFalse(last_mail_srv)
        self.assertEqual(
            last_mail_msg['From'],
            'YourCompany Demo Requests '
            '<demo-requests@example.com>')
        self.assertEqual(
            last_mail_msg['Reply-To'],
            'YourCompany Demo Requests '
            '<demo-requests@example.com>')
        self.assertEqual(
            last_mail_msg['To'],
            '"Valid Lelitre" <valid.lelitre@agrolait.com>')
