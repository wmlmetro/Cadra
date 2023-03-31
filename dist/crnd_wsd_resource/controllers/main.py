import logging
from odoo import _
from odoo import http
from odoo.osv import expression

from odoo.addons.crnd_wsd.controllers.main import WebsiteRequest

_logger = logging.getLogger(__name__)


class WebsiteRequestResource(WebsiteRequest):

    def _request_new_get_public_types_domain(self, type_id=None,
                                             category_id=None,
                                             resource_id=None, **kwargs):
        domain = super(
            WebsiteRequestResource, self
        )._request_new_get_public_types_domain(
            type_id=type_id, category_id=category_id, resource_id=resource_id,
            **kwargs)

        resource = self._id_to_record('generic.resource', resource_id)
        if resource_id:
            return expression.AND([
                domain,
                [('resource_type_ids.resource_ids.id', '=', resource.id)]
            ])
        return domain

    def _request_new_get_public_types_filter_resource(self, req_type,
                                                      category_id=None,
                                                      resource_id=None,
                                                      **kwargs):
        """ Check if request type could be used to create request from website,
            especally check if user has access to resources needed for this
            request type
        """
        resource = self._id_to_record('generic.resource', resource_id)
        if resource_id:
            # If resource specified, then we have to show only request types
            # related to selected resource
            return bool(self._request_new_get_resource_types(
                req_type, category_id=category_id,
                resource_id=resource.id, **kwargs))
        if not req_type.resource_required:
            # Always show request types that does not require resource
            return True
        return bool(
            self._request_new_get_resource_types(
                req_type, category_id=category_id, resource_id=resource.id,
                **kwargs))

    def _request_new_get_public_types(self, type_id=None, category_id=None,
                                      resource_id=None, **kwargs):
        res = super(
            WebsiteRequestResource, self
        )._request_new_get_public_types(
            type_id=type_id, category_id=category_id,
            resource_id=resource_id, **kwargs)

        return res.filtered(
            lambda rt: self._request_new_get_public_types_filter_resource(
                rt, category_id=category_id,
                resource_id=resource_id, **kwargs))

    def _request_new_get_resource_types(self, req_type, category_id=None,
                                        resource_id=None, **post):
        """ Find resource types available for current user to be used
            in request that being created
        """
        if resource_id:
            resource = self._id_to_record('generic.resource', resource_id)
            return req_type.resource_type_ids.filtered(
                lambda r: resource in r.resource_ids)
        return req_type.resource_type_ids.filtered(
            lambda r: r.resource_ids)

    def _request_new_process_resource_data(self, req_type, **post):
        resource_types = self._request_new_get_resource_types(
            req_type, **post)

        # Resource
        resource = False
        if post.get('resource_id'):
            resource = self._id_to_record(
                'generic.resource', post.get('resource_id'))
        if isinstance(resource_types, bool):
            resource_types = False

        if (resource and resource_types and
                resource.res_type_id not in resource_types):
            resource = False
        return {
            'request_resource_types': resource_types,
            'resource': resource,
            'resource_required': req_type.resource_required,
        }

    def _request_new_process_data(self, req_type, req_category=False,
                                  req_text=None, **post):
        result = super(WebsiteRequestResource, self)._request_new_process_data(
            req_type, req_category=req_category, req_text=req_text, **post)

        process_resource = self._is_view_active(
            'crnd_wsd_resource.wsd_requests_new_request_data_resource')
        if process_resource:
            result.update(
                self._request_new_process_resource_data(req_type, **post)
            )

        return result

    def _request_new_prepare_data(self, req_type, req_category,
                                  req_text, **post):
        result = super(WebsiteRequestResource, self)._request_new_prepare_data(
            req_type, req_category, req_text, **post)

        process_resource = self._is_view_active(
            'crnd_wsd_resource.wsd_requests_new_request_data_resource')
        if process_resource:
            resource = self._id_to_record('generic.resource',
                                          post.get('resource_id'))
            result.update({
                'resource_id': resource and resource.id or False,
            })

        return result

    def _request_new_validate_data(self, req_type, req_category,
                                   req_text, data, **post):
        errs = super(WebsiteRequestResource, self)._request_new_validate_data(
            req_type, req_category, req_text, data, **post)

        process_resource = self._is_view_active(
            'crnd_wsd_resource.wsd_requests_new_request_data_resource')
        if not process_resource:
            return errs

        if data.get('resource_id'):
            resource = self._id_to_record('generic.resource',
                                          data['resource_id'])
            if resource:
                if resource.res_type_id not in req_type.resource_type_ids:
                    errs.update({
                        'resource_id': {
                            'error_text': _("Wrong resource type selected!")}})
            elif req_type.resource_required:
                errs.update({
                    'resource_id': {
                        'error_text': _("Resource not selected!")}})
        elif req_type.resource_required:
            errs.update({
                'resource_id': {
                    'error_text': _("Resource not selected!")}})
        return errs

    @http.route()
    def request_new_fill_data(self, type_id=None, category_id=None,
                              req_text=None, **kwargs):

        res = super(WebsiteRequestResource, self).request_new_fill_data(
            type_id=type_id, category_id=category_id, req_text=req_text,
            **kwargs)
        resource_id = kwargs.get('resource_id', False)
        if resource_id:
            res.qcontext.update({'resource_id': resource_id})

        return res

    @http.route()
    def request_new(self, **kwargs):

        res = super(WebsiteRequestResource, self).request_new(**kwargs)
        resource_id = kwargs.get('resource_id', False)

        if not resource_id or \
                self._id_to_record('generic.resource', resource_id):
            return res

        return http.request.not_found()
