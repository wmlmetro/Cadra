import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)


class RequestAPIEndpoint(models.Model):
    _inherit = "request.api.endpoint"

    field_map_ids = fields.One2many(
        'request.api.endpoint.field.map',
        'endpoint_id', string="Fields Map")

    def _prepare_request_data(self, data):
        res = super(RequestAPIEndpoint, self)._prepare_request_data(data)

        values = res['value_ids'] = []
        for f_map in self.field_map_ids:
            value = data.pop(f_map.data_field, f_map.default_value)
            values.append((0, 0, {
                'field_id': f_map.field_id.id,
                'value': value,
            }))
        return res

    # --------------
    # REST API Logic
    # --------------
    def _rest_prepare_request_info(self, request):
        res = super()._rest_prepare_request_info(request)
        fields_data = request.get_fields_data()
        if fields_data:
            res['data'] = fields_data
        return res

    def _rest_parse_data__data(self, operation, fields_info, request=None):
        res = {'value_ids': []}
        if operation == 'update' and request:
            for v in request.value_ids:
                if v.field_id.code in fields_info:
                    res['value_ids'] += [
                        (1, v.id, {
                            'value': fields_info[v.field_id.code]})
                    ]
        elif operation == 'create':
            for f in self.request_type_id.field_ids:
                field_value = fields_info.get(f.code, False)
                if field_value:
                    res['value_ids'] += [
                        (0, 0, {
                            'field_id': f.id,
                            'value': field_value,
                        })
                    ]
        return res

    def _rest_parse_data(self, operation, data, request=None):
        res = super()._rest_parse_data(operation, data, request=request)
        if data.get('data'):
            res.update(self._rest_parse_data__data(
                operation, data['data'], request=request))
        return res

    ################
    # Docs Section #
    ################
    def _get_data_api_fields(self):
        request_type_id = self.request_creation_template_id.request_type_id
        request_fields = request_type_id._get_request_fields({})
        res = {}
        if not request_fields:
            return res
        for f in request_fields:
            if f.mandatory:
                field_description = '%s (mandatory)' % f.name
            else:
                field_description = '%s (optional)' % f.name
            res.update({f.code: field_description})
        return res

    # POST
    def _api_help_post_request_json(self):
        res = super(RequestAPIEndpoint, self)._api_help_post_request_json()
        data = self._get_data_api_fields()
        if not data:
            return res

        res.update({
            'data': data
        })
        return res

    # GET
    def _api_help_get_response_json(self):
        res = super(RequestAPIEndpoint, self)._api_help_get_response_json()
        data = self._get_data_api_fields()
        if not data:
            return res
        res['request'].update({
            'data': data
        })
        return res

    # PUT
    def _api_help_put_request_json(self):
        res = super(RequestAPIEndpoint, self)._api_help_put_request_json()
        data = self._get_data_api_fields()
        if not data:
            return res
        res.update({
            'data': data
        })
        return res
