import logging

from odoo import fields

from .common import TestGenericContractResourceCommon

_logger = logging.getLogger(__name__)

try:
    from freezegun import freeze_time
except ImportError:  # noqa
    _logger.warning(
        "freezegun not installed. Tests will not work!")


class TestGenericContractResourceService(TestGenericContractResourceCommon):

    @classmethod
    def setUpClass(cls):
        super(TestGenericContractResourceService, cls).setUpClass()
        # Resource Service Lines
        cls.guest_book_consulting = cls.env.ref(
            'generic_contract_resource.'
            'basic_support_guest_book_consulting')
        cls.guest_book_development = cls.env.ref(
            'generic_contract_resource.'
            'basic_support_guest_book_development')
        cls.guest_book_hosting = cls.env.ref(
            'generic_contract_resource.'
            'basic_support_guest_book_hosting')

        # Services
        cls.default_service = cls.env.ref(
            'generic_service.generic_service_default')
        cls.support_service_consulting = cls.env.ref(
            'generic_service.generic_service_support_consulting')
        cls.support_service_development = cls.env.ref(
            'generic_service.generic_service_support_development')
        cls.support_service_hosting = cls.env.ref(
            'generic_service.generic_service_support_hosting')

        cls.ContractResourceServiceLine = cls.env[
            'generic.contract.resource.service.line']

    def test_onchange_resource(self):
        # create contract with resource service line
        contract = self.Contract.create({
            'partner_type': 'customer',
            'partner_id': self.customer_contract.partner_id.id,
            'name': 'test',
            'date_begin': self.today,
        })

        resource_line = self.ContractResourceLine.create({
            'contract_id': contract.id,
            'resource_id': self.resource_guest_book.id,
        })

        resource_service_line = self.ContractResourceServiceLine.create({
            'service_id': self.support_service_hosting.id,
            'contract_resource_line_id': resource_line.id,
        })
        # call onchange
        res = resource_line._onchange_resource()

        value_for_onchange = [(2, resource_service_line.id)]

        # ensure onchange return value for unlink
        self.assertListEqual(
            res['value']['resource_service_line_ids'], value_for_onchange)

    def test_get_resource_service_line_for(self):

        srl = self.customer_contract.get_resource_service_line_for(
            self.support_service_development, self.resource_guest_book)

        # ensure no service resource line (contract no active)
        self.assertFalse(srl)

        # Fix dates
        self.customer_contract.write({
            'date_end': False,
        })
        self.customer_contract.write({
            'date_begin': fields.Date.to_date('2018-04-03'),
            'date_end': fields.Date.to_date('2019-01-03'),
        })

        # activate contracts
        with freeze_time('2018-04-15'):
            self._run_contract_schedulers()

        srl_dev = self.customer_contract_initial.get_resource_service_line_for(
            self.support_service_development, self.resource_guest_book)
        # ensure service resource line
        self.assertEqual(srl_dev, self.guest_book_development)

        srl_host = (
            self.customer_contract_final.get_resource_service_line_for(
                self.support_service_hosting, self.resource_guest_book))

        # ensure service resource line
        self.assertEqual(srl_host, self.guest_book_hosting)

        srl_default = (
            self.customer_contract_final.get_resource_service_line_for(
                self.default_service, self.resource_guest_book))

        # ensure no service resource line
        self.assertFalse(srl_default)
