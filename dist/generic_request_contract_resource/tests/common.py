from odoo.addons.generic_request_contract.tests.common import (
    TestRequestContractCommon
)


class TestRequestContractResourceCommon(TestRequestContractCommon):
    @classmethod
    def setUpClass(cls):
        super(TestRequestContractResourceCommon, cls).setUpClass()
        cls.basic_support_guest_book_line = cls.env.ref(
            'generic_contract_resource.basic_support_guest_book')
        cls.basic_development_guest_book_line = cls.env.ref(
            'generic_contract_resource.basic_development_guest_book')
        cls.basic_hosting_guest_book_line = cls.env.ref(
            'generic_contract_resource.basic_hosting_guest_book')
        cls.template_basic_support_guest_book_line = cls.env.ref(
            'generic_contract_resource.template_basic_support_guest_book')
        cls.template_basic_development_guest_book_line = cls.env.ref(
            'generic_contract_resource.template_basic_development_guest_book')
        cls.template_basic_hosting_guest_book_line = cls.env.ref(
            'generic_contract_resource.template_basic_hosting_guest_book')
        cls.ContractResourceLine = cls.env['generic.contract.resource.line']
        cls.resource_guest_book = cls.env.ref(
            'generic_contract_resource.'
            'simple_resource_guest_book_generic_resource')
        cls.resource_computer_5 = cls.env.ref(
            'generic_resource.'
            'simple_resource_computer_5_generic_resource')
