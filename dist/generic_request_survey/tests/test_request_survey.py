import logging
from odoo.tests.common import TransactionCase
from odoo.addons.generic_request.tests.common import ReduceLoggingMixin

_logger = logging.getLogger(__name__)


class TestRequestSurvey(ReduceLoggingMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestSurvey, cls).setUpClass()

        cls.assignee = cls.env.ref(
            'generic_request.user_demo_request_manager'
        )
        cls.author = cls.env.ref('base.res_partner_1')
        cls.partner = cls.env.ref('base.res_partner_2')
        cls.user_admin = cls.env.ref('base.user_admin')

    def test_generic_request_survey(self):
        # create request
        request = self.env['request.request'].with_user(
            self.user_admin
        ).create({
            'type_id': self.env.ref(
                'generic_request.request_type_sequence').id,
            'request_text': 'Test',
            'author_id': self.author.id,
            'user_id': self.assignee.id,
        })

        # create survey
        survey = self.env['survey.survey'].sudo().create(
            {'title': "S1", 'page_ids': [(0, 0, {'title': "P1"})]})

        # subscribe Agrolite partner to request
        request.message_subscribe([self.partner.id, ])

        survey_subject = '{}: Test Survey'.format(request.name)
        SendSurveyWizard = self.env['request.send.survey']
        survey_ctx = request.action_send_request_survey()['context']

        # open request_send_survey wizard
        send_survey_wizard = SendSurveyWizard.sudo().with_context(
            **survey_ctx).create({
                'survey_template_id': survey.id,
                'body': "test survey body __URL__",
                'subject': survey_subject,
                'send_author': True,
                'send_assignee': True,
                'send_creator': True,
                'send_others': True,
            })

        # send emails to recipients
        send_survey_wizard.send_mail()

        # test event - Survey Sent
        self.assertIn(
            'survey_sent',
            request.request_event_ids.mapped('event_type_id.code')
            )

        survey_emails = self.env['mail.mail'].search([(
            'subject', '=', survey_subject
        )])

        # check number of sent emails
        self.assertEqual(len(survey_emails), 4)

        temp_message_body_list = []
        temp_recipients_list = [
            self.author,
            self.assignee.partner_id,
            self.user_admin.partner_id,
            self.partner
        ]
        for email in survey_emails:
            # check email content of sent emails
            self.assertIn('test survey body', email.body)

            # check if users get unique survey links
            self.assertNotIn(email.body, temp_message_body_list)
            temp_message_body_list.append(email.body)

            # check if email sent only to selected recipients
            self.assertIn(email.recipient_ids, temp_recipients_list)
            temp_recipients_list.remove(email.recipient_ids)

        # check if emails sent to all recipients
        self.assertFalse(temp_recipients_list)

        # check number of displayed completed answers
        self.assertFalse(request.answer_count)

        # complete one survey answer
        request.answer_ids[0].state = 'done'

        # check number of displayed completed answers
        self.assertEqual(request.answer_count, 1)

        # test event - Survey Answer Received
        self.assertIn(
            'survey_answer_received',
            request.request_event_ids.mapped('event_type_id.code')
        )

        self.assertNotIn(
            'survey_completed',
            request.request_event_ids.mapped('event_type_id.code')
        )

        # survey completed
        for answer in request.answer_ids:
            answer.state = 'done'

        # test event - Survey Completed
        self.assertIn(
            'survey_completed',
            request.request_event_ids.mapped('event_type_id.code')
        )
