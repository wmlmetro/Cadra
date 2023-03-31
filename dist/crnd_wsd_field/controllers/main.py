from odoo import http, _

from odoo.addons.crnd_wsd.controllers.main import WebsiteRequest


class WebsiteRequestFields(WebsiteRequest):

    def _request_new_fields_get_search_context(self, req_type,
                                               req_category=False, **post):
        """ Prepare context to find request fields

            :param req_type: record representing type of request
            :param req_category: record, containing category of request
            :return Record(request.request): new (not commited to db) record
            that could be used to find fields needed to display
        """
        return http.request.env['request.request'].new({
            'type_id': req_type.id,
            'category_id': req_category.id,
        })

    def _request_new_get_request_fields(self, req_type, req_category=False,
                                        **post):
        request_ctx = self._request_new_fields_get_search_context(
            req_type, req_category=req_category, **post)
        return request_ctx._request_fields__get_fields()

    def _request_new_process_data(self, req_type, req_category=False,
                                  req_text=None, **post):
        result = super(WebsiteRequestFields, self)._request_new_process_data(
            req_type, req_category=req_category, req_text=req_text, **post)

        if self._is_view_active(
                'crnd_wsd_field.wsd_requests_new_request_data_extra_fields'):
            req_fields = self._request_new_get_request_fields(
                req_type, req_category=req_category, **post)
            req_field_values = {}
            request_fields_top = []
            request_fields_bottom = []
            request_fields_has_required = False
            for field in req_fields:
                req_field_values[field.website_name] = post.get(
                    field.website_name, field._get_default_value())
                if field.position == 'before':
                    request_fields_top.append(field)
                elif field.position == 'after':
                    request_fields_bottom.append(field)

                if field.mandatory:
                    request_fields_has_required = True

            result.update({
                'request_field_values': req_field_values,
                'request_fields_top': request_fields_top,
                'request_fields_bottom': request_fields_bottom,
                'request_fields_has_required': request_fields_has_required,
            })

        return result

    def _request_new_prepare_data(self, req_type, req_category,
                                  req_text, **post):
        result = super(WebsiteRequestFields, self)._request_new_prepare_data(
            req_type, req_category, req_text, **post)

        if self._is_view_active(
                'crnd_wsd_field.wsd_requests_new_request_data_extra_fields'):
            req_fields = self._request_new_get_request_fields(
                req_type, req_category=req_category, **post)
            req_value_ids = result['value_ids'] = []
            for field in req_fields:
                req_value_ids.append((0, 0, {
                    'field_id': field.id,
                    'value': post.get(
                        field.website_name, field._get_default_value()),
                }))

        return result

    def _request_new_validate_data(self, req_type, req_category,
                                   req_text, data, **post):
        errors = super(WebsiteRequestFields, self)._request_new_validate_data(
            req_type, req_category, req_text, data, **post)
        fields = self._is_view_active(
            'crnd_wsd_field.wsd_requests_new_request_data_extra_fields')
        if fields:
            req_fields = self._request_new_get_request_fields(
                req_type, req_category=req_category, **post)
            for field in req_fields:
                if field.mandatory:
                    if not post.get(field.website_name, field.default):
                        errors.update({
                            field.website_name: {
                                'error_text': _(
                                    "Fill mandatory field %s!") % field.name
                            }
                        })

        return errors
