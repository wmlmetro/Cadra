import logging

from odoo.addons.generic_request.tests.common import freeze_time
from .common import TestRequestContractResourceCommon

_logger = logging.getLogger(__name__)


class TestRequestContractResourceService(TestRequestContractResourceCommon):

    @freeze_time('2018-04-15')
    def test_generic_request_resource_service(self):

        # Run schedulers
        self._run_contract_schedulers()

        # Ensure active contracts will be guessed
        contract_resource_lines = self.env[
            'generic.contract.resource.line'
        ].search([('resource_id', '=', self.resource_guest_book.id),
                  ('contract_id', '=', self.customer_contract.id)])

        contract_resource_service_lines = self.env[
            'generic.contract.resource.service.line'
        ].search([('resource_id', '=', self.resource_guest_book.id),
                  ('service_id', '=', self.support_service_consulting.id),
                  ('contract_resource_line_id', '=',
                   contract_resource_lines.id)])
        contract_service_lines = self.env[
            'generic.contract.service.line'
        ].search([('contract_id', '=', self.customer_contract.id)])

        self.assertEqual(contract_service_lines.service_level_id,
                         self.service_level_1)

        self.assertEqual(contract_resource_service_lines.service_level_id,
                         self.service_level_2)

        self.assertIn(
            self.customer_contract.contract_resource_line_ids,
            contract_resource_lines)

        self.assertEqual(self.customer_contract.state, 'active')
        self.assertEqual(
            self.customer_contract.partner_id, self.request_partner)

        # we ensured:
        # customer_contract has service_line
        # with service support consulting and service level 1
        # customer_contract has resource_line with resource guest_book
        # this resource_line has resource_service_line with
        # service support consulting and service level 2
        # customer_contract has state - active

        # change service level for service line contract
        contract_resource_service_lines.service_level_id = self.service_level_3

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'resource_id': self.resource_guest_book.id,
            'service_id': self.support_service_consulting.id,
        })

        self.assertEqual(request.contract_id, self.customer_contract)
        self.assertEqual(request.resource_id, self.resource_guest_book)
        self.assertEqual(request.service_id, self.support_service_consulting)
        self.assertEqual(request.service_level_id, self.service_level_3)

        request.write({
            'resource_id': False,
        })

        self.assertEqual(request.contract_id, self.customer_contract)
        self.assertFalse(request.resource_id)
        self.assertEqual(request.service_id, self.support_service_consulting)
        # service level from service
        self.assertEqual(request.service_level_id, self.service_level_1)

        request.write({
            'partner_id': False,
        })

        # ensure no contract
        self.assertFalse(request.contract_id)
        self.assertFalse(request.resource_id)
        self.assertFalse(request.service_level_id)
        self.assertEqual(request.service_id, self.support_service_consulting)

        # return all
        request.write({
            'partner_id': self.request_partner.id,
            'resource_id': self.resource_guest_book.id,
            'contract_id': self.customer_contract.id,
        })

        self.assertEqual(request.contract_id, self.customer_contract)
        self.assertEqual(request.resource_id, self.resource_guest_book)
        self.assertEqual(request.service_id, self.support_service_consulting)
        self.assertEqual(request.service_level_id, self.service_level_3)

        # remove contract from request
        request.write({
            'contract_id': False,
        })

        # ensure no contract but resource and service exists
        self.assertFalse(request.contract_id)
        self.assertEqual(request.resource_id, self.resource_guest_book)
        self.assertEqual(request.service_id, self.support_service_consulting)
        # service level from partner
        self.assertEqual(request.service_level_id, self.service_level_2)
