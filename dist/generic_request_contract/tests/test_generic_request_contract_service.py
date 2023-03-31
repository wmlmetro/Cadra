import json
import logging

from odoo.addons.generic_request.tests.common import freeze_time
from .common import TestRequestContractCommon

_logger = logging.getLogger(__name__)


class TestRequestContractService(TestRequestContractCommon):

    def test_write_request_partner_service_level(self):
        # fix date_start and date_end of customer contract
        self.customer_contract.write({
            'date_start': '2015-05-02',
            'date_end': '2015-05-10',
        })

        # confirm contract
        with freeze_time('2015-05-03'):
            self.customer_contract.action_confirm()

        self.assertEqual(self.customer_contract.state, 'active')

        # set service level 1 for request author
        self.env.user.partner_id.service_level_id = self.service_level_3.id

        # set service level 2 for request partner
        self.request_partner.service_level_id = self.service_level_2.id

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'contract_id': self.customer_contract.id,
            'service_id': self.support_service_consulting.id,
        })

        # ensure service level
        # (contract for service support has service level 1)
        self.assertEqual(request.service_level_id, self.service_level_1)

        request.contract_id = False

        # ensure service level
        # sets service level from partner
        self.assertEqual(request.service_level_id, self.service_level_2)

        request.contract_id = self.customer_contract.id

        # ensure service level
        # (contract for service support has service level 1)
        self.assertEqual(request.service_level_id, self.service_level_1)

        request.write({
            'contract_id': False,
            'partner_id': False,
        })

        # ensure service level
        # sets service level from author (request have no partner nor contract)
        self.assertEqual(request.service_level_id, self.service_level_3)

        request.partner_id = self.request_partner_fake.id

        # ensure not service level (partner have no service level defined)
        self.assertFalse(request.service_level_id)

        # request without contract
        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.support_service_consulting.id,
        })

        # ensure contract is guessed and service level set from contract
        self.assertEqual(request.contract_id, self.customer_contract)
        self.assertEqual(request.service_level_id, self.service_level_1)

    @freeze_time('2018-04-15')
    def test_new_request_restrict_service(self):
        self.assertEqual(self.customer_contract.state, 'draft')
        # Run schedulers
        self._run_contract_schedulers()

        # Ensure contract is active
        self.assertEqual(self.customer_contract.state, 'active')

        # Start creation of request
        request = self.env['request.request'].new({
            'request_text': 'test',
        })
        request._onchange_update_contract()
        request._onchange_contract_id_restrict_service()

        # Ensure that there is no contract and all services could be selected
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_id_domain, "[]")

        # Set partner for contract
        request.partner_id = self.request_partner
        request._onchange_update_contract()
        request._onchange_contract_id_restrict_service()

        # Ensure that contract was detected and selectable services are
        # restricted by contract's services
        self.assertEqual(request.contract_id, self.customer_contract)
        parsed_domain = json.loads(request.service_id_domain)
        self.assertEqual(len(parsed_domain), 1)
        self.assertEqual(
            set(parsed_domain[0][2]),
            set([self.support_service_consulting.id]))

    @freeze_time('2018-04-15')
    def test_onchange_contract_restrict_service_clean_service(self):
        self.assertEqual(self.customer_contract.state, 'draft')
        # Run schedulers
        self._run_contract_schedulers()

        # Ensure contract is active
        self.assertEqual(self.customer_contract.state, 'active')

        # Create contract with default service
        request = self.env['request.request'].new({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.default_service.id,
        })
        request._onchange_update_contract()
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_id, self.default_service)

        # Set contract manually
        request.contract_id = self.customer_contract

        # Run onchange contract and ensure service got new domain
        request._onchange_contract_id_restrict_service()
        self.assertFalse(request.service_id)
        parsed_domain = json.loads(request.service_id_domain)
        self.assertEqual(len(parsed_domain), 1)
        self.assertEqual(
            set(parsed_domain[0][2]),
            set([self.support_service_consulting.id]))
