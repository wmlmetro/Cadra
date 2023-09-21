import logging

from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import (
    ReduceLoggingMixin,
    AccessRulesFixMixinST,
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


class GenericContractAccessRightsCase(AccessRulesFixMixinST,
                                      ReduceLoggingMixin,
                                      TransactionCase):
    @classmethod
    def setUpClass(cls):
        super(GenericContractAccessRightsCase, cls).setUpClass()

        # Users
        cls.user_demo = cls.env.ref('base.user_demo')
        cls.user_admin = cls.env.ref('base.user_admin')

        cls.main_company = cls.env.ref('base.main_company')

        # Envs
        cls.uenv = cls.env(user=cls.user_demo)  # pylint: disable=not-callable
        cls.menv = cls.env(user=cls.user_admin)  # pylint: disable=not-callable

        # Contract view action
        cls.contract_action = cls.env.ref(
            'generic_contract.generic_contract_action')

        # Contract groups
        cls.group_contract_implicit = cls.env.ref(
            'generic_contract'
            '.group_generic_contract_user_implicit')
        cls.group_contract_readonly = cls.env.ref(
            'generic_contract'
            '.group_generic_contract_user_readonly')
        cls.group_contract_user = cls.env.ref(
            'generic_contract'
            '.group_generic_contract_user')
        cls.group_contract_manager = cls.env.ref(
            'generic_contract'
            '.group_generic_contract_manager')

    def _read_contract_fields(self, user, contract):
        contract_fields = list(
            self.env['generic.contract'].with_user(
                user
            ).load_views(
                self.contract_action.views
            )['fields_views']['form']['fields']
        )
        return contract.with_user(user).read(contract_fields)
