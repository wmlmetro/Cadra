from odoo import http
from odoo.addons.generic_request_api.controllers.main import GenericRequestApi
from odoo.addons.website.controllers.main import QueryURL


class ServiceDeskAPI(GenericRequestApi):

    def _post_process_api_call(self, endpoint, request, **kwargs):
        if endpoint.on_success == 'redirect_to_req':
            return http.request.redirect(QueryURL(
                '/requests/request/%d' % request.id, [])(**kwargs))
        return super(ServiceDeskAPI, self)._post_process_api_call(
            endpoint, request, **kwargs)
