import logging
from odoo import fields
from odoo.addons.generic_request.tests.common import freeze_time
from .common import RequestSLACase

_logger = logging.getLogger(__name__)


class TestRequestSLACalendarComplex(RequestSLACase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestSLACalendarComplex, cls).setUpClass()
        # Request type
        cls.request_type_sla = cls.env.ref(
            'generic_request_sla_log.request_type_sla')
        # Request Channel
        cls.request_website_channel = cls.env.ref(
            'generic_request.request_channel_website'
        )
        # SLA Rules
        cls.sla_sent = cls.env.ref(
            'generic_request_sla.request_sla_rule_2h_unassigned')

    def test_sla_rule_sla_with_specific_line_website(self):
        Request = self.env['request.request']

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.request_type_sla.id,
                'request_text': 'Request from Website Channel!',
                'channel_id': self.request_website_channel.id,
            })

            # Get references to sla_control_ids
            sla_control_sent = self._get_sla_control(request, self.sla_sent)

            # Test active sla controls
            self.assertFalse(sla_control_sent.sla_active)
            self.assertEqual(sla_control_sent.sla_state, 'ok')

            # Send request
            request.with_user(self.request_user).stage_id = self.stage_sent

            # Test active sla controls
            self.assertTrue(sla_control_sent.sla_active)
            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok']))
            self.assertEqual(sla_control_sent.sla_state, 'ok')

            # Test time
            self.assertEqual(
                fields.Datetime.to_string(sla_control_sent.warn_date),
                '2017-05-03 14:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_sent.limit_date),
                '2017-05-03 15:03:00')
