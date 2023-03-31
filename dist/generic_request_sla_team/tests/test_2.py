import logging

from odoo import fields
from odoo.addons.generic_request.tests.common import freeze_time
from odoo.addons.generic_request_sla.tests.common import RequestSLACase


_logger = logging.getLogger(__name__)


class TestReqSLATeamAbility(RequestSLACase):
    @classmethod
    def setUpClass(cls):
        super(TestReqSLATeamAbility, cls).setUpClass()
        cls.request_sla_team_type = cls.env.ref(
            'generic_request_sla_team.request_type_sla_team')
        cls.team_1 = cls.env.ref('generic_team.generic_team_team1')
        cls.team_user_1 = cls.env.ref('generic_team.team_res_users_user1')
        cls.stage_in_progress = cls.env.ref(
            'generic_request_sla_team.request_stage_type_sla_team_in_progress')

    def test_sla_team_1_failed(self):
        # pylint: disable=too-many-statements
        Request = self.env['request.request']
        self.assertEqual(
            self.request_sla_team_type.sla_compute_type,
            'least_date_worst_status')

        with freeze_time('2021-07-08 11:06:30'):
            request = Request.with_user(self.request_manager).create({
                'type_id': self.request_sla_team_type.id,
                'request_text': 'Checking the SLA status, active rules,'
                                'log lines with added team_id of the request',
            })

            # ensure that needed request created
            self.assertEqual(request.stage_id.name, 'New')
            self.assertEqual(len(request.sla_control_ids), 3)

            # ensure that created request has state 'ok'
            self.assertEqual(request.sla_state, 'ok')

            # Test SLA Control lines (team-assignment-time-2h)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_active', True)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'warn_date',
                '2021-07-08 12:06:30')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'limit_date',
                '2021-07-08 13:06:30')

            # Test SLA Control lines (user-assignment-time-3h)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_active', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'warn_date', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-6h)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'limit_date', False)

            # Test SLA logs are absent for now
            self.assertFalse(request.sla_log_ids)
            self.assertEqual(request.sla_log_count, 0)

        with freeze_time('2021-07-08 11:36:00'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'ok')

            # Test SLA Control lines (team-assignment-time-2h)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_active', True)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'warn_date',
                '2021-07-08 12:06:30')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'limit_date',
                '2021-07-08 13:06:30')

            # Test SLA Control lines (user-assignment-time-3h)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_active', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'warn_date', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-6h)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'limit_date', False)

            # Test SLA logs are absent for now
            self.assertFalse(request.sla_log_ids)
            self.assertEqual(request.sla_log_count, 0)

        with freeze_time('2021-07-08 12:10:56'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'warning')

            # Test SLA Control lines (team-assignment-time-2h)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_state', 'warning')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_active', True)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'warn_date',
                '2021-07-08 12:06:30')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'limit_date',
                '2021-07-08 13:06:30')

            # Test SLA Control lines (user-assignment-time-3h)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_active', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'warn_date', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-6h)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'limit_date', False)

            # Test SLA logs are absent for now
            self.assertFalse(request.sla_log_ids)
            self.assertEqual(request.sla_log_count, 0)

        with freeze_time('2021-07-08 13:10:00'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'failed')

            # Test SLA Control lines (team-assignment-time-2h)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_active', True)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'warn_date',
                '2021-07-08 12:06:30')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'limit_date',
                '2021-07-08 13:06:30')

            # Test SLA Control lines (user-assignment-time-3h)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_active', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'warn_date', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-6h)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'limit_date', False)

            # Test SLA logs are absent for now
            self.assertFalse(request.sla_log_ids)
            self.assertEqual(request.sla_log_count, 0)

        with freeze_time('2021-07-08 13:11:00'):
            self.cron_update_state.method_direct_trigger()
            request.with_user(self.request_manager).team_id = self.team_1

            self.assertEqual(request.is_assigned, False)
            self.assertEqual(request.type_id.sla_compute_type,
                             'least_date_worst_status')
            self.assertEqual(request.sla_state, 'failed')

            # Test SLA Control lines (team-assignment-time-2h)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_active', False)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'warn_date', False)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'limit_date', False)

            # Test SLA Control lines (user-assignment-time-3h)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_active', True)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'warn_date',
                '2021-07-08 15:11:00')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'limit_date',
                '2021-07-08 16:11:00')

            # Test SLA Control lines (demo-solution-time-6h)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'limit_date', False)

            # Test SLA logs
            self.assertEqual(request.sla_log_count, 1)

            self.assertEqual(
                fields.Datetime.to_string(
                    request.sla_log_ids.sorted()[0].date_prev),
                '2021-07-08 11:06:30')
            self.assertEqual(fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date), '2021-07-08 13:11:00')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].request_type_id.name,
                'SLA Request (team)')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].stage_id.name, 'New')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].stage_type_id.name, 'Draft')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].assignee_id.name, False)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].team_id.name, False)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].user_id.name,
                'Demo Request Manager')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].kanban_state, 'normal')
            self.assertEqual(
                round(request.sla_log_ids.sorted()[0].time_spent_total, 2),
                2.08)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].time_spent_calendar, 0.0)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].calendar_id.id, False)

        with freeze_time('2021-07-08 14:11:00'):
            self.cron_update_state.method_direct_trigger()
            request.with_user(self.request_manager).write({
                'user_id': self.team_user_1.id,
                'team_id': self.team_1.id,
                'stage_id': self.stage_in_progress.id,
            })

            self.assertEqual(request.is_assigned, True)
            self.assertEqual(request.sla_state, 'failed')

            # Test SLA Control lines (team-assignment-time-2h)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_active', False)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'warn_date', False)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'limit_date', False)

            # Test SLA Control lines (user-assignment-time-3h)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_active', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'warn_date', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-6h)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'warn_date',
                '2021-07-08 19:11:00')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'limit_date',
                '2021-07-08 20:11:00')

            self.assertEqual(request.sla_log_count, 2)
            self.assertEqual(
                fields.Datetime.to_string(
                    request.sla_log_ids.sorted()[0].date_prev),
                '2021-07-08 13:11:00')
            self.assertEqual(fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date), '2021-07-08 14:11:00')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].request_type_id.name,
                'SLA Request (team)')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].stage_id.name, 'New')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].stage_type_id.name, 'Draft')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].assignee_id.name, False)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].team_id.name,
                'Odoo functional team')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].user_id.name,
                'Demo Request Manager')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].kanban_state, 'normal')
            self.assertEqual(
                round(request.sla_log_ids.sorted()[0].time_spent_total, 2), 1)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].time_spent_calendar, 0.0)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].calendar_id.id, False)

        with freeze_time('2021-07-09 12:45:00'):
            self.cron_update_state.method_direct_trigger()
            request.with_user(self.request_manager).write({
                'user_id': self.team_user_1.id,
                'team_id': False,
            })
            self.assertEqual(request.sla_state, 'failed')

            # Test SLA Control lines (team-assignment-time-2h)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_active', False)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'warn_date', False)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'limit_date', False)

            # Test SLA Control lines (user-assignment-time-3h)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_active', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'warn_date', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-6h)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'warn_date',
                '2021-07-08 19:11:00')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'limit_date',
                '2021-07-08 20:11:00')

            self.assertEqual(request.sla_log_count, 3)
            self.assertEqual(
                fields.Datetime.to_string(
                    request.sla_log_ids.sorted()[0].date_prev),
                '2021-07-08 14:11:00')
            self.assertEqual(fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date), '2021-07-09 12:45:00')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].request_type_id.name,
                'SLA Request (team)')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].stage_id.name, 'In progress')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].stage_type_id.name, 'Progress')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].assignee_id.name,
                'Pietro Abernathy')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].team_id.name,
                'Odoo functional team')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].user_id.name,
                'Demo Request Manager')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].kanban_state, 'normal')
            self.assertEqual(
                round(request.sla_log_ids.sorted()[0].time_spent_total, 2),
                22.57)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].time_spent_calendar, 0.0)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].calendar_id.id, False)

    def test_sla_team_1_ok(self):
        # pylint: disable=too-many-statements
        Request = self.env['request.request']
        self.assertEqual(
            self.request_sla_team_type.sla_compute_type,
            'least_date_worst_status')

        with freeze_time('2021-07-09 09:59:00'):
            request = Request.with_user(self.request_manager).create({
                'type_id': self.request_sla_team_type.id,
                'request_text': 'Checking the SLA status, active rules,'
                                'log lines with added team_id of the request',
            })

            # ensure that needed request created
            self.assertEqual(request.stage_id.name, 'New')
            self.assertEqual(len(request.sla_control_ids), 3)

            # ensure that created request has state 'ok'
            self.assertEqual(request.sla_state, 'ok')

            # Test SLA Control lines (team-assignment-time-2h)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_active', True)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'warn_date',
                '2021-07-09 10:59:00')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'limit_date',
                '2021-07-09 11:59:00')

            # Test SLA Control lines (user-assignment-time-3h)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_active', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'warn_date', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-6h)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'limit_date', False)

            # Test SLA logs are absent for now
            self.assertFalse(request.sla_log_ids)
            self.assertEqual(request.sla_log_count, 0)

        with freeze_time('2021-07-09 10:36:00'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'ok')

            # Test SLA Control lines (team-assignment-time-2h)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_active', True)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'warn_date',
                '2021-07-09 10:59:00')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'limit_date',
                '2021-07-09 11:59:00')

            # Test SLA Control lines (user-assignment-time-3h)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_active', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'warn_date', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-6h)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'limit_date', False)

            # Test SLA logs are absent for now
            self.assertFalse(request.sla_log_ids)
            self.assertEqual(request.sla_log_count, 0)

            request.with_user(self.request_manager).team_id = self.team_1

            self.assertEqual(request.is_assigned, False)
            self.assertEqual(request.type_id.sla_compute_type,
                             'least_date_worst_status')
            self.assertEqual(request.sla_state, 'ok')

            # Test SLA Control lines (team-assignment-time-2h)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_active', False)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'warn_date', False)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'limit_date', False)

            # Test SLA Control lines (user-assignment-time-3h)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_active', True)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'warn_date',
                '2021-07-09 12:36:00')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'limit_date',
                '2021-07-09 13:36:00')

            # Test SLA Control lines (demo-solution-time-6h)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'limit_date', False)

            # Test SLA logs
            self.assertEqual(request.sla_log_count, 1)

            self.assertEqual(
                fields.Datetime.to_string(
                    request.sla_log_ids.sorted()[0].date_prev),
                '2021-07-09 09:59:00')
            self.assertEqual(fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date), '2021-07-09 10:36:00')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].request_type_id.name,
                'SLA Request (team)')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].stage_id.name, 'New')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].stage_type_id.name, 'Draft')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].assignee_id.name, False)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].team_id.name, False)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].user_id.name,
                'Demo Request Manager')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].kanban_state, 'normal')
            self.assertEqual(
                round(request.sla_log_ids.sorted()[0].time_spent_total, 2),
                0.62)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].time_spent_calendar, 0.0)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].calendar_id.id, False)

        with freeze_time('2021-07-09 12:40:05'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.sla_state, 'warning')

            # Test SLA Control lines (team-assignment-time-2h)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_active', False)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'warn_date', False)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'limit_date', False)

            # Test SLA Control lines (user-assignment-time-3h)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_state', 'warning')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_active', True)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'warn_date',
                '2021-07-09 12:36:00')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'limit_date',
                '2021-07-09 13:36:00')

            # Test SLA Control lines (demo-solution-time-6h)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_active', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'warn_date', False)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'limit_date', False)

            # Test SLA logs are absent for now
            self.assertEqual(request.sla_log_count, 1)

            request.with_user(self.request_manager).write({
                'user_id': self.team_user_1.id,
                'team_id': self.team_1.id,
                'stage_id': self.stage_in_progress.id,
            })

            self.assertEqual(request.is_assigned, True)

            # Test SLA Control lines (team-assignment-time-2h)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_active', False)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'warn_date', False)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'limit_date', False)

            # Test SLA Control lines (user-assignment-time-3h)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_state', 'warning')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_active', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'warn_date', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-6h)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'warn_date',
                '2021-07-09 17:40:05')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'limit_date',
                '2021-07-09 18:40:05')

            # Test SLA logs
            self.assertEqual(request.sla_log_count, 2)

            self.assertEqual(
                fields.Datetime.to_string(
                    request.sla_log_ids.sorted()[0].date_prev),
                '2021-07-09 10:36:00')
            self.assertEqual(fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date), '2021-07-09 12:40:05')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].request_type_id.name,
                'SLA Request (team)')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].stage_id.name, 'New')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].stage_type_id.name, 'Draft')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].assignee_id.name, False)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].team_id.name, self.team_1.name)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].user_id.name,
                'Demo Request Manager')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].kanban_state, 'normal')
            self.assertEqual(
                round(request.sla_log_ids.sorted()[0].time_spent_total, 2),
                2.07)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].time_spent_calendar, 0.0)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].calendar_id.id, False)

        with freeze_time('2021-07-09 18:45:00'):
            self.cron_update_state.method_direct_trigger()
            self.assertEqual(request.is_assigned, True)
            self.assertEqual(request.sla_state, 'failed')

            # Test SLA Control lines (team-assignment-time-2h)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_state', 'ok')
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'sla_active', False)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'warn_date', False)
            self.assertSLAControl(
                request, 'team-assignment-time-2h', 'limit_date', False)

            # Test SLA Control lines (user-assignment-time-3h)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_state', 'warning')
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'sla_active', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'warn_date', False)
            self.assertSLAControl(
                request, 'user-assignment-time-3h', 'limit_date', False)

            # Test SLA Control lines (demo-solution-time-6h)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_state', 'failed')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'sla_active', True)
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'warn_date',
                '2021-07-09 17:40:05')
            self.assertSLAControl(
                request, 'demo-solution-time-6h', 'limit_date',
                '2021-07-09 18:40:05')

            self.assertEqual(request.sla_log_count, 2)

            request.with_user(self.request_manager).write({
                'user_id': self.team_user_1.id,
                'team_id': False,
            })

            self.assertEqual(request.sla_log_count, 3)
            self.assertEqual(request.is_assigned, True)
            self.assertEqual(
                fields.Datetime.to_string(
                    request.sla_log_ids.sorted()[0].date_prev),
                '2021-07-09 12:40:05')
            self.assertEqual(fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date), '2021-07-09 18:45:00')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].request_type_id.name,
                'SLA Request (team)')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].stage_id.name, 'In progress')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].stage_type_id.name, 'Progress')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].assignee_id.name,
                'Pietro Abernathy')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].team_id.name,
                'Odoo functional team')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].user_id.name,
                'Demo Request Manager')
            self.assertEqual(
                request.sla_log_ids.sorted()[0].kanban_state, 'normal')
            self.assertEqual(
                round(request.sla_log_ids.sorted()[0].time_spent_total, 2),
                6.08)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].time_spent_calendar, 0.0)
            self.assertEqual(
                request.sla_log_ids.sorted()[0].calendar_id.id, False)
