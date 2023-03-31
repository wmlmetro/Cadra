import logging

from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import (
    ReduceLoggingMixin,
)

_logger = logging.getLogger(__name__)

try:
    # pylint: disable=unused-import
    from freezegun import freeze_time  # noqa
except (ImportError, IOError):  # noqa
    _logger.warning(  # noqa
        "freezegun not installed. Tests will not work!")  # noqa


class TestGenericContractCommon(ReduceLoggingMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestGenericContractCommon, cls).setUpClass()

        cls.customer_template = cls.env.ref(
            'generic_contract.contract_template_demo_client_customer')
        cls.supplier_template = cls.env.ref(
            'generic_contract.contract_template_demo_supplier')
        cls.template_basic_support = cls.env.ref(
            'generic_contract.contract_template_demo_basic_support')
        cls.template_basic_support_initial_stage = cls.env.ref(
            'generic_contract.'
            'contract_template_demo_basic_support_initial_stage')
        cls.template_basic_support_final_stage = cls.env.ref(
            'generic_contract.'
            'contract_template_demo_basic_support_final_stage')
        cls.partner_supplier = cls.env.ref('base.res_partner_1')
        cls.partner_customer = cls.env.ref('base.res_partner_12')
        cls.customer_contract = cls.env.ref(
            'generic_contract.contract_basic_support')
        cls.customer_contract_initial = cls.env.ref(
            'generic_contract.contract_basic_support_initial_stage')
        cls.customer_contract_final = cls.env.ref(
            'generic_contract.contract_basic_support_final_stage')
        cls.supplier_contract = cls.env.ref(
            'generic_contract.contract_basic_provider')
        cls.ContractCreateWizard = cls.env['generic.contract.wizard.create']
        cls.Contract = cls.env['generic.contract']
        cls.ContractTemplate = cls.env['generic.contract.template']
        cls.today = fields.Date.today()
        cls.activate_scheduler = cls.env.ref(
            'generic_contract.activate_pending_contracts')
        cls.close_scheduler = cls.env.ref(
            'generic_contract.close_reached_contracts')

        # Service info
        cls.service_level_1 = cls.env.ref(
            'generic_service.generic_service_level_1')
        cls.service_level_2 = cls.env.ref(
            'generic_service.generic_service_level_2')
        cls.service_level_3 = cls.env.ref(
            'generic_service.generic_service_level_3')
        cls.service_level_4 = cls.env.ref(
            'generic_service.generic_service_level_4')
        cls.default_service = cls.env.ref(
            'generic_service.generic_service_default')
        cls.rent_notebook_service = cls.env.ref(
            'generic_service.generic_service_rent_notebook')
        cls.support_consulting_service = cls.env.ref(
            'generic_service.generic_service_support_consulting')
        cls.support_development_service = cls.env.ref(
            'generic_service.generic_service_support_development')
        cls.support_configuration_service = cls.env.ref(
            'generic_service.generic_service_support_configuration')
        cls.support_administration_service = cls.env.ref(
            'generic_service.generic_service_support_administration')
        cls.support_hosting_service = cls.env.ref(
            'generic_service.generic_service_support_hosting')
        cls.ContractServiceLine = cls.env['generic.contract.service.line']
        cls.ContractTemplateServiceLine = cls.env[
            'generic.contract.template.service.line']

    def _run_contract_schedulers(self):
        self.env['generic.contract'].search(
            [('state', '=', 'draft')]
        ).action_confirm_contracts()
        self.env['generic.contract'].scheduler_activate_contracts()
        self.env['generic.contract'].scheduler_close_contracts()
