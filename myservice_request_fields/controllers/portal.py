from odoo import http
from odoo.http import request
from odoo.addons.crnd_wsd.controllers.main import WebsiteRequest


class MyServicePortalController(WebsiteRequest):

    def _request_new_process_data(self, req_type, req_category=False,
                                  req_text=None, **kwargs):
        values = super()._request_new_process_data(
            req_type, req_category, req_text=req_text, **kwargs)

        all_locs = request.env['generic.location'].sudo().search(
            [], order='name asc')

        seen = set()
        unique_locs = []
        for loc in all_locs:
            key = loc.name.strip().upper()
            if key not in seen:
                seen.add(key)
                unique_locs.append(loc)

        selected_loc_id = False
        raw = kwargs.get('generic_location_id')
        if raw:
            try:
                selected_loc_id = int(raw)
            except (ValueError, TypeError):
                pass

        values['nrs_locations'] = unique_locs
        values['selected_location_id'] = selected_loc_id
        return values

    def _request_new_prepare_data(self, req_type, req_category,
                                  req_text, **kwargs):
        data = super()._request_new_prepare_data(
            req_type, req_category, req_text, **kwargs)
        raw = kwargs.get('generic_location_id')
        if raw:
            try:
                loc_id = int(raw)
                loc = request.env['generic.location'].sudo().browse(loc_id)
                if loc.exists():
                    data['generic_location_id'] = loc_id
            except (ValueError, TypeError):
                pass
        return data

    def _request_new_validate_data(self, req_type, req_category,
                                   req_text, req_data, **kwargs):
        errors = super()._request_new_validate_data(
            req_type, req_category, req_text, req_data, **kwargs)
        if not kwargs.get('generic_location_id'):
            errors['generic_location_id'] = {
                'error_text': 'Office / Location is required.'
            }
        return errors
