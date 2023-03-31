from urllib.parse import urljoin
from odoo.tests import common
from odoo.api import Environment
from odoo.tools import mute_logger
from odoo.addons.generic_mixin.tests.common import ReduceLoggingMixin, TEST_URL


class TestApiEndpointsBase(ReduceLoggingMixin, common.HttpCase):

    def setUp(self):
        super(TestApiEndpointsBase, self).setUp()

        self.Request = self.env['request.request']
        self.user_public = self.env.ref(
            'generic_request.user_demo_request_manager')
        self.request_type = self.env.ref(
            'generic_request_api.test_api_request_type')
        self.request_category = self.env.ref(
            'generic_request_api.test_api_request_category')
        self.internal_endpoint = self.env.ref(
            'generic_request_api.test_api_internal_endpoint')
        self.public_endpoint = self.env.ref(
            'generic_request_api.test_api_public_endpoint')
        self.redirect_url_endpoint = self.env.ref(
            'generic_request_api.test_redirect_url_internal_endpoint')
        self.rest_api_endpoint = self.env.ref(
            'generic_request_api.test_rest_api_endpoint')
        self.rest_api_endpoint_with_auth = self.env.ref(
            'generic_request_api.test_rest_api_endpoint_with_keys')

    def _get_test_url(self, url):
        return urljoin(TEST_URL, url)

    @mute_logger('odoo.addons.base.ir.ir_model')
    def _call_api(self, api_url, method="get", data=None,  # nosec
                  user="demo-request-manager", password="demo",
                  **kwargs):
        """ Call API url via http and return response object
        """
        self.authenticate(user, password)
        if api_url.startswith('/'):
            api_url = self._get_test_url(api_url)

        meth_in = method.lower()
        meth = getattr(self.opener, meth_in)
        if meth_in in ("post", "put"):
            return meth(api_url, data=data, **kwargs)
        return meth(api_url, **kwargs)

    # Call api method:
    def call_api(self, api_url, method="get", data=None,  # nosec
                 user="demo-request-manager", password="demo",
                 **kwargs):
        response = self._call_api(
            api_url, method=method, data=data,
            user=user, password=password, **kwargs)

        if response.status_code == 200:
            cr = self.registry.cursor()
            env = Environment(cr, self.uid, {})
            api_request = env['request.request'].browse(int(response.text))
            return api_request
        return False
