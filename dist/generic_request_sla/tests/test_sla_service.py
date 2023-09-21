import logging

from datetime import datetime as dt
from odoo import fields
from odoo.addons.generic_request_sla.tests.common import RequestSLACase
from odoo.addons.generic_request.tests.common import freeze_time
from odoo.tests.common import Form

_logger = logging.getLogger(__name__)


class TestRequestSLAService(RequestSLACase):

    def setUp(self):
        super(TestRequestSLAService, self).setUp()

        self.default_service = self.env.ref(
            'generic_service.generic_service_default')

        # Ensure expected classifiers for default service exists
        self.ensure_classifier(
            service=self.default_service,
            category=self.request_category_general,
            request_type=self.sla_type,
        )
        self.ensure_classifier(
            service=self.default_service,
            category=self.request_category_support,
            request_type=self.sla_type,
        )
        self.ensure_classifier(
            service=self.default_service,
            category=self.request_category_technical,
            request_type=self.sla_type,
        )

        self.rent_service = self.env.ref(
            'generic_service.generic_service_rent_notebook')

        # Ensure expected classifiers for rent service exists
        self.ensure_classifier(
            service=self.rent_service,
            category=self.request_category_general,
            request_type=self.sla_type,
        )
        self.ensure_classifier(
            service=self.rent_service,
            category=self.request_category_support,
            request_type=self.sla_type,
        )
        self.ensure_classifier(
            service=self.rent_service,
            category=self.request_category_technical,
            request_type=self.sla_type,
        )

        self.partner = self.env.ref('base.res_partner_12')

        self.service_level_1 = self.env.ref(
            'generic_service.generic_service_level_1')
        self.service_level_2 = self.env.ref(
            'generic_service.generic_service_level_2')

        self.sla_draft_rule_line_service = self.env.ref(
            'generic_request_sla.'
            'request_sla_rule_8h_in_draft_default_service')
        self.sla_draft_rule_line_service_level_1 = self.env.ref(
            'generic_request_sla.'
            'request_sla_rule_8h_in_draft_service_level_1')
        self.sla_draft_rule_line_service_level_2 = self.env.ref(
            'generic_request_sla.'
            'request_sla_rule_8h_in_draft_service_level_2')
        self.sla_draft_rule_line_s_cat_s_l_2 = self.env.ref(
            'generic_request_sla.'
            'request_sla_rule_8h_in_draft_mixed')
        self.sla_draft.rule_line_ids.filtered(
            lambda rl: rl not in [
                self.sla_draft_rule_line_service,
                self.sla_draft_rule_line_service_level_1,
                self.sla_draft_rule_line_service_level_2,
                self.sla_draft_rule_line_s_cat_s_l_2,
                self.sla_draft_support]
        ).unlink()

    def test_sla_rule_sla_special_lines_ok_no_service(self):
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

    def test_sla_rule_sla_special_lines_ok_wrong_service(self):
        Request = self.env['request.request']

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category_support.id,
                'request_text': 'Hello!',
                'service_id': self.rent_service.id,
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

    def test_sla_rule_sla_special_lines_warning_with_service(self):
        Request = self.env['request.request']

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category_support.id,
                'service_id': self.default_service.id,
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
                '2017-05-03 09:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 10:03:00')

        # Send request
        with freeze_time('2017-05-03 09:53:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'warning')

    def test_sla_rule_sla_special_lines_ok_with_author_service_level(self):
        Request = self.env['request.request']

        # set service level to author
        self.request_user.partner_id.service_level_id = self.service_level_1.id

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
                '2017-05-03 08:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 08:03:00')

        # Send request
        with freeze_time('2017-05-03 07:53:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent

            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok']))
            self.assertEqual(request.sla_state, 'ok')

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')

    def test_sla_rule_sla_special_lines_ok_with_partner_service_level(self):
        Request = self.env['request.request']

        # set service level to author and partner
        self.request_user.partner_id.service_level_id = self.service_level_1.id
        self.partner.service_level_id = self.service_level_2.id

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'category_id': self.request_category_support.id,
                'partner_id': self.partner.id,
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
                '2017-05-03 11:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 12:03:00')

        # Send request
        with freeze_time('2017-05-03 10:53:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent

            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok']))
            self.assertEqual(request.sla_state, 'ok')

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')

    def test_sla_rule_sla_special_lines_ok_mixed(self):
        Request = self.env['request.request']

        # set service level to author and partner
        self.request_user.partner_id.service_level_id = self.service_level_1.id
        self.partner.service_level_id = self.service_level_2.id

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'partner_id': self.partner.id,
                'category_id': self.request_category_support.id,
                'service_id': self.default_service.id,
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
                '2017-05-03 19:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 20:03:00')

        # Send request
        with freeze_time('2017-05-03 10:53:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent

            self.assertEqual(set(request.sla_control_ids.mapped('sla_state')),
                             set(['ok']))
            self.assertEqual(request.sla_state, 'ok')

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')

    def test_sla_rule_sla_special_lines_warning_with_service_level(self):
        Request = self.env['request.request']

        # set service level to author and partner
        self.request_user.partner_id.service_level_id = self.service_level_1.id
        self.partner.service_level_id = self.service_level_2.id

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'partner_id': self.partner.id,
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
                '2017-05-03 11:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 12:03:00')

        # Send request
        with freeze_time('2017-05-03 11:53:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'warning')

    def test_sla_rule_sla_special_lines_failed_with_service_level(self):
        Request = self.env['request.request']

        # set service level to author and partner
        self.request_user.partner_id.service_level_id = self.service_level_1.id
        self.partner.service_level_id = self.service_level_2.id

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'partner_id': self.partner.id,
                'category_id': self.request_category_support.id,
                'request_text': 'Hello!',
            })

            # Test service level
            self.assertEqual(request.service_level_id, self.service_level_2)

            # Get references to sla_control_ids
            sla_control_draft = self._get_sla_control(request, self.sla_draft)

            # Test active sla controls
            self.assertTrue(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')

            # Test SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.warn_date),
                '2017-05-03 11:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 12:03:00')

        # Send request
        with freeze_time('2017-05-03 12:04:00'):
            request.with_user(self.request_user).stage_id = self.stage_sent

            # Test active sla controls
            self.assertFalse(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'failed')

    def test_sla_rule_sla_special_lines_update_on_sl_change(self):
        Request = self.env['request.request']

        # set service level to partner
        self.partner.service_level_id = self.service_level_2.id

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'partner_id': self.partner.id,
                'category_id': self.request_category_support.id,
                'request_text': 'Hello!',
            })
            self.assertEqual(request.service_level_id, self.service_level_2)

            # Get references to sla_control_ids
            sla_control_draft = self._get_sla_control(request, self.sla_draft)

            # Test active sla controls
            self.assertTrue(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')

            # Test SLA Dates
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.warn_date),
                '2017-05-03 11:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 12:03:00')

            # Change service level
            request.service_level_id = self.service_level_1

            # Test active sla controls
            self.assertTrue(sla_control_draft.sla_active)
            self.assertEqual(sla_control_draft.sla_state, 'ok')

            # Test SLA Dates: ensude dates recomputed when service level
            # changed
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.warn_date),
                '2017-05-03 08:03:00')
            self.assertEqual(
                fields.Datetime.to_string(sla_control_draft.limit_date),
                '2017-05-03 08:03:00')

    def test_onchange_service(self):
        self._enable_use_services_setting()
        Request = self.env['request.request']

        # unlink existing rule lines to avoid errors
        self.sla_draft.rule_line_ids.unlink()

        # create rule line for SLA without category and service
        rule_line = self.env['request.sla.rule.line'].create({
            'sla_rule_id': self.sla_draft.id,
            'compute_time': 'absolute',
            'warn_time': 2,
            'limit_time': 3,
        })

        # create service with category and type
        request_service = self.env['generic.service'].create({
            'name': 'Test SLA Service',
            'code': 'test-sla-service',
        })
        self.ensure_classifier(
            service=request_service,
            category=self.request_category_support,
            request_type=self.sla_type,
        )

        # check that rule line doesn't have category and service
        self.assertFalse(rule_line.category_ids)
        self.assertFalse(rule_line.service_id)

        # create category that not belongs to rule request type and service
        false_category = self.env['request.category'].create({
            'name': 'false_category',
            'code': 'false-category'
        })

        self.assertNotIn(
            false_category, rule_line.request_type_id.category_ids)

        # add service and category to rule line
        # triggering '_onchange_filter_categories' function on UI level
        with Form(rule_line) as rl:
            rl.category_ids.add(self.env.ref(
                'generic_request.request_category_demo_support'))
            rl.service_id = request_service

            # try to add category that not belongs to service
            rl.category_ids.add(false_category)

        # check that false category was not added to rule line
        self.assertNotIn(false_category, rule_line.category_ids)

        # Create request
        with freeze_time('2017-05-03 7:03:00'):
            request = Request.with_user(self.request_user).create({
                'type_id': self.sla_type.id,
                'service_id': request_service.id,
                'category_id': self.request_category_support.id,
                'request_text': 'Test SLA onchange service',
            })

        # check that rule line has same category and service as request
        self.assertIn(request.category_id, rule_line.category_ids)
        self.assertEqual(request.service_id, request_service)

        # get SLA control
        sla_control_draft = self._get_sla_control(request, self.sla_draft)

        # Test active sla controls
        self.assertTrue(sla_control_draft.sla_active)
        self.assertEqual(sla_control_draft.sla_state, 'ok')

        # Test to assure that sla time set from rule line
        self.assertEqual(sla_control_draft.warn_date,
                         dt(2017, 5, 3, 9, 3))
        self.assertEqual(sla_control_draft.limit_date,
                         dt(2017, 5, 3, 10, 3))
