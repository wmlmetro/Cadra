import json
import logging

import traceback
import werkzeug

from odoo import http, exceptions
from odoo.addons.generic_mixin.tools.monkey import monkey
from odoo.tools import date_utils


from .constants import API_PREFIX_REST

_logger = logging.getLogger(__name__)


class RestAPIRequest(http.HttpRequest):
    def __init__(self, httprequest):
        super(RestAPIRequest, self).__init__(httprequest)
        if self.httprequest.mimetype == "application/json":
            data = self.httprequest.get_data().decode(self.httprequest.charset)
            if data and data.strip():
                try:
                    self.jsondata = json.loads(data)
                except ValueError as exc:
                    _logger.info(
                        "Invalid JSON data (%s): %s",
                        self.httprequest.path, str(exc))
                    raise werkzeug.exceptions.BadRequest(
                        "Invalid JSON data %s" % str(exc))
            else:
                self.jsondata = None
        elif self.httprequest.url.split('/')[-1] == 'api_help':
            # In this case is Generic Request API help request
            pass
        else:
            raise werkzeug.exceptions.BadRequest(
                "Only application/json requests allowed!")

    def _json_response(self, result, status_code=200):
        body = json.dumps(result, default=date_utils.json_default)

        return http.Response(
            body, status_code,
            headers=[
                ('Content-Type', 'application/json'),
                ('Content-Length', len(body))]
        )

    def dispatch(self):
        try:
            result = self._call_function(**self.params)
        except werkzeug.exceptions.Unauthorized as exc:
            return self._json_response({
                'status': 'error',
                'error': {
                    'message': str(exc),
                }
            }, status_code=401)
        except exceptions.AccessError as exc:
            return self._json_response({
                'status': 'error',
                'error': {
                    'message': str(exc),
                }
            }, status_code=403)
        except Exception as exc:
            _logger.error(
                "Error caught while processing request's API Endpoint!",
                exc_info=True)
            return self._json_response({
                'status': 'error',
                'error': {
                    'message': str(exc),
                    'traceback': traceback.format_exc(),
                }
            }, status_code=500)
        if isinstance(result, http.Response):
            return result
        return self._json_response(result)


@monkey(http.Root, 'get_request')
def get_request(self, httprequest):
    # We have to enforce usage of HttpRequest for request's API, because
    # if application/json content type specified, then Odoo will think that
    # it is json+rpc request.
    # See:
    # - https://github.com/odoo/odoo/issues/7766
    #
    # Note, first request handled by worker may not be affected by this patch,
    # thus it is recommended to place this module to `system_wide_module`
    # to make it work smoothly

    if (httprequest.path.startswith(API_PREFIX_REST) and
            httprequest.mimetype == "application/json"):
        return RestAPIRequest(httprequest)
    return get_request.__wrapped__(self, httprequest)
