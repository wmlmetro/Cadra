import logging
from odoo import http

from ..constants import API_PREFIX_REST

_logger = logging.getLogger(__name__)


class GenericRequestApiRest(http.Controller):

    def _get_api_endpoint(self, api_type, endpoint_slug):
        domain = [
            ('slug', '=', endpoint_slug),
            ('type', '=', api_type),
        ]
        # TODO: check if multiple endpoints found
        return http.request.env['request.api.endpoint'].search(domain, limit=1)

    @http.route(
        ['%s/<string:endpoint_slug>/api_help' % API_PREFIX_REST],
        auth="public",
        website=True)
    def get_api_help(self, endpoint_slug, **kw):
        endpoint = self._get_api_endpoint('rest', endpoint_slug)
        values = {
            'endpoint': endpoint
        }
        return http.request.render(
            "generic_request_api.request_api_help_main", values)

    @http.route(
        ['%s/<string:endpoint_slug>' % API_PREFIX_REST],
        type='http',
        auth="public",
        methods=["POST"],
        csrf=False,
        website=True)
    def post_request(self, endpoint_slug, **kw):
        endpoint = self._get_api_endpoint('rest', endpoint_slug)
        if not endpoint:
            raise http.request.not_found()
        endpoint = endpoint.ensure_authorized()
        data = http.request.jsondata
        return endpoint.handle_rest_create_request(data)

    @http.route(
        ['%s/<string:endpoint_slug>/<int:request_id>' % API_PREFIX_REST,
         '%s/<string:endpoint_slug>/<string:request_name>' % API_PREFIX_REST],
        type='http',
        auth="public",
        methods=["GET"],
        csrf=False,
        website=True)
    def get_request_info(self, endpoint_slug, request_id=None,
                         request_name=None, what=None, **kw):
        endpoint = self._get_api_endpoint('rest', endpoint_slug)
        if not endpoint:
            raise http.request.not_found()
        endpoint = endpoint.ensure_authorized()
        request = endpoint._find_request(
            request_id=request_id, request_name=request_name)
        if not request:
            raise http.request.not_found()

        if what:
            what = [w.strip() for w in what.split(',')]
        return endpoint.handle_rest_get_request(request, what=what)

    @http.route(
        ['%s/<string:endpoint_slug>/<int:request_id>' % API_PREFIX_REST,
         '%s/<string:endpoint_slug>/<string:request_name>' % API_PREFIX_REST],
        type='http',
        auth="public",
        methods=["PUT"],
        csrf=False,
        website=True)
    def put_request(self, endpoint_slug, request_id=None,
                    request_name=None, **kw):
        endpoint = self._get_api_endpoint('rest', endpoint_slug)
        if not endpoint:
            raise http.request.not_found()
        endpoint = endpoint.ensure_authorized()
        request = endpoint._find_request(
            request_id=request_id, request_name=request_name)
        if not request:
            raise http.request.not_found()

        data = http.request.jsondata
        return endpoint.handle_rest_put_request(request, data)
