import logging
from datetime import datetime as dt
from odoo import fields, exceptions
from odoo.addons.generic_request.tests.common import freeze_time
from .common import RequestSLACase

_logger = logging.getLogger(__name__)


class TestRequestSLACalendar(RequestSLACase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestSLACalendar, cls).setUpClass()

        # Add SLA Calendar to type
        cls.sla_type.sla_calendar_id = cls.sla_calendar

        # Compute SLA rules as following:
        # - DRAFT-8H as absolute
        # - UNASSIGNED-2H as working time
        # - ASSIGNED-4H as working time
        cls.sla_sent_unassigned.compute_time = 'calendar'
        cls.sla_sent_assigned.compute_time = 'calendar'

    def setUp(self):
        super(TestRequestSLACalendar, self).setUp()
        # if rule lines will be added to demo in next modules for
        # sla_draft_support rule,
        # we must reject it, because it can work on any rule line without
        # category and this tests will failed
        self.sla_draft.rule_line_ids.filtered(
            lambda rl: rl != self.sla_draft_support).unlink()

    def test_sla_rule_type_set_no_calendar(self):
        with self.assertRaises(exceptions.ValidationError):
            self.sla_type.sla_calendar_id = False

    def test_sla_rule_type_no_calendar_set_compute_time_calendar(self):
        self.sla_sent_unassigned.compute_time = 'absolute'
        self.sla_sent_assigned.compute_time = 'absolute'
        self.sla_type.sla_calendar_id = False

        with self.assertRaises(exceptions.ValidationError):
            self.sla_sent_assigned.compute_time = 'calendar'

    def test_sla_rule_scheduler(self):
        Request = self.env['request.request']

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category_general.id,
                'request_text': 'Hello!',
            })

            # Ensure sla controls generated
            self.assertEqual(len(request.sla_control_ids), 3)

            # Get references to sla_control_ids
            sla_control_draft = self._get_sla_control(request, self.sla_draft)
            sla_control_sent_unassigned = self._get_sla_control(
                request, self.sla_sent_unassigned)
            sla_control_sent_assigned = self._get_sla_control(
                request, self.sla_sent_assigned)

            # SLA Active
            self.assertTrue(sla_control_draft.sla_active)
            self.assertFalse(sla_control_sent_unassigned.sla_active)
            self.assertFalse(sla_control_sent_assigned.sla_active)

            # SLA State
            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok']))
            self.assertEqual(request.sla_state, 'ok')

            # SLA dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.warn_date),
                '2017-05-03 13:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 15:03:00')

        # No state changes by scheduler after few minutes
        with freeze_time('2017-05-03 7:15:00'):
            self.cron_update_state.method_direct_trigger()

            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok']))
            self.assertEqual(request.sla_state, 'ok')

        # SLA State is warning after 6+ hours
        with freeze_time('2017-05-03 13:15:00'):
            self.cron_update_state.method_direct_trigger()

            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok', 'warning']))
            self.assertEqual(request.sla_state, 'ok')

        # SLA State is failed after 8+ hours
        with freeze_time('2017-05-03 15:17:00'):
            self.cron_update_state.method_direct_trigger()

            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok', 'failed']))
            self.assertEqual(request.sla_state, 'ok')

    def test_sla_rule_sla_ok(self):
        Request = self.env['request.request']

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category_general.id,
                'request_text': 'Hello!',
            })

            # Get references to sla_control_ids
            sla_control_draft = self._get_sla_control(request, self.sla_draft)
            sla_control_sent_unassigned = self._get_sla_control(
                request, self.sla_sent_unassigned)
            sla_control_sent_assigned = self._get_sla_control(
                request, self.sla_sent_assigned)

            # Test active sla controls
            self.assertTrue(sla_control_draft.sla_active)
            self.assertFalse(sla_control_sent_unassigned.sla_active)
            self.assertFalse(sla_control_sent_assigned.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')
            self.assertEqual(sla_control_sent_unassigned.sla_state, 'ok')
            self.assertEqual(sla_control_sent_assigned.sla_state, 'ok')

            # Test SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.warn_date),
                '2017-05-03 13:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 15:03:00')

        # Send request
        # 12:00 - 13:00 lunch time, so warning and limit dates should be moved
        with freeze_time('2017-05-03 12:03:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent

            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok']))
            self.assertEqual(request.sla_state, 'ok')

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertTrue(sla_control_sent_unassigned.sla_active)
            self.assertFalse(sla_control_sent_assigned.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')
            self.assertEqual(sla_control_sent_unassigned.sla_state, 'ok')
            self.assertEqual(sla_control_sent_assigned.sla_state, 'ok')

            # Test SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_unassigned.warn_date),
                '2017-05-03 14:00:00')
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_unassigned.limit_date),
                '2017-05-03 15:00:00')

        # Assign request
        with freeze_time('2017-05-03 13:33:00'):
            request.with_user(
                self.request_manager).user_id = self.request_manager_2

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertFalse(sla_control_sent_unassigned.sla_active)
            self.assertTrue(sla_control_sent_assigned.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')
            self.assertEqual(sla_control_sent_unassigned.sla_state, 'ok')
            self.assertEqual(sla_control_sent_assigned.sla_state, 'ok')

            # Rest SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_assigned.warn_date),
                '2017-05-03 16:33:00')
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_assigned.limit_date),
                '2017-05-03 17:33:00')

            self.assertEqual(request.sla_state, 'ok')

        # Confirm request
        with freeze_time('2017-05-03 15:03:00'):
            request.with_user(
                self.request_manager_2).stage_id = self.stage_confirmed

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertFalse(sla_control_sent_unassigned.sla_active)
            self.assertFalse(sla_control_sent_assigned.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')
            self.assertEqual(sla_control_sent_unassigned.sla_state, 'ok')
            self.assertEqual(sla_control_sent_assigned.sla_state, 'ok')

            self.assertEqual(request.sla_state, 'ok')

    def test_sla_rule_sla_warning_then_failed(self):
        # pylint: disable=too-many-statements
        Request = self.env['request.request']

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category_general.id,
                'request_text': 'Hello!',
            })

            # Get references to sla_control_ids
            sla_control_draft = self._get_sla_control(request, self.sla_draft)
            sla_control_sent_unassigned = self._get_sla_control(
                request, self.sla_sent_unassigned)
            sla_control_sent_assigned = self._get_sla_control(
                request, self.sla_sent_assigned)

            # Test active sla controls
            self.assertTrue(sla_control_draft.sla_active)
            self.assertFalse(sla_control_sent_unassigned.sla_active)
            self.assertFalse(sla_control_sent_assigned.sla_active)

            # Test SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.warn_date),
                '2017-05-03 13:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 15:03:00')

        # Trigger assign event
        with freeze_time('2017-05-03 10:33:00'):
            request.with_user(
                self.request_manager).user_id = self.request_manager_2

            self.assertEqual(request.sla_log_count, 1)

            # Test active sla controls
            self.assertTrue(sla_control_draft.sla_active)
            self.assertFalse(sla_control_sent_unassigned.sla_active)
            self.assertFalse(sla_control_sent_assigned.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')
            self.assertEqual(sla_control_sent_unassigned.sla_state, 'ok')
            self.assertEqual(sla_control_sent_assigned.sla_state, 'ok')

            # Test request sla state
            self.assertEqual(request.sla_state, 'ok')

            # Test SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.warn_date),
                '2017-05-03 13:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 15:03:00')

        # Trigger unassign event
        with freeze_time('2017-05-03 11:03:00'):
            request.with_user(self.request_manager).user_id = False

            self.assertEqual(request.sla_log_count, 2)

            # Test active sla controls
            self.assertTrue(sla_control_draft.sla_active)
            self.assertFalse(sla_control_sent_unassigned.sla_active)
            self.assertFalse(sla_control_sent_assigned.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')
            self.assertEqual(sla_control_sent_unassigned.sla_state, 'ok')
            self.assertEqual(sla_control_sent_assigned.sla_state, 'ok')

            # Test request sla state
            self.assertEqual(request.sla_state, 'ok')

            # Test SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.warn_date),
                '2017-05-03 13:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 15:03:00')

        # Send request
        with freeze_time('2017-05-03 13:53:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent

            self.assertEqual(request.sla_log_count, 3)

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertTrue(sla_control_sent_unassigned.sla_active)
            self.assertFalse(sla_control_sent_assigned.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'warning')
            self.assertEqual(sla_control_sent_unassigned.sla_state, 'ok')
            self.assertEqual(sla_control_sent_assigned.sla_state, 'ok')

            # Test request sla state
            self.assertEqual(request.sla_state, 'ok')

            # Test SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_unassigned.warn_date),
                '2017-05-03 14:53:00')
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_unassigned.limit_date),
                '2017-05-03 15:53:00')

        # Trigger assign event
        with freeze_time('2017-05-03 15:47:00'):
            request.with_user(
                self.request_manager).user_id = self.request_manager_2

            self.assertEqual(request.sla_log_count, 4)

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertFalse(sla_control_sent_unassigned.sla_active)
            self.assertTrue(sla_control_sent_assigned.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'warning')
            self.assertEqual(sla_control_sent_unassigned.sla_state, 'warning')
            self.assertEqual(sla_control_sent_assigned.sla_state, 'ok')

            # Test request sla state
            self.assertEqual(request.sla_state, 'ok')

            # Test SLA Dates
            # 16:00 - end of working day
            # 15:47 + 3h = 18:47 so 2h 47m moved in next day
            # Thus next warn time will be: 8:00 + 47m + 2h = 10:47
            # Same logic applied to limit date: 8:00 + 1h + 47m + 2h = 11:47
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_assigned.warn_date),
                '2017-05-04 08:47:00')
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_assigned.limit_date),
                '2017-05-04 09:47:00')

        # Confirm request
        with freeze_time('2017-05-04 12:17:00'):
            request.with_user(
                self.request_manager_2).stage_id = self.stage_confirmed

            self.assertEqual(request.sla_log_count, 5)

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertFalse(sla_control_sent_unassigned.sla_active)
            self.assertFalse(sla_control_sent_assigned.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'warning')
            self.assertEqual(sla_control_sent_unassigned.sla_state, 'warning')
            self.assertEqual(sla_control_sent_assigned.sla_state, 'failed')

            # Test request sla state
            self.assertEqual(request.sla_state, 'failed')

    def test_sla_rule_sla_special_lines_ok(self):
        # Test is same as without calendar, because lines has comute_time set
        # to 'absolute', thus if even rule hast compute_time set to 'calendar'
        # rule lines will use 'absolute time'
        Request = self.env['request.request']

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category_support.id,
                'request_text': 'Hello!',
            })

            # Get references to sla_control_ids
            sla_control_draft = self._get_sla_control(request, self.sla_draft)

            # Test active sla controls
            self.assertTrue(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')

            # Test SLA Dates
            self.assertEqual(sla_control_draft.warn_date,
                             dt(2017, 5, 3, 10, 3))
            self.assertEqual(sla_control_draft.limit_date,
                             dt(2017, 5, 3, 11, 3))

        # Send request
        with freeze_time('2017-05-03 09:53:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent

            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok']))
            self.assertEqual(request.sla_state, 'ok')

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')

    def test_sla_rule_sla_special_lines_fail_then_ok(self):
        # Test is same as without calendar, because lines has comute_time set
        # to 'absolute', thus if even rule hast compute_time set to 'calendar'
        # rule lines will use 'absolute time'
        Request = self.env['request.request']

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category_support.id,
                'request_text': 'Hello!',
            })

            # Get references to sla_control_ids
            sla_control_draft = self._get_sla_control(request, self.sla_draft)

            # Test active sla controls
            self.assertTrue(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')

            # Test SLA Dates
            self.assertEqual(sla_control_draft.warn_date,
                             dt(2017, 5, 3, 10, 3))
            self.assertEqual(sla_control_draft.limit_date,
                             dt(2017, 5, 3, 11, 3))

        # Send request
        with freeze_time('2017-05-03 11:53:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent
            self.assertEqual(request.sla_state, 'ok')

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'failed')

    def test_sla_rule_sla_ok_public_holidays(self):
        Request = self.env['request.request']

        # Create holiday for Thursday, 2017-05-04
        self.env['resource.calendar.leaves'].create({
            'date_from': fields.Datetime.from_string("2017-05-04 00:00:00"),
            'date_to': fields.Datetime.from_string("2017-05-04 23:59:59"),
            'calendar_id': self.sla_calendar.id,
        })

        # Create request
        # 2017-05-03 is Wednesday, next day is holiday
        with freeze_time('2017-05-03 10:05:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category_general.id,
                'request_text': 'Hello!',
            })

            # Get references to sla_control_ids
            sla_control_draft = self._get_sla_control(request, self.sla_draft)
            sla_control_sent_unassigned = self._get_sla_control(
                request, self.sla_sent_unassigned)
            sla_control_sent_assigned = self._get_sla_control(
                request, self.sla_sent_assigned)

            # Test active sla controls
            self.assertTrue(sla_control_draft.sla_active)
            self.assertFalse(sla_control_sent_unassigned.sla_active)
            self.assertFalse(sla_control_sent_assigned.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')
            self.assertEqual(sla_control_sent_unassigned.sla_state, 'ok')
            self.assertEqual(sla_control_sent_assigned.sla_state, 'ok')

            # Test SLA Dates
            # The draft-8h rule is absolute time
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.warn_date),
                '2017-05-03 16:05:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 18:05:00')

        # Send request in the end of the day.
        # Next day is holiday, thus limit dates have to be moved on Friday
        with freeze_time('2017-05-03 16:03:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent

            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok']))
            self.assertEqual(request.sla_state, 'ok')

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertTrue(sla_control_sent_unassigned.sla_active)
            self.assertFalse(sla_control_sent_assigned.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')
            self.assertEqual(sla_control_sent_unassigned.sla_state, 'ok')
            self.assertEqual(sla_control_sent_assigned.sla_state, 'ok')

            # Test SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_unassigned.warn_date),
                '2017-05-03 17:03:00')
            # Note, that date is transferred to 2017-05-05, because
            # 2017-05-04 is holiday
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_unassigned.limit_date),
                '2017-05-05 08:03:00')

        # Assign request in the end of day before holiday
        with freeze_time('2017-05-03 17:01:00'):
            request.with_user(
                self.request_manager
            ).user_id = self.request_manager_2

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertFalse(sla_control_sent_unassigned.sla_active)
            self.assertTrue(sla_control_sent_assigned.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')
            self.assertEqual(sla_control_sent_unassigned.sla_state, 'ok')
            self.assertEqual(sla_control_sent_assigned.sla_state, 'ok')

            # SLA limit and warning dates must take into account
            # public holiday defined on 2017-05-04, thus dates will be
            # moved to next working day - Friday, 2017-05-05
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_assigned.warn_date),
                '2017-05-05 10:01:00')
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_assigned.limit_date),
                '2017-05-05 11:01:00')

            self.assertEqual(request.sla_state, 'ok')

        # Confirm request
        with freeze_time('2017-05-05 09:03:00'):
            request.with_user(
                self.request_manager_2).stage_id = self.stage_confirmed

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertFalse(sla_control_sent_unassigned.sla_active)
            self.assertFalse(sla_control_sent_assigned.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')
            self.assertEqual(sla_control_sent_unassigned.sla_state, 'ok')
            self.assertEqual(sla_control_sent_assigned.sla_state, 'ok')

            self.assertEqual(request.sla_state, 'ok')
