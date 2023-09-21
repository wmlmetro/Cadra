import logging

from .common import TestGenericContractResourceCommon

_logger = logging.getLogger(__name__)


class TestGenericContractResourceWizard(TestGenericContractResourceCommon):

    def test_generic_contract_resource_wizard_create(self):
        basic_support_wizard = self.ContractCreateWizard.sudo().create({
            'partner_type': 'supplier',
            'partner_id': self.partner_supplier.id,
            'template_id': self.template_basic_support.id,
            'date_begin': self.today,
        })

        basic_support_wizard.sudo().create_contract()

        contract = self.Contract.search(
            [('template_id', '=', self.template_basic_support.id)])

        # ensure contract resource line created
        self.assertEqual(contract.contract_resource_line_ids.resource_id,
                         self.resource_guest_book)
        self.assertEqual(contract.contract_resource_line_ids.contract_id,
                         contract)
