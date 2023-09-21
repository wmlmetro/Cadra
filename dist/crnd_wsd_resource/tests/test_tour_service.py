from odoo.addons.crnd_wsd.tests.phantom_common import (
    TestPhantomTour
)


class TestWebsiteServiceDeskServiceResource(TestPhantomTour):

    def setUp(self):
        super(TestWebsiteServiceDeskServiceResource, self).setUp()
        self.user_demo = self.env.ref(
            'crnd_wsd.user_demo_service_desk_website')
        self.group_portal = self.env.ref('base.group_portal')
        self._enable_use_services_setting()

    def test_tour_request_new(self):
        self.assertIn(self.group_portal, self.user_demo.groups_id)

        # Classifiers with the following parameters are expected
        # to be created:
        self.ensure_classifier(
            category='crnd_wsd.request_category_demo_website_support',
            request_type='crnd_service_desk.request_type_incident',
            website_published=True)
        self.ensure_classifier(
            service='generic_service.generic_service_rent_notebook',
            category='crnd_wsd.request_category_demo_website_support',
            request_type='crnd_service_desk.request_type_incident',
            website_published=True)
        self.ensure_classifier(
            service='generic_service.generic_service_support_configuration',
            category='crnd_wsd.request_category_demo_website_support',
            request_type='crnd_wsd_resource.request_type_resource_question',
            website_published=True)
        self.ensure_classifier(
            service='generic_service.generic_service_rent_notebook',
            category='crnd_wsd.request_category_demo_website_support',
            request_type='crnd_wsd_resource.request_type_resource_question',
            website_published=True)
        self.ensure_classifier(
            service='generic_service.generic_service_default',
            category='crnd_wsd.request_category_demo_website_tech',
            request_type='crnd_wsd_resource.request_type_resource_question',
            website_published=True)
        self.ensure_classifier(
            service='generic_service.generic_service_default',
            category='generic_request.request_category_demo_resource',
            request_type='generic_request.request_type_sequence',
            website_published=True)

        new_requests = self._test_phantom_tour_requests(
            '/',
            'crnd_wsd_service_resource_tour_request_new',
            login=self.user_demo.login)

        self.assertEqual(len(new_requests), 1)
        self.assertTrue(
            new_requests.request_text.startswith(
                u'<h1>Test request with resource</h1>'))

    def test_tour_request_new_with_resource_parameter(self):
        self.env.ref(
            'generic_service.generic_service_support_configuration'
        ).write({
            'resource_ids': [(4, self.env.ref(
                'generic_resource.simple_resource_computer_2').id)],
        })

        self.ensure_classifier(
            service='generic_service.generic_service_default',
            category='generic_request.request_category_demo_resource',
            request_type='generic_request.request_type_simple',
            website_published=True)
        self.ensure_classifier(
            service='generic_service.generic_service_default',
            category='generic_request.request_category_demo_resource',
            request_type='generic_request.request_type_sequence',
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
        self._test_phantom_tour(
            '/requests/new?resource_id=%s' % self.env.ref(
                'generic_resource.simple_resource_computer_2').resource_id.id,
            'crnd_wsd_service_resource_tour_request_new_with_res_parameter',
            login=self.user_demo.login)
