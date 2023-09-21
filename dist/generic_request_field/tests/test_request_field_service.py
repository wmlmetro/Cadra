import logging

from odoo.exceptions import ValidationError
from odoo.addons.generic_request_field.tests.common import TestRequestFieldCase
from odoo.addons.generic_request_field.tests.test_request_field import (
    FIELD_NOT_FOUND
)

_logger = logging.getLogger(__name__)


class TestRequestFieldService(TestRequestFieldCase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestFieldService, cls).setUpClass()
        cls.default_service = cls.env.ref(
            'generic_service.generic_service_default')
        cls.rent_nout_service = cls.env.ref(
            'generic_service.generic_service_rent_notebook')
        cls.request_category_demo_technical_config = cls.env.ref(
            'generic_request.request_category_demo_technical_configuration')
        cls.request_category_demo_resource = cls.env.ref(
            'generic_request.request_category_demo_resource')

    def test_show_data_without_service_in_field(self):
        Request = self.env['request.request']

        # Create request with field_type
        request = Request.new({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # Ensure all fields without service in request fields
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB')
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(
            request.get_field_value('cpu', FIELD_NOT_FOUND), '')
        self.assertIs(
            request.get_field_value('os', FIELD_NOT_FOUND), '')

    def test_show_data_with_service_in_field(self):

        Request = self.env['request.request']

        # Create request with field_type without service
        request = Request.new({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # Ensure all fields without service in request fields
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB')
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('cpu', FIELD_NOT_FOUND), '')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')

        # Add service to memory field
        self.request_field_memory.write({
            'service_ids': [(4, self.default_service.id)]
        })

        request.onchange_type_id_fields()

        # Ensure all fields without service in request
        # and memory field not in request fields
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('cpu', FIELD_NOT_FOUND), '')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND),
            FIELD_NOT_FOUND
        )

        # Add service to cpu field
        self.request_field_cpu.write({
            'service_ids': [(4, self.default_service.id)]
        })

        request.onchange_type_id_fields()

        # Ensure all fields without service in request
        # and memory and cpu fields not in request fields
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')
        self.assertEqual(
            request.get_field_value('cpu', FIELD_NOT_FOUND), FIELD_NOT_FOUND)
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND),
            FIELD_NOT_FOUND
        )

    def test_show_data_with_service_in_field_and_request(self):
        # Add classifiers to type of requests
        self.ensure_classifier(
            service=self.rent_nout_service,
            request_type=self.field_type)

        Request = self.env['request.request']
        # Create request with field_type and service
        request = Request.new({
            'type_id': self.field_type.id,
            'service_id': self.default_service.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # Ensure all fields without service in request fields
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB')
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('cpu', FIELD_NOT_FOUND), '')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')

        # Add service to cpu field
        self.request_field_cpu.write({
            'service_ids': [(4, self.rent_nout_service.id)]
        })

        request.onchange_type_id_fields()

        # Ensure all fields without service in request
        # and only cpu fields not in request fields
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')
        self.assertEqual(
            request.get_field_value('cpu', FIELD_NOT_FOUND), FIELD_NOT_FOUND)
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB'
        )

        # Add false service to memory field
        self.request_field_memory.write({
            'service_ids': [(4, self.rent_nout_service.id)]
        })

        request.onchange_type_id_fields()

        # Ensure all fields without service in request
        # and memory and cpu fields not in request fields
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')
        self.assertEqual(
            request.get_field_value('cpu', FIELD_NOT_FOUND), FIELD_NOT_FOUND)
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND),
            FIELD_NOT_FOUND
        )

        # Add true service to memory field
        self.request_field_memory.write({
            'service_ids': [(4, self.default_service.id)]
        })

        request.onchange_type_id_fields()

        # Ensure all fields without service in request
        # and only cpu fields not in request fields
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')
        self.assertEqual(
            request.get_field_value('cpu', FIELD_NOT_FOUND), FIELD_NOT_FOUND)
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB'
        )

    def test_show_data_with_service_and_category_in_field_and_request(self):
        # Add classifiers to type of requests
        self.ensure_classifier(
            service=self.rent_nout_service,
            category=self.request_category_demo_technical,
            request_type=self.field_type)
        self.ensure_classifier(
            service=self.rent_nout_service,
            category=self.request_category_demo_resource,
            request_type=self.field_type)

        Request = self.env['request.request']

        # Create request with field_type
        request = Request.new({
            'type_id': self.field_type.id,
            'service_id': self.rent_nout_service.id,
            'category_id': self.request_category_demo_technical_config.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # Ensure all fields without services and categories in request fields
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB')
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('cpu', FIELD_NOT_FOUND), '')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')

        # Add false service to memory field
        self.request_field_memory.write({
            'service_ids': [(4, self.default_service.id)]
        })

        # Add false category to cpu field
        self.request_field_cpu.write({
            'category_ids': [(4, self.request_category_demo_resource.id)]
        })
        request.onchange_type_id_fields()

        # Ensure all fields without service and category in request fields
        # and memory and cpu fields not in request fields
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')
        self.assertEqual(
            request.get_field_value('cpu', FIELD_NOT_FOUND), FIELD_NOT_FOUND)
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND),
            FIELD_NOT_FOUND
        )

        # Add true service and false category to hdd field
        #  (category must reject show field value)
        self.request_field_hdd.write({
            'service_ids': [(4, self.rent_nout_service.id)],
            'category_ids': [(4, self.request_category_demo_resource.id)]
        })
        request.onchange_type_id_fields()

        # Ensure all fields without service and category in request fields
        # and memory and cpu fields not in request fields
        # hdd field with true service and false category is invisible
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), FIELD_NOT_FOUND)
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')
        self.assertEqual(
            request.get_field_value('cpu', FIELD_NOT_FOUND), FIELD_NOT_FOUND)
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND),
            FIELD_NOT_FOUND
        )

    def test_constrains_service_in_field(self):

        Request = self.env['request.request']

        # Create request with field_type
        request = Request.new({
            'type_id': self.field_type.id,
            'service_id': self.default_service.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # Ensure all fields without service in request fields
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB')
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('cpu', FIELD_NOT_FOUND), '')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')

        # Ensure ValidationError if add false service to memory field
        with self.assertRaises(ValidationError):
            self.request_field_memory.write({
                'service_ids': [(4, self.rent_nout_service.id)]
            })

    def test_constrains_service_in_request_type(self):

        Request = self.env['request.request']
        # Create request with field_type
        request = Request.new({
            'type_id': self.field_type.id,
            'service_id': self.default_service.id,
            'request_text': 'Request Fields text',
        })
        request.onchange_type_id_fields()

        # Ensure all fields without service in request fields
        self.assertEqual(
            request.get_field_value('memory', FIELD_NOT_FOUND), '4 GB')
        self.assertEqual(
            request.get_field_value('hdd', FIELD_NOT_FOUND), '30 GB')
        self.assertIs(request.get_field_value('cpu', FIELD_NOT_FOUND), '')
        self.assertIs(request.get_field_value('os', FIELD_NOT_FOUND), '')

        # Add true service to memory field
        self.request_field_memory.write({
            'service_ids': [(4, self.default_service.id)]
        })

        with self.assertRaises(ValidationError):
            self.field_type.classifier_ids.filtered(
                lambda c: c.service_id == self.default_service
            ).unlink()
