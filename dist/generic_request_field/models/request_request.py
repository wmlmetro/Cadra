import json
import logging

from odoo import models, fields, api, exceptions, _

from ..tools.field_utils import FieldsUIHelper

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = "request.request"

    value_ids = fields.One2many(
        'request.field.value', 'request_id', string='Values',
        readonly=True, copy=False)

    request_field_values_json = fields.Text(
        compute="_compute_request_values_json",
        inverse="_inverse_request_values_json",
        copy=True,
        help="Technical field, that could be used to update request "
             "field values via json string. This field can handle "
             "json encoded dict where keys are codes of the request fields.")

    # Technical fields used to display values in user-friendly way
    request_fields_json_top = fields.Text(
        "Fields Info (JSON) [TOP]",
        compute='_compute_request_fields_json',
        inverse='_inverse_request_fields_json')
    request_fields_json_bottom = fields.Text(
        "Fields Info (JSON) [BOTTOM]",
        compute='_compute_request_fields_json',
        inverse='_inverse_request_fields_json')
    request_has_fields_top = fields.Boolean(
        compute='_compute_request_fields_json', readonly=True)
    request_has_fields_bottom = fields.Boolean(
        compute='_compute_request_fields_json', readonly=True)

    @api.depends('value_ids')
    def _compute_request_values_json(self):
        for record in self:
            record.request_field_values_json = json.dumps({
                v.field_id.code: v.value for v in record.value_ids
            })

    def _inverse_request_values_json(self):
        RequestFieldValue = self.env['request.field.value']
        for record in self:
            # mapping of values to field_id
            # {field_id: value(str)}
            values_map = record._request_fields__parse_json_field_values()

            # Resulting values
            # {field_id: value(record)}
            # Here we create mapping to existing records (field value)
            res_values = {
                val.field_id.id: val for val in record.value_ids
            }

            # Generate recordset to with values for this request.
            # Reuse existing values if they are already exists
            values = RequestFieldValue.browse([])
            for field_id, value in values_map.items():
                if field_id in res_values:
                    res_values[field_id].value = value
                else:
                    res_values[field_id] = RequestFieldValue.new({
                        'field_id': field_id,
                        'value': value,
                    })
                values += res_values[field_id]

            record.value_ids = values

    @api.depends('value_ids')
    def _compute_request_fields_json(self):
        for record in self:
            values_top = record.value_ids.filtered(
                lambda r: r.field_id.position == 'before')
            values_bottom = record.value_ids.filtered(
                lambda r: r.field_id.position == 'after')
            record.request_fields_json_top = json.dumps(
                values_top.convert_to_fields_info())
            record.request_fields_json_bottom = json.dumps(
                values_bottom.convert_to_fields_info())
            record.request_has_fields_top = bool(values_top)
            record.request_has_fields_bottom = bool(values_bottom)

    def _inverse_request_fields_json(self):
        """ Handle writes in `request_fields_json_top` and
            `request_fields_json_bottom`.

            This method updates 'value_ids' from json UI fields
        """
        for record in self:
            fields_top = FieldsUIHelper(self.env)
            fields_top.from_json(record.request_fields_json_top)
            fields_top.enforce_fields(
                record._request_fields__get_fields(position='before'))

            fields_bottom = FieldsUIHelper(self.env)
            fields_bottom.from_json(record.request_fields_json_bottom)
            fields_bottom.enforce_fields(
                record._request_fields__get_fields(position='after'))

            values = self.env['request.field.value'].browse([])
            values += fields_top.to_values()
            values += fields_bottom.to_values()
            record.value_ids = values

    @api.constrains('value_ids')
    def _constraint_validate_value_ids(self):
        if self.env.context.get("_request_field__no_validate_values"):
            # Request fields validation could be disabled via context switch
            return
        for record in self:
            # TODO: Add ability to disable check via flag in context
            errors = record.value_ids.validate_values()
            if errors:
                msg = ""
                for err in errors.values():
                    msg += "- %s\n" % err
                raise exceptions.ValidationError(_(
                    "There is following errors in request fields:\n"
                    "%(error_msg)s"
                ) % {'error_msg': msg})

    def _request_fields__get_fields(self, position=None):
        """ Return request fields for request

            :param str position': Return only fields for specific position.
                Possible values are: 'before' and 'after'
            :return RecordSet: fields that have to be displayed for request
        """
        if not self.type_id:
            return self.env['request.field'].browse()
        request_fields = self.type_id.field_ids.filtered(
            lambda f:
                not f.category_ids or self.category_id in f.category_ids)
        if position is not None:
            request_fields = request_fields.filtered(
                lambda f: f.position == position)
        return request_fields

    def _request_fields__parse_json_field_values(self):
        """ This method have to be used to parse field values from json,
            and return dictionary with mapping field_id to field value
            from json data.

            This method will not process default values,
            so if only value for single field will be provided,
            then only this value will be in resulting dict.

            But, this method takes into account the `value_ids` field.

            :return dict: mapping of format {field_id: field_value}
        """
        self.ensure_one()
        request_fields = self._request_fields__get_fields()
        fields_map = {f.code: f for f in request_fields}

        # {field_id: value}
        values_map = {
            val.field_id.id: val.value for val in self.value_ids
        }

        # Parse json data
        json_values = self.request_field_values_json
        if json_values and isinstance(json_values, str):
            data = json.loads(self.request_field_values_json)
            if not isinstance(data, dict):
                raise exceptions.ValidationError(_(
                    "Incorrect format of request_field_values_json. "
                    "Expected json-encoded dict, got: %(data_type)s"
                ) % type(data))

        elif json_values:
            raise exceptions.ValidationError(_(
                "Field request_field_values_json supports only str "
                "with encoded json or python dict as possible values"
            ))
        else:
            data = {}

        # Update values_map from json
        for code, value in data.items():
            if code not in fields_map:
                # Ignore values if it is not related to request's field
                continue
            values_map[fields_map[code].id] = value

        return values_map

    def _create_update_from_type(self, r_type, vals):
        res = super()._create_update_from_type(r_type, vals)
        # Add field values to request if needed
        if not r_type.field_ids:
            return res

        if (vals.get('request_fields_json_top') or
                vals.get('request_fields_json_bottom')):
            # It seems that it is attempt to create request from UI, thus
            # we do not need to add any pre-processing to set default values
            # for request fields.
            return res

        # Here we have to preprocess fields data to automatically add default
        # values for fields (or at least field values with empty vals)
        # Also, we have to take into account field values provided via
        # request_field_values_json field
        request_new = self.new(res)

        # Compute current values map based on
        # value_ids and request_field_values_json fields.
        # As result of method below we will get mapping of values to field_id
        # {field_id: value(str)}
        values_map = request_new._request_fields__parse_json_field_values()

        # Update value_ids with default values if needed
        res['value_ids'] = [
            (0, 0, {
                'field_id': field.id,
                'value': values_map.get(field.id, field._get_default_value()),
            })
            for field in request_new._request_fields__get_fields()
        ]
        return res

    @api.returns(None, lambda value: value[0])
    def copy_data(self, default=None):
        # Here we override copy_data method to be able to copy request fields
        # by field code, on copy of request.
        # The idea is following:
        # when we copy request, the in new request we would like to have
        # field values for fields with same code from previous request.
        # For example:
        # - We have request (request1) with:
        #     - fields: memory = 24, cpu = 2 core, name = 42
        #     - type: type 1
        # - We have request type: type 2
        #     - with fields: memory, cpu, container-name
        # - When we copy request1 with overwrite of type to 'type 2',
        #   we would like to copy as much data from original request
        #   as possible.
        # - Thus we expect copied request (request2) will have following:
        #     - type: type 2
        #     - fields: memory = 24, cpu = 2 core, container-name = ''
        # - To make this possible, the field 'request_field_values_json'
        #   has 'copy=True' attribute, thus, this field always will be provided
        #   to this method.
        self.ensure_one()
        if not default:
            return super().copy_data(default=default)

        # If one of json UI fields provided, then we do not need to copy
        # values via json field, because UI fields have higher priority.
        # In this case, 'value_ids' will be computed via inverse methods of
        # UI fields.
        copy_via_json = True
        if default.get('request_fields_json_top'):
            copy_via_json = False
        if default.get('request_fields_json_bottom'):
            copy_via_json = False

        # Also, if 'value_ids' provided, then we have to ignore
        # 'request_field_values_json' field
        # (ir will be recomputed based on values)
        if default.get('value_ids'):
            copy_via_json = False

        if copy_via_json and default.get('request_field_values_json'):
            # If copy of values via json is enabled
            # (no ui fields nor value_ids provided)
            # and request_field_values_json provided, then we have to copy
            # values from provided data.
            default = dict(default)
            new_json_vals = json.loads(self.request_field_values_json)
            new_json_vals.update(json.loads(
                default['request_field_values_json']))
            default['request_field_values_json'] = json.dumps(new_json_vals)
        elif not copy_via_json:
            # If we have one of other fields for values, then we have to
            # override 'request_field_values_json' with empty dict
            # to avoid rewrite of values provided by that fields
            # (UI json fields or value_ids).
            default = dict(default)
            default['request_field_values_json'] = json.dumps({})
        return super().copy_data(default=default)

    @api.onchange('type_id', 'category_id',
                  'request_fields_json_top', 'request_fields_json_bottom')
    def onchange_type_id_fields(self):
        for record in self:
            fields_top = FieldsUIHelper(self.env)
            fields_top.from_json(record.request_fields_json_top)
            fields_top.enforce_fields(
                record._request_fields__get_fields(position='before'))

            fields_bottom = FieldsUIHelper(self.env)
            fields_bottom.from_json(record.request_fields_json_bottom)
            fields_bottom.enforce_fields(
                record._request_fields__get_fields(position='after'))

            values = self.env['request.field.value'].browse([])
            values += fields_top.to_values()
            values += fields_bottom.to_values()
            record.value_ids = values

    def get_field_value(self, field_name, default=None):
        """ Get value for specified field.
            If no such field found - return default

            :param str field_name: name of field to get value for
            :param str default: default value to return
                 if there is no such field in request
            :return str: value of the field, or default value
        """
        self.ensure_one()
        for v in self.value_ids:
            if v.field_id.code == field_name:
                return v.value
        return default

    def set_field_value(self, field_name, value):
        """ Set value for request field by field's code

            :param str field_name: code of request's field to set value for
            :param str value: the value to set for the field
            :raises ValueError: if there is no such field in request
        """
        self.ensure_one()
        for v in self.value_ids:
            if v.field_id.code == field_name:
                v.value = value
                return

        raise ValueError(
            "There is no field named %s in request %s"
            "" % (field_name, self.name)
        )

    def get_fields_data(self):
        """ Return dictionary with mapping field_code: field_value

            :rtype: dict
        """
        self.ensure_one()
        # TODO: implement some sort of caching as dictionary
        return {v.field_id.code: v.value for v in self.value_ids}

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        # We have to disable fields validation on requests created via email
        # TODO: Implement some kind of defaults values
        #       for fields for request creation templates
        return super(
            RequestRequest,
            self.with_context(_request_field__no_validate_values=True)
        ).message_new(msg_dict, custom_values=custom_values)
