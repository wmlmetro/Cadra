import logging

from odoo.addons.generic_request.tests.common import freeze_time
from .common import TestRequestContractResourceCommon

_logger = logging.getLogger(__name__)


class TestRequestContractResourceGuessOnWrite(
        TestRequestContractResourceCommon):

    def test_guess_contract_no_contract_related_to_resource(self):
        self.assertFalse(
            self.env['generic.contract.resource.line'].search_count(
                [('resource_id', '=', self.resource_computer_5.id)])
        )

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'resource_id': self.resource_computer_5.id,
        })

        self.assertFalse(request.contract_id)

    def test_guess_contract_no_active_contract_related_to_resource(self):
        # Ensure inactive contracts will not be guessed
        contract_resource_lines = self.env[
            'generic.contract.resource.line'
        ].search(
            [('resource_id', '=', self.resource_guest_book.id)]
        )
        self.assertIn(
            self.customer_contract.contract_resource_line_ids,
            contract_resource_lines)
        self.assertEqual(self.customer_contract.state, 'draft')
        self.assertEqual(
            self.customer_contract.partner_id, self.request_partner)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'resource_id': self.resource_guest_book.id,
        })

        self.assertFalse(request.contract_id)

    @freeze_time('2018-03-15')
    def test_guess_contract_no_active_contract_related_to_guest_book(self):
        # Ensure pending contracts will not be guessed

        # Run schedulers
        self._run_contract_schedulers()

        contract_resource_lines = self.env[
            'generic.contract.resource.line'
        ].search(
            [('resource_id', '=', self.resource_guest_book.id)]
        )
        # Ensure contract is pending
        self.assertIn(
            self.customer_contract.contract_resource_line_ids,
            contract_resource_lines)
        self.assertEqual(self.customer_contract.state, 'pending')
        self.assertEqual(
            self.customer_contract.partner_id, self.request_partner)

        # Ensure pending contracts will not be guessed
        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'resource_id': self.resource_guest_book.id,
        })

        self.assertFalse(request.contract_id)

    @freeze_time('2018-04-15')
    def test_guess_contract_active_contract_related_to_to_guest_book_exists(
            self):
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

        # Ensure pending contracts will not be guessed
        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'resource_id': self.resource_guest_book.id,
        })

        self.assertEqual(request.contract_id, self.customer_contract)

    @freeze_time('2018-04-15')
    def test_guess_contract_partner_has_active_contract_force_no_contr(self):
        # Test that if 'contract_id': False present in vals, then contract will
        # not be guessed

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

        # Ensure pending contracts will not be guessed
        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'resource_id': self.resource_guest_book.id,
            'contract_id': False,
        })

        self.assertFalse(request.contract_id)

    def test_guess_contract_no_contract_related_to_resource_or_service(self):
        # TODO: Do we need this test case?
        self.assertFalse(
            self.env['generic.contract.resource.line'].search_count(
                [('resource_id', '=', self.resource_computer_5.id)])
        )
        self.assertFalse(
            self.env['generic.contract.resource.service.line'].search_count(
                [('resource_id', '=', self.resource_computer_5.id),
                 ('service_id', '=', self.default_service.id)])
        )
        self.assertFalse(
            self.env['generic.contract.service.line'].search_count(
                [('service_id', '=', self.default_service.id)])
        )
        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertFalse(request.service_level_id)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        # service level 2 from partner
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.default_service.id,
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        # service level 2 from partner
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'resource_id': self.resource_computer_5.id,
            'service_id': self.default_service.id,
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        # service level 2 from partner
        self.assertEqual(request.service_level_id, self.service_level_2)

    def test_guess_contract_no_active_contract_related_to_resource_or_service(
            self):
        # Ensure inactive contracts will not be guessed
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

        self.assertEqual(self.customer_contract.state, 'draft')
        self.assertEqual(
            self.customer_contract.partner_id, self.request_partner)

        # we ensured:
        # customer_contract has service_line
        # with service support consulting and service level 1
        # customer_contract has resource_line with resource guest_book
        # this resource_line has resource_service_line with
        # service support consulting and service level 2
        # customer_contract has state - draft

        # change service level for service line contract
        contract_resource_service_lines.service_level_id = self.service_level_3

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertFalse(request.service_level_id)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        # service level 2 from partner
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.support_service_consulting.id,
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        # service level 2 from partner
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'resource_id': self.resource_guest_book.id,
            'service_id': self.support_service_consulting.id,
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        # service level 2 from partner
        self.assertEqual(request.service_level_id, self.service_level_2)

    @freeze_time('2018-03-15')
    def test_guess_contract_pending_contract_related_to_resource_or_service(
            self):
        # Run schedulers
        self._run_contract_schedulers()

        # Ensure pending contracts will not be guessed
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

        self.assertEqual(self.customer_contract.state, 'pending')
        self.assertEqual(
            self.customer_contract.partner_id, self.request_partner)

        # we ensured:
        # customer_contract has service_line
        # with service support consulting and service level 1
        # customer_contract has resource_line with resource guest_book
        # this resource_line has resource_service_line with
        # service support consulting and service level 2
        # customer_contract has state - pending

        # change service level for service line contract
        contract_resource_service_lines.service_level_id = self.service_level_3

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertFalse(request.service_level_id)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        # service level 2 from partner
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.support_service_consulting.id,
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        # service level 2 from partner
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'resource_id': self.resource_guest_book.id,
            'service_id': self.support_service_consulting.id,
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        # service level 2 from partner
        self.assertEqual(request.service_level_id, self.service_level_2)

    @freeze_time('2018-04-15')
    def test_guess_contract_active_contract_related_resource_or_service_exists(
            self):
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
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertFalse(request.service_level_id)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertEqual(request.contract_id, self.customer_contract)
        # service level 2 from partner
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.support_service_consulting.id,
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertEqual(request.contract_id, self.customer_contract)
        # service level 1 from contract service
        self.assertEqual(request.service_level_id, self.service_level_1)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'resource_id': self.resource_guest_book.id,
            'service_id': self.support_service_consulting.id,
        })

        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertEqual(request.contract_id, self.customer_contract)
        # service level 3 from contract resource service
        self.assertEqual(request.service_level_id, self.service_level_3)
