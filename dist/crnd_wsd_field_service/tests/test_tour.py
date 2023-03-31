from odoo.addons.crnd_wsd.tests.phantom_common import (
    TestPhantomTour,
)


class TestWebsiteServiceDeskField(TestPhantomTour):

    def setUp(self):
        super(TestWebsiteServiceDeskField, self).setUp()
        self.user_demo = self.env.ref(
            'crnd_wsd.user_demo_service_desk_website')
        self.group_portal = self.env.ref('base.group_portal')
        self._enable_use_services_setting()

    def test_tour_request_new(self):
        self.assertIn(self.group_portal, self.user_demo.groups_id)

        # Run tour
        new_requests = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_field_service_tour_request_new_with_fields_service',
            login=self.user_demo.login)

        self.assertEqual(len(new_requests), 1)
        self.assertTrue(
            new_requests.request_text.startswith(
                u'<h1>Test create-vm request</h1>'))
        self.assertEqual(new_requests.get_field_value('cpu'), '2 Cores')
