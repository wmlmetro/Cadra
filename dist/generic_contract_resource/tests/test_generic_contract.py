import logging

from odoo import fields

from .common import TestGenericContractResourceCommon

_logger = logging.getLogger(__name__)

try:
    from freezegun import freeze_time
except ImportError:  # noqa
    _logger.warning(
        "freezegun not installed. Tests will not work!")


class TestGenericContractResource(TestGenericContractResourceCommon):
    @classmethod
    def setUpClass(cls):
        super(TestGenericContractResource, cls).setUpClass()

        (cls.customer_contract).write({
            'date_end': False,
        })
        cls.customer_contract.write({
            'date_start': fields.Date.from_string('2018-04-03'),
            'date_end': fields.Date.from_string('2019-01-03'),
        })

    def test_add_resource_line(self):
        resource_note4 = self.env.ref(
            'generic_resource.simple_resource_notebook_4')
        resource_note6 = self.env.ref(
            'generic_resource.simple_resource_notebook_6')
        resource_print_2 = self.env.ref(
            'generic_resource.simple_resource_inkprinter_2')

        simple_contract = self.env.ref(
            'generic_contract.generic_contract_simple_customer_contract')

        self.assertEqual(len(simple_contract.contract_resource_line_ids), 1)
        self.assertFalse(simple_contract.get_resource_line_for(resource_note4))
        self.assertFalse(simple_contract.get_resource_line_for(resource_note6))

        simple_contract.action_confirm()

        self.assertEqual(len(simple_contract.contract_resource_line_ids), 1)
        self.assertEqual(
            simple_contract.get_resource_line_for(resource_note4),
            self.env.ref(
                'generic_contract_resource.simple_contract_resource_notebook_4'
            )
        )
        self.assertFalse(simple_contract.get_resource_line_for(resource_note6))
        self.assertEqual(
            simple_contract.get_resource_line_for(resource_note4.resource_id),
            self.env.ref(
                'generic_contract_resource.simple_contract_resource_notebook_4'
            )
        )
        self.assertFalse(
            simple_contract.get_resource_line_for(resource_note6.resource_id))

        with freeze_time('2020-05-04 16:30:00'):
            new_res_line = simple_contract.add_resource_line(resource_note6)

        self.assertTrue(
            simple_contract.get_resource_line_for(resource_note6))
        self.assertEqual(
            simple_contract.get_resource_line_for(resource_note6).resource_id,
            resource_note6.resource_id)
        self.assertEqual(
            simple_contract.get_resource_line_for(
                resource_note6).datetime_added,
            fields.Datetime.from_string('2020-05-04 16:30:00'))

        # Try to add line that was already added
        new_res_line_2 = simple_contract.add_resource_line(resource_note6)
        self.assertTrue(
            simple_contract.get_resource_line_for(resource_note6))
        self.assertEqual(
            simple_contract.get_resource_line_for(resource_note6).resource_id,
            resource_note6.resource_id)
        self.assertEqual(
            simple_contract.get_resource_line_for(
                resource_note6).datetime_added,
            fields.Datetime.from_string('2020-05-04 16:30:00'))
        self.assertEqual(new_res_line, new_res_line_2)
        self.assertEqual(
            simple_contract.get_resource_line_for(resource_note6),
            new_res_line)

        with freeze_time('2020-05-04 16:30:00'):
            # Add new line with specified date
            simple_contract.add_resource_line(
                resource_print_2,
                date='2020-05-02 12:13:13')

        self.assertTrue(
            simple_contract.get_resource_line_for(resource_print_2))
        self.assertEqual(
            simple_contract.get_resource_line_for(
                resource_print_2).resource_id,
            resource_print_2.resource_id)
        self.assertEqual(
            simple_contract.get_resource_line_for(
                resource_print_2).datetime_added,
            fields.Datetime.from_string('2020-05-02 12:13:13'))

        # Test get_resouorce method
        self.assertEqual(
            simple_contract.get_resources('generic.resource.simple'),
            (resource_note4 + resource_note6 + resource_print_2))
