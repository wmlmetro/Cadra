import json
import logging

_logger = logging.getLogger(__name__)


class FieldsUIHelper:
    """ Helper class to simplify operations with json fields (top and bottom)
        in onchange, inverse and tests.

        This class can handle data-structure for request_fields js widget
        and convert it from and to different formats.

        :param env: Environment to bind instance of this class to
    """
    def __init__(self, env):
        self._env = env
        self._fields_data = None

    @property
    def env(self):
        return self._env

    @property
    def fields_data(self):
        """ Represents fields data for this helper.

            Data format:
                {
                    'fields_info': {
                        int(field_id): {
                            'name': str,
                            'code': str,
                            'mandatory': bool,
                            'default': str,
                            'sequence': int,
                            'position': str('before', 'after'),
                            'value': str,
                            'field_id': int,
                            'grid_classes': str(default='col-md-4'),
                            'help': str,
                            'placeholder': str,
                        },
                    },
                    'fields_order': [int(field_id), int(field_id), ...],
                }

            :rtype: dict
        """
        if self._fields_data is None:
            raise Exception("Fields data is not initialized yet")
        return self._fields_data

    @property
    def fields_info(self):
        """ Returns only info about fields.

            Following format of data used:

                {
                    int(field_id): {
                        'name': str,
                        'code': str,
                        'mandatory': bool,
                        'default': str,
                        'sequence': int,
                        'position': str('before', 'after'),
                        'value': str,
                        'field_id': int,
                        'grid_classes': str(default='col-md-4'),
                        'help': str,
                        'placeholder': str,
                    },
                }

            :rtype: dict
        """
        return self.fields_data['fields_info']

    @property
    def field_ids(self):
        """ Return tuple of field ids present in this helper
        """
        return tuple(self.fields_info.keys())

    @property
    def fields_order(self):
        """ Return list of ids of fields ordered by 'sequence'

            :rtype list[int]:
        """
        return [
            f.id
            for f in self.env['request.field'].browse(
                self.field_ids).sorted()
        ]

    @property
    def fields_values(self):
        """ Return mapping field_id: field_value

            :rtype: dict
        """
        return {
            field_id: field_info['value']
            for field_id, field_info in self.fields_info.items()
        }

    def add_field(self, field_id, value=None):
        """ Add new field, possibly with provided value

            :param int field_id: ID of request.field to add
            :param str value: Value of the field to assign
        """
        field = self.env['request.field'].browse(field_id)
        self.fields_info[field_id] = field._get_request_field_info(value=value)

    def del_field(self, field_id):
        """ Remove field.

            :param int field_id: ID of request.field to remove
        """
        del self.fields_info[field_id]

    def has_field(self, field_id):
        """ Check if field is present in this instance of helper

            :param int field_id: ID of request.field to remove
        """
        return field_id in self.fields_info

    def get_val(self, field_id):
        """ Return value for this specified field

            :param int field_id: ID of request.field to remove
        """
        return self.fields_info[field_id]['value']

    def set_val(self, field_id, value):
        """ Set value for specified field

            :param int field_id: ID of request.field to remove
            :param str value: Value to set for the field
        """
        if not self.has_field(field_id):
            self.add_field(field_id, value=value)
        else:
            self.fields_info[field_id]['value'] = value

    def enforce_fields(self, fields, custom_defaults=None):
        """ Ensure that only fields mentioned in param present in current
            instance of this helper. Also, add new fields with default values
            if needed.

            :param fields: recordset of fields,
                 to update this helper instance with.
            :param dict custom_defaults: Dict with custom default values
                 for fields.
                 Dict mapping: {field_id: default_value}
                 Or dict mapping: {field_code: default_value}
        """
        if custom_defaults is None:
            custom_defaults = {}
        for field_id in self.field_ids:
            if field_id not in fields.ids:
                self.del_field(field_id)
        for field in fields:
            if not self.has_field(field.id):
                # Try to get default value by field.id
                value = custom_defaults.get(field.id)
                if value is None:
                    value = custom_defaults.get(field.code)
                self.add_field(field.id, value=value)

    def initialize_as_empty(self):
        """ Initialize helper with empty values
        """
        self._fields_data = {
            'fields_info': {},
            'fields_order': [],
        }

    def from_json(self, values_json):
        """ Initialize helper from json values provided.
            The format of json values must be same as for request_field
            js widget.

            Expected format of values_json:

                {
                    'fields_info': {
                        'field_id': {
                            'name': str,
                            'code': str,
                            'mandatory': bool,
                            'default': str,
                            'sequence': int,
                            'position': str('before', 'after'),
                            'value': str,
                            'field_id': int,
                            'grid_classes': str(default='col-md-4'),
                            'help': str,
                            'placeholder': str,
                        },
                    },
                    'fields_order': ['field_id', 'field_id', ...],
                }

            :param str values_json: JSON data to initialize helper from
            :return: self
        """
        if values_json:
            json_data = json.loads(values_json)
            if 'fields_info' in json_data:
                self._fields_data = {
                    'fields_info': {
                        int(k): v for k, v in json_data['fields_info'].items()
                    },
                }
            else:
                self.initialize_as_empty()
        else:
            self.initialize_as_empty()
        return self

    def from_fields(self, req_fields):
        """ Initialize from fields with default values

            :param Recordset req_fields: recordset with request fields to
                initialize helper from
            :return: self
        """
        self._fields_data = {
            'fields_info': {
                f.id: f._get_request_field_info() for f in req_fields
            }
        }
        return self

    def to_json(self):
        """ Convert data managed by this helper to json format
            suitable to use to write to request_fields_json_top and
            request_fields_json_bottom or to js widget for these fields.
        """
        return json.dumps({
            'fields_info': {
                str(k): v for k, v in self.fields_info.items()
            },
            'fields_order': [str(f) for f in self.fields_order],
        })

    def to_values(self):
        """ Convert data managed by this helper to
            recordset of request.field.value
            that will be suitable to write (via assignment (=)) to 'value_ids'
            field of request.

            The result is Recordset that contains request.field.value records
            created via 'new' method.
        """
        values = self.env['request.field.value'].browse()
        for field_id, value in self.fields_values.items():
            values += self.env['request.field.value'].new({
                'field_id': field_id,
                'value': value,
            })
        return values

    def to_values_wizard(self):
        """ Convert data managed by this helper to
            recordset of request.wizard.close.field.value
            that will be suitable to write (via assignment (=)) to 'value_ids'
            field of request.wizard.close.

            The result is Recordset that contains
            request.wizard.close.field.value records
            created via 'new' method.
        """
        values = self.env['request.wizard.close.field.value'].browse()
        for field_id, value in self.fields_values.items():
            values += self.env['request.wizard.close.field.value'].new({
                'field_id': field_id,
                'value': value,
            })
        return values
