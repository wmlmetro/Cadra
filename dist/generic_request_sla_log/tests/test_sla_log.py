from odoo.tests.common import TransactionCase
from odoo.tools.misc import mute_logger
from odoo import fields

from odoo.addons.generic_mixin.tests.common import (
    AccessRulesFixMixinST,
    ReduceLoggingMixin,
)
from odoo.addons.generic_request.tests.common import (
    freeze_time,
)


class TestRequestSLALog(AccessRulesFixMixinST,
                        ReduceLoggingMixin,
                        TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestSLALog, cls).setUpClass()
        cls.env.user.tz = 'UTC'

        cls.sla_type = cls.env.ref(
            'generic_request_sla_log.request_type_sla')

        cls.request_category = cls.env.ref(
            'generic_request.request_category_demo_general')

        # Stages
        cls.stage_draft = cls.env.ref(
            'generic_request_sla_log.request_stage_type_sla_draft')
        cls.stage_sent = cls.env.ref(
            'generic_request_sla_log.request_stage_type_sla_sent')
        cls.stage_confirmed = cls.env.ref(
            'generic_request_sla_log.request_stage_type_sla_confirmed')
        cls.stage_rejected = cls.env.ref(
            'generic_request_sla_log.request_stage_type_sla_rejected')

        # Users
        cls.demo_user = cls.env.ref('base.user_demo')
        cls.request_user = cls.env.ref(
            'generic_request.user_demo_request')
        cls.request_manager = cls.env.ref(
            'generic_request.user_demo_request_manager')
        cls.request_manager_2 = cls.env.ref(
            'generic_request.user_demo_request_manager_2')

        cls.sla_type.message_subscribe(
            partner_ids=cls.request_user.partner_id.ids)

        # Calendar
        cls.sla_calendar = cls.env.ref(
            'generic_request_sla_log.example_sla_calendar')
        cls.sla_calendar.tz = 'UTC'

    def run(self, result=None):
        # Hide unnecessary log output
        with mute_logger('odoo.models.unlink',
                         'odoo.addons.mail.models.mail_mail'):
            return super(TestRequestSLALog, self).run(result=result)

    def test_sla_log(self):
        Request = self.env['request.request']

        # Create request
        with freeze_time('2017-05-03 11:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category.id,
                'request_text': 'Hello!',
            })
        self.assertFalse(request.sla_log_ids)
        self.assertEqual(request.sla_log_count, 0)

        # Send request
        with freeze_time('2017-05-03 12:03:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent

        self.assertEqual(request.sla_log_count, 1)
        self.assertEqual(
            fields.Datetime.to_string(request.sla_log_ids.sorted()[0].date),
            '2017-05-03 12:03:00')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date_prev),
            '2017-05-03 11:03:00')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].stage_id, self.stage_draft)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].user_id, self.request_user)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_total, 1.0)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_calendar, 0.0)
        self.assertFalse(request.sla_log_ids.sorted()[0].assignee_id)

        # Assign request
        with freeze_time('2017-05-03 14:03:00'):
            request.with_user(
                self.request_manager).user_id = self.request_manager_2

        self.assertEqual(request.sla_log_count, 2)
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date),
            '2017-05-03 14:03:00')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date_prev),
            '2017-05-03 12:03:00')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].stage_id, self.stage_sent)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].user_id, self.request_manager)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_total, 2.0)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_calendar, 0.0)
        self.assertFalse(request.sla_log_ids.sorted()[0].assignee_id)

        # Confirm request
        with freeze_time('2017-05-04 11:03:00'):
            request.with_user(
                self.request_manager_2).stage_id = self.stage_confirmed

        self.assertEqual(request.sla_log_count, 3)
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date),
            '2017-05-04 11:03:00')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date_prev),
            '2017-05-03 14:03:00')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].stage_id, self.stage_sent)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].user_id, self.request_manager_2)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_total, 21.0)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_calendar, 0.0)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].assignee_id,
            self.request_manager_2)

    def test_sla_log_calendar(self):
        Request = self.env['request.request']

        # Set calendar for reauest type
        self.sla_type.sla_calendar_id = self.sla_calendar

        # Create request
        with freeze_time('2017-05-03 11:03:00'):   # wednesday
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category.id,
                'request_text': 'Hello!',
            })
        self.assertFalse(request.sla_log_ids)
        self.assertEqual(request.sla_log_count, 0)

        # Send request
        with freeze_time('2017-05-03 12:33:00'):   # 12-13 is lunch time
            request.with_user(self.request_user).stage_id = self.stage_sent

        self.assertEqual(request.sla_log_count, 1)
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date),
            '2017-05-03 12:33:00')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date_prev),
            '2017-05-03 11:03:00')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].stage_id, self.stage_draft)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].user_id, self.request_user)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_total, 1.50)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_calendar, 0.95)
        self.assertFalse(request.sla_log_ids.sorted()[0].assignee_id)

        # Assign request
        with freeze_time('2017-05-03 14:03:00'):
            request.with_user(
                self.request_manager).user_id = self.request_manager_2

        self.assertEqual(request.sla_log_count, 2)
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date),
            '2017-05-03 14:03:00')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date_prev),
            '2017-05-03 12:33:00')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].stage_id, self.stage_sent)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].user_id, self.request_manager)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_total, 1.50)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_calendar, 1.05)
        self.assertFalse(request.sla_log_ids.sorted()[0].assignee_id)

        # Confirm request
        with freeze_time('2017-05-04 11:03:00'):
            request.with_user(
                self.request_manager_2).stage_id = self.stage_confirmed

        self.assertEqual(request.sla_log_count, 3)
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date),
            '2017-05-04 11:03:00')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date_prev),
            '2017-05-03 14:03:00')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].stage_id, self.stage_sent)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].user_id, self.request_manager_2)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_total, 21.0)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_calendar, 7.00)
        self.assertEqual(
            request.sla_log_ids.sorted()[0].assignee_id,
            self.request_manager_2)

    def test_sla_log_kanban_state(self):
        Request = self.env['request.request']

        # Create request
        with freeze_time('2017-05-03 11:07:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category.id,
                'request_text': 'Hello!',
            })
        self.assertFalse(request.sla_log_ids)
        self.assertEqual(request.sla_log_count, 0)
        self.assertTrue(request.kanban_state == 'normal')

        # Pause request
        with freeze_time('2017-05-03 12:07:00'):
            request.with_user(self.request_user).kanban_state = 'blocked'

        self.assertEqual(request.sla_log_count, 1)
        self.assertTrue(request.kanban_state == 'blocked')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date),
            '2017-05-03 12:07:00')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date_prev),
            '2017-05-03 11:07:00')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].kanban_state, 'normal')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_total, 1.0)

        # In progres request
        with freeze_time('2017-05-03 13:37:00'):
            request.with_user(self.request_user).kanban_state = 'normal'

        self.assertEqual(request.sla_log_count, 2)
        self.assertTrue(request.kanban_state == 'normal')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date),
            '2017-05-03 13:37:00')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date_prev),
            '2017-05-03 12:07:00')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].kanban_state, 'blocked')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_total, 1.5)

        # Pause request
        with freeze_time('2017-05-03 14:07:00'):
            request.with_user(self.request_user).kanban_state = 'blocked'

        self.assertEqual(request.sla_log_count, 3)
        self.assertTrue(request.kanban_state == 'blocked')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date),
            '2017-05-03 14:07:00')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date_prev),
            '2017-05-03 13:37:00')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].kanban_state, 'normal')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_total, 0.5)

        # In progres request
        with freeze_time('2017-05-04 11:07:00'):
            request.with_user(self.request_user).kanban_state = 'normal'

        self.assertEqual(request.sla_log_count, 4)
        self.assertTrue(request.kanban_state == 'normal')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date),
            '2017-05-04 11:07:00')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date_prev),
            '2017-05-03 14:07:00')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].kanban_state, 'blocked')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_total, 21.0)

        # Ready to next stage request
        with freeze_time('2017-05-04 17:07:00'):
            request.with_user(self.request_user).kanban_state = 'done'

        self.assertEqual(request.sla_log_count, 5)
        self.assertTrue(request.kanban_state == 'done')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date),
            '2017-05-04 17:07:00')
        self.assertEqual(
            fields.Datetime.to_string(
                request.sla_log_ids.sorted()[0].date_prev),
            '2017-05-04 11:07:00')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].kanban_state, 'normal')
        self.assertEqual(
            request.sla_log_ids.sorted()[0].time_spent_total, 6.0)
