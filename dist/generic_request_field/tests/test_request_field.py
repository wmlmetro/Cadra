import logging

from odoo import exceptions
from odoo.tests.common import Form

from .common import TestRequestFieldCase

from ..tools.field_utils import FieldsUIHelper

_logger = logging.getLogger(__name__)

FIELD_NOT_FOUND = 'field not found'


class TestRequestField(TestRequestFieldCase):

    def test_request_field_name_changed(self):
        field = self.env.ref('generic_request_field.request_stage_field_cpu')

        self.assertEqual(field.name, 'CPU')
        self.assertEqual(field.code, 'cpu')

        field.name = 'Field CPU'
        field._onchange_mixin_name_set_code()

        # Ensure field code is not changed for existing record
        self.assertEqual(field.name, 'Field CPU')
        self.assertEqual(field.code, 'cpu')

        # Code have to be automatically generated for new records
        field2 = self.env['request.field'].new({
            'request_type_id': field.request_type_id.id,
            'name': 'My New Field',
        })
        field2._onchange_mixin_name_set_code()
        self.assertEqual(field2.name, 'My New Field')
        self.assertEqual(field2.code, 'my-new-field')

        # Ensure that code is not changed if it was already set
        field2.name = 'My New Field Renamed'
        field2._onchange_mixin_name_set_code()
        self.assertEqual(field2.name, 'My New Field Renamed')
        self.assertEqual(field2.code, 'my-new-field')

    def test_request_field(self):
        Request = self.env['request.request']

        # Create request with simple_type
        request = Request.new({
            'type_id': self.simple_type.id,
            'request_text': 'Request Fields text',
        })

        # Run onchange and see no values generated (simple type have no fields)
        request.onchange_type_id_fields()
        self.assertFalse(request.value_ids)

        # Set type that contains fields
        request.type_id = self.field_type

        # Run onchange and ensure that field values added
        request.onchange_type_id_fields()
        self.assertTrue(request.value_ids)

        # Test that right fields used
        fields = request.value_ids.mapped('field_id.name')
        self.assertEqual(len(request.value_ids), 5)
        self.assertIn('Memory', fields)
        self.assertIn('CPU', fields)
        self.assertIn('HDD', fields)
        self.assertIn('OS', fields)
        self.assertIn('Comment', fields)

        # map values to field codes
        values = {v.field_id.code: v.value for v in request.value_ids}

        # Ensure default values set
        self.assertEqual(values['memory'], '4 GB')
        self.assertFalse(values['cpu'])
        self.assertEqual(values['hdd'], '30 GB')
        self.assertFalse(values['os'])
        self.assertFalse(values['comment'])

    def test_request_field_create_no_val_for_required_field(self):
        with self.assertRaisesRegex(exceptions.ValidationError,
                                    r".*Field CPU is required.*"):
            # Create request with simple_type, but without value for field CPU
            self.env['request.request'].create({
                'type_id': self.field_type.id,
                'request_text': 'Request Fields text',
            })

    def test_request_field_created_with_all_field(self):
        Request = self.env['request.request']

        fields_info = {
            'cpu': '2 core',
            'memory': '6 GB',
            'comment': 'Comment added for testing',
            'hdd': '40 GB',
            'os': 'Ubuntu',
        }
        vals = {
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
            'value_ids': [],
        }

        for f in self.field_type.field_ids:
            field_value = fields_info.get(f.code, False)
            if field_value:
                vals['value_ids'] += [
                    (0, 0, {
                        'field_id': f.id,
                        'value': field_value,
                    })
                ]

        # Create request with field_type
        request = Request.create(vals)
        self.assertTrue(request.value_ids)

        # Test that right fields used
        fields = request.value_ids.mapped('field_id.name')
        self.assertEqual(len(request.value_ids), 5)
        self.assertIn('Memory', fields)
        self.assertIn('CPU', fields)
        self.assertIn('HDD', fields)
        self.assertIn('OS', fields)
        self.assertIn('Comment', fields)

        # map values to field codes
        values = {v.field_id.code: v.value for v in request.value_ids}

        # Ensure default values set
        self.assertEqual(values['memory'], '6 GB')
        self.assertEqual(values['cpu'], '2 core')
        self.assertEqual(values['hdd'], '40 GB')
        self.assertEqual(values['os'], 'Ubuntu')
        self.assertEqual(values['comment'], 'Comment added for testing')

    def test_request_field_created_with_some_field(self):
        Request = self.env['request.request']

        fields_info = {
            'cpu': '2 core',
            'memory': '6 GB',
            'comment': 'Comment added for testing'
        }
        vals = {
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
            'value_ids': [],
        }

        for f in self.field_type.field_ids:
            field_value = fields_info.get(f.code, False)
            if field_value:
                vals['value_ids'] += [
                    (0, 0, {
                        'field_id': f.id,
                        'value': field_value,
                    })
                ]

        # Create request with field_type
        request = Request.create(vals)
        self.assertTrue(request.value_ids)

        # Test that right fields used
        fields = request.value_ids.mapped('field_id.name')
        self.assertEqual(len(request.value_ids), 5)
        self.assertIn('Memory', fields)
        self.assertIn('CPU', fields)
        self.assertIn('HDD', fields)
        self.assertIn('OS', fields)
        self.assertIn('Comment', fields)

        # map values to field codes
        values = {v.field_id.code: v.value for v in request.value_ids}

        # Ensure default values set
        self.assertEqual(values['memory'], '6 GB')
        self.assertEqual(values['cpu'], '2 core')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertFalse(values['os'])
        self.assertEqual(values['comment'], 'Comment added for testing')

    def test_request_get_fields_data(self):
        Request = self.env['request.request']

        # Create request with simple_type
        request = Request.new({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # map values to field codes
        values = request.get_fields_data()

        # Ensure default values set
        self.assertEqual(values['memory'], '4 GB')
        self.assertFalse(values['cpu'])
        self.assertEqual(values['hdd'], '30 GB')
        self.assertFalse(values['os'])
        self.assertFalse(values['comment'])

    def test_request_get_field_value(self):
        Request = self.env['request.request']

        # Create request with simple_type
        request = Request.new({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # Ensure default values set
        self.assertEqual(request.get_field_value('memory'), '4 GB')
        self.assertEqual(request.get_field_value('hdd'), '30 GB')
        self.assertIs(request.get_field_value('cpu'), '')

        # Field is present in request, so event if this field is False return
        # it unchanged
        self.assertIs(request.get_field_value('cpu', 'test'), '')

        # If field is not present in request, return default value for it
        self.assertIs(
            request.get_field_value('unexisting'), None)
        self.assertEqual(
            request.get_field_value('unexisting', 'test'), 'test')

    def test_request_set_field_value_1(self):
        Request = self.env['request.request']

        # Create request with simple_type
        request = Request.new({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # Ensure default values set
        self.assertEqual(request.get_field_value('memory'), '4 GB')
        self.assertEqual(request.get_field_value('hdd'), '30 GB')
        self.assertIs(request.get_field_value('cpu'), '')

        # Try to set value to some field
        request.set_field_value('memory', '1 GB')

        # Check that value was set
        self.assertEqual(request.get_field_value('memory'), '1 GB')

        # Try to set value of unexisting field
        with self.assertRaises(ValueError):
            request.set_field_value('unexisting-field', '42')

    def test_show_data_without_category_in_field(self):
        Request = self.env['request.request']

        # Create request with field_type
        request = Request.new({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # Ensure all fields without category in request
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB')
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('cpu', FIELD_NOT_FOUND), '')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')
        self.assertIs(request.get_field_value(
            'comment', FIELD_NOT_FOUND), '')

    def test_show_data_with_category_in_field(self):
        Request = self.env['request.request']

        # Create request with field_type
        request = Request.new({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # Ensure all fields without category in request
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB')
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('cpu', FIELD_NOT_FOUND), '')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')
        self.assertIs(request.get_field_value(
            'comment', FIELD_NOT_FOUND), '')

        # Add classifiers to type of requests
        self.ensure_classifier(
            category=self.request_category_demo,
            request_type=self.field_type)
        self.ensure_classifier(
            category=self.request_category_demo_technical,
            request_type=self.field_type)

        # Add category to memory field
        self.request_field_memory.write({
            'category_ids': [(4, self.request_category_demo.id)]
        })

        request.onchange_type_id_fields()

        # Ensure all fields without category in request
        # and memory field not in request
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('cpu', FIELD_NOT_FOUND), '')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND),
            FIELD_NOT_FOUND
        )

        # Add category to cpu field
        self.request_field_cpu.write({
            'category_ids': [(4, self.request_category_demo_technical.id)]
        })

        request.onchange_type_id_fields()

        # Ensure all fields without category in request
        # and memory and cpu fields not in request
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')
        self.assertEqual(
            request.get_field_value('cpu', FIELD_NOT_FOUND), FIELD_NOT_FOUND)
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND),
            FIELD_NOT_FOUND
        )

    def test_show_data_with_category_in_field_and_request(self):
        # Add classifiers to type of requests
        self.ensure_classifier(
            category=self.request_category_demo,
            request_type=self.field_type)
        self.ensure_classifier(
            category=self.request_category_demo_technical,
            request_type=self.field_type)

        Request = self.env['request.request']
        # Create request with field_type
        request = Request.new({
            'type_id': self.field_type.id,
            'category_id': self.request_category_demo.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # Ensure all fields without category in request
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB')
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('cpu', FIELD_NOT_FOUND), '')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')

        # Add category to cpu field
        self.request_field_cpu.write({
            'category_ids': [(4, self.request_category_demo_technical.id)]
        })

        request.onchange_type_id_fields()

        # Ensure all fields without category in request
        # and only cpu fields not in request
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')
        self.assertEqual(
            request.get_field_value('cpu', FIELD_NOT_FOUND), FIELD_NOT_FOUND)
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB'
        )

        # Add category to cpu field
        self.request_field_memory.write({
            'category_ids': [(4, self.request_category_demo_technical.id)]
        })

        request.onchange_type_id_fields()

        # Ensure all fields without category in request
        # and memory and cpu fields not in request
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')
        self.assertEqual(
            request.get_field_value('cpu', FIELD_NOT_FOUND), FIELD_NOT_FOUND)
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND),
            FIELD_NOT_FOUND
        )

        # Add category to cpu field
        self.request_field_memory.write({
            'category_ids': [(4, self.request_category_demo.id)]
        })

        request.onchange_type_id_fields()

        # Ensure all fields without category in request
        # and only cpu fields not in request
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')
        self.assertEqual(
            request.get_field_value('cpu', FIELD_NOT_FOUND), FIELD_NOT_FOUND)
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB'
        )

    def test_constrains_category_in_field(self):
        # Add classifiers to type of requests
        self.ensure_classifier(
            category=self.request_category_demo,
            request_type=self.field_type)

        Request = self.env['request.request']
        # Create request with field_type
        request = Request.new({
            'type_id': self.field_type.id,
            'category_id': self.request_category_demo.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # Ensure all fields without category in request
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB')
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('cpu', FIELD_NOT_FOUND), '')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')

        # Ensure ValidationError if add category to memory field
        with self.assertRaises(exceptions.ValidationError):
            self.request_field_memory.write({
                'category_ids': [(4, self.request_category_demo_technical.id)]
            })

        # Unlink category from memory field
        self.request_field_memory.write({'category_ids': [(5, )]})
        self.assertEqual(self.request_field_memory.category_ids.ids, [])

        # Add classifiers to type of requests
        self.ensure_classifier(
            category=self.request_category_demo_technical,
            request_type=self.field_type)

        # Add category to memory field
        self.request_field_memory.write({
            'category_ids': [(4, self.request_category_demo_technical.id)]
        })

        # Ensure the category was added
        self.assertEqual(
            self.request_field_memory.category_ids.ids,
            [self.request_category_demo_technical.id]
        )

    def test_constrains_category_in_request_type(self):
        # Add classifiers to type of requests
        self.ensure_classifier(
            category=self.request_category_demo,
            request_type=self.field_type)
        self.ensure_classifier(
            category=self.request_category_demo_technical,
            request_type=self.field_type)

        Request = self.env['request.request']
        # Create request with field_type
        request = Request.new({
            'type_id': self.field_type.id,
            'category_id': self.request_category_demo.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # Ensure all fields without category in request
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB')
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('cpu', FIELD_NOT_FOUND), '')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')

        # Add categories to memory field
        self.request_field_memory.write({
            'category_ids': [(4, self.request_category_demo_technical.id)]
        })

        with self.assertRaises(exceptions.ValidationError):
            self.field_type.classifier_ids.filtered(
                lambda c: c.category_id == self.request_category_demo_technical
            ).unlink()

    def test_fields_default_jinja_template_onchanges(self):
        self.request_field_comment.default = (
            "Current user's name = {{ current_user.name }}")

        with Form(self.env['request.request']) as request_f:
            request_f.type_id = self.field_type

            fields_top = FieldsUIHelper(self.env).from_json(
                request_f.request_fields_json_top)
            fields_top.set_val(self.request_field_os.id, 'Mint')
            fields_top.set_val(self.request_field_cpu.id, '2 Cores')
            request_f.request_fields_json_top = fields_top.to_json()

            fields_bottom = FieldsUIHelper(self.env).from_json(
                request_f.request_fields_json_bottom)
            self.assertEqual(
                fields_bottom.get_val(self.request_field_comment.id),
                "Current user's name = OdooBot")

            request_f.request_text = "My request"

    def test_fields_default_jinja_template_create(self):
        self.request_field_comment.default = (
            "Current user's name = {{ current_user.name }}")
        self.request_field_cpu.default = (
            "{{ current_user.id }} Cores")

        request = self.env['request.request'].create({
            'type_id': self.field_type.id,
            'request_text': 'Test request',
        })
        self.assertEqual(
            request.get_field_value('cpu'),
            "%s Cores" % self.env.user.id)

        # Note, that this test have to be run with module mail_bot installed,
        # because that module changes the name of base.user_root to OdooBot
        self.assertEqual(
            request.get_field_value('comment'),
            "Current user's name = OdooBot")
