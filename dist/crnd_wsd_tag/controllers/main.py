from odoo.addons.crnd_wsd.controllers.main import WebsiteRequest


class WebsiteRequestTags(WebsiteRequest):

    def _request_new_process_data(self, req_type, req_category=False,
                                  req_text=None, **post):
        result = super(WebsiteRequestTags, self)._request_new_process_data(
            req_type, req_category=req_category, req_text=req_text, **post)

        if self._is_view_active(
                'crnd_wsd_tag.wsd_requests_new_request_data_tags'):
            req_tag_categories = req_type.tag_category_ids
            result.update({
                'request_tag_categories': req_tag_categories
            })
        return result

    def _request_new_prepare_data(self, req_type, req_category,
                                  req_text, **post):
        result = super(WebsiteRequestTags, self)._request_new_prepare_data(
            req_type, req_category, req_text, **post)
        if self._is_view_active(
                'crnd_wsd_tag.wsd_requests_new_request_data_tags'):
            req_tag_categories = req_type.tag_category_ids
            req_tag_ids = result['tag_ids'] = []
            tag_keys = []
            for tag_category in req_tag_categories:
                for tag in tag_category.tag_ids:
                    if tag_category.check_xor:
                        tag_keys.append('tag_id_%d' % tag_category.id)
                    else:
                        tag_keys.append('tag_id_%d_%d' % (
                            tag_category.id, tag.id))
            tag_ids = [int(post.get(i)) for i in tag_keys if post.get(i)]
            req_tag_ids.append((6, 0, tag_ids))
        return result
