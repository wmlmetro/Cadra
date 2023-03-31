from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import ReduceLoggingMixin


class TestSendSurveyAction(ReduceLoggingMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestSendSurveyAction, cls).setUpClass()

        cls.test_request_type = cls.env.ref(
            'generic_request_action_survey.request_type_with_survey')
        cls.test_route = cls.env.ref(
            'generic_request_action_survey.'
            'request_stage_type_with_survey_new_to_survey_sent')
        cls.stage_new = cls.env.ref(
            'generic_request_action_survey.'
            'request_stage_type_with_survey_new')
        cls.stage_survey_sent = cls.env.ref(
            'generic_request_action_survey.'
            'request_stage_type_with_survey_survey_sent')
        cls.survey_template_id = cls.env.ref(
            'generic_request_survey.request_bug_form')
        cls.test_action = cls.env.ref(
            'generic_request_action_survey.'
            'demo_send_survey_action')
        cls.test_request = cls.env.ref(
            'generic_request_action_survey.demo_request_with_survey')
        cls.author = cls.env.ref('base.res_partner_1')
        cls.test_request.author_id = cls.author.id

    def test_send_survey_action(self):
        self.assertEqual(self.test_request.stage_id, self.stage_new)
        self.assertNotIn(
            'survey_sent',
            self.test_request.request_event_ids.mapped('event_type_id.code')
        )
        survey_emails = self.env['mail.mail'].search([(
            'body_html', 'like', 'We are conducting a survey'
        )])
        self.assertEqual(len(survey_emails), 0)

        # move along the route
        self.test_request.stage_id = self.stage_survey_sent
        self.assertIn(
            'survey_sent',
            self.test_request.request_event_ids.mapped('event_type_id.code')
        )
        survey_emails = self.env['mail.mail'].search([(
            'body_html', 'like', 'We are conducting a survey'
        )])
        self.assertEqual(len(survey_emails), 1)
        self.assertEqual(
            survey_emails.subject, "Survey for %s" % self.test_request.name)
