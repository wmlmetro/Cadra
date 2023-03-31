import logging
import psycopg2

from odoo import exceptions, fields
from odoo.tools import mute_logger
from .common import TestGenericContractCommon

_logger = logging.getLogger(__name__)

try:
    from freezegun import freeze_time
except ImportError:  # noqa
    _logger.warning(
        "freezegun not installed. Tests will not work!")


class TestGenericContractService(TestGenericContractCommon):

    def test_generic_contract_supplier_service_line(self):

        supplier_contract_wizard = self.ContractCreateWizard.sudo().create({
            'partner_type': 'supplier',
            'partner_id': self.partner_supplier.id,
            'template_id': self.supplier_template.id,
            'date_start': self.today,
        })

        supplier_contract_wizard.sudo().create_contract()

        supplier_contracts = self.Contract.sudo().search(
            [('partner_type', '=', 'supplier')])
        supplier_contract = supplier_contracts.sudo().search(
            [('template_id', '=', self.supplier_template.id),
             ('partner_id', '=', self.partner_supplier.id)])

        # ensure contract has relevant service and service level
        self.assertEqual(len(supplier_contract.service_contract_line_ids), 1)
        self.assertEqual(
            supplier_contract.service_contract_line_ids.service_id.id,
            self.default_service.id)
        self.assertFalse(
            supplier_contract.service_contract_line_ids.service_level_id)

    def test_generic_contract_customer_service_line(self):
        # ensure contract has relevant service and service level
        customer_contract = self.customer_contract
        self.assertEqual(
            len(customer_contract.service_contract_line_ids), 1)
        self.assertEqual(
            customer_contract.service_contract_line_ids.service_id.id,
            self.support_consulting_service.id)
        self.assertEqual(
            customer_contract.service_contract_line_ids.service_level_id.id,
            self.service_level_1.id)

    def test_service_line_constrains(self):
        new_contract_service_line = self.ContractServiceLine.new({})

        # ensure constrains 'any service or service level'
        with self.assertRaises(exceptions.ValidationError):
            new_contract_service_line._ensure_service_id_or_service_level_id()

        new_contract_template_service_line = \
            self.ContractTemplateServiceLine.new({})

        # ensure constrains 'any service or service level'
        with self.assertRaises(exceptions.ValidationError):
            new_contract_template_service_line.\
                _ensure_service_id_or_service_level_id()

    @mute_logger('odoo.sql_db')
    def test_contract_service_unique(self):
        # for contract
        # test constraint contract_service_unique:
        with self.assertRaises(psycopg2.IntegrityError):
            self.ContractServiceLine.create({
                'contract_id': self.customer_contract.id,
                'service_id': self.support_consulting_service.id,
                'service_level_id': self.service_level_2.id,
            })

    @mute_logger('odoo.sql_db')
    def test_contract_template_service_unique(self):
        # for contract template
        # contract template service line for default_service exists
        # test constraint contract_template_service_unique:
        with self.assertRaises(psycopg2.IntegrityError):
            self.ContractTemplateServiceLine.create({
                'contract_template_id': self.customer_template.id,
                'service_id': self.default_service.id,
            })

    def test_add_service_line(self):
        simple_contract = self.env.ref(
            'generic_contract.generic_contract_simple_customer_contract')

        self.assertEqual(len(simple_contract.service_contract_line_ids), 1)
        self.assertFalse(
            simple_contract.get_service_line_for(
                self.support_development_service))
        self.assertFalse(
            simple_contract.get_service_line_for(
                self.support_configuration_service))

        simple_contract.action_confirm()

        self.assertEqual(len(simple_contract.service_contract_line_ids), 1)
        self.assertEqual(
            simple_contract.get_service_line_for(
                self.support_development_service),
            self.env.ref(
                'generic_contract.simple_contract_service_line_2'))
        self.assertFalse(
            simple_contract.get_service_line_for(
                self.support_configuration_service))

        with freeze_time('2020-05-04 16:30:00'):
            simple_contract.add_service_line(
                self.support_configuration_service)

        self.assertTrue(
            simple_contract.get_service_line_for(
                self.support_configuration_service))
        self.assertEqual(
            simple_contract.get_service_line_for(
                self.support_configuration_service).service_id,
            self.support_configuration_service)
        self.assertFalse(
            simple_contract.get_service_line_for(
                self.support_configuration_service).service_level_id)
        self.assertEqual(
            simple_contract.get_service_line_for(
                self.support_configuration_service).date_added,
            fields.Datetime.from_string('2020-05-04 16:30:00'))

        with freeze_time('2020-05-04 16:30:00'):
            # Change service level of already created service line
            # But date not changed
            simple_contract.add_service_line(
                self.support_configuration_service,
                service_level=self.service_level_1)

        self.assertTrue(
            simple_contract.get_service_line_for(
                self.support_configuration_service))
        self.assertEqual(
            simple_contract.get_service_line_for(
                self.support_configuration_service).service_id,
            self.support_configuration_service)
        self.assertEqual(
            simple_contract.get_service_line_for(
                self.support_configuration_service).service_level_id,
            self.service_level_1)
        self.assertEqual(
            simple_contract.get_service_line_for(
                self.support_configuration_service).date_added,
            fields.Datetime.from_string('2020-05-04 16:30:00'))

        with freeze_time('2020-05-04 16:30:00'):
            # Add new line with specified service level and specified date
            simple_contract.add_service_line(
                self.support_consulting_service,
                service_level=self.service_level_4,
                date='2020-05-02 12:13:13')

        self.assertTrue(
            simple_contract.get_service_line_for(
                self.support_consulting_service))
        self.assertEqual(
            simple_contract.get_service_line_for(
                self.support_consulting_service).service_id,
            self.support_consulting_service)
        self.assertEqual(
            simple_contract.get_service_line_for(
                self.support_consulting_service).service_level_id,
            self.service_level_4)
        self.assertEqual(
            simple_contract.get_service_line_for(
                self.support_consulting_service).date_added,
            fields.Datetime.from_string('2020-05-02 12:13:13'))
