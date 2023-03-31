from odoo.addons.crnd_wsd.tests.phantom_common import (
    TestPhantomTour
)


class TestCrndWsdProject(TestPhantomTour):

    def setUp(self):
        super(TestCrndWsdProject, self).setUp()
        self.user_demo = self.env.ref(
            'crnd_wsd.user_demo_service_desk_website')

    def test_request_with_task(self):
        self._test_phantom_tour(
            '/', 'crnd_wsd_project_request_with_task',
            login=self.user_demo.login)
