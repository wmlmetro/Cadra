import logging

from odoo.tests.common import TransactionCase
from odoo import exceptions
from odoo.addons.generic_mixin.tests.common import (
    ReduceLoggingMixin,
    AccessRulesFixMixinMT,
)

_logger = logging.getLogger(__name__)


class TestRouteActionsAuto(ReduceLoggingMixin,
                           AccessRulesFixMixinMT,
                           TransactionCase):

    def setUp(self):
        super(TestRouteActionsAuto, self).setUp()
        self.request_category = self.env.ref(
            'generic_request.request_category_demo_general')

        # Request type auto
        self.request_type_auto = self.env.ref(
            'generic_request_route_auto.request_type_auto')
        self.auto_stage_draft = self.env.ref(
            'generic_request_route_auto.request_stage_type_auto_draft')
        self.auto_stage_sent = self.env.ref(
            'generic_request_route_auto.request_stage_type_auto_sent')
        self.auto_stage_confirmed = self.env.ref(
            'generic_request_route_auto.request_stage_type_auto_confirmed')
        self.auto_stage_rejected = self.env.ref(
            'generic_request_route_auto.request_stage_type_auto_rejected')
        self.auto_route_send = self.env.ref(
            'generic_request_route_auto.'
            'request_stage_route_type_auto_draft_to_sent')
        self.auto_route_confirm = self.env.ref(
            'generic_request_route_auto.'
            'request_stage_route_type_auto_sent_confirmed')
        self.auto_route_reject = self.env.ref(
            'generic_request_route_auto.'
            'request_stage_route_type_auto_sent_rejected')

        # Request data
        self.request_data_auto = {
            'type_id': self.request_type_auto.id,
            'category_id': self.request_category.id,
            'request_text': 'Test request',
        }

    def test_10_auto_route_trigger_no_falsy_trigger(self):
        # auto send route not triggered
        request = self.env['request.request'].create(self.request_data_auto)
        self.assertEqual(request.stage_id, self.auto_stage_draft)

    def test_20_auto_route_trigger_auto_confirm(self):
        # auto send route triggered
        request = self.env['request.request'].create(
            dict(self.request_data_auto,
                 request_text='<p>send on create</p>'))
        self.assertEqual(request.stage_id, self.auto_stage_sent)
        self.assertEqual(request.trigger_event_count, 1)
        self.assertTrue(request.trigger_event_ids.success)

        # auto route on write (if text is confirm me)
        request.request_text = '<p>confirm me</p>'
        self.assertEqual(request.stage_id, self.auto_stage_confirmed)
        self.assertEqual(request.trigger_event_count, 2)
        self.assertFalse(
            request.trigger_event_ids.filtered(
                lambda e: e.route_id == self.auto_route_reject).success)
        self.assertTrue(
            request.trigger_event_ids.filtered(
                lambda e: e.route_id == self.auto_route_confirm).success)

        # Test request action to show trigger events
        action = request.action_show_trigger_events()
        self.assertTrue(action['context']['search_default_filter_errors'])
        events = self.env[action['res_model']].search(action['domain'])
        self.assertEqual(len(events), 2)
        self.assertFalse(
            events.filtered(
                lambda e: e.route_id == self.auto_route_reject).success)
        self.assertTrue(
            events.filtered(
                lambda e: e.route_id == self.auto_route_confirm).success)

    def test_20_auto_route_trigger_auto_confirm_event_conditions(self):
        self.env.ref(
            'generic_request_route_auto.'
            'request_stage_route_trigger_auto_sent_confirmed'
        ).write({
            'trigger': 'event',
            'event_type_ids': [
                (4, self.env.ref(
                    'generic_request.request_event_type_changed').id),
            ],
            'event_condition_ids': [
                (4, self.env.ref(
                    'generic_request_route_auto.'
                    'condition_event_request_text_is_confirm_me').id),
            ],
            'condition_ids': [(5, 0)],
            'trigger_on_write_field_ids': [(5, 0)],
        })
        # auto send route triggered
        request = self.env['request.request'].create(
            dict(self.request_data_auto,
                 request_text='<p>send on create</p>'))
        self.assertEqual(request.stage_id, self.auto_stage_sent)
        self.assertEqual(request.trigger_event_count, 1)
        self.assertTrue(request.trigger_event_ids.success)

        # auto route on write (if text is confirm me)
        request.request_text = '<p>confirm me</p>'
        self.assertEqual(request.stage_id, self.auto_stage_confirmed)
        self.assertEqual(request.trigger_event_count, 2)
        self.assertFalse(
            request.trigger_event_ids.filtered(
                lambda e: e.route_id == self.auto_route_reject).success)
        self.assertTrue(
            request.trigger_event_ids.filtered(
                lambda e: e.route_id == self.auto_route_confirm).success)
        self.assertEqual(
            request.trigger_event_ids.filtered(
                lambda e: e.route_id == self.auto_route_confirm
            ).request_event_id.event_type_id,
            self.env.ref(
                'generic_request.request_event_type_changed'))

    def test_20_auto_route_trigger_auto_confirm_no_field_restrict(self):
        # Remove fields restriction from trigger sent->confirm
        self.env.ref(
            'generic_request_route_auto.'
            'request_stage_route_trigger_auto_sent_confirmed'
        ).write({
            'trigger_on_write_field_ids': [(5, 0)],
        })
        # auto send route triggered
        request = self.env['request.request'].create(
            dict(self.request_data_auto,
                 request_text='<p>send on create</p>'))
        self.assertEqual(request.stage_id, self.auto_stage_sent)
        self.assertTrue(
            request.trigger_event_ids.filtered(
                lambda e: e.route_id == self.auto_route_send).success)
        self.assertEqual(
            set(request.trigger_event_ids.filtered(
                lambda e: e.route_id == self.auto_route_confirm).mapped(
                    'success')), {False})

        # auto route on write (if text is confirm me)
        request.request_text = '<p>confirm me</p>'
        self.assertEqual(request.stage_id, self.auto_stage_confirmed)
        self.assertIn(
            True,
            request.trigger_event_ids.filtered(
                lambda e: e.route_id == self.auto_route_confirm).mapped(
                    'success'))
        self.assertIn(
            False,
            request.trigger_event_ids.filtered(
                lambda e: e.route_id == self.auto_route_confirm).mapped(
                    'success'))

    def test_30_auto_route_trigger_auto_reject(self):
        # auto send route triggered
        request = self.env['request.request'].create(
            dict(self.request_data_auto,
                 request_text='<p>send on create</p>'))
        self.assertEqual(request.stage_id, self.auto_stage_sent)
        self.assertEqual(request.trigger_event_count, 1)
        self.assertTrue(request.trigger_event_ids.success)

        # write to user_id field (triggers are listening request_text only)
        # No stage change have to be added, no trigger events generated
        request.user_id = self.env.user
        self.assertEqual(request.stage_id, self.auto_stage_sent)
        self.assertEqual(request.trigger_event_count, 1)
        self.assertTrue(request.trigger_event_ids.success)

        # auto route on write (if text is reject me)
        request.request_text = '<p>reject me</p>'
        self.assertEqual(request.stage_id, self.auto_stage_rejected)
        self.assertEqual(request.trigger_event_count, 3)
        self.assertTrue(
            request.trigger_event_ids.filtered(
                lambda e: e.route_id == self.auto_route_reject).success)
        self.assertFalse(
            request.trigger_event_ids.filtered(
                lambda e: e.route_id == self.auto_route_confirm).success)

    def test_40_auto_route_trigger__auto_only__fail_manual(self):
        route = self.env.ref(
            'generic_request_route_auto.'
            'request_stage_route_type_auto_sent_rejected')
        route.auto_only = True

        # auto send route triggered
        request = self.env['request.request'].create(
            dict(self.request_data_auto,
                 request_text='<p>send on create</p>'))
        self.assertEqual(request.stage_id, self.auto_stage_sent)

        with self.assertRaises(exceptions.AccessError):
            request.stage_id = self.auto_stage_rejected

    def test_50_auto_route_trigger__auto_only__ok_by_trigger(self):
        route = self.env.ref(
            'generic_request_route_auto.'
            'request_stage_route_type_auto_sent_rejected')
        route.auto_only = True

        # auto send route triggered
        request = self.env['request.request'].create(
            dict(self.request_data_auto,
                 request_text='<p>send on create</p>'))
        self.assertEqual(request.stage_id, self.auto_stage_sent)

        # auto route on write (if text is confirm me)
        request.request_text = '<p>reject me</p>'
        self.assertEqual(request.stage_id, self.auto_stage_rejected)
