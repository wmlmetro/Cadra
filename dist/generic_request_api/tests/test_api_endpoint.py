import logging
from odoo.addons.generic_mixin.tests.common import TEST_URL
from .test_api_endpoint_base import TestApiEndpointsBase


_logger = logging.getLogger(__name__)


class TestRequestApiEndpoint(TestApiEndpointsBase):

    # Testing API controllers:
    def test_internal_endpoint_controllers(self):
        internal_request = self.call_api(self.internal_endpoint.url)

        # Testing Internal Request
        self.assertEqual(internal_request.type_id.id,
                         self.request_type.id)
        self.assertEqual(internal_request.category_id,
                         self.request_category)
        self.assertEqual(internal_request.request_text,
                         '<p>Test internal endpoint</p>')

    def test_redirect_url_internal_endpoint_controllers(self):
        response = self._call_api(
            self.redirect_url_endpoint.url, allow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertTrue(
            response.headers['Location'].startswith(
                '%s/mail/view?model=request.request' % TEST_URL))

    # Testing API controllers:
    def test_public_endpoint_controllers(self):
        public_request = self.call_api(self.public_endpoint.url)

        # Testing Public Request
        self.assertEqual(public_request.type_id.id,
                         self.request_type.id)
        self.assertEqual(public_request.category_id,
                         self.request_category)
        self.assertEqual(public_request.request_text,
                         '<p>Test public endpoint</p>')

    def test_api_endpoint_model(self):
        endpoint = self.env['request.api.endpoint'].new({
            'name': 'test tset',
        })
        self.assertFalse(endpoint.slug)

        endpoint._onchange_name()
        self.assertEqual(endpoint.slug, 'test-tset')

    def test_handle_request_api(self):
        self.authenticate("demo-request-manager", "demo")
        internal_res = self.url_open(
            "/api/requests/internal/invalid-url").status_code
        public_res = self.url_open(
            "/api/requests/public/invalid-url").status_code
        self.assertEqual(internal_res, 404)
        self.assertEqual(public_res, 404)

    # Testing API creating request with channel_api:
    def test_request_channel_created_via_api(self):
        request = self.call_api(self.internal_endpoint.url)
        channel_api = self.env.ref('generic_request.request_channel_api')

        self.assertEqual(request.channel_id, channel_api)

    def test_request_channel_api_archived(self):
        # Make api channel archived
        channel_api = self.env.ref('generic_request.request_channel_api')
        channel_other = self.env.ref('generic_request.request_channel_other')
        channel_api.sudo().active = False
        channel_api.invalidate_cache()

        # Check that default channel assigned to the request
        request = self.call_api(self.internal_endpoint.url)
        self.assertEqual(request.channel_id, channel_other)

    def test_request_channel_api_deleted(self):
        # Make api channel deleted
        self.env.ref(
            'generic_request.request_channel_api').sudo().unlink()
        channel_other = self.env.ref('generic_request.request_channel_other')

        # Check that default channel assigned to the request
        request = self.call_api(self.internal_endpoint.url)
        self.assertEqual(request.channel_id, channel_other)

    def test_delete_default_channel_also(self):
        # Make api and default channels deleted
        self.env.ref(
            'generic_request.request_channel_api').sudo().unlink()
        self.env.ref(
            'generic_request.request_channel_other').sudo().unlink()

        # Check that request channel is False
        request = self.call_api(self.internal_endpoint.url)
        self.assertFalse(request.channel_id)
