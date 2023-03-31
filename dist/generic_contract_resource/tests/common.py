import logging

from odoo.addons.generic_contract.tests.common import TestGenericContractCommon

_logger = logging.getLogger(__name__)


class TestGenericContractResourceCommon(TestGenericContractCommon):

    @classmethod
    def setUpClass(cls):
        super(TestGenericContractResourceCommon, cls).setUpClass()
        cls.basic_support_guest_book_line = cls.env.ref(
            'generic_contract_resource.basic_support_guest_book')
        cls.template_basic_support_guest_book_line = cls.env.ref(
            'generic_contract_resource.template_basic_support_guest_book')
        cls.ContractResourceLine = cls.env['generic.contract.resource.line']
        cls.resource_guest_book = cls.env.ref(
            'generic_contract_resource.'
            'simple_resource_guest_book_generic_resource')
