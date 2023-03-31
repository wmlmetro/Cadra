import logging
from odoo.addons.generic_request.tests.common import freeze_time
from .common import RequestSLACase

_logger = logging.getLogger(__name__)


class TestRequestSLA(RequestSLACase):

    def setUp(self):
        super(TestRequestSLA, self).setUp()
        # if rule lines will be added to demo in next modules for
        # sla_draft_support rule,
        # we must reject it, because it can work on any rule line without
        # category and this tests will failed
        self.sla_draft.rule_line_ids.filtered(
            lambda rl: rl not in [self.sla_draft_support,
                                  self.sla_draft_technical]
        ).unlink()

    def test_sla_rule_sla_kanban_state_normal(self):
        Request = self.env['request.request']

        # Set active rule when only kanban state is 'normal'
        self.sla_draft.kanban_state_normal = True

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'request_text': 'Hello!',
            })

            sla_control_draft = self._get_sla_control(request, self.sla_draft)

            self.assertTrue(request.kanban_state == 'normal')
            self.assertTrue(sla_control_draft.sla_active)

        with freeze_time('2017-05-03 9:03:00'):

            # Change kanban state to blocked, the rule must become inactive
            request.kanban_state = 'blocked'
            self.assertTrue(request.kanban_state == 'blocked')
            self.assertFalse(sla_control_draft.sla_active)

        with freeze_time('2017-05-03 10:03:00'):

            # Change kanban state to normal, the rule must become inactive
            request.kanban_state = 'normal'
            self.assertTrue(request.kanban_state == 'normal')
            self.assertTrue(sla_control_draft.sla_active)

        with freeze_time('2017-05-03 11:03:00'):

            # Change kanban state to done, the rule must become inactive
            request.kanban_state = 'done'
            self.assertTrue(request.kanban_state == 'done')
            self.assertFalse(sla_control_draft.sla_active)

    def test_sla_rule_sla_kanban_state_normal_done(self):
        Request = self.env['request.request']

        # Set active rule when only kanban state are 'normal' and 'done'
        self.sla_draft.kanban_state_normal = True
        self.sla_draft.kanban_state_done = True

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'request_text': 'Hello!',
            })

            sla_control_draft = self._get_sla_control(request, self.sla_draft)

            self.assertTrue(request.kanban_state == 'normal')
            self.assertTrue(sla_control_draft.sla_active)

        with freeze_time('2017-05-03 9:03:00'):

            # Change kanban state to blocked, the rule must become inactive
            request.kanban_state = 'blocked'
            self.assertTrue(request.kanban_state == 'blocked')
            self.assertFalse(sla_control_draft.sla_active)

        with freeze_time('2017-05-03 10:03:00'):

            # Change kanban state to normal, the rule must become inactive
            request.kanban_state = 'normal'
            self.assertTrue(request.kanban_state == 'normal')
            self.assertTrue(sla_control_draft.sla_active)

        with freeze_time('2017-05-03 11:03:00'):

            # Change kanban state to blocked, the rule must become inactive
            request.kanban_state = 'blocked'
            self.assertTrue(request.kanban_state == 'blocked')
            self.assertFalse(sla_control_draft.sla_active)

        with freeze_time('2017-05-03 12:03:00'):

            # Change kanban state to normal, the rule must become inactive
            request.kanban_state = 'normal'
            self.assertTrue(request.kanban_state == 'normal')
            self.assertTrue(sla_control_draft.sla_active)

        with freeze_time('2017-05-03 13:03:00'):

            # Change kanban state to done, the rule must become inactive
            request.kanban_state = 'done'
            self.assertTrue(request.kanban_state == 'done')
            self.assertTrue(sla_control_draft.sla_active)

    def test_sla_rule_sla_kanban_state_no_used_in_rule(self):
        Request = self.env['request.request']

        # Kanban state no checked in SLA rule
        self.sla_draft.kanban_state_normal = False
        self.sla_draft.kanban_state_done = False
        self.sla_draft.kanban_state_blocked = False

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'request_text': 'Hello!',
            })

            sla_control_draft = self._get_sla_control(request, self.sla_draft)

            self.assertTrue(request.kanban_state == 'normal')
            self.assertTrue(sla_control_draft.sla_active)

        with freeze_time('2017-05-03 9:03:00'):

            # Change kanban state to blocked, the rule must be active
            request.kanban_state = 'blocked'
            self.assertTrue(request.kanban_state == 'blocked')
            self.assertTrue(sla_control_draft.sla_active)

        with freeze_time('2017-05-03 10:03:00'):

            # Change kanban state to normal, the rule must be active
            request.kanban_state = 'normal'
            self.assertTrue(request.kanban_state == 'normal')
            self.assertTrue(sla_control_draft.sla_active)

        with freeze_time('2017-05-03 11:03:00'):

            # Change kanban state to blocked, the rule must be active
            request.kanban_state = 'blocked'
            self.assertTrue(request.kanban_state == 'blocked')
            self.assertTrue(sla_control_draft.sla_active)

        with freeze_time('2017-05-03 12:03:00'):

            # Change kanban state to normal, the rule must be active
            request.kanban_state = 'normal'
            self.assertTrue(request.kanban_state == 'normal')
            self.assertTrue(sla_control_draft.sla_active)

        with freeze_time('2017-05-03 13:03:00'):

            # Change kanban state to done, the rule must be active
            request.kanban_state = 'done'
            self.assertTrue(request.kanban_state == 'done')
            self.assertTrue(sla_control_draft.sla_active)
