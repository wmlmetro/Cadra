from datetime import datetime as dt
from odoo import fields
from odoo.addons.generic_request.tests.common import freeze_time
from odoo.tests.common import Form
from .common import RequestSLACase


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

    def test_sla_control_name(self):
        Request = self.env['request.request']

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category_general.id,
                'request_text': 'Hello!',
            })
            sla_control_draft = self._get_sla_control(request, self.sla_draft)
            self.assertEqual(sla_control_draft.display_name,
                             u'8H in Draft [%s]' % request.name)

    def test_sla_main_rule(self):
        self.assertEqual(self.sla_type.sla_main_rule_id,
                         self.sla_sent_assigned)

    def test_sla_main_rule_deactivated(self):
        # If main rule is deactivated, then it have to be recomputed.
        self.assertEqual(self.sla_type.sla_main_rule_id,
                         self.sla_sent_assigned)
        self.sla_type.sla_main_rule_id.active = False
        self.assertEqual(self.sla_type.sla_main_rule_id,
                         self.sla_sent_unassigned)

    def test_sla_rule_scheduler(self):
        self.assertEqual(self.sla_type.sla_compute_type, 'main_sla_rule')
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
                '2017-05-03 13:03:00')
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_unassigned.limit_date),
                '2017-05-03 14:03:00')

        # Assign request
        with freeze_time('2017-05-03 12:33:00'):
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
                '2017-05-03 15:33:00')
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_assigned.limit_date),
                '2017-05-03 16:33:00')

            self.assertEqual(request.sla_state, 'ok')

            # Test total time is zero, because rule just activated
            self.assertEqual(sla_control_sent_assigned.total_time, 0.0)

        # Change assignee to test that total time will be updated
        with freeze_time('2017-05-03 13:03:00'):
            request.with_user(
                self.request_manager).user_id = self.request_manager

            # Test total time is 30 minutest (0.5 hour)
            self.assertEqual(sla_control_sent_assigned.total_time, 0.5)

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
        with freeze_time('2017-05-03 13:33:00'):
            self.assertEqual(sla_control_sent_unassigned.total_time, 0)

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
                '2017-05-03 14:33:00')
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_unassigned.limit_date),
                '2017-05-03 15:33:00')

        # Trigger assign event
        with freeze_time('2017-05-03 14:53:00'):
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
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_assigned.warn_date),
                '2017-05-03 17:53:00')
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_assigned.limit_date),
                '2017-05-03 18:53:00')

        # Confirm request
        with freeze_time('2017-05-03 19:17:00'):
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

    def test_sla_rule_sla_warning_no_scheduler_v2(self):
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

            # Test active sla controls
            self.assertTrue(sla_control_draft.sla_active)

            # Test SLA Dates
            self.assertEqual(sla_control_draft.warn_date,
                             dt(2017, 5, 3, 13, 3))
            self.assertEqual(sla_control_draft.limit_date,
                             dt(2017, 5, 3, 15, 3))

        # Trigger assign event
        with freeze_time('2017-05-03 14:33:00'):
            request.with_user(
                self.request_manager).user_id = self.request_manager_2

            self.assertEqual(request.sla_log_count, 1)

            # Test active sla controls
            self.assertTrue(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'warning')

    def test_sla_rule_sla_responsible_user(self):
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

            # Test sla responsible user
            self.assertFalse(sla_control_draft.user_id)
            self.assertFalse(sla_control_sent_unassigned.user_id)
            self.assertFalse(sla_control_sent_assigned.user_id)
            self.assertFalse(request.sla_user_id)

        # Send request
        with freeze_time('2017-05-03 12:03:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent

            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok']))
            self.assertEqual(request.sla_state, 'ok')

            # Test sla responsible user
            self.assertFalse(sla_control_draft.user_id)
            self.assertFalse(sla_control_sent_unassigned.user_id)
            self.assertFalse(sla_control_sent_assigned.user_id)
            self.assertFalse(request.sla_user_id)

        # Assign request
        with freeze_time('2017-05-03 12:33:00'):
            request.with_user(
                self.request_manager).user_id = self.request_manager_2

            # Test sla responsible user
            self.assertFalse(sla_control_draft.user_id)
            self.assertFalse(sla_control_sent_unassigned.user_id)
            self.assertEqual(sla_control_sent_assigned.user_id,
                             self.request_manager_2)
            self.assertEqual(request.sla_user_id, self.request_manager_2)

        # Confirm request
        with freeze_time('2017-05-03 15:03:00'):
            request.with_user(
                self.request_manager_2).stage_id = self.stage_confirmed

            # Test sla responsible user
            self.assertFalse(sla_control_draft.user_id)
            self.assertFalse(sla_control_sent_unassigned.user_id)
            self.assertEqual(sla_control_sent_assigned.user_id,
                             self.request_manager_2)
            self.assertEqual(request.sla_user_id, self.request_manager_2)

    def test_sla_rule_sla_special_lines_ok(self):
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
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.warn_date),
                '2017-05-03 10:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 11:03:00')

        # Send request
        with freeze_time('2017-05-03 09:53:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent

            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok']))
            self.assertEqual(request.sla_state, 'ok')

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')

    def test_sla_rule_sla_special_lines_fail(self):
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
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.warn_date),
                '2017-05-03 10:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 11:03:00')

        # Send request
        with freeze_time('2017-05-03 11:53:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent
            self.assertEqual(request.sla_state, 'ok')

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'failed')

    def test_sla_rule_sla_ok_no_category(self):
        Request = self.env['request.request']

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
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
                '2017-05-03 13:03:00')
            self.assertEqual(
                fields.Datetime.to_string(
                    sla_control_sent_unassigned.limit_date),
                '2017-05-03 14:03:00')

    def test_related_act_windows(self):
        act_data = self.sla_type.action_show_request_sla_rules()
        actions = self.env[act_data['res_model']].search(act_data['domain'])
        self.assertEqual(actions._name, 'request.sla.rule')
        self.assertGreater(len(actions), 1)

    def test_onchange_category(self):
        Request = self.env['request.request']

        # unlink existing rule lines to avoid errors
        self.sla_draft.rule_line_ids.unlink()

        # create rule line for SLA without category
        rule_line = self.env['request.sla.rule.line'].create({
            'sla_rule_id': self.sla_draft.id,
            'compute_time': 'absolute',
            'warn_time': 1,
            'limit_time': 2,
        })

        # check that rule line doesn't have category
        self.assertFalse(rule_line.mapped('category_ids'))

        # create category that not belongs to rule request type
        test_category = self.env['request.category'].create({
            'name': 'test_category',
            'code': 'test-category'
        })
        self.assertNotIn(test_category, rule_line.request_type_id.category_ids)

        # add category to rule line
        # triggering '_onchange_filter_categories' function on UI level
        with Form(rule_line) as rl:
            rl.category_ids.add(self.env.ref(
                'generic_request.request_category_demo_support'))

            # try to add category that not belongs to rule request_type
            rl.category_ids.add(test_category)

        # check that test category was not added to rule line
        self.assertNotIn(test_category, rule_line.category_ids)

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category_support.id,
                'request_text': 'Test SLA onchange category',
            })

        # check that rule line has same category as request
        self.assertIn(request.category_id, rule_line.category_ids)

        # get SLA control
        sla_control_draft = self._get_sla_control(request, self.sla_draft)

        # Test active sla controls
        self.assertTrue(sla_control_draft.sla_active)
        self.assertEqual(sla_control_draft.sla_state, 'ok')

        # Test to assure that sla time set from rule line
        self.assertEqual(sla_control_draft.warn_date,
                         dt(2017, 5, 3, 8, 3))
        self.assertEqual(sla_control_draft.limit_date,
                         dt(2017, 5, 3, 9, 3))
