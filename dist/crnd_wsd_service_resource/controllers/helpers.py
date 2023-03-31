from odoo import http
from odoo.addons.crnd_wsd_resource.controllers.helpers import (
    WSDResourceHelpers)


class WSDResourceServiceHelpers(WSDResourceHelpers):

    def _wsd_request_resources_search_domain(self, req_type, res_type, **post):
        domain = super(
            WSDResourceServiceHelpers, self
        )._wsd_request_resources_search_domain(req_type, res_type, **post)
        if post.get('service_id'):
            domain += [('service_ids.id', '=', post['service_id'])]
        return domain

    def _wsd_request_resources_find_resource_types(
            self, req_type, **post):
        """ Find resource types, that have to be available
            for resource selection for current user
        """
        resource_types = super(
            WSDResourceServiceHelpers, self
        )._wsd_request_resources_find_resource_types(req_type, **post)

        if post.get('service_id'):
            ResourceType = http.request.env['generic.resource.type']
            resource_types = ResourceType.search([
                ('id', 'in', resource_types.ids),
                ('resource_ids.service_ids', '=', post['service_id'])])

        return resource_types
