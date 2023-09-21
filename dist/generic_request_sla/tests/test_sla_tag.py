import logging
from odoo import fields
from odoo.addons.generic_request.tests.common import freeze_time
from .common import RequestSLACase

_logger = logging.getLogger(__name__)


class TestRequestSLATag(RequestSLACase):

    def setUp(self):
        super(TestRequestSLATag, self).setUp()

        # SLA Rules
        self.sla_sent_unassigned.rule_line_ids.unlink()

        # Tags
        self.tag_categ_platform = self.env.ref(
            'generic_request.tag_category_platform')
        self.tag_linux = self.env.ref(
            'generic_request.tag_platform_linux')

    def test_sla_rule_with_tag(self):
        Request = self.env['request.request']

        # Add tag categories to request type
        self.sla_type.write({
            'tag_category_ids': [(4, self.tag_categ_platform.id)]
        })
        self.assertIn(self.tag_categ_platform, self.sla_type.tag_category_ids)

        # Create rule line with tag
        tag_rule_line = self.env['request.sla.rule.line'].create({
            'sla_rule_id': self.sla_sent_unassigned.id,
            'tag_id': self.tag_linux.id,
            'compute_time': 'absolute',
            'warn_time': 4,
            'limit_time': 5,
            'priority': '0'
        })
        self.assertEqual(len(self.sla_sent_unassigned.rule_line_ids), 1)
        self.assertIn(
            tag_rule_line, self.sla_sent_unassigned.rule_line_ids)

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'request_text': 'Request to test SLA tag',
            })

            # Get references to sla_control_ids
            sla_control = self._get_sla_control(
                request, self.sla_sent_unassigned)

            # Test active sla controls
            self.assertFalse(sla_control.sla_active)
            self.assertEqual(sla_control.sla_state, 'ok')

            # Send request to activate SLA
            request.with_user(self.request_user).stage_id = self.stage_sent

            # Test active sla controls
            self.assertTrue(sla_control.sla_active)
            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok']))
            self.assertEqual(sla_control.sla_state, 'ok')

            # Test time to assure it align to main rule
            self.assertEqual(
                fields.Datetime.to_string(sla_control.warn_date),
                '2017-05-03 08:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control.limit_date),
                '2017-05-03 09:03:00')

            # Add tag to request to activate sla rule line
            request.write({
                'tag_ids': [(4, self.tag_linux.id)],
            })

            # Test active sla controls
            self.assertTrue(sla_control.sla_active)
            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok']))
            self.assertEqual(sla_control.sla_state, 'ok')

            # Test time to assure it align to rule line with tag
            self.assertEqual(
                fields.Datetime.to_string(sla_control.warn_date),
                '2017-05-03 11:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control.limit_date),
                '2017-05-03 12:03:00')
