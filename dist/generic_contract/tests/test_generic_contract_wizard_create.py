import logging

from .common import TestGenericContractCommon

_logger = logging.getLogger(__name__)


class TestGenericContractWizardCreate(TestGenericContractCommon):

    def test_onchange_partner_type(self):
        new_supplier_contract_wizard = self.ContractCreateWizard.sudo().new({
            'partner_type': 'supplier',
            'partner_id': self.partner_supplier.id,
            'template_id': self.supplier_template.id,
            'date_begin': self.today,
        })
        new_supplier_contract_wizard._onchange_partner_type()

        # ensure onchange
        self.assertFalse(new_supplier_contract_wizard.template_id)
        self.assertFalse(new_supplier_contract_wizard.partner_id)
