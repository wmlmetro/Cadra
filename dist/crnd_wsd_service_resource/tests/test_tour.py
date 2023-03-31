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

        # show on website notebook rent service
        self.env.ref('crnd_service_desk.request_type_incident').write({
            'website_published': True,
            'category_ids': [(4, self.env.ref(
                'crnd_wsd.'
                'request_category_demo_website_support').id)],
        })
        self.env.ref('generic_service.generic_service_rent_notebook').write({
            'request_type_ids': [
                (4, self.env.ref(
                    'crnd_service_desk.request_type_incident').id),
            ],
            'category_ids': [
                (4, self.env.ref(
                    'crnd_wsd.'
                    'request_category_demo_website_support').id),
            ],
            'website_published': True,
        })

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
            'website_published': True,
            'resource_ids': [(4, self.env.ref(
                'generic_resource.simple_resource_computer_2').id)],
            'request_type_ids': [(4, self.env.ref(
                'crnd_wsd_resource.request_type_resource_question').id)],
            'category_ids': [(4, self.env.ref(
                'crnd_wsd.request_category_demo_website_support').id)],
        })
        self.env.ref(
            'generic_service.generic_service_rent_notebook'
        ).write({
            'website_published': True,
            'request_type_ids': [(4, self.env.ref(
                'crnd_wsd_resource.request_type_resource_question').id)],
            'category_ids': [(4, self.env.ref(
                'crnd_wsd.request_category_demo_website_support').id)],
        })
        self.env.ref(
            'generic_service.generic_service_default'
        ).write({
            'request_type_ids': [(4, self.env.ref(
                'crnd_wsd_resource.request_type_resource_question').id)],
        })

        self.env.ref(
            'crnd_wsd_resource.request_type_resource_question'
        ).write({
            'category_ids': [(4, self.env.ref(
                'crnd_wsd.request_category_demo_website_tech').id)],
        })
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
