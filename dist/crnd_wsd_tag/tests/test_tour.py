from odoo.addons.crnd_wsd.tests.phantom_common import (
    TestPhantomTour
)


class TestWebsiteServiceDeskTag(TestPhantomTour):

    def setUp(self):
        super(TestWebsiteServiceDeskTag, self).setUp()
        self.user_demo = self.env.ref(
            'crnd_wsd.user_demo_service_desk_website')
        self.group_portal = self.env.ref('base.group_portal')
        self._disable_use_services_setting()

    def test_tour_request_new(self):
        self.assertIn(self.group_portal, self.user_demo.groups_id)

        new_requests = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_tag_tour_request_new_with_tags',
            login=self.user_demo.login)

        self.assertEqual(len(new_requests), 1)
        self.assertTrue(
            new_requests.request_text.startswith(
                u'<h1>Test request with tags</h1>'))

    def test_tour_public_user(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = 'restrict'
        self._test_phantom_tour(
            '/', 'crnd_wsd_tag_tour_request_public_user')

    def test_tour_public_user_redirect(self):
        self.env.user.company_id.request_wsd_public_ui_visibility = 'redirect'
        self._test_phantom_tour(
            '/', 'crnd_wsd_tag_tour_request_public_user_redirect')
