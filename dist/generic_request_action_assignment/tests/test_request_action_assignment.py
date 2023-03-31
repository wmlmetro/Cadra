import logging

from odoo.addons.generic_request_action.tests.common import (
    RouteActionsTestCase
)

_logger = logging.getLogger(__name__)


class TestMailActivityAssignment(RouteActionsTestCase):

    @classmethod
    def setUpClass(cls):
        super(TestMailActivityAssignment, cls).setUpClass()
        cls.user_policy = cls.env.ref('base.demo_user0')
        cls.action_policy = cls.env.ref(
            'generic_request_action_assignment.'
            'request_stage_route_type_action_'
            'draft_to_sent_mail_activity_policy')
        cls.activity_type_email = cls.env.ref(
            'mail.mail_activity_data_email')
        cls.activity_type_call = cls.env.ref(
            'mail.mail_activity_data_call')
        cls.user_policy.groups_id += cls.env.ref(
            'generic_request.group_request_user_implicit')

    def test_mail_activity_assignment(self):
        request = self.demo_request
        self.assertEqual(request.stage_id, self.stage_draft)

        request.stage_id = self.stage_sent
        self.assertEqual(request.stage_id, self.stage_sent)

        mail_activity_user = self.env['mail.activity'].search(
            [('res_id', '=', request.id),
             ('res_model', '=', 'request.request')]).mapped('user_id.id')

        self.assertIn(self.user_policy.id, mail_activity_user)
