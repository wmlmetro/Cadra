import logging

from odoo import fields
from odoo.addons.generic_request.tests.common import freeze_time
from .common import RequestSLACase

_logger = logging.getLogger(__name__)


class TestRequestSLAState(RequestSLACase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestSLAState, cls).setUpClass()

        cls.request_sla_type_2 = cls.env.ref(
            'generic_request_sla.request_type_sla_2')

    def test_sla_type_main_rule_computation(self):
        rtype = self.request_sla_type_2

        self.assertEqual(rtype.sla_compute_type, 'least_date_worst_status')
        self.assertFalse(rtype.sla_main_rule_id)

        rtype.sla_compute_type = 'main_sla_rule'

        self.assertEqual(rtype.sla_compute_type, 'main_sla_rule')
        self.assertEqual(
            rtype.sla_main_rule_id,
            self.env.ref(
                'generic_request_sla.request_sla_rule_testing_time_72h')
        )

    def test_sla_control_state_least_date_worst_status_1(self):
        # pylint: disable=too-many-statements
        Request = self.env['request.request']
        self.assertEqual(
            self.request_sla_type_2.sla_compute_type,
            'least_date_worst_status')

        with freeze_time('2021-06-10 08:05:56'):
            request = Request.with_user(self.request_manager).create({
                'type_id': self.request_sla_type_2.id,
                'request_text': 'Checking the SLA status of the request',
            })

            # ensure that needed request created
            self.assertEqual(request.stage_id.name, 'New')
            self.assertEqual(len(request.sla_control_ids), 3)

            # ensure that created request has state 'ok'
            self.assertEqual(request.sla_state, 'ok')

            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-10 09:05:56')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-10 10:05:56')

            # Test SLA Control lines (demo-assignment-time-2h)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'warn_date',
                '2021-06-10 09:05:56')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'limit_date',
                '2021-06-10 10:05:56')

            # Test SLA Control lines (demo-solution-time-8h)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'limit_date', False)

            # Test SLA Control lines (testing-time-72h)
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_active', False)
            self.assertSLAControl(
                request, 'testing-time-72h', 'warn_date', False)
            self.assertSLAControl(
                request, 'testing-time-72h', 'limit_date', False)

        with freeze_time('2021-06-10 08:30:56'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'ok')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-10 09:05:56')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-10 10:05:56')

            # Test SLA Control lines (demo-assignment-time-2h)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'warn_date',
                '2021-06-10 09:05:56')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'limit_date',
                '2021-06-10 10:05:56')

            # Test SLA Control lines (demo-solution-time-8h)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'limit_date', False)

            # Test SLA Control lines (testing-time-72h)
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_active', False)
            self.assertSLAControl(
                request, 'testing-time-72h', 'warn_date', False)
            self.assertSLAControl(
                request, 'testing-time-72h', 'limit_date', False)

        with freeze_time('2021-06-10 10:00:56'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'warning')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-10 09:05:56')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-10 10:05:56')

            # Test SLA Control lines (demo-assignment-time-2h)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_state', 'warning')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'warn_date',
                '2021-06-10 09:05:56')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'limit_date',
                '2021-06-10 10:05:56')

            # Test SLA Control lines (demo-solution-time-8h)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'limit_date', False)

            # Test SLA Control lines (testing-time-72h)
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_active', False)
            self.assertSLAControl(
                request, 'testing-time-72h', 'warn_date', False)
            self.assertSLAControl(
                request, 'testing-time-72h', 'limit_date', False)

        with freeze_time('2021-06-10 16:41:56'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'failed')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-10 09:05:56')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-10 10:05:56')

            # Test SLA Control lines (demo-assignment-time-2h)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'warn_date',
                '2021-06-10 09:05:56')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'limit_date',
                '2021-06-10 10:05:56')

            # Test SLA Control lines (demo-solution-time-8h)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'limit_date', False)

            # Test SLA Control lines (testing-time-72h)
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_active', False)
            self.assertSLAControl(
                request, 'testing-time-72h', 'warn_date', False)
            self.assertSLAControl(
                request, 'testing-time-72h', 'limit_date', False)

        with freeze_time('2021-06-10 17:00:00'):
            self.cron_update_state.method_direct_trigger()
            request.with_user(self.request_manager).stage_id = self.env.ref(
                'generic_request_sla.request_stage_type_sla_2_in_progress').id
            request.with_user(
                self.request_manager
            ).user_id = self.request_manager_2

            self.assertEqual(request.type_id.sla_compute_type,
                             'least_date_worst_status')
            self.assertEqual(request.sla_state, 'failed')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-11 00:00:00')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-11 01:00:00')

            # Test SLA Control lines (demo-assignment-time-2h)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-8h)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'warn_date',
                '2021-06-11 00:00:00')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'limit_date',
                '2021-06-11 01:00:00')

            # Test SLA Control lines (testing-time-72h)
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_active', True)
            self.assertSLAControl(
                request, 'testing-time-72h', 'warn_date',
                '2021-06-12 17:00:00')
            self.assertSLAControl(
                request, 'testing-time-72h', 'limit_date',
                '2021-06-13 17:00:00')

        with freeze_time('2021-06-11 00:00:01'):
            self.cron_update_state.method_direct_trigger()

            self.assertEqual(request.sla_state, 'failed')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-11 00:00:00')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-11 01:00:00')

            # Test SLA Control lines (demo-assignment-time-2h)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-8h)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_state', 'warning')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'warn_date',
                '2021-06-11 00:00:00')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'limit_date',
                '2021-06-11 01:00:00')

            # Test SLA Control lines (testing-time-72h)
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_active', True)
            self.assertSLAControl(
                request, 'testing-time-72h', 'warn_date',
                '2021-06-12 17:00:00')
            self.assertSLAControl(
                request, 'testing-time-72h', 'limit_date',
                '2021-06-13 17:00:00')

        with freeze_time('2021-06-11 01:45:00'):
            self.cron_update_state.method_direct_trigger()

            self.assertEqual(request.sla_state, 'failed')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-11 00:00:00')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-11 01:00:00')

            # Test SLA Control lines (demo-assignment-time-2h)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-8h)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'warn_date',
                '2021-06-11 00:00:00')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'limit_date',
                '2021-06-11 01:00:00')

            # Test SLA Control lines (testing-time-72h)
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_active', True)
            self.assertSLAControl(
                request, 'testing-time-72h', 'warn_date',
                '2021-06-12 17:00:00')
            self.assertSLAControl(
                request, 'testing-time-72h', 'limit_date',
                '2021-06-13 17:00:00')

    def test_sla_control_state_least_date_worst_status_2(self):
        # pylint: disable=too-many-statements
        Request = self.env['request.request']
        self.assertEqual(
            self.request_sla_type_2.sla_compute_type,
            'least_date_worst_status')

        with freeze_time('2021-06-10 08:05:56'):
            request = Request.with_user(self.request_manager).create({
                'type_id': self.request_sla_type_2.id,
                'request_text': 'Checking the SLA status of the request',
            })

            # ensure that needed request created
            self.assertEqual(request.stage_id.name, 'New')
            self.assertEqual(len(request.sla_control_ids), 3)

            # ensure that created request has state 'ok'
            self.assertEqual(request.sla_state, 'ok')

            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-10 09:05:56')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-10 10:05:56')

            # Test SLA Control lines (demo-assignment-time-2h)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'warn_date',
                '2021-06-10 09:05:56')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'limit_date',
                '2021-06-10 10:05:56')

            # Test SLA Control lines (demo-solution-time-8h)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'limit_date', False)

            # Test SLA Control lines (testing-time-72h)
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_active', False)
            self.assertSLAControl(
                request, 'testing-time-72h', 'warn_date', False)
            self.assertSLAControl(
                request, 'testing-time-72h', 'limit_date', False)

        with freeze_time('2021-06-10 08:30:56'):
            request.with_user(self.request_manager).stage_id = self.env.ref(
                'generic_request_sla.request_stage_type_sla_2_in_progress').id
            request.with_user(
                self.request_manager
            ).user_id = self.request_manager_2
            self.assertEqual(request.sla_state, 'ok')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-10 15:30:56')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-10 16:30:56')

            # Test SLA Control lines (demo-assignment-time-2h)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-8h)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'warn_date',
                '2021-06-10 15:30:56')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'limit_date',
                '2021-06-10 16:30:56')

            # Test SLA Control lines (testing-time-72h)
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_active', True)
            self.assertSLAControl(
                request, 'testing-time-72h', 'warn_date',
                '2021-06-12 08:30:56')
            self.assertSLAControl(
                request, 'testing-time-72h', 'limit_date',
                '2021-06-13 08:30:56')

        with freeze_time('2021-06-10 16:01:53'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'warning')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-10 15:30:56')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-10 16:30:56')

            # Test SLA Control lines (demo-assignment-time-2h)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-8h)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_state', 'warning')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'warn_date',
                '2021-06-10 15:30:56')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'limit_date',
                '2021-06-10 16:30:56')

            # Test SLA Control lines (testing-time-72h)
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_active', True)
            self.assertSLAControl(
                request, 'testing-time-72h', 'warn_date',
                '2021-06-12 08:30:56')
            self.assertSLAControl(
                request, 'testing-time-72h', 'limit_date',
                '2021-06-13 08:30:56')

        with freeze_time('2021-06-10 18:01:53'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'failed')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-10 15:30:56')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-10 16:30:56')

            # Test SLA Control lines (demo-assignment-time-2h)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-assignment-time-2h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-8h)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'warn_date',
                '2021-06-10 15:30:56')
            self.assertSLAControl(
                request, 'demo-solution-time-8h', 'limit_date',
                '2021-06-10 16:30:56')

            # Test SLA Control lines (testing-time-72h)
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'testing-time-72h', 'sla_active', True)
            self.assertSLAControl(
                request, 'testing-time-72h', 'warn_date',
                '2021-06-12 08:30:56')
            self.assertSLAControl(
                request, 'testing-time-72h', 'limit_date',
                '2021-06-13 08:30:56')
