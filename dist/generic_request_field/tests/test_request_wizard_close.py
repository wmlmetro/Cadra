import json
import logging

from odoo.tests.common import Form

from odoo.addons.generic_request_field.tests.common import TestRequestFieldCase

from ..tools.field_utils import FieldsUIHelper

_logger = logging.getLogger(__name__)


class TestRequestReopenWithFields(TestRequestFieldCase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestReopenWithFields, cls).setUpClass()

        cls.new_to_rejected = cls.env.ref(
            'generic_request_field'
            '.request_stage_route_type_field_new_to_rejected')
        cls.new_request_category = cls.env.ref(
            'generic_request.request_category_demo_technical_configuration')
        cls.request_type__create_lxc = cls.env.ref(
            'generic_request_field.request_type__create_lxc')
        cls.field_type = cls.env.ref(
            'generic_request_field.request_type_field')

        cls.default_service = cls.env.ref(
            'generic_service.generic_service_default')
        cls.request_new_vm = cls.env.ref(
            'generic_request_field.request_request_type_field_new_vm')

    def test_request_wizard_close_reopen_with_new_values_fields(self):
        # Add request type to rejected route
        self.assertIn(
            self.request_type__create_lxc,
            self.new_to_rejected.reopen_as_type_ids)

        # Create request with field_type
        request = self.env['request.request'].create({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
            'request_field_values_json': json.dumps({
                'cpu': '2 core',
                'memory': '6 GB',
                'hdd': '10 GB',
                'comment': 'Comment added for testing',
                'os': False,
            }),
        })
        self.assertTrue(request.value_ids)

        # map values to field codes
        values = request.get_fields_data()

        # Ensure default values set
        self.assertEqual(values['cpu'], '2 core')
        self.assertEqual(values['memory'], '6 GB')
        self.assertEqual(values['hdd'], '10 GB')
        self.assertFalse(values['os'])
        self.assertEqual(values['comment'], 'Comment added for testing')

        # Check stage of the request.
        self.assertEqual(request.stage_id.code, 'new')

        # Remove Default Service from category
        self.assertIn(
            self.default_service, self.new_request_category.service_ids)
        self.new_request_category.write({
            'service_ids': [(5, 0)]
        })
        self.assertNotIn(
            self.default_service, self.new_request_category.service_ids)

        # Create wizard for closing the request.
        wiz_close_f = Form(self.env['request.wizard.close'])
        wiz_close_f.request_id = request
        wiz_close_f.close_route_id = self.new_to_rejected
        wiz_close_f.new_request_category_id = self.new_request_category
        wiz_close_f.new_request_type_id = self.request_type__create_lxc
        wiz_close_f.new_request_text = 'test fields'

        # Set new values for request fields top
        fields_top = FieldsUIHelper(self.env).from_json(
            wiz_close_f.wizard_fields_json_top)
        fields_top.set_val(self.request_field_lxc_cpu.id, '3 cores')
        wiz_close_f.wizard_fields_json_top = fields_top.to_json()

        # Set new values for request fields bottom
        fields_bottom = FieldsUIHelper(self.env).from_json(
            wiz_close_f.wizard_fields_json_bottom)
        fields_bottom.set_val(
            self.request_field_lxc_container_name.id,
            'Container Name added from wizard')
        wiz_close_f.wizard_fields_json_bottom = fields_bottom.to_json()

        wiz_request_close = wiz_close_f.save()

        # Close current request with reopening as new request
        close_res = wiz_request_close.action_close_request()
        new_request = self.env[close_res['res_model']].browse(
            close_res['res_id'])
        self.assertEqual(new_request.parent_id, request)
        self.assertEqual(request.stage_id.code, 'rejected')

        # Test if new request created in right way
        self.assertEqual(new_request.stage_id.code, 'new')
        self.assertEqual(new_request.request_text, '<p>test fields</p>')
        self.assertEqual(
            new_request.type_id, self.request_type__create_lxc)
        self.assertEqual(new_request.category_id, self.new_request_category)
        self.assertEqual(new_request.author_id, request.author_id)
        self.assertEqual(new_request.partner_id, request.partner_id)
        self.assertEqual(new_request.created_by_id, self.env.user)

        # Test that right fields used with right values
        self.assertEqual(len(new_request.value_ids), 7)
        values = new_request.get_fields_data()
        self.assertEqual(values['cpu'], '3 cores')
        self.assertEqual(values['memory'], '6 GB')
        self.assertEqual(values['hdd'], '10 GB')
        self.assertEqual(values['priviledged'], 'Yes')
        self.assertEqual(
            values['container-name'], 'Container Name added from wizard')
        self.assertFalse(values['domain-name'])
        self.assertFalse(values['expose-port'])

    def test_request_wizard_close_reopen_with_old_values_fields_1(self):
        # Add request type to rejected route
        self.assertIn(
            self.request_type__create_lxc,
            self.new_to_rejected.reopen_as_type_ids)

        # Create request with field_type
        request = self.env['request.request'].create({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
            'request_field_values_json': json.dumps({
                'cpu': '2 core',
                'memory': '6 GB',
                'hdd': '10 GB',
                'comment': 'Comment added for testing',
                'os': False,
            }),
        })
        self.assertTrue(request.value_ids)

        # Test that right fields used
        self.assertEqual(len(request.value_ids), 5)

        # Ensure default values set
        values = request.get_fields_data()
        self.assertEqual(values['cpu'], '2 core')
        self.assertEqual(values['memory'], '6 GB')
        self.assertEqual(values['hdd'], '10 GB')
        self.assertFalse(values['os'])
        self.assertEqual(values['comment'], 'Comment added for testing')

        # Check stage of the request.
        self.assertEqual(request.stage_id.code, 'new')

        # Remove Default Service from category
        self.assertIn(
            self.default_service, self.new_request_category.service_ids)
        self.new_request_category.write({
            'service_ids': [(5, 0)]
        })
        self.assertNotIn(
            self.default_service, self.new_request_category.service_ids)

        # Create wizard for closing the request.
        wiz_close_f = Form(self.env['request.wizard.close'])
        wiz_close_f.request_id = request
        wiz_close_f.close_route_id = self.new_to_rejected
        wiz_close_f.new_request_category_id = self.new_request_category
        wiz_close_f.new_request_type_id = self.request_type__create_lxc
        wiz_close_f.new_request_text = 'test fields'

        # Set new values for some fields
        fields_bottom = FieldsUIHelper(self.env).from_json(
            wiz_close_f.wizard_fields_json_bottom)
        fields_bottom.set_val(
            self.request_field_lxc_container_name.id,
            'Container Name added from wizard')
        wiz_close_f.wizard_fields_json_bottom = fields_bottom.to_json()

        # Closes the request and create new request with other type
        wiz_request_close = wiz_close_f.save()
        close_res = wiz_request_close.action_close_request()

        new_request = self.env[close_res['res_model']].browse(
            close_res['res_id'])
        self.assertEqual(new_request.parent_id, request)

        self.assertEqual(request.stage_id.code, 'rejected')

        # Test if new_request created right
        self.assertEqual(new_request.stage_id.code, 'new')
        self.assertEqual(new_request.request_text, '<p>test fields</p>')
        self.assertEqual(
            new_request.type_id, self.request_type__create_lxc)
        self.assertEqual(new_request.category_id, self.new_request_category)
        self.assertEqual(new_request.author_id, request.author_id)
        self.assertEqual(new_request.partner_id, request.partner_id)
        self.assertEqual(new_request.created_by_id, self.env.user)

        # Test that right fields and right values set on new request
        self.assertEqual(len(new_request.value_ids), 7)
        values = new_request.get_fields_data()
        self.assertEqual(values['cpu'], '2 core')
        self.assertEqual(values['memory'], '6 GB')
        self.assertEqual(values['hdd'], '10 GB')
        self.assertEqual(values['priviledged'], 'Yes')
        self.assertEqual(
            values['container-name'], 'Container Name added from wizard')
        self.assertFalse(values['domain-name'])
        self.assertFalse(values['expose-port'])

    def test_request_wizard_close_reopen_with_old_values_fields_2(self):
        # Add request type to rejected route
        self.assertIn(
            self.request_type__create_lxc,
            self.new_to_rejected.reopen_as_type_ids)

        # Create request with field_type
        request = self.env['request.request'].create({
            'type_id': self.field_type.id,
            'request_text': 'Request Fields text',
            'request_field_values_json': json.dumps({
                'cpu': '2 core',
                'memory': '6 GB',
                'hdd': '12 GB',
                'comment': 'Comment added for testing',
                'os': False,
            }),
        })
        self.assertTrue(request.value_ids)

        # Ensure correct field values set
        self.assertEqual(len(request.value_ids), 5)
        values = request.get_fields_data()
        self.assertEqual(values['cpu'], '2 core')
        self.assertEqual(values['memory'], '6 GB')
        self.assertEqual(values['hdd'], '12 GB')
        self.assertFalse(values['os'])
        self.assertEqual(values['comment'], 'Comment added for testing')

        # Check stage of the request.
        self.assertEqual(request.stage_id.code, 'new')

        # Remove Default Service from category
        self.assertIn(
            self.default_service, self.new_request_category.service_ids)
        self.new_request_category.write({
            'service_ids': [(5, 0)]
        })
        self.assertNotIn(
            self.default_service, self.new_request_category.service_ids)

        # Create wizard for closing the request.
        wiz_close_f = Form(self.env['request.wizard.close'])
        wiz_close_f.request_id = request
        wiz_close_f.close_route_id = self.new_to_rejected
        wiz_close_f.new_request_category_id = self.new_request_category
        wiz_close_f.new_request_type_id = self.request_type__create_lxc
        wiz_close_f.new_request_text = 'test fields'

        # Set new values for some fields
        fields_top = FieldsUIHelper(self.env).from_json(
            wiz_close_f.wizard_fields_json_top)
        fields_top.set_val(self.request_field_lxc_memory.id, '16 GB')
        wiz_close_f.wizard_fields_json_top = fields_top.to_json()

        fields_bottom = FieldsUIHelper(self.env).from_json(
            wiz_close_f.wizard_fields_json_bottom)
        fields_bottom.set_val(
            self.request_field_lxc_domain_name.id,
            'Domain Name added from wizard')
        fields_bottom.set_val(
            self.request_field_lxc_expose_port.id,
            'false')
        wiz_close_f.wizard_fields_json_bottom = fields_bottom.to_json()

        # Closes the request and create new request as child of current request
        wiz_request_close = wiz_close_f.save()
        close_res = wiz_request_close.action_close_request()

        new_request = self.env[close_res['res_model']].browse(
            close_res['res_id'])
        self.assertEqual(new_request.parent_id, request)

        self.assertEqual(request.stage_id.code, 'rejected')

        # Test if new_request created right
        self.assertEqual(new_request.stage_id.code, 'new')
        self.assertEqual(new_request.request_text, '<p>test fields</p>')
        self.assertEqual(
            new_request.type_id, self.request_type__create_lxc)
        self.assertEqual(new_request.category_id, self.new_request_category)
        self.assertEqual(new_request.author_id, request.author_id)
        self.assertEqual(new_request.partner_id, request.partner_id)
        self.assertEqual(new_request.created_by_id, self.env.user)

        # Ensure new request has correct field values
        self.assertEqual(len(new_request.value_ids), 7)
        values = new_request.get_fields_data()
        self.assertEqual(values['cpu'], '2 core')
        self.assertEqual(values['memory'], '16 GB')
        self.assertEqual(values['hdd'], '12 GB')
        self.assertEqual(values['priviledged'], 'Yes')
        self.assertFalse(values['container-name'])
        self.assertEqual(
            values['domain-name'], 'Domain Name added from wizard')
        # In this case, the 'false' value was set as string.
        # So it is OK to have it here.
        self.assertEqual(values['expose-port'], 'false')
