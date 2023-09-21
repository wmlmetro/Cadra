import logging

from datetime import datetime

from odoo import fields
from odoo.addons.generic_request.tests.common import freeze_time
from .common import RequestSLACase

_logger = logging.getLogger(__name__)


class TestRequestSLACalendarComplex(RequestSLACase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestSLACalendarComplex, cls).setUpClass()

        # Type Complex
        cls.sla_type_complex = cls.env.ref(
            'generic_request_sla.request_type_sla_complex')

        # Stages
        cls.t_complex_stage_new = cls.env.ref(
            'generic_request_sla.request_stage_type_sla_complex_new')
        cls.t_complex_stage_progress = cls.env.ref(
            'generic_request_sla.'
            'request_stage_type_sla_complex_in_progress')
        cls.t_complex_stage_cancel = cls.env.ref(
            'generic_request_sla.'
            'request_stage_type_sla_complex_completed')
        cls.t_complex_stage_done = cls.env.ref(
            'generic_request_sla.'
            'request_stage_type_sla_complex_cancelled')

        # SLA Rules
        cls.sla_complex_reaction_time = cls.env.ref(
            'generic_request_sla.request_sla_rule_reaction_time_2h')
        cls.sla_complex_resolution_time = cls.env.ref(
            'generic_request_sla.request_sla_rule_resolution_time_8h')

        # Subscribe users for request type
        cls.sla_type_complex.message_subscribe(
            partner_ids=cls.request_user.partner_id.ids)

        # Fix timezone for calendard
        (
            cls.env.ref('generic_request_sla.example_sla_calendar_1') +
            cls.env.ref('generic_request_sla.example_sla_calendar_2') +
            cls.env.ref('generic_request_sla.example_sla_calendar_3')
        ).write({
            'tz': 'UTC',
        })

    def test_sla_rule_scheduler(self):
        # Test reaction time to be warning and then failed
        Request = self.env['request.request']

        # Create request (Sunday)
        with freeze_time('2020-07-05 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type_complex.id,
                'category_id': self.request_category_general.id,
                'request_text': 'Hello!',
            })

            # Ensure sla controls generated
            self.assertEqual(len(request.sla_control_ids), 2)

            # Get references to sla_control_ids
            sla_control_reaction = self._get_sla_control(
                request, self.sla_complex_reaction_time)
            sla_control_resolution = self._get_sla_control(
                request, self.sla_complex_resolution_time)

            # SLA Active
            self.assertTrue(sla_control_reaction.sla_active)
            self.assertFalse(sla_control_resolution.sla_active)

            # SLA State
            self.assertEqual(sla_control_reaction.sla_state, 'ok')
            self.assertEqual(sla_control_resolution.sla_state, 'ok')
            self.assertEqual(request.sla_state, 'ok')

            # SLA dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_reaction.warn_date),
                '2020-07-05 11:00:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_reaction.limit_date),
                '2020-07-05 12:00:00')

        # No state changes by scheduler after few minutes
        with freeze_time('2020-07-05 7:15:00'):
            self.cron_update_state.method_direct_trigger()

            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok']))
            self.assertEqual(request.sla_state, 'ok')

        # SLA State is warning after 1+ working hours
        with freeze_time('2020-07-05 11:15:00'):
            self.cron_update_state.method_direct_trigger()

            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok', 'warning']))
            self.assertEqual(request.sla_state, 'ok')

        # SLA State is failed after 12:00:01 hours
        with freeze_time('2020-07-05 12:00:01'):
            self.cron_update_state.method_direct_trigger()

            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok', 'failed']))
            self.assertEqual(request.sla_state, 'ok')

    def test_sla_rule_sla_no_specific_lines(self):
        # Use 40 Hours/Week calendar for resolution time
        # (09:00-18:00 Mon-Fri)
        Request = self.env['request.request']

        # Create request (Sunday)
        with freeze_time('2020-07-05 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type_complex.id,
                'category_id': self.request_category_general.id,
                'request_text': 'Hello!',
            })

            # Get references to sla_control_ids
            # Get references to sla_control_ids
            sla_control_reaction = self._get_sla_control(
                request, self.sla_complex_reaction_time)
            sla_control_resolution = self._get_sla_control(
                request, self.sla_complex_resolution_time)

            # SLA Active
            self.assertTrue(sla_control_reaction.sla_active)
            self.assertFalse(sla_control_resolution.sla_active)

            # SLA State
            self.assertEqual(sla_control_reaction.sla_state, 'ok')
            self.assertEqual(sla_control_resolution.sla_state, 'ok')
            self.assertEqual(request.sla_state, 'ok')

            # SLA dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_reaction.warn_date),
                '2020-07-05 11:00:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_reaction.limit_date),
                '2020-07-05 12:00:00')

        # Start working on request before warning date reached
        with freeze_time('2020-07-05 10:33:00'):
            request.user_id = self.request_user
            request.with_user(
                self.request_user
            ).stage_id = self.t_complex_stage_progress

            # Test active sla controls
            self.assertFalse(sla_control_reaction.sla_active)
            self.assertTrue(sla_control_resolution.sla_active)

            self.assertEqual(sla_control_reaction.sla_state, 'ok')
            self.assertEqual(sla_control_resolution.sla_state, 'ok')
            self.assertEqual(request.sla_state, 'ok')

            # Test SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_resolution.warn_date),
                '2020-07-06 17:00:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_resolution.limit_date),
                '2020-07-06 18:00:00')

        # Complete request
        with freeze_time('2020-07-06 17:43:00'):
            request.with_user(
                self.request_user
            ).stage_id = self.t_complex_stage_done

            request.with_user(
                self.request_manager).user_id = self.request_manager_2

            # Test active sla controls
            self.assertFalse(sla_control_reaction.sla_active)
            self.assertFalse(sla_control_resolution.sla_active)

            self.assertEqual(sla_control_reaction.sla_state, 'ok')
            self.assertEqual(sla_control_resolution.sla_state, 'warning')
            self.assertEqual(request.sla_state, 'warning')

    def test_sla_rule_sla_no_specific_lines_public_holidays(self):
        # Use 40 Hours/Week calendar for resolution time
        # (09:00-18:00 Mon-Fri)
        Request = self.env['request.request']

        # Add Time Off on next work day
        self.env['resource.calendar.leaves'].create({
            'name': 'Test Time Off',
            'date_from': datetime(2020, 7, 6, 0, 0),
            'date_to': datetime(2020, 7, 6, 23, 0),
        })

        # Create request (Sunday)
        with freeze_time('2020-07-05 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type_complex.id,
                'category_id': self.request_category_general.id,
                'request_text': 'Hello!',
            })

            # Get references to sla_control_ids
            # Get references to sla_control_ids
            sla_control_reaction = self._get_sla_control(
                request, self.sla_complex_reaction_time)
            sla_control_resolution = self._get_sla_control(
                request, self.sla_complex_resolution_time)

            # SLA Active
            self.assertTrue(sla_control_reaction.sla_active)
            self.assertFalse(sla_control_resolution.sla_active)

            # SLA State
            self.assertEqual(sla_control_reaction.sla_state, 'ok')
            self.assertEqual(sla_control_resolution.sla_state, 'ok')
            self.assertEqual(request.sla_state, 'ok')

            # SLA dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_reaction.warn_date),
                '2020-07-05 11:00:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_reaction.limit_date),
                '2020-07-05 12:00:00')

        # Start working on request before warning date reached
        with freeze_time('2020-07-05 10:33:00'):
            request.user_id = self.request_user
            request.with_user(
                self.request_user
            ).stage_id = self.t_complex_stage_progress

            # Test active sla controls
            self.assertFalse(sla_control_reaction.sla_active)
            self.assertTrue(sla_control_resolution.sla_active)

            self.assertEqual(sla_control_reaction.sla_state, 'ok')
            self.assertEqual(sla_control_resolution.sla_state, 'ok')
            self.assertEqual(request.sla_state, 'ok')

            # Test SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_resolution.warn_date),
                '2020-07-07 17:00:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_resolution.limit_date),
                '2020-07-07 18:00:00')

        # Complete request
        with freeze_time('2020-07-07 17:43:00'):
            request.with_user(
                self.request_user
            ).stage_id = self.t_complex_stage_done

            request.with_user(
                self.request_manager).user_id = self.request_manager_2

            # Test active sla controls
            self.assertFalse(sla_control_reaction.sla_active)
            self.assertFalse(sla_control_resolution.sla_active)

            self.assertEqual(sla_control_reaction.sla_state, 'ok')
            self.assertEqual(sla_control_resolution.sla_state, 'warning')
            self.assertEqual(request.sla_state, 'warning')

    def test_sla_rule_sla_with_specific_lines(self):
        # Test for case with 'Support' category, that will use another woring
        # time calendar for resolution time (9:00-17:00 Mon-Sat)
        Request = self.env['request.request']

        # Create request (Sunday)
        with freeze_time('2020-07-05 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type_complex.id,
                'category_id': self.request_category_support.id,
                'request_text': 'Hello!',
            })

            # Get references to sla_control_ids
            # Get references to sla_control_ids
            sla_control_reaction = self._get_sla_control(
                request, self.sla_complex_reaction_time)
            sla_control_resolution = self._get_sla_control(
                request, self.sla_complex_resolution_time)

            # SLA Active
            self.assertTrue(sla_control_reaction.sla_active)
            self.assertFalse(sla_control_resolution.sla_active)

            # SLA State
            self.assertEqual(sla_control_reaction.sla_state, 'ok')
            self.assertEqual(sla_control_resolution.sla_state, 'ok')
            self.assertEqual(request.sla_state, 'ok')

            # SLA dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_reaction.warn_date),
                '2020-07-05 11:00:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_reaction.limit_date),
                '2020-07-05 12:00:00')

        # Start working on request before warning date reached
        with freeze_time('2020-07-05 10:33:00'):
            request.user_id = self.request_user
            request.with_user(
                self.request_user
            ).stage_id = self.t_complex_stage_progress

            # Test active sla controls
            self.assertFalse(sla_control_reaction.sla_active)
            self.assertTrue(sla_control_resolution.sla_active)

            self.assertEqual(sla_control_reaction.sla_state, 'ok')
            self.assertEqual(sla_control_resolution.sla_state, 'ok')
            self.assertEqual(request.sla_state, 'ok')

            # Test SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_resolution.warn_date),
                '2020-07-06 17:00:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_resolution.limit_date),
                '2020-07-07 10:00:00')

        # Complete request
        with freeze_time('2020-07-07 09:43:00'):
            request.with_user(
                self.request_user
            ).stage_id = self.t_complex_stage_done

            request.with_user(
                self.request_manager).user_id = self.request_manager_2

            # Test active sla controls
            self.assertFalse(sla_control_reaction.sla_active)
            self.assertFalse(sla_control_resolution.sla_active)

            self.assertEqual(sla_control_reaction.sla_state, 'ok')
            self.assertEqual(sla_control_resolution.sla_state, 'warning')
            self.assertEqual(request.sla_state, 'warning')

    def test_sla_rule_sla_with_specific_lines_change_category(self):
        # Test that when category of request changed, then SLA dates recomputed
        Request = self.env['request.request']

        # Create request (Sunday)
        with freeze_time('2020-07-05 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type_complex.id,
                'category_id': self.request_category_general.id,
                'request_text': 'Hello!',
            })

            # Get references to sla_control_ids
            # Get references to sla_control_ids
            sla_control_reaction = self._get_sla_control(
                request, self.sla_complex_reaction_time)
            sla_control_resolution = self._get_sla_control(
                request, self.sla_complex_resolution_time)

            # SLA Active
            self.assertTrue(sla_control_reaction.sla_active)
            self.assertFalse(sla_control_resolution.sla_active)

            # SLA State
            self.assertEqual(sla_control_reaction.sla_state, 'ok')
            self.assertEqual(sla_control_resolution.sla_state, 'ok')
            self.assertEqual(request.sla_state, 'ok')

            # SLA dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_reaction.warn_date),
                '2020-07-05 11:00:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_reaction.limit_date),
                '2020-07-05 12:00:00')

        # Start working on request before warning date reached
        with freeze_time('2020-07-05 10:33:00'):
            request.user_id = self.request_user
            request.with_user(
                self.request_user
            ).stage_id = self.t_complex_stage_progress

            # Test active sla controls
            self.assertFalse(sla_control_reaction.sla_active)
            self.assertTrue(sla_control_resolution.sla_active)

            self.assertEqual(sla_control_reaction.sla_state, 'ok')
            self.assertEqual(sla_control_resolution.sla_state, 'ok')
            self.assertEqual(request.sla_state, 'ok')

            # Test SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_resolution.warn_date),
                '2020-07-06 17:00:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_resolution.limit_date),
                '2020-07-06 18:00:00')

            # Change  category of request
            request.category_id = self.request_category_support

            # Test SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_resolution.warn_date),
                '2020-07-06 17:00:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_resolution.limit_date),
                '2020-07-07 10:00:00')
