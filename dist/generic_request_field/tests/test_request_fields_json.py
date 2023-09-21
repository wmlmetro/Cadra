import json
import logging

from odoo import exceptions
from odoo.tests.common import Form

from .common import TestRequestFieldCase
from ..tools.field_utils import FieldsUIHelper

_logger = logging.getLogger(__name__)


class TestRequestFieldJSON(TestRequestFieldCase):

    def test_request_field_created_without_onchange(self):
        Request = self.env['request.request']

        # Create request with simple_type
        request = Request.create({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
            'request_field_values_json': json.dumps({
                'cpu': '4',
            }),
        })
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
        self.assertEqual(values['cpu'], '4')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertFalse(values['os'])
        self.assertFalse(values['comment'])

    def test_request_fields_json(self):
        Request = self.env['request.request']

        # Create request with fields type
        request = Request.new({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # map values to field codes
        self.assertTrue(request.request_has_fields_top)
        self.assertTrue(request.request_has_fields_bottom)

        fields_top = json.loads(request.request_fields_json_top)
        fields_bottom = json.loads(request.request_fields_json_bottom)

        # Ensure fields by position 'top'
        self.assertIn(
            str(self.request_field_memory.id), fields_top['fields_info'])
        self.assertIn(
            str(self.request_field_cpu.id), fields_top['fields_info'])
        self.assertIn(
            str(self.request_field_hdd.id), fields_top['fields_info'])
        self.assertIn(
            str(self.request_field_os.id), fields_top['fields_info'])
        self.assertNotIn(
            str(self.request_field_comment.id), fields_top['fields_info'])
        self.assertEqual(
            [str(self.request_field_cpu.id),
             str(self.request_field_memory.id),
             str(self.request_field_hdd.id),
             str(self.request_field_os.id)],
            fields_top['fields_order'])

        # Ensure fields by position 'bottom'
        self.assertNotIn(
            str(self.request_field_memory.id), fields_bottom['fields_info'])
        self.assertNotIn(
            str(self.request_field_cpu.id), fields_bottom['fields_info'])
        self.assertNotIn(
            str(self.request_field_hdd.id), fields_bottom['fields_info'])
        self.assertNotIn(
            str(self.request_field_os.id), fields_bottom['fields_info'])
        self.assertIn(
            str(self.request_field_comment.id), fields_bottom['fields_info'])
        self.assertEqual(
            [str(self.request_field_comment.id)],
            fields_bottom['fields_order'])

        f_info_top = fields_top['fields_info']
        f_info_bottom = fields_bottom['fields_info']
        # Ensure default values are set
        self.assertEqual(
            f_info_top[str(self.request_field_memory.id)]['value'], '4 GB')
        self.assertFalse(
            f_info_top[str(self.request_field_cpu.id)]['value'])
        self.assertEqual(
            f_info_top[str(self.request_field_hdd.id)]['value'], '30 GB')
        self.assertFalse(
            f_info_top[str(self.request_field_os.id)]['value'])
        self.assertFalse(
            f_info_bottom[str(self.request_field_comment.id)]['value'])

        # Change some values
        f_info_top[str(self.request_field_cpu.id)]['value'] = '42'
        f_info_bottom[str(self.request_field_comment.id)]['value'] = 'Hello!'

        # Try to save request:
        request = Request.create({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
            'request_fields_json_top': json.dumps(fields_top),
            'request_fields_json_bottom': json.dumps(fields_bottom),
        })

        # check written values
        values = request.get_fields_data()

        # Ensure default values set
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '42')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertFalse(values['os'])
        self.assertEqual(values['comment'], 'Hello!')

    def test_request_fields_json_validation(self):
        Request = self.env['request.request']

        # Create request with fields type
        request = Request.new({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        fields_top = json.loads(request.request_fields_json_top)
        fields_bottom = json.loads(request.request_fields_json_bottom)
        f_info_bottom = fields_bottom['fields_info']

        # Change some values
        f_info_bottom[str(self.request_field_comment.id)]['value'] = 'Hello!'

        # Try to create request without value for CPU
        with self.assertRaises(exceptions.ValidationError):
            Request.create({
                'type_id': self.field_type.id,
                'request_text': 'Request Fields text',
                'request_fields_json_top': json.dumps(fields_top),
                'request_fields_json_bottom': json.dumps(fields_bottom),
            })

    def test_request_fields_json_validation_categ(self):
        Request = self.env['request.request']

        # Add classifiers to type of requests
        self.ensure_classifier(
            category=self.request_category_demo,
            request_type=self.field_type)

        self.request_field_cpu.category_ids = self.request_category_demo
        self.assertTrue(self.request_field_cpu.mandatory)

        # Create request with fields type
        request = Request.new({
            'type_id': self.field_type.id,
            'category_id': self.request_category_demo_technical,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        fields_top = json.loads(request.request_fields_json_top)
        fields_bottom = json.loads(request.request_fields_json_bottom)
        f_info_bottom = fields_bottom['fields_info']

        # Change some values
        f_info_bottom[str(self.request_field_comment.id)]['value'] = 'Hello!'

        # Try to create request without value for CPU,
        # because it is required in other category.
        # So, there is no error expected
        request = Request.create({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
            'request_fields_json_top': json.dumps(fields_top),
            'request_fields_json_bottom': json.dumps(fields_bottom),
        })

        # check written values
        values = request.get_fields_data()

        # Check that 'cpu' is not in values
        self.assertNotIn('cpu', values)

        # Ensure default values set
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertFalse(values['os'])

    def test_request_field_values_json__write(self):
        request = self.env['request.request'].create({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
            'request_field_values_json': json.dumps({
                'cpu': '4 cores',
            }),
        })

        # map values to field codes
        values = request.get_fields_data()

        # Ensure default values set
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '4 cores')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertFalse(values['os'])
        self.assertFalse(values['comment'])

        # Try to update request fields via json
        request.request_field_values_json = json.dumps({
            'cpu': '2 cores',
            'os': 'Ubuntu',
        })

        values = request.get_fields_data()
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '2 cores')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertEqual(values['os'], 'Ubuntu')
        self.assertFalse(values['comment'])

        # Try to update request fields via json using write
        request.write({
            'request_field_values_json': json.dumps({
                'cpu': '2 cores',
                'os': 'Mint',
            }),
        })

        values = request.get_fields_data()
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '2 cores')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertEqual(values['os'], 'Mint')
        self.assertFalse(values['comment'])

        # Try to write empty value to request_field_values_json
        request.request_field_values_json = json.dumps({})
        values = request.get_fields_data()
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '2 cores')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertEqual(values['os'], 'Mint')
        self.assertFalse(values['comment'])

        # Try to write False to request_field_values_json
        request.request_field_values_json = False
        values = request.get_fields_data()
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '2 cores')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertEqual(values['os'], 'Mint')
        self.assertFalse(values['comment'])

        # Try to set required field to False, and expect error
        self.assertTrue(self.request_field_hdd.mandatory, False)
        with self.assertRaisesRegex(exceptions.ValidationError,
                                    r".*Field HDD is required.*"):
            request.request_field_values_json = json.dumps({
                'hdd': False,
            })

    def test_request_field_values_json__read(self):
        request = self.env['request.request'].create({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
            'request_field_values_json': json.dumps({
                'cpu': '4 cores',
            }),
        })

        values = json.loads(request.request_field_values_json)
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '4 cores')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertFalse(values['os'])
        self.assertFalse(values['comment'])

        # Try to update request fields via json
        request.request_field_values_json = json.dumps({
            'cpu': '2 cores',
            'os': 'Ubuntu',
        })

        values = json.loads(request.request_field_values_json)
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '2 cores')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertEqual(values['os'], 'Ubuntu')
        self.assertFalse(values['comment'])

    def test_fields_change_category(self):
        # pylint: disable=too-many-statements
        category1 = self.env['request.category'].create({
            'name': 'Test Categ 1',
            'code': 'test-f-categ-1',
        })
        category2 = self.env['request.category'].create({
            'name': 'Test Categ 2',
            'code': 'test-f-categ-2',
        })

        # Add classifiers to type of requests
        self.ensure_classifier(
            category=category1,
            request_type=self.field_type)
        self.ensure_classifier(
            category=category2,
            request_type=self.field_type)
        self.request_field_cpu.write({
            'category_ids': [(6, 0, (category1.id, category2.id))],
        })
        f_request = Form(self.env['request.request'])
        f_request.type_id = self.field_type

        fields_top = json.loads(f_request.request_fields_json_top)
        fields_info = fields_top['fields_info']

        # Ensure fields by position 'top' displayed on the form
        self.assertIn(str(self.request_field_memory.id), fields_info)
        self.assertNotIn(str(self.request_field_cpu.id), fields_info)
        self.assertIn(str(self.request_field_hdd.id), fields_info)
        self.assertIn(str(self.request_field_os.id), fields_info)
        self.assertNotIn(str(self.request_field_comment.id), fields_info)
        self.assertEqual(
            [str(self.request_field_memory.id),
             str(self.request_field_hdd.id),
             str(self.request_field_os.id)],
            fields_top['fields_order'])

        # Ensure default values are set for the fields
        self.assertEqual(
            fields_info[str(self.request_field_memory.id)]['value'], '4 GB')
        self.assertEqual(
            fields_info[str(self.request_field_hdd.id)]['value'], '30 GB')
        self.assertFalse(
            fields_info[str(self.request_field_os.id)]['value'])

        # Change request category to that one that has field 'cpu'
        f_request.category_id = category1

        fields_top = json.loads(f_request.request_fields_json_top)
        fields_info = fields_top['fields_info']

        # Ensure fields by position 'top' displayed on the form
        self.assertIn(str(self.request_field_memory.id), fields_info)
        self.assertIn(str(self.request_field_cpu.id), fields_info)
        self.assertIn(str(self.request_field_hdd.id), fields_info)
        self.assertIn(str(self.request_field_os.id), fields_info)
        self.assertNotIn(str(self.request_field_comment.id), fields_info)
        self.assertEqual(
            [str(self.request_field_cpu.id),
             str(self.request_field_memory.id),
             str(self.request_field_hdd.id),
             str(self.request_field_os.id)],
            fields_top['fields_order'])

        # Ensure default values are set for the fields
        self.assertEqual(
            fields_info[str(self.request_field_memory.id)]['value'], '4 GB')
        self.assertFalse(
            fields_info[str(self.request_field_cpu.id)]['value'])
        self.assertEqual(
            fields_info[str(self.request_field_hdd.id)]['value'], '30 GB')
        self.assertFalse(
            fields_info[str(self.request_field_os.id)]['value'])

        # Set value for the CPU field
        fields_top['fields_info'][str(self.request_field_cpu.id)]['value'] = (
            '4 Cores')
        fields_top['fields_info'][str(self.request_field_hdd.id)]['value'] = (
            '60 GB')
        f_request.request_fields_json_top = json.dumps(fields_top)

        # Check that field's value updated
        fields_top = json.loads(f_request.request_fields_json_top)
        fields_info = fields_top['fields_info']

        # Ensure fields by position 'top' displayed on the form
        self.assertIn(str(self.request_field_memory.id), fields_info)
        self.assertIn(str(self.request_field_cpu.id), fields_info)
        self.assertIn(str(self.request_field_hdd.id), fields_info)
        self.assertIn(str(self.request_field_os.id), fields_info)
        self.assertNotIn(str(self.request_field_comment.id), fields_info)
        self.assertEqual(
            [str(self.request_field_cpu.id),
             str(self.request_field_memory.id),
             str(self.request_field_hdd.id),
             str(self.request_field_os.id)],
            fields_top['fields_order'])

        # Ensure default values are set for the fields
        self.assertEqual(
            fields_info[str(self.request_field_memory.id)]['value'], '4 GB')
        self.assertEqual(
            fields_info[str(self.request_field_cpu.id)]['value'], '4 Cores')
        self.assertEqual(
            fields_info[str(self.request_field_hdd.id)]['value'], '60 GB')
        self.assertFalse(
            fields_info[str(self.request_field_os.id)]['value'])

        # Change request category to another one that has field 'cpu'
        f_request.category_id = category2

        # Check that field's value for CPU field kept unchanged
        fields_top = json.loads(f_request.request_fields_json_top)
        fields_info = fields_top['fields_info']

        # Ensure fields by position 'top' displayed on the form
        self.assertIn(str(self.request_field_memory.id), fields_info)
        self.assertIn(str(self.request_field_cpu.id), fields_info)
        self.assertIn(str(self.request_field_hdd.id), fields_info)
        self.assertIn(str(self.request_field_os.id), fields_info)
        self.assertNotIn(str(self.request_field_comment.id), fields_info)
        self.assertEqual(
            [str(self.request_field_cpu.id),
             str(self.request_field_memory.id),
             str(self.request_field_hdd.id),
             str(self.request_field_os.id)],
            fields_top['fields_order'])

        # Ensure default values are set for the fields
        self.assertEqual(
            fields_info[str(self.request_field_memory.id)]['value'], '4 GB')
        self.assertEqual(
            fields_info[str(self.request_field_cpu.id)]['value'], '4 Cores')
        self.assertEqual(
            fields_info[str(self.request_field_hdd.id)]['value'], '60 GB')
        self.assertFalse(
            fields_info[str(self.request_field_os.id)]['value'])

        # Save request
        f_request.request_text = "<p>Hello World!</p>"
        request = f_request.save()

        # Check created request's fields values
        values = request.get_fields_data()
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '4 Cores')
        self.assertEqual(values['hdd'], '60 GB')
        self.assertFalse(values['os'])
        self.assertFalse(values['comment'])

        # Prepare request update form
        f_request = Form(request)

        # Set value for the OS field
        fields_top = FieldsUIHelper(self.env).from_json(
            f_request.request_fields_json_top)
        fields_top.set_val(self.request_field_os.id, 'Mint')
        fields_top.set_val(self.request_field_cpu.id, '2 Cores')
        f_request.request_fields_json_top = fields_top.to_json()

        # Set value for the Comment field
        fields_bottom = FieldsUIHelper(self.env).from_json(
            f_request.request_fields_json_bottom)
        fields_bottom.set_val(self.request_field_comment.id, 'Test Comment')
        f_request.request_fields_json_bottom = fields_bottom.to_json()

        # Save request form
        f_request.save()

        # Check request values
        values = request.get_fields_data()
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '2 Cores')
        self.assertEqual(values['hdd'], '60 GB')
        self.assertEqual(values['os'], 'Mint')
        self.assertEqual(values['comment'], 'Test Comment')

    def test_fields_json_top_bottom_create_write(self):
        request_new = self.env['request.request'].new({
            'type_id': self.field_type.id,
            'category_id': self.request_category_demo_technical.id,
        })
        fields_top = FieldsUIHelper(self.env).from_fields(
            request_new._request_fields__get_fields(position='before')
        )
        fields_top.set_val(self.request_field_cpu.id, '3 Cores')
        request = self.env['request.request'].create({
            'type_id': self.field_type.id,
            'category_id': self.request_category_demo_technical.id,
            'request_fields_json_top': fields_top.to_json(),
            'request_text': 'Test Request',
        })
        values = request.get_fields_data()
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '3 Cores')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertFalse(values['os'])
        self.assertFalse(values['comment'])

        # Update only bottom fields (comment)
        fields_bottom = FieldsUIHelper(self.env).from_json(
            request.request_fields_json_bottom)
        fields_bottom.set_val(self.request_field_comment.id, 'Test Comment')
        request.request_fields_json_bottom = fields_bottom.to_json()

        # Check that only request comment updated
        values = request.get_fields_data()
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '3 Cores')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertFalse(values['os'])
        self.assertEqual(values['comment'], 'Test Comment')

    def test_fields_json_top_create_no_val_for_cpu(self):
        request_new = self.env['request.request'].new({
            'type_id': self.field_type.id,
            'category_id': self.request_category_demo_technical.id,
        })
        fields_top = FieldsUIHelper(self.env).from_fields(
            request_new._request_fields__get_fields(position='before')
        )
        with self.assertRaisesRegex(exceptions.ValidationError,
                                    r".*Field CPU is required.*"):
            self.env['request.request'].create({
                'type_id': self.field_type.id,
                'category_id': self.request_category_demo_technical.id,
                'request_fields_json_top': fields_top.to_json(),
                'request_text': 'Test Request',
            })

    def test_fields_json_bottom_create_no_val_for_cpu(self):
        request_new = self.env['request.request'].new({
            'type_id': self.field_type.id,
            'category_id': self.request_category_demo_technical.id,
        })
        fields_bottom = FieldsUIHelper(self.env).from_fields(
            request_new._request_fields__get_fields(position='after')
        )
        with self.assertRaisesRegex(exceptions.ValidationError,
                                    r".*Field CPU is required.*"):
            self.env['request.request'].create({
                'type_id': self.field_type.id,
                'category_id': self.request_category_demo_technical.id,
                'request_fields_json_bottom': fields_bottom.to_json(),
                'request_text': 'Test Request',
            })
