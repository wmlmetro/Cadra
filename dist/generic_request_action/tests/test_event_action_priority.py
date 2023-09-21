import logging
from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import ReduceLoggingMixin
_logger = logging.getLogger(__name__)


class TestPriority(ReduceLoggingMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestPriority, cls).setUpClass()
        cls.test_request_type = cls.env.ref(
            'generic_request.request_type_simple')
        cls.test_request_type_complex = cls.env.ref(
            'generic_request.request_type_with_complex_priority')
        cls.stage_new = cls.env.ref(
            'generic_request.request_type_with_complex_priority_new')
        cls.stage_in_progress = cls.env.ref(
            'generic_request.'
            'request_type_with_complex_priority_in_progress')
        cls.test_event_action_complex = cls.env.ref(
            'generic_request_action.demo_complex_priority_action')
        cls.test_event_action_simple = cls.env.ref(
            'generic_request_action.demo_priority_action')
        cls.test_user = cls.env.ref('base.user_root')

    def test_complex_priority(self):
        # test complex priority
        new_request = self.env['request.request'].create({
            'type_id': self.test_request_type_complex.id,
            'request_text': 'Test complex priority',
        })
        self.assertEqual(new_request.stage_id, self.stage_new)
        self.assertEqual(new_request.priority, '3')

        new_request.stage_id = self.stage_in_progress
        self.assertEqual(new_request.stage_id, self.stage_in_progress)
        self.assertEqual(new_request.priority, '5')

        self.test_event_action_complex.act_priority_type = 'set'
        self.test_event_action_complex.act_priority_impact = '2'
        self.test_event_action_complex.act_priority_urgency = '1'

        new_request = self.env['request.request'].create({
            'type_id': self.test_request_type_complex.id,
            'request_text': 'Test complex priority',
        })
        self.assertEqual(new_request.stage_id, self.stage_new)
        self.assertEqual(new_request.priority, '3')

        new_request.stage_id = self.stage_in_progress
        self.assertEqual(new_request.stage_id, self.stage_in_progress)
        self.assertEqual(new_request.priority, '2')

        self.test_event_action_complex.act_priority_type = 'decrease'
        self.test_event_action_complex.act_priority_impact_modifier = 1
        self.test_event_action_complex.act_priority_urgency_modifier = 1

        new_request = self.env['request.request'].create({
            'type_id': self.test_request_type_complex.id,
            'request_text': 'Test complex priority',
        })
        self.assertEqual(new_request.stage_id, self.stage_new)
        self.assertEqual(new_request.priority, '3')

        new_request.stage_id = self.stage_in_progress
        self.assertEqual(new_request.stage_id, self.stage_in_progress)
        self.assertEqual(new_request.priority, '1')

        # test simple priority
        new_request = self.env['request.request'].create({
            'type_id': self.test_request_type.id,
            'request_text': 'Test priority',
        })
        self.assertEqual(new_request.priority, '3')

        new_request.user_id = self.test_user
        self.assertEqual(new_request.user_id, self.test_user)
        self.assertEqual(new_request.priority, '2')

        self.test_event_action_simple.act_priority_type = 'set'
        self.test_event_action_simple.act_priority_priority = '4'

        new_request = self.env['request.request'].create({
            'type_id': self.test_request_type.id,
            'request_text': 'Test priority',
        })

        new_request.user_id = self.test_user
        self.assertEqual(new_request.user_id, self.test_user)
        self.assertEqual(new_request.priority, '4')

        self.test_event_action_simple.act_priority_type = 'increase'
        self.test_event_action_simple.act_priority_priority_modifier = 2

        new_request = self.env['request.request'].create({
            'type_id': self.test_request_type.id,
            'request_text': 'Test priority',
        })
        new_request.user_id = self.test_user
        self.assertEqual(new_request.user_id, self.test_user)
        self.assertEqual(new_request.priority, '5')
