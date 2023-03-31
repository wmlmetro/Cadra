import json
import logging

from .common import TestRequestFieldCase

_logger = logging.getLogger(__name__)


class TestRequestFieldCopy(TestRequestFieldCase):

    # @classmethod
    # def setUpClass(cls):
    #     super(TestRequestFieldCopy, cls).setUpClass()

    def test_request_copy_with_fields(self):
        Request = self.env['request.request']

        # Create request with simple_type
        request = Request.create({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
            'request_field_values_json': json.dumps({
                'cpu': '4 Cores',
                'os': 'Mint',
            }),
        })

        values = request.get_fields_data()
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '4 Cores')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertEqual(values['os'], 'Mint')
        self.assertFalse(values['comment'])

        request2 = request.copy()

        self.assertNotEqual(request, request2)

        # Check values of Request 2
        values = request2.get_fields_data()
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '4 Cores')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertEqual(values['os'], 'Mint')
        self.assertFalse(values['comment'])

        request3 = request.copy({
            'request_field_values_json': json.dumps({
                'os': 'Ubuntu',
            }),
        })

        # Check values of Request 3
        values = request3.get_fields_data()
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '4 Cores')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertEqual(values['os'], 'Ubuntu')
        self.assertFalse(values['comment'])

    def test_copy_request_field_change_type(self):
        new_request_type = self.env['request.type'].with_context(
            create_default_stages=True,
        ).create({
            'name': 'Test Request Copy Fields',
            'code': 'test-request-copy',
            'field_ids': [
                (0, 0, {
                    'name': 'Memory',
                    'code': 'memory',
                    'default': '1 GB',
                }),
                (0, 0, {
                    'name': 'CPU',
                    'code': 'cpu',
                }),
                (0, 0, {
                    'name': 'Platform',
                    'code': 'platform',
                    'default': 'linux',
                })
            ]
        })

        # Create request with simple_type
        request = self.env['request.request'].create({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
            'request_field_values_json': json.dumps({
                'cpu': '4 Cores',
                'os': 'Mint',
            }),
        })

        values = request.get_fields_data()
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '4 Cores')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertEqual(values['os'], 'Mint')
        self.assertFalse(values['comment'])

        request2 = request.copy({
            'type_id': new_request_type.id,
        })

        values = request2.get_fields_data()
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '4 Cores')
        self.assertEqual(values['platform'], 'linux')
        self.assertNotIn('hdd', values)
        self.assertNotIn('os', values)
        self.assertNotIn('comment', values)

        request3 = request.copy({
            'type_id': new_request_type.id,
            'request_field_values_json': json.dumps({
                'platform': 'Windows',
                'memory': '2 GB',
            }),
        })

        values = request3.get_fields_data()
        self.assertEqual(values['memory'], '2 GB')
        self.assertEqual(values['cpu'], '4 Cores')
        self.assertEqual(values['platform'], 'Windows')
        self.assertNotIn('hdd', values)
        self.assertNotIn('os', values)
        self.assertNotIn('comment', values)
