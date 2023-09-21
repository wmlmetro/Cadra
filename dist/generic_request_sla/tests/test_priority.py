from datetime import datetime as dt
import logging

from odoo.addons.generic_request_sla.tests.common import RequestSLACase
from odoo.addons.generic_request.tests.common import freeze_time

_logger = logging.getLogger(__name__)


class TestRequestSLAPriority(RequestSLACase):

    def setUp(self):
        super(TestRequestSLAPriority, self).setUp()
        self.priority_3 = self.env.ref(
            'generic_request_sla.request_sla_rule_8h_in_draft_priority_3')
        self.priority_4 = self.env.ref(
            'generic_request_sla.request_sla_rule_8h_in_draft_priority_4')
        self.sla_draft.rule_line_ids.filtered(
            lambda rl: rl not in [
                self.priority_3, self.priority_4,
                self.sla_draft_support, self.sla_draft_technical]
        ).unlink()

    def test_priority(self):
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

            self.assertEqual(request.priority, self.priority_3.priority)
            # Test SLA Dates
            self.assertEqual(sla_control_draft.warn_date,
                             dt(2017, 5, 3, 9, 3))
            self.assertEqual(sla_control_draft.limit_date,
                             dt(2017, 5, 3, 10, 3))

            request.priority = '4'
            self.assertEqual(request.priority, self.priority_4.priority)
            # Test SLA Dates
            self.assertEqual(sla_control_draft.warn_date,
                             dt(2017, 5, 3, 8, 3))
            self.assertEqual(sla_control_draft.limit_date,
                             dt(2017, 5, 3, 8, 3))

    def test_priority_calendar(self):
        self.sla_type.sla_calendar_id = self.sla_calendar
        self.sla_draft_support.compute_time = 'calendar'
        self.priority_3.compute_time = 'calendar'

        Request = self.env['request.request']

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category_technical.id,
                'request_text': 'Hello!',
                'priority': '1',
            })

            # Get references to sla_control_ids
            sla_control_draft = self._get_sla_control(request, self.sla_draft)

            # Test active sla controls
            self.assertTrue(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')

            # Test SLA Dates
            # SLA Technical rule line have to be used here. It is absolute time
            # warn: 5, limit: 6
            self.assertEqual(
                sla_control_draft.warn_date,
                dt(2017, 5, 3, 12, 3))
            self.assertEqual(
                sla_control_draft.limit_date,
                dt(2017, 5, 3, 13, 3))
            self.assertEqual(sla_control_draft.compute_time, 'absolute')

            # Change priority to 3
            request.priority = '3'

            self.assertEqual(request.priority, self.priority_3.priority)
            # Test SLA Dates
            # Rule line with priority 3 have to be used here.
            # It have to use calendar time
            # Warn: 2 Limit 3
            self.assertEqual(
                sla_control_draft.warn_date,
                dt(2017, 5, 3, 10))
            self.assertEqual(
                sla_control_draft.limit_date,
                dt(2017, 5, 3, 11))
            self.assertEqual(sla_control_draft.compute_time, 'calendar')

            # increase request's priority to 4
            request.priority = '4'
            self.assertEqual(request.priority, self.priority_4.priority)

            # Test SLA Dates
            # Rule line with priority 3 have to be used
            # It have to use absolute time
            # Warn: 1
            # Limit: 1
            self.assertEqual(
                sla_control_draft.warn_date,
                dt(2017, 5, 3, 8, 3))
            self.assertEqual(
                sla_control_draft.limit_date,
                dt(2017, 5, 3, 8, 3))
            self.assertEqual(sla_control_draft.compute_time, 'absolute')

    def test_zero_priority(self):
        Request = self.env['request.request']
        self.sla_draft.rule_line_ids.unlink()
        self.env['request.sla.rule.line'].create({
            'sla_rule_id': self.sla_draft.id,
            'compute_time': 'absolute',
            'warn_time': 1,
            'limit_time': 2,
            'priority': '0'
        })
        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            # self.sla_type
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category_support.id,
                'request_text': 'Test SLA Rule line zero priority',
            })

            # Get references to sla_control_ids
            sla_control_draft = self._get_sla_control(request, self.sla_draft)

            # Test active sla controls
            self.assertTrue(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')

            # Test to assure that sla time set from rule line
            self.assertEqual(sla_control_draft.warn_date,
                             dt(2017, 5, 3, 8, 3))
            self.assertEqual(sla_control_draft.limit_date,
                             dt(2017, 5, 3, 9, 3))
