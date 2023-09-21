import logging

from odoo.tests.common import Form

from odoo.addons.generic_request_field.tests.common import TestRequestFieldCase
from odoo.addons.generic_request_field.tools.field_utils import FieldsUIHelper

_logger = logging.getLogger(__name__)


class TestRequestFieldServiceJSON(TestRequestFieldCase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestFieldServiceJSON, cls).setUpClass()
        cls.default_service = cls.env.ref(
            'generic_service.generic_service_default')
        cls.rent_nout_service = cls.env.ref(
            'generic_service.generic_service_rent_notebook')
        cls.request_category_demo_technical_config = cls.env.ref(
            'generic_request.request_category_demo_technical_configuration')
        cls.request_category_demo_resource = cls.env.ref(
            'generic_request.request_category_demo_resource')

    def test_request_fields_related_to_service(self):
        self._enable_use_services_setting()
        # Add service to memory field
        self.request_field_memory.write({
            'service_ids': [(4, self.default_service.id)]
        })

        f_request = Form(self.env['request.request'])
        f_request.type_id = self.field_type
        f_request.request_text = 'Request Fields text'

        # Ensure all fields without service in request fields
        fields_top = FieldsUIHelper(self.env).from_json(
            f_request.request_fields_json_top)
        self.assertFalse(
            fields_top.get_val(self.request_field_cpu.id))
        self.assertEqual(
            fields_top.get_val(self.request_field_hdd.id), '30 GB')
        self.assertFalse(
            fields_top.get_val(self.request_field_os.id))

        # Ensure that memory field that is related to service is not available
        # in fields_top
        self.assertFalse(fields_top.has_field(self.request_field_memory.id))

        # Set value for CPU field
        fields_top.set_val(self.request_field_cpu.id, '2 Cores')
        f_request.request_fields_json_top = fields_top.to_json()

        # Change service of the request
        f_request.service_id = self.default_service

        # Ensure all fields without service in request fields
        fields_top = FieldsUIHelper(self.env).from_json(
            f_request.request_fields_json_top)
        self.assertEqual(
            fields_top.get_val(self.request_field_cpu.id), '2 Cores')
        self.assertEqual(
            fields_top.get_val(self.request_field_hdd.id), '30 GB')
        self.assertFalse(
            fields_top.get_val(self.request_field_os.id))

        # Ensure that memory field that is bound to service is present on
        # request form and has default value
        self.assertEqual(
            fields_top.get_val(self.request_field_memory.id), '4 GB')

        # Save request
        request = f_request.save()

        # Check request values
        values = request.get_fields_data()
        self.assertEqual(values['memory'], '4 GB')
        self.assertEqual(values['cpu'], '2 Cores')
        self.assertEqual(values['hdd'], '30 GB')
        self.assertFalse(values['os'])
        self.assertFalse(values['comment'])
