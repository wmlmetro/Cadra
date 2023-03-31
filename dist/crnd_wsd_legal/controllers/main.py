import logging
from odoo import http, _
from odoo.addons.crnd_wsd.controllers.main import WebsiteRequest
from odoo.tools.misc import str2bool
_logger = logging.getLogger(__name__)


class WebsiteRequestLegal(WebsiteRequest):

    def _request_new_process_data(self, req_type, req_category=False,
                                  req_text=None, **post):
        result = super(WebsiteRequestLegal, self)._request_new_process_data(
            req_type, req_category, req_text, **post)

        user = http.request.env.user
        if req_type.terms_and_conditions_url:
            terms_url = req_type.terms_and_conditions_url
        elif user.company_id.request_terms_and_conditions_url:
            terms_url = user.company_id.request_terms_and_conditions_url
        else:
            terms_url = None
        result['terms_and_conditions_url'] = terms_url
        result.update({
            'term_and_conditions_required':
                self._request_is_accept_terms_required(req_type)})
        return result

    def _request_is_accept_terms_required(self, req_type):
        user = http.request.env.user
        if (user.company_id.request_require_terms_and_conditions == 'yes' and
                req_type.require_terms_and_conditions in ('yes', 'global')):
            return True
        if (user.company_id.request_require_terms_and_conditions == 'no' and
                req_type.require_terms_and_conditions == 'yes'):
            return True
        return False

    def _request_new_validate_data(self, req_type, req_category,
                                   req_text, data, **post):
        errors = super(WebsiteRequestLegal, self)._request_new_validate_data(
            req_type, req_category, req_text, data, **post)

        is_term_and_conditions = str2bool(
            post.get('terms_and_conditions', 'false'))
        if not is_term_and_conditions and (
                self._request_is_accept_terms_required(req_type)):
            errors.update({
                'is_term_and_conditions': {
                    'error_text': _(
                        "It is required to accept terms and conditions "
                        "to continue!")}})
        return errors
