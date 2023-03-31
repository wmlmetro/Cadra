import logging

from odoo.addons.generic_request.tests.common import freeze_time
from .common import TestRequestContractCommon

_logger = logging.getLogger(__name__)


class TestRequestContractGuessOnWrite(TestRequestContractCommon):

    def test_guess_contract_no_contract_related_to_partner(self):
        self.assertFalse(self.env['generic.contract'].search_count(
            [('partner_id', '=', self.env.user.partner_id.id)]))

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
        })
        self.assertFalse(request.contract_id)

    def test_guess_contract_no_active_contract_related_to_partner(self):
        self.assertEqual(self.customer_contract.state, 'draft')

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })
        self.assertFalse(request.contract_id)

    @freeze_time('2018-03-15')
    def test_guess_contract_no_active_contract_related_to_partner_2(self):
        self.assertEqual(self.customer_contract.state, 'draft')

        # Run schedulers
        self._run_contract_schedulers()

        self.assertEqual(self.customer_contract.state, 'pending')

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })
        self.assertFalse(request.contract_id)

    @freeze_time('2018-04-15')
    def test_guess_contract_active_contract_related_to_partner_exists(self):
        self.assertEqual(self.customer_contract.state, 'draft')

        # Run schedulers
        self._run_contract_schedulers()

        # Ensure contract is active
        self.assertEqual(self.customer_contract.state, 'active')

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })
        self.assertEqual(request.contract_id, self.customer_contract)

    @freeze_time('2018-04-15')
    def test_guess_contract_active_contract_related_to_partner_exists_a(self):
        self.assertEqual(self.customer_contract.state, 'draft')

        # Run schedulers
        self._run_contract_schedulers()

        # Ensure contract is active
        self.assertEqual(self.customer_contract.state, 'active')

        request = self.env['request.request'].with_user(
            self.request_manager
        ).create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'author_id': self.request_author.id,
        })
        self.assertEqual(request.partner_id, self.request_partner)
        self.assertEqual(request.contract_id, self.customer_contract)

    @freeze_time('2018-04-15')
    def test_guess_contract_partner_has_active_contract_force_no_contr(self):
        self.assertEqual(self.customer_contract.state, 'draft')
        # Run schedulers
        self._run_contract_schedulers()

        # Ensure contract is active
        self.assertEqual(self.customer_contract.state, 'active')

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'contract_id': False,
        })
        self.assertFalse(request.contract_id)

    def test_guess_contract_srv_no_contract_related_to_partner(self):
        self.assertFalse(self.env['generic.contract'].search_count(
            [('partner_id', '=', self.env.user.partner_id.id)]))

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
        })
        self.assertFalse(request.contract_id)
        self.assertFalse(request.service_level_id)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'service_id': self.default_service.id,
        })
        self.assertFalse(request.contract_id)
        self.assertFalse(request.service_level_id)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'service_id': self.support_service_consulting.id,
        })
        self.assertFalse(request.contract_id)
        self.assertFalse(request.service_level_id)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'service_id': self.support_service_hosting.id,
        })
        self.assertFalse(request.contract_id)
        self.assertFalse(request.service_level_id)

    def test_guess_contract_srv_no_active_contract_related_to_partner(self):
        # Ensure inactive contracts will not be guessed
        self.assertEqual(self.customer_contract.state, 'draft')

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.default_service.id,
        })
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.support_service_consulting.id,
        })
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.support_service_hosting.id,
        })
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

    @freeze_time('2018-03-15')
    def test_guess_contract_srv_no_active_contract_related_to_partner_2(self):
        self.assertEqual(self.customer_contract.state, 'draft')
        # Ensure pending contracts will not be guessed

        # Run schedulers
        self._run_contract_schedulers()

        self.assertEqual(self.customer_contract.state, 'pending')

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.default_service.id,
        })
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.support_service_consulting.id,
        })
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.support_service_hosting.id,
        })
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

    @freeze_time('2018-04-15')
    def test_guess_contract_srv_act_contract_related_to_partner_exists(self):
        simple_contract = self.env.ref(
            'generic_contract.generic_contract_simple_customer_contract')

        self.assertEqual(self.customer_contract.state, 'draft')
        self.assertEqual(simple_contract.state, 'draft')
        # Run schedulers
        self._run_contract_schedulers()

        # Ensure contract is active
        self.assertEqual(self.customer_contract.state, 'active')
        self.assertEqual(len(self.customer_contract.contracts_service_ids), 1)
        self.assertIn(
            self.support_service_consulting.id,
            self.customer_contract.contracts_service_ids.ids)

        # Ensure contract is pending
        self.assertEqual(simple_contract.state, 'pending')
        self.assertEqual(len(self.customer_contract.contracts_service_ids), 1)
        self.assertIn(
            self.support_service_development.id,
            simple_contract.contracts_service_ids.ids)

        # No service defined on request, thus first contract for this partner
        # will be guessed
        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })
        self.assertEqual(request.contract_id, self.customer_contract)
        self.assertEqual(request.service_level_id, self.service_level_2)

        # service not mentioned in any contract and thus no contract guessed
        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.default_service.id,
        })
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        # service mentioned in an contract and thus contract guessed
        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.support_service_consulting.id,
        })
        self.assertEqual(request.contract_id, self.customer_contract)
        self.assertEqual(request.service_level_id, self.service_level_1)

        # service mentioned in an contract but state conract in not active
        # and thus no contract guessed
        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'service_id': self.support_service_development.id,
        })
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

    @freeze_time('2018-04-15')
    def test_guess_contract_srv_partner_has_act_contract_force_no_contr(self):
        # Test that if 'contract_id': False present in vals, then contract will
        # not be guessed
        self.assertEqual(self.customer_contract.state, 'draft')

        # Run schedulers
        self._run_contract_schedulers()

        # Ensure contract is active
        self.assertEqual(self.customer_contract.state, 'active')

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'contract_id': False,
        })
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'contract_id': False,
            'service_id': self.default_service.id,
        })
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'contract_id': False,
            'service_id': self.support_service_consulting.id,
        })
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
            'contract_id': False,
            'service_id': self.support_service_hosting.id,
        })
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)
