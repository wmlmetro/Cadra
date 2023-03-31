import logging

from odoo.addons.generic_request.tests.common import freeze_time
from .common import TestRequestContractResourceCommon

_logger = logging.getLogger(__name__)


class TestRequestContractResource(TestRequestContractResourceCommon):

    @freeze_time('2018-04-15')
    def test_generic_request_resource(self):
        # Run schedulers
        self._run_contract_schedulers()

        contract_resource_lines = self.env[
            'generic.contract.resource.line'
        ].search(
            [('resource_id', '=', self.resource_guest_book.id)]
        )
        # Ensure contract is active
        self.assertIn(
            self.customer_contract.contract_resource_line_ids,
            contract_resource_lines)
        self.assertEqual(self.customer_contract.state, 'active')
        self.assertEqual(
            self.customer_contract.partner_id, self.request_partner)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'resource_id': self.resource_guest_book.id,
            'contract_id': self.customer_contract.id,
        })

        self.assertEqual(request.contract_id, self.customer_contract)
        self.assertEqual(request.resource_id, self.resource_guest_book)

        request.write({
            'resource_id': False,
        })

        # ensure contract the same (recomputed by partner)
        self.assertEqual(request.contract_id, self.customer_contract)
        self.assertFalse(request.resource_id)

        request.write({
            'partner_id': False,
        })

        # ensure no contract
        self.assertFalse(request.contract_id)
        self.assertFalse(request.resource_id)

        # return partner contract and resource to request

        request.write({
            'partner_id': self.request_partner.id,
            'resource_id': self.resource_guest_book.id,
            'contract_id': self.customer_contract.id,
        })

        self.assertEqual(request.contract_id, self.customer_contract)
        self.assertEqual(request.resource_id, self.resource_guest_book)

        # remove contract from request
        request.write({
            'contract_id': False,
        })

        # ensure no contract but resource exists
        self.assertFalse(request.contract_id)
        self.assertEqual(request.resource_id, self.resource_guest_book)
