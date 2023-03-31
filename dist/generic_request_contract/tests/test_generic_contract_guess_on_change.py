import logging

from odoo.addons.generic_request.tests.common import freeze_time
from .common import TestRequestContractCommon

_logger = logging.getLogger(__name__)


class TestRequestContractGuessOnChange(TestRequestContractCommon):

    def test_guess_contract_no_contract_related_to_partner(self):
        self.assertFalse(self.env['generic.contract'].search_count(
            [('partner_id', '=', self.env.user.partner_id.id)]))

        request = self.env['request.request'].new({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.env.user.partner_id.id,
        })
        request._onchange_update_contract()
        self.assertFalse(request.contract_id)

    def test_guess_contract_no_active_contract_related_to_partner(self):
        self.assertEqual(self.customer_contract.state, 'draft')

        request = self.env['request.request'].new({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })
        request._onchange_update_contract()
        self.assertFalse(request.contract_id)

    @freeze_time('2018-03-15')
    def test_guess_contract_no_active_contract_related_to_partner_2(self):
        self.assertEqual(self.customer_contract.state, 'draft')

        # Run schedulers
        self._run_contract_schedulers()

        self.assertEqual(self.customer_contract.state, 'pending')

        request = self.env['request.request'].new({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })
        request._onchange_update_contract()
        self.assertFalse(request.contract_id)

    @freeze_time('2018-04-15')
    def test_guess_contract_active_contract_related_to_partner_exists(self):
        self.assertEqual(self.customer_contract.state, 'draft')

        # Run schedulers
        self._run_contract_schedulers()

        # Ensure contract is active
        self.assertEqual(self.customer_contract.state, 'active')

        request = self.env['request.request'].new({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })
        request._onchange_update_contract()
        self.assertEqual(request.contract_id, self.customer_contract)

    def test_request_contract_changed_event_created(self):
        request = self.env['request.request'].create({
            'type_id': self.type_simple.id,
            'request_text': 'test on creation event when contract_id changed',
        })
        self.assertEqual(request.request_event_count, 1)
        self.assertEqual(request.request_event_ids.event_type_id.code,
                         'record-created')
        contract_ids = self.env['generic.contract'].search([]).ids
        request.contract_id = contract_ids[0]
        self.assertSetEqual(
            set(request.request_event_ids.mapped('event_type_id.code')),
            {'record-created', 'contract-changed'})
        self.assertEqual(request.request_event_count, 2)

    def test_guess_contract_srv_no_contract_related_to_partner(self):
        self.assertFalse(self.env['generic.contract'].search_count(
            [('partner_id', '=', self.env.user.partner_id.id)]))

        request = self.env['request.request'].new({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.env.user.partner_id.id,
        })
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertFalse(request.service_level_id)

        request.service_id = self.default_service
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertFalse(request.service_level_id)

        request.service_id = self.support_service_consulting
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertFalse(request.service_level_id)

        request.service_id = self.support_service_hosting
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertFalse(request.service_level_id)

    def test_guess_contract_srv_no_active_contract_related_to_partner(self):
        # Ensure inactive contracts will not be guessed
        self.assertEqual(self.customer_contract.state, 'draft')

        request = self.env['request.request'].new({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request.service_id = self.default_service
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request.service_id = self.support_service_consulting
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request.service_id = self.support_service_hosting
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

    @freeze_time('2018-03-15')
    def test_guess_contract_srv_no_active_contract_related_to_partner_2(self):
        # Ensure pending contracts will not be guessed
        self.assertEqual(self.customer_contract.state, 'draft')

        # Run schedulers
        self._run_contract_schedulers()

        self.assertEqual(self.customer_contract.state, 'pending')

        request = self.env['request.request'].new({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request.service_id = self.default_service
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request.service_id = self.support_service_consulting
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request.service_id = self.support_service_hosting
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

    @freeze_time('2018-04-15')
    def test_guess_contract_srv_act_contract_related_to_partner_exists(self):
        self.assertEqual(self.customer_contract.state, 'draft')
        # Run schedulers
        self._run_contract_schedulers()

        # Ensure contract is active
        self.assertEqual(self.customer_contract.state, 'active')

        # If no service defined on request, default contract will be guessed
        # as first contract related to partner
        request = self.env['request.request'].new({
            'type_id': self.type_simple.id,
            'request_text': 'test',
            'partner_id': self.request_partner.id,
        })
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertEqual(request.contract_id, self.customer_contract)
        self.assertEqual(request.service_level_id, self.service_level_2)

        # Change service to service not mentioned in any contract and see that
        # no contract guessed
        request.service_id = self.default_service
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)

        request.service_id = self.support_service_consulting
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertEqual(request.contract_id, self.customer_contract)
        self.assertEqual(request.service_level_id, self.service_level_1)

        request.service_id = self.support_service_development
        request._onchange_update_contract()
        request._onchange_update_service_level()
        self.assertFalse(request.contract_id)
        self.assertEqual(request.service_level_id, self.service_level_2)
