from odoo.addons.crnd_wsd.tests.phantom_common import TestPhantomTour
from odoo.addons.generic_mixin.tests.common import deactivate_records_for_model


class TestWebsiteServiceDeskField(TestPhantomTour):

    def setUp(self):
        super(TestWebsiteServiceDeskField, self).setUp()
        self.user_demo = self.env.ref(
            'crnd_wsd.user_demo_service_desk_website')
        self.group_portal = self.env.ref('base.group_portal')
        self.request_field_comment = self.env.ref(
            'generic_request_field.request_stage_field_comment')
        deactivate_records_for_model(self.env, 'ir.rule')
        self._disable_use_services_setting()

    def test_tour_request_new(self):
        self.assertIn(self.group_portal, self.user_demo.groups_id)

        # Run tour
        new_requests = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_field_tour_request_new_with_fields',
            login=self.user_demo.login)

        self.assertEqual(len(new_requests), 1)
        self.assertTrue(
            new_requests.request_text.startswith(
                u'<h1>Test create-vm request</h1>'))
        self.assertEqual(new_requests.get_field_value('cpu'), '2 Cores')

    def test_tour_request_new__templated_default(self):
        self.request_field_comment.default = (
            "Current user's name = {{ current_user.name }}")
        self.assertIn(self.group_portal, self.user_demo.groups_id)

        # Run tour
        new_requests = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_field_tour_request_new_with_fields',
            login=self.user_demo.login)

        self.assertEqual(len(new_requests), 1)
        self.assertTrue(
            new_requests.request_text.startswith(
                u'<h1>Test create-vm request</h1>'))
        self.assertEqual(new_requests.get_field_value('cpu'), '2 Cores')

        self.assertEqual(
            new_requests.get_field_value('comment'),
            "Current user's name = Demo Service Desk Website User")

    def test_tour_public_user(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = 'restrict'
        self._test_phantom_tour(
            '/', 'crnd_wsd_fields_tour_request_public_user')

    def test_tour_public_user_create_request(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = (
            'create-request')
        request = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_fields_tour_request_public_user_create_request')

        self.assertEqual(len(request), 1)
        self.assertFalse(request.author_id)
        self.assertFalse(request.partner_id)
        self.assertEqual(request.author_name, 'John Doe')
        self.assertEqual(request.email_from, 'john@doe.net')
        self.assertEqual(request.get_field_value('cpu'), '2 Cores')

    def test_tour_public_user_create_request_create_contact(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = (
            'create-request')
        company = self.env.user.company_id
        company.request_mail_create_author_contact_from_email = True
        request = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_fields_tour_request_public_user_create_request')

        self.assertEqual(len(request), 1)
        self.assertTrue(request.author_id)
        self.assertFalse(request.partner_id)
        self.assertFalse(request.author_name)
        self.assertFalse(request.email_from)
        self.assertEqual(request.author_id.name, 'John Doe')
        self.assertEqual(request.author_id.email, 'john@doe.net')
        self.assertEqual(request.get_field_value('cpu'), '2 Cores')

    def test_tour_public_user_redirect(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = 'redirect'
        self._test_phantom_tour(
            '/', 'crnd_wsd_fields_tour_request_public_user_redirect')
