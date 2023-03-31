from odoo import http
from odoo.osv import expression

from odoo.addons.crnd_wsd.controllers.helpers import WSDHelpers


class WSDResourceHelpers(WSDHelpers):

    def _wsd_request_resources_search_domain(
            self, req_type, res_type, **post):
        """ Prepare domain for resource autocomplete on website request
            creation form
        """
        return []

    def _wsd_request_resources_find_resource_types(
            self, req_type, **post):
        """ Find resource types, that have to be available
            for resource selection for current user
        """
        resource_types = post.get('resource_types', False)
        if resource_types:
            return req_type.resource_type_ids.filtered(
                lambda r: r.id in resource_types)
        return req_type.resource_type_ids

    def _wsd_request_iter_resources_types(
            self, req_type, **post):
        """ Iterate over resource_types availables for selection.
            On each iteration yield typle with following info:
                - resource_type
                - resource_model
                - resource_domain
        """
        # Needed to handle language in right way
        env = http.request.env(
            context=dict(http.request.env.context,
                         lang=post.get('lang', False)))

        resource_types = self._wsd_request_resources_find_resource_types(
            req_type, **post)
        for res_type in resource_types:
            model = res_type.sudo().model_id.model
            if not env[model].check_access_rights(
                    'read', raise_exception=False):
                continue

            domain = self._wsd_request_resources_search_domain(
                req_type, res_type, **post)

            yield res_type, model, domain

    @http.route('/crnd_wsd/api/resources', type='json',
                auth='public', methods=['POST'])
    def wsd_request_resources(self, **post_data):
        # Needed to handle language in right way
        env = http.request.env(
            context=dict(http.request.env.context,
                         lang=post_data.get('lang', False)))
        max_autocomplete_resources = (
            env.user.company_id.request_resource_autocomplete_max_resources)
        request_type = env['request.type'].browse(
            post_data.get('request_type_id', False))

        # TODO: It is better to get this parameter from the settings
        response = [{
            'settings': {
                'allowed_count': max_autocomplete_resources,
            },
        }]
        for res_type, model, domain in self._wsd_request_iter_resources_types(
                request_type, **post_data):
            term = post_data.get('term', False)
            if res_type.sudo().search_by_field_id:
                search_by_field = res_type.sudo().search_by_field_id.name
                resource_names = env[model].search(
                    expression.AND([
                        domain,
                        [(search_by_field, 'ilike', term)]
                    ]),
                    limit=max_autocomplete_resources + 1,
                ).name_get()
            else:
                resource_names = env[model].name_search(
                    term, args=domain,
                    limit=max_autocomplete_resources + 1)

            if not resource_names:
                # Skipe if there is no resources available for this type
                continue

            resources_count = len(resource_names)
            if resources_count > max_autocomplete_resources:
                resource_names = (
                    resource_names[:max_autocomplete_resources])

            resource_names = dict(resource_names)
            resources = env[model].browse(list(resource_names.keys())).mapped(
                'resource_id')

            response.append({
                'resource_type_name': res_type.display_name,
                'resources': [
                    {
                        'value': resource_names.get(res.res_id),
                        'id': res.id,
                    }
                    for res in resources
                ],
                'resources_count': resources_count,
            })
        return response

    @http.route('/crnd_wsd/api/resource_name', type='json',
                auth='public', methods=['POST'])
    def wsd_request_api_get_resource_name(self, **post_data):
        resource_id = post_data.get('resource_id', False)
        if not resource_id:
            return {}

        env = http.request.env(
            context=dict(http.request.env.context,
                         lang=post_data.get('lang', False)))
        resource = env['generic.resource'].browse(resource_id)
        return {'resource_name': resource.display_name}
