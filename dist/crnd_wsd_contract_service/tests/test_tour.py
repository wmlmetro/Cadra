from odoo.addons.crnd_wsd.tests.phantom_common import (
    TestPhantomTour
)


class TestWebsiteServiceDeskContractService(TestPhantomTour):

    def setUp(self):
        super(TestWebsiteServiceDeskContractService, self).setUp()
        self.user_demo = self.env.ref(
            'base.demo_user0')
        self._enable_use_services_setting()

    def init_test_data(self):
        # TODO: refactor demo data to avoid using non-demo data
        # show on website notebook rent service
        self.env.ref('crnd_service_desk.request_type_incident').write({
            'website_published': True,
            'service_ids': [
                (4, self.env.ref(
                    'generic_service.generic_service_default').id),
            ],
            'category_ids': [
                (4, self.env.ref(
                    'crnd_wsd.'
                    'request_category_demo_website_support').id),
                (4, self.env.ref(
                    'generic_request.request_category_demo_general').id),
            ],
        })
        self.env.ref(
            'generic_service.generic_service_support_consulting').write({
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
            'website_published': False,
        })
        self.env.ref(
            'generic_service.generic_service_support_development'
        ).write({
            'request_type_ids': [
                (4, self.env.ref(
                    'crnd_service_desk.request_type_incident').id),
            ],
            'category_ids': [
                (4, self.env.ref(
                    'crnd_wsd.'
                    'request_category_demo_website_support').id),
            ],
            'website_published': False,
        })
        self.env.ref('crnd_wsd_contract_service.demo_contract_service').write({
            'state': 'active',
        })

    def test_tour_request_contract_service_consulting(self):
        self.init_test_data()
        new_requests = self._test_phantom_tour_requests(
            '/',
            'crnd_wsd_contract_service_'
            'tour_request_contract_service_consulting',
            login=self.user_demo.login)

        self.assertEqual(len(new_requests), 1)
        self.assertTrue(
            new_requests.request_text.startswith(
                u'<h1>Test incident request support consulting</h1>'))

        self.assertEqual(
            new_requests.service_id,
            self.env.ref('generic_service.generic_service_support_consulting'))
        self.assertEqual(
            new_requests.contract_id,
            self.env.ref(
                'crnd_wsd_contract_service.demo_contract_service'))

    def test_tour_request_contract_service_development(self):
        self.init_test_data()
        new_requests = self._test_phantom_tour_requests(
            '/',
            'crnd_wsd_contract_service_'
            'tour_request_contract_service_dev',
            login=self.user_demo.login)

        self.assertEqual(len(new_requests), 1)
        self.assertTrue(
            new_requests.request_text.startswith(
                u'<h1>Test incident request support development</h1>'))
        self.assertEqual(
            new_requests.service_id,
            self.env.ref(
                'generic_service.generic_service_support_development'))
        self.assertEqual(
            new_requests.contract_id,
            self.env.ref(
                'crnd_wsd_contract_service.demo_contract_service'))

    def test_tour_request_contract_service_rent_notebook(self):
        self.init_test_data()

        self.env.ref('generic_service.generic_service_rent_notebook').write({
            'website_published': True,
        })
        new_requests = self._test_phantom_tour_requests(
            '/', 'crnd_wsd_contract_service_tour_request_contract_service',
            login=self.user_demo.login)

        self.assertEqual(len(new_requests), 1)
        self.assertTrue(
            new_requests.request_text.startswith(
                u'<h1>Test incident request rent of notebook</h1>'))
        self.assertEqual(
            new_requests.service_id,
            self.env.ref('generic_service.generic_service_rent_notebook'))
        self.assertFalse(new_requests.contract_id)
