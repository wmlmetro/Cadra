from odoo import http
from odoo.osv import expression

from odoo.addons.crnd_wsd.controllers.main import WebsiteRequest


class WebsiteRequestContractServices(WebsiteRequest):

    def _request_new_get_public_services_domain(self, **post):
        domain = super(
            WebsiteRequestContractServices, self
        )._request_new_get_public_services_domain(**post)
        domain = expression.OR([
            domain,
            [('active_contract_ids.partner_id', 'parent_of',
              http.request.env.user.partner_id.id)]
        ])
        return domain

    def _request_new_get_public_categs_domain(self, category_id=None,
                                              service_id=None, **kwargs):
        domain = super(
            WebsiteRequestContractServices, self
        )._request_new_get_public_categs_domain(
            category_id=category_id, service_id=service_id, **kwargs)

        service = self._id_to_record('generic.service', service_id)
        if service:
            slines = http.request.env['generic.contract.service.line'].search([
                ('contract_id.partner_id', 'parent_of',
                 http.request.env.user.partner_id.id),
                ('service_id', '=', service.id),
            ])
            categs = slines.mapped('request_category_ids')
            if categs:
                return expression.OR([
                    domain,
                    [('id', 'in', categs.ids)],
                ])
        return domain
