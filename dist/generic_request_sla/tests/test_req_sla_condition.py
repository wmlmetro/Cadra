import logging

from odoo import fields
from odoo.addons.generic_request.tests.common import freeze_time
from .common import RequestSLACase

_logger = logging.getLogger(__name__)


class TestRequestSLAStateCondition(RequestSLACase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestSLAStateCondition, cls).setUpClass()

        cls.request_sla_type_connditions = cls.env.ref(
            'generic_request_sla.request_type_sla_conditions')
        cls.tag_on_site_fix = cls.env.ref(
            'generic_request_sla.tag_on_site_fix')

        cls.stage_condition_new = cls.env.ref(
            'generic_request_sla.request_stage_type_sla_condition_new')
        cls.stage_condition_analysis = cls.env.ref(
            'generic_request_sla.request_stage_type_sla_condition_analysis')

    def test_sla_type_check_sla_rule_condition(self):
        rtype = self.request_sla_type_connditions

        self.assertEqual(rtype.sla_compute_type, 'conditional')
        self.assertFalse(rtype.sla_main_rule_id)

        self.assertEqual(len(rtype.sla_rule_condition_ids), 2)
        self.assertIn(
            self.env.ref(
                'generic_request_sla'
                '.sla_rule_condition_remoute_fix'),
            rtype.sla_rule_condition_ids
        )
        self.assertIn(
            self.env.ref(
                'generic_request_sla'
                '.sla_rule_condition_on_site_fix'),
            rtype.sla_rule_condition_ids
        )

    def test_sla_control_state_sla_rule_condition(self):
        # pylint: disable=too-many-statements
        Request = self.env['request.request']
        self.assertEqual(
            self.request_sla_type_connditions.sla_compute_type,
            'conditional')

        with freeze_time('2021-06-10 08:05:56'):
            request = Request.with_user(self.request_manager).create({
                'type_id': self.request_sla_type_connditions.id,
                'request_text': 'Checking the SLA status of the request',
            })

            self.assertEqual(request.stage_id, self.stage_condition_new)

            request.write({
                'stage_id': self.stage_condition_analysis.id})

            self.assertEqual(request.stage_id, self.stage_condition_analysis)

            # ensure that needed request created
            self.assertEqual(request.stage_id.name, 'Analysis')
            self.assertEqual(len(request.sla_control_ids), 2)
            self.assertFalse(request.tag_ids)

            # ensure that created request has state 'ok'
            self.assertEqual(request.sla_state, 'ok')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-10 10:05:56')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-10 12:05:56')

            # Test SLA Control lines
            # (on-site-fix-time)
            self.assertSLAControl(
                request, 'on-site-fix-time', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'on-site-fix-time', 'sla_active', True)
            self.assertSLAControl(
                request, 'on-site-fix-time', 'warn_date',
                '2021-06-10 13:05:56')
            self.assertSLAControl(
                request, 'on-site-fix-time', 'limit_date',
                '2021-06-10 16:05:56')

            # Test SLA Control lines (standart-fix-time)
            self.assertSLAControl(
                request, 'standart-fix-time', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'standart-fix-time', 'sla_active', True)
            self.assertSLAControl(
                request, 'standart-fix-time', 'warn_date',
                '2021-06-10 10:05:56')
            self.assertSLAControl(
                request, 'standart-fix-time', 'limit_date',
                '2021-06-10 12:05:56')

        request.add_tag(code='on-site-fix')
        self.assertEqual(len(request.tag_ids), 1)
        self.assertTrue(request.check_tag(code='on-site-fix'))

        with freeze_time('2021-06-10 08:30:56'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'ok')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-10 13:05:56')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-10 16:05:56')

            # Test SLA Control lines
            # (on-site-fix-time)
            self.assertSLAControl(
                request, 'on-site-fix-time', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'on-site-fix-time', 'sla_active', True)
            self.assertSLAControl(
                request, 'on-site-fix-time', 'warn_date',
                '2021-06-10 13:05:56')
            self.assertSLAControl(
                request, 'on-site-fix-time', 'limit_date',
                '2021-06-10 16:05:56')

            # Test SLA Control lines (standart-fix-time)
            self.assertSLAControl(
                request, 'standart-fix-time', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'standart-fix-time', 'sla_active', True)
            self.assertSLAControl(
                request, 'standart-fix-time', 'warn_date',
                '2021-06-10 10:05:56')
            self.assertSLAControl(
                request, 'standart-fix-time', 'limit_date',
                '2021-06-10 12:05:56')

        with freeze_time('2021-06-10 14:00:56'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'warning')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-10 13:05:56')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-10 16:05:56')

            # Test SLA Control lines
            # (on-site-fix-time)
            self.assertSLAControl(
                request, 'on-site-fix-time', 'sla_state', 'warning')
            self.assertSLAControl(
                request, 'on-site-fix-time', 'sla_active', True)
            self.assertSLAControl(
                request, 'on-site-fix-time', 'warn_date',
                '2021-06-10 13:05:56')
            self.assertSLAControl(
                request, 'on-site-fix-time', 'limit_date',
                '2021-06-10 16:05:56')

            # Test SLA Control lines (standart-fix-time)
            self.assertSLAControl(
                request, 'standart-fix-time', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'standart-fix-time', 'sla_active', True)
            self.assertSLAControl(
                request, 'standart-fix-time', 'warn_date',
                '2021-06-10 10:05:56')
            self.assertSLAControl(
                request, 'standart-fix-time', 'limit_date',
                '2021-06-10 12:05:56')

        request.remove_tag(code='on-site-fix')
        self.assertFalse(len(request.tag_ids))

        with freeze_time('2021-06-10 14:00:56'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'failed')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-10 10:05:56')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-10 12:05:56')

            # Test SLA Control lines
            # (on-site-fix-time)
            self.assertSLAControl(
                request, 'on-site-fix-time', 'sla_state', 'warning')
            self.assertSLAControl(
                request, 'on-site-fix-time', 'sla_active', True)
            self.assertSLAControl(
                request, 'on-site-fix-time', 'warn_date',
                '2021-06-10 13:05:56')
            self.assertSLAControl(
                request, 'on-site-fix-time', 'limit_date',
                '2021-06-10 16:05:56')

            # Test SLA Control lines (standart-fix-time)
            self.assertSLAControl(
                request, 'standart-fix-time', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'standart-fix-time', 'sla_active', True)
            self.assertSLAControl(
                request, 'standart-fix-time', 'warn_date',
                '2021-06-10 10:05:56')
            self.assertSLAControl(
                request, 'standart-fix-time', 'limit_date',
                '2021-06-10 12:05:56')

        request.add_tag(code='on-site-fix')
        self.assertEqual(len(request.tag_ids), 1)
        self.assertTrue(request.check_tag(code='on-site-fix'))

        with freeze_time('2021-06-10 14:00:56'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'warning')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-10 13:05:56')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-10 16:05:56')

            # Test SLA Control lines
            # (on-site-fix-time)
            self.assertSLAControl(
                request, 'on-site-fix-time', 'sla_state', 'warning')
            self.assertSLAControl(
                request, 'on-site-fix-time', 'sla_active', True)
            self.assertSLAControl(
                request, 'on-site-fix-time', 'warn_date',
                '2021-06-10 13:05:56')
            self.assertSLAControl(
                request, 'on-site-fix-time', 'limit_date',
                '2021-06-10 16:05:56')

            # Test SLA Control lines (standart-fix-time)
            self.assertSLAControl(
                request, 'standart-fix-time', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'standart-fix-time', 'sla_active', True)
            self.assertSLAControl(
                request, 'standart-fix-time', 'warn_date',
                '2021-06-10 10:05:56')
            self.assertSLAControl(
                request, 'standart-fix-time', 'limit_date',
                '2021-06-10 12:05:56')

        with freeze_time('2021-06-10 16:41:56'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'failed')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_warn_date),
                '2021-06-10 13:05:56')
            self.assertEqual(
                fields.Datetime.to_string(request.sla_limit_date),
                '2021-06-10 16:05:56')

            # Test SLA Control lines
            # (on-site-fix-time)
            self.assertSLAControl(
                request, 'on-site-fix-time', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'on-site-fix-time', 'sla_active', True)
            self.assertSLAControl(
                request, 'on-site-fix-time', 'warn_date',
                '2021-06-10 13:05:56')
            self.assertSLAControl(
                request, 'on-site-fix-time', 'limit_date',
                '2021-06-10 16:05:56')

            # Test SLA Control lines (standart-fix-time)
            self.assertSLAControl(
                request, 'standart-fix-time', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'standart-fix-time', 'sla_active', True)
            self.assertSLAControl(
                request, 'standart-fix-time', 'warn_date',
                '2021-06-10 10:05:56')
            self.assertSLAControl(
                request, 'standart-fix-time', 'limit_date',
                '2021-06-10 12:05:56')
