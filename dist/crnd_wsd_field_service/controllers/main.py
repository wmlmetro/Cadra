from odoo.addons.crnd_wsd_field.controllers.main import WebsiteRequestFields
from odoo.addons.crnd_wsd.controllers.main import WebsiteRequest


class WebsiteRequestFieldsService(WebsiteRequestFields, WebsiteRequest):

    def _request_new_fields_get_search_context(self, req_type,
                                               req_category=False, **post):
        ctx_record = super(
            WebsiteRequestFieldsService, self
        )._request_new_fields_get_search_context(
            req_type, req_category=req_category, **post)

        service = self._id_to_record('generic.service', post.get('service_id'))
        ctx_record.service_id = service
        return ctx_record
