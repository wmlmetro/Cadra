import unittest
from odoo.tests.common import tagged
from odoo.addons.crnd_wsd.tests.phantom_common import (
    TestPhantomTour
)


@tagged('post_install', '-at_install')
class TestCrndWsdRelatedRequest(TestPhantomTour):

    def setUp(self):
        super(TestCrndWsdRelatedRequest, self).setUp()
        self.user_demo = self.env.ref(
            'base.user_demo')
        self.test_request = self.env.ref(
            'generic_request.request_request_type_access_demo_1')

    def test_tour_crnd_wsd_related_request(self):
        # This is necessary for the tests to pass successfully until
        # the bug in the Odoo code is fixed
        # https://github.com/odoo/odoo/commit/f74434c6f4303650e886d99fb950c763f2d4cc6e

        try:
            self.assertEqual(len(self.test_request.message_ids), 2)
            self.test_request.message_ids[0].portal_message_format()
            self.test_request.message_ids[1].portal_message_format()
        except TypeError:
            raise unittest.SkipTest(
                'BUG in method portal_message_format() is not fixed')

        self._test_phantom_tour(
            '/', 'tour_crnd_wsd_related_request',
            login=self.user_demo.login)
