from odoo import fields

from odoo.addons.generic_contract.tests.common import TestGenericContractCommon
from odoo.addons.generic_mixin.tests.common import (
    AccessRulesFixMixinST,
)


class TestRequestContractCommon(AccessRulesFixMixinST,
                                TestGenericContractCommon):
    @classmethod
    def setUpClass(cls):
        super(TestRequestContractCommon, cls).setUpClass()

        # Request Type
        cls.type_simple = cls.env.ref(
            'generic_request.request_type_simple')

        # Request manager user
        cls.request_manager = cls.env.ref(
            'generic_request.user_demo_request_manager')

        # Partner with contract
        cls.request_partner = cls.env.ref('base.res_partner_2')
        cls.request_author = cls.env.ref('base.res_partner_address_4')

        # Partner without contract
        cls.request_partner_fake = cls.env.ref('base.res_partner_3')

        cls.customer_contract.write({
            'date_end': False,
        })
        cls.customer_contract.write({
            'date_begin': fields.Date.from_string('2018-04-03'),
            'date_end': fields.Date.from_string('2019-01-03'),
        })
        cls.customer_contract_initial.write({
            'date_begin': fields.Date.from_string('2018-06-03'),
            'date_end': fields.Date.from_string('2018-12-03'),
        })
        cls.customer_contract_final.write({
            'date_begin': fields.Date.from_string('2018-07-03'),
            'date_end': fields.Date.from_string('2019-01-03'),
        })

        # Service levels
        cls.service_level_1 = cls.env.ref(
            'generic_service.generic_service_level_1')
        cls.service_level_2 = cls.env.ref(
            'generic_service.generic_service_level_2')
        cls.service_level_3 = cls.env.ref(
            'generic_service.generic_service_level_3')

        # Services
        cls.default_service = cls.env.ref(
            'generic_service.generic_service_default')
        cls.support_service_consulting = cls.env.ref(
            'generic_service.generic_service_support_consulting')
        cls.support_service_development = cls.env.ref(
            'generic_service.generic_service_support_development')
        cls.support_service_hosting = cls.env.ref(
            'generic_service.generic_service_support_hosting')
        cls.support_service_configuration = cls.env.ref(
            'generic_service.generic_service_support_configuration')
        cls.support_service_administration = cls.env.ref(
            'generic_service.generic_service_support_administration')
