from odoo.tests.common import tagged
from odoo.addons.crnd_wsd.tests.phantom_common import (
    TestPhantomTour
)


@tagged('post_install', '-at_install')
class TestCrndWsdRelatedDocument(TestPhantomTour):

    def setUp(self):
        super(TestCrndWsdRelatedDocument, self).setUp()
        self.user_demo = self.env.ref(
            'crnd_wsd.user_demo_service_desk_website')

    def test_tour_crnd_wsd_related_document(self):
        self._test_phantom_tour(
            '/', 'tour_crnd_wsd_related_document',
            login=self.user_demo.login)
