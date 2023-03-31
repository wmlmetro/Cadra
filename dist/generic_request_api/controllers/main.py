import logging
from odoo import http

from ..constants import (
    API_PREFIX_PUBLIC,
    API_PREFIX_INTERNAL,
)
_logger = logging.getLogger(__name__)


class GenericRequestApi(http.Controller):

    def _post_process_api_call(self, endpoint, request, **kwargs):
        if endpoint.on_success == 'return_req_id':
            return str(request.id)
        if endpoint.on_success == 'redirect_url':
            url = endpoint.on_success_redirect_url.format(
                request=request)
            return http.request.redirect(url)
        return "OK"

    def _get_api_endpoint(self, api_type, endpoint_slug):
        domain = [
            ('slug', '=', endpoint_slug),
            ('type', '=', api_type),
        ]
        # TODO: check if multiple endpoints found
        return http.request.env['request.api.endpoint'].search(domain, limit=1)

    def _handle_request_api(self, api_type, endpoint_slug, **data):
        endpoint = self._get_api_endpoint(api_type, endpoint_slug)

        if not endpoint:
            return http.request.not_found()

        request = endpoint.handle_simple_api_call(data)

        return self._post_process_api_call(endpoint, request, **data)

    @http.route([API_PREFIX_INTERNAL + '/<string:endpoint_slug>'],
                type='http',
                auth="user",
                methods=["GET"],
                website=True)
    def handle_request_internal_api(self, endpoint_slug, **data):
        return self._handle_request_api('internal', endpoint_slug, **data)

    @http.route(API_PREFIX_PUBLIC + '/<string:endpoint_slug>',
                type='http',
                auth="public",
                methods=["GET"],
                csrf=False,
                website=True)
    def handle_request_public_api(self, endpoint_slug, **data):
        return self._handle_request_api('public', endpoint_slug, **data)
