from odoo import http
from odoo.osv import expression
from odoo.addons.crnd_wsd.controllers.main import WebsiteRequest
from odoo.addons.crnd_wsd_resource.controllers.main import (
    WebsiteRequestResource
)


class WebsiteRequestResourceService(WebsiteRequestResource,
                                    WebsiteRequest):

    def _request_new_get_public_services_domain(self, resource_id=None,
                                                **post):
        # Required to show only services related to selected resource
        domain = super()._request_new_get_public_services_domain(
            resource_id=None, **post)

        if resource_id:
            resource = self._id_to_record('generic.resource', resource_id)
            return expression.AND([
                domain,
                [('resource_ids.id', '=', resource.id)],
            ])
        return domain

    def _request_new_get_resource_types(self, req_type, category_id=None,
                                        resource_id=None, service_id=None,
                                        **post):
        resource_types = super(
            WebsiteRequestResourceService, self
        )._request_new_get_resource_types(
            req_type, category_id=category_id, service_id=service_id, **post)

        service = self._id_to_record('generic.service', service_id)
        resource = self._id_to_record('generic.resource', resource_id)
        if service and resource and service in resource.service_ids:
            # If resource specified and it contains selected service,
            # then everything seems to be ok, so we just return selected
            # resource types (usualy it will be only single resource type)
            return resource_types
        if service and resource:
            # Empty list if service and resource specified, but selected
            # resource has no selected service
            return http.request.env['generic.resource.type'].browse()
        if service:
            # If only service specified, then just filtere request types to
            # those, that has resources that has selected service
            ResourceType = http.request.env['generic.resource.type']
            return ResourceType.search([
                ('id', 'in', resource_types.ids),
                ('resource_ids.service_ids', '=', service.id)])

        return resource_types
