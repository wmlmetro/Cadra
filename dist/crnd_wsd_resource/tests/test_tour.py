from odoo.addons.crnd_wsd.tests.phantom_common import (
    TestPhantomTour
)


class TestWebsiteServiceDeskResource(TestPhantomTour):

    def setUp(self):
        super(TestWebsiteServiceDeskResource, self).setUp()
        self.user_demo = self.env.ref(
            'crnd_wsd.user_demo_service_desk_website')
        self.group_portal = self.env.ref('base.group_portal')

        # Disable services for this test case
        self._disable_use_services_setting()
        self.env['generic.resource'].search([]).write({
            'service_ids': [(5, 0)]
        })

    def test_tour_request_new(self):
        self.assertIn(self.group_portal, self.user_demo.groups_id)

        new_requests = self._test_phantom_tour_requests(
            '/',
            'crnd_wsd_resource_tour_request_new_with_resource',
            login=self.user_demo.login)

        self.assertEqual(len(new_requests), 1)
        self.assertTrue(
            new_requests.request_text.startswith(
                u'<h1>Test request with resource</h1>'))

    def test_tour_public_user(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = 'restrict'
        self._test_phantom_tour(
            '/', 'crnd_wsd_resource_tour_request_public_user')

    def test_tour_public_user_create_request(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = (
            'create-request')
        request = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_resource_tour_request_public_user_create_req')

        self.assertEqual(len(request), 1)
        self.assertFalse(request.author_id)
        self.assertFalse(request.partner_id)
        self.assertEqual(request.author_name, 'John Doe')
        self.assertEqual(request.email_from, 'john@doe.net')
        self.assertEqual(
            request.resource_id,
            self.env.ref(
                'generic_resource.'
                'simple_resource_inkprinter_6_generic_resource'))

    def test_tour_public_user_redirect(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = 'redirect'
        self._test_phantom_tour(
            '/', 'crnd_wsd_resource_tour_request_public_user_redirect')

    def test_tour_request_new_with_resource_parameter(self):
        self.ensure_classifier(
            category='crnd_wsd.request_category_demo_website_tech',
            request_type='crnd_wsd_resource.request_type_resource_question',
            website_published=True)

        self.env.ref(
            'crnd_wsd.request_type_generic'
        ).write({
            'resource_type_ids': [(4, self.env.ref(
                'generic_resource.generic_resource_type_default').id)],
        })
        self.env.ref(
            'generic_resource.simple_resource_computer_2'
        ).write({
            'resource_visibility': 'portal',
        })
        new_requests = self._test_phantom_tour_requests(
            '/requests/new?resource_id=%s' % self.env.ref(
                'generic_resource.simple_resource_computer_2').resource_id.id,
            'crnd_wsd_resource_tour_request_new_with_resource_parameter',
            login=self.user_demo.login)
        self.assertEqual(len(new_requests), 1)
        self.assertEqual(
            new_requests.resource_id,
            self.env.ref(
                'generic_resource.simple_resource_computer_2_generic_resource'
            ))
