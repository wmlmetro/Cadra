import logging
from ast import literal_eval

from odoo.addons.generic_request.tests.common import freeze_time
from odoo.tests.common import Form
from .common import TestRequestContractCommon

_logger = logging.getLogger(__name__)


class TestRequestContractService(TestRequestContractCommon):

    def test_write_request_partner_service_level(self):
        # fix date_begin and date_end of customer contract
        self.customer_contract.write({
            'date_begin': '2015-05-02',
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
        with Form(self.env['request.request']) as request_form:

            # Ensure that there is no contract
            # and all services could be selected
            self.assertFalse(request_form.contract_id)
            expected_classifier_service_ids = self.env[
                'request.classifier'].search([]).mapped('service_id').ids
            self.assertListEqual(
                literal_eval(request_form.service_id_domain),
                [('id', 'in', expected_classifier_service_ids)])

            # Set partner for contract
            request_form.partner_id = self.request_partner

            # Ensure that contract was detected and selectable services are
            # restricted by contract's services
            self.assertEqual(request_form.contract_id, self.customer_contract)
            self.assertEqual(len(request_form.service_id_domain[2]), 1)
            str_domain_to_list = literal_eval(request_form.service_id_domain)
            self.assertEqual(str_domain_to_list[0], '&')
            self.assertEqual(len(str_domain_to_list[2][2]), 1)
            self.assertEqual(
                str_domain_to_list[2][2][0],
                self.support_service_consulting.id)

            # This is needed to properly save the form with required fields
            request_form.request_text = 'test'
            request_form.type_id = self.type_simple
            request_form.save()

    @freeze_time('2018-04-15')
    def test_onchange_contract_restrict_service_clean_service(self):
        self.assertEqual(self.customer_contract.state, 'draft')
        # Run schedulers
        self._run_contract_schedulers()

        # Ensure contract is active
        self.assertEqual(self.customer_contract.state, 'active')

        with Form(self.env['request.request']) as request_form:
            # Create contract with default service
            request_form.service_id = self.default_service
            request_form.type_id = self.type_simple
            request_form.request_text = 'test'
            request_form.partner_id = self.request_partner

            self.assertEqual(request_form.type_id, self.type_simple)
            self.assertEqual(request_form.partner_id, self.request_partner)
            self.assertEqual(request_form.service_id, self.default_service)

            self.assertFalse(request_form.contract_id)
            self.assertEqual(request_form.service_id, self.default_service)

            # Set contract manually
            request_form.contract_id = self.customer_contract

            # Ensure service got new domain
            self.assertFalse(request_form.service_id)
            service_id_domain = literal_eval(request_form.service_id_domain)
            self.assertEqual(len(service_id_domain), 3)
            self.assertEqual(service_id_domain[0], '&')
            self.assertEqual(service_id_domain[2][2][0],
                             self.support_service_consulting.id)
            request_form.save()
