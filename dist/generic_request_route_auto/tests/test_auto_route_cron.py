from odoo import exceptions
from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import (
    ReduceLoggingMixin,
    AccessRulesFixMixinMT)


class TestRouteActionsCron(ReduceLoggingMixin,
                           AccessRulesFixMixinMT,
                           TransactionCase):

    def setUp(self):
        super(TestRouteActionsCron, self).setUp()
        self.request_category = self.env.ref(
            'generic_request.request_category_demo_general')

        # Request type cron
        self.request_type_cron = self.env.ref(
            'generic_request_route_auto.request_type_cron')
        self.cron_stage_draft = self.env.ref(
            'generic_request_route_auto.request_stage_type_cron_draft')
        self.cron_stage_sent = self.env.ref(
            'generic_request_route_auto.request_stage_type_cron_sent')

        # Cron jobs
        self.cron_hourly = self.env.ref(
            'generic_request_route_auto.ir_cron_request_auto_route_hourly')
        self.cron_daily = self.env.ref(
            'generic_request_route_auto.ir_cron_request_auto_route_daily')

        # Cron route
        self.cron_route = self.env.ref(
            'generic_request_route_auto.'
            'request_stage_route_type_cron_draft_to_sent')

        # Request data
        self.request_data_cron = {
            'type_id': self.request_type_cron.id,
            'category_id': self.request_category.id,
            'request_text': 'Test request',
        }

        # Cron trigger
        self.cron_trigger = self.env.ref(
            'generic_request_route_auto.'
            'request_stage_route_trigger_cron_sent_confirmed')

    def test_10_auto_route_cron_hourly(self):
        self.assertEqual(self.cron_trigger.trigger, 'cron_hourly')
        self.assertEqual(self.cron_trigger.route_id, self.cron_route)
        request = self.env['request.request'].create(self.request_data_cron)

        self.assertEqual(request.stage_id, self.cron_stage_draft)

        # Run daily cron job
        self.cron_daily.method_direct_trigger()
        self.assertEqual(request.stage_id, self.cron_stage_draft)

        # Run hourly cron job
        self.cron_hourly.method_direct_trigger()
        self.assertEqual(request.stage_id, self.cron_stage_draft)

        # Change request to satisfy trigger conditions
        request.write({'request_text': '<p>auto send</p>'})

        # Run daily cron job (ensure nothing done)
        self.cron_daily.method_direct_trigger()
        self.assertEqual(request.stage_id, self.cron_stage_draft)

        # Run hourly cron job (ensure request is sent now)
        self.cron_hourly.method_direct_trigger()
        self.assertEqual(request.stage_id, self.cron_stage_sent)

    def test_20_auto_route_cron_daily(self):
        self.cron_trigger.trigger = 'cron_daily'
        self.assertEqual(self.cron_trigger.trigger, 'cron_daily')
        request = self.env['request.request'].create(self.request_data_cron)

        self.assertEqual(request.stage_id, self.cron_stage_draft)

        # Run daily cron job
        self.cron_daily.method_direct_trigger()
        self.assertEqual(request.stage_id, self.cron_stage_draft)

        # Run hourly cron job
        self.cron_hourly.method_direct_trigger()
        self.assertEqual(request.stage_id, self.cron_stage_draft)

        # Change request to satisfy trigger conditions
        request.write({'request_text': '<p>auto send</p>'})

        # Run hourly cron job (ensure nothing done)
        self.cron_hourly.method_direct_trigger()
        self.assertEqual(request.stage_id, self.cron_stage_draft)

        # Run daily cron job (ensure request is sent now)
        self.cron_daily.method_direct_trigger()
        self.assertEqual(request.stage_id, self.cron_stage_sent)

    def test_30_auto_route_cron_hourly_retry_event(self):
        self.assertEqual(self.cron_trigger.trigger, 'cron_hourly')
        self.assertEqual(self.cron_trigger.route_id, self.cron_route)
        request = self.env['request.request'].create(self.request_data_cron)

        self.assertEqual(request.stage_id, self.cron_stage_draft)

        # Run hourly cron job
        self.cron_hourly.method_direct_trigger()
        self.assertEqual(request.stage_id, self.cron_stage_draft)
        self.assertEqual(request.trigger_event_count, 1)
        self.assertEqual(
            request.trigger_event_ids.trigger_id,
            self.env.ref(
                'generic_request_route_auto.'
                'request_stage_route_trigger_cron_sent_confirmed'))
        self.assertFalse(
            request.trigger_event_ids.success)

        trigger_event = request.trigger_event_ids

        # Retry failed trigger event
        trigger_event.action_retry_trigger()
        self.assertEqual(request.stage_id, self.cron_stage_draft)

        # Change request to satisfy trigger conditions
        request.write({'request_text': '<p>auto send</p>'})

        # Retry failed trigger event
        trigger_event.action_retry_trigger()

        # Ensure request stage was changed
        self.assertEqual(request.stage_id, self.cron_stage_sent)

        # Retry failed trigger event and see that it raises error
        with self.assertRaises(exceptions.UserError):
            trigger_event.action_retry_trigger()

    def test_40_auto_route_cron_hourly_retry_event_2(self):
        self.assertEqual(self.cron_trigger.trigger, 'cron_hourly')
        self.assertEqual(self.cron_trigger.route_id, self.cron_route)
        request = self.env['request.request'].create(self.request_data_cron)
        request.write({'request_text': '<p>auto send</p>'})

        self.assertEqual(request.stage_id, self.cron_stage_draft)

        # Run hourly cron job
        self.cron_hourly.method_direct_trigger()
        self.assertEqual(request.stage_id, self.cron_stage_sent)
        self.assertEqual(request.trigger_event_count, 1)
        self.assertEqual(
            request.trigger_event_ids.trigger_id,
            self.env.ref(
                'generic_request_route_auto.'
                'request_stage_route_trigger_cron_sent_confirmed'))
        self.assertTrue(
            request.trigger_event_ids.success)

        trigger_event = request.trigger_event_ids

        # Retry failed trigger event and see that it raises error
        with self.assertRaises(exceptions.UserError):
            trigger_event.action_retry_trigger()
