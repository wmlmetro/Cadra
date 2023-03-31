import logging
from datetime import date as dt

import psycopg2

from odoo.exceptions import ValidationError, UserError
from odoo import exceptions
from odoo.tools import mute_logger
from .common import TestGenericContractCommon, freeze_time

_logger = logging.getLogger(__name__)


class TestGenericContract(TestGenericContractCommon):

    def test_date_order_constraint(self):
        self.customer_contract.date_start = '2015-05-03'

        # ensure constrains 'date_start less date_end'
        with self.assertRaises(ValidationError):
            self.customer_contract.date_end = '2015-05-02'

        self.customer_contract.date_end = '2015-05-10'

    def test_draft_activate_contracts(self):
        # fix date_starts of existing contract
        # customer contract
        self.customer_contract.write({
            'date_start': '2015-05-10',
            'date_end': '2015-05-20',
        })
        # supplier contract
        self.supplier_contract.write({
            'date_start': '2015-05-02',
            'date_end': '2015-05-20',
        })

        # confirm one contract
        with freeze_time('2015-05-01'):

            self.supplier_contract.action_confirm()

        # ensure confirmed
        self.assertEqual(self.supplier_contract.state, 'pending')

        # activate contracts
        with freeze_time('2015-05-03'):
            self.activate_scheduler.method_direct_trigger()

        # ensure activated
        self.assertEqual(self.supplier_contract.state, 'active')

        self.assertEqual(self.customer_contract.state, 'draft')

    def test_closed_activate_contracts(self):
        # fix date_starts of existing contract
        # customer contract
        self.customer_contract.write({
            'date_start': '2015-05-10',
            'date_end': '2015-05-20',
        })
        # supplier contract
        self.supplier_contract.write({
            'date_start': '2015-05-02',
            'date_end': '2015-05-05',
        })

        # confirm contracts and close supplier contract
        with freeze_time('2015-05-09'):
            self.customer_contract.action_confirm()
            self.supplier_contract.action_confirm()
            self.supplier_contract.close_contract()

        # ensure done
        self.assertEqual(self.customer_contract.state, 'pending')

        self.assertEqual(self.supplier_contract.state, 'closed')

        # activate contracts
        with freeze_time('2015-05-11'):
            self.activate_scheduler.method_direct_trigger()

        # ensure activated
        self.assertEqual(self.customer_contract.state, 'active')

        self.assertEqual(self.supplier_contract.state, 'closed')

    def test_unlink(self):

        self.customer_contract.unlink()

        # ensure unlink
        self.assertFalse(self.customer_contract.exists())

        # fix date_starts supplier contract
        self.supplier_contract['date_start'] = '2015-05-02'

        # confirm supplier contract
        with freeze_time('2015-05-01'):
            self.supplier_contract.action_confirm()

        with self.assertRaises(UserError):
            self.supplier_contract.unlink()

        # ensure not unlink
        self.assertTrue(self.supplier_contract.exists())

    def test_ok_close_contracts(self):
        # fix date_start and date_end of existing contract
        # customer contract
        self.customer_contract.write({
            'date_start': '2015-05-02',
            'date_end': '2015-05-10',
        })

        # confirm customer contract
        with freeze_time('2015-05-03'):
            self.customer_contract.action_confirm()

        # ensure activated
        self.assertEqual(self.customer_contract.state, 'active')

        # close customer contract
        with freeze_time('2015-05-10'):
            self.customer_contract.action_close()

        # ensure closed
        self.assertEqual(self.customer_contract.state, 'closed')

        # return active state customer contract
        self.customer_contract.state = 'active'

        # ensure active
        self.assertEqual(self.customer_contract.state, 'active')

        # close customer contract
        with freeze_time('2015-05-10'):
            self.customer_contract.action_close()

        # ensure closed
        self.assertEqual(self.customer_contract.state, 'closed')

    def test_ok_close_contracts_different_dates(self):
        # fix date_start and date_end of existing contract
        # customer contract
        self.customer_contract.write({
            'date_start': '2015-05-02',
            'date_end': '2015-05-10',
        })

        # confirm customer contract
        with freeze_time('2015-05-03'):
            self.customer_contract.action_confirm()

        # ensure activated
        self.assertEqual(self.customer_contract.state, 'active')

        # ensure contracts
        self.assertEqual(self.customer_contract.state, 'active')
        self.assertEqual(self.customer_contract.date_end, dt(2015, 5, 10))
        self.assertFalse(self.customer_contract.date_closed)

        with freeze_time('2015-05-12'):
            self.customer_contract.action_close()

        # ensure contracts
        self.assertEqual(self.customer_contract.state, 'closed')
        self.assertEqual(self.customer_contract.date_end, dt(2015, 5, 10))
        self.assertEqual(self.customer_contract.date_closed, dt(2015, 5, 12))

    def test_scheduler_close_contracts(self):
        # fix date_start and date_end of existing contract
        # customer contract
        self.customer_contract.write({
            'date_start': '2015-05-02',
            'date_end': '2015-05-10',
        })
        # supplier contract
        self.supplier_contract.write({
            'date_start': '2015-05-02',
            'date_end': '2015-05-10',
        })

        with freeze_time('2015-05-03'):
            self.customer_contract.action_confirm()

            self.supplier_contract.action_confirm()

        # ensure correct activated
        self.assertEqual(self.customer_contract.state, 'active')
        self.assertEqual(self.supplier_contract.state, 'active')

        # scheduler close contracts
        with freeze_time('2015-05-10'):
            self.close_scheduler.method_direct_trigger()

        # ensure customer contract closed
        self.assertEqual(self.customer_contract.state, 'closed')
        # ensure supplier contract closed
        self.assertEqual(self.supplier_contract.state, 'closed')

    def test_close_contract_no_end_same_date(self):
        # We have active contract with start date today and no end date.
        # Ensure such contract will not be closed
        with freeze_time('2019-05-10'):
            contract = self.env['generic.contract'].create({
                'name': 'Test',
                'partner_id': self.env.ref('base.res_partner_2').id,
            })

        self.assertEqual(contract.date_start, dt(2019, 5, 10))
        self.assertFalse(contract.date_end)
        self.assertEqual(contract.state, 'draft')

        # Confirm contract
        with freeze_time('2019-05-10'):
            contract.action_confirm()

        self.assertEqual(contract.state, 'active')
        self.assertEqual(contract.date_start, dt(2019, 5, 10))
        self.assertFalse(contract.date_end)

        # Run scheduler to close contracts
        with freeze_time('2019-05-10'):
            self.env['generic.contract'].scheduler_close_contracts()

        # Ensure contract was not closed
        self.assertEqual(contract.state, 'active')
        self.assertEqual(contract.date_start, dt(2019, 5, 10))
        self.assertFalse(contract.date_end)

    def test_contract_api_methods_create_get(self):
        # Test contract api methods:
        # 1. Create contract from template
        # 2. Get active contract for partner
        contract = self.customer_template.create_contract(
            partner=self.partner_customer,
            date_start=self.today,
        )

        self.assertEqual(
            contract.template_id, self.customer_template)

        self.assertEqual(contract.partner_type, 'customer')
        self.assertEqual(contract.state, 'draft')
        self.assertEqual(contract.date_start, self.today)

        # Try to get contract for partner
        customer_contract = self.partner_customer.get_generic_contract()
        self.assertFalse(customer_contract)
        customer_contract = self.partner_customer.get_generic_contract(
            states='draft')
        self.assertEqual(customer_contract, contract)

        # Confirm contract
        contract.action_confirm_contracts()

        self.assertEqual(contract.partner_type, 'customer')
        self.assertEqual(contract.state, 'active')
        self.assertEqual(contract.date_start, self.today)

        # Try to get contract for partner
        customer_contract = self.partner_customer.get_generic_contract()
        self.assertEqual(customer_contract, contract)

    def test_contract_api_methods_create_get_contact(self):
        # Test contract api methods:
        # 1. Create contract from template
        # 2. Get active contract for partner
        partner_contact = self.env.ref('base.res_partner_address_15')
        contract = self.customer_template.create_contract(
            partner=partner_contact,
            date_start=self.today,
        )

        self.assertEqual(
            contract.template_id, self.customer_template)

        self.assertEqual(contract.partner_type, 'customer')
        self.assertEqual(contract.state, 'draft')
        self.assertEqual(contract.date_start, self.today)
        self.assertEqual(contract.partner_id, self.partner_customer)

        # Try to get contract for partner
        customer_contract = self.partner_customer.get_generic_contract()
        self.assertFalse(customer_contract)
        customer_contract = self.partner_customer.get_generic_contract(
            states='draft')
        self.assertEqual(customer_contract, contract)

        # Confirm contract
        contract.action_confirm_contracts()

        self.assertEqual(contract.partner_type, 'customer')
        self.assertEqual(contract.state, 'active')
        self.assertEqual(contract.date_start, self.today)
        self.assertEqual(contract.partner_id, self.partner_customer)

        # Try to get contract for partner
        customer_contract = self.partner_customer.get_generic_contract()
        self.assertEqual(customer_contract, contract)

    def test_convert_to_draft(self):
        contract = self.customer_template.create_contract(
            partner=self.partner_customer,
            date_start=self.today,
        )

        self.assertEqual(
            contract.template_id, self.customer_template)

        self.assertEqual(contract.partner_type, 'customer')
        self.assertEqual(contract.state, 'draft')
        self.assertEqual(contract.date_start, self.today)

        # Confirm contract
        contract.action_confirm_contracts()

        self.assertEqual(contract.state, 'active')

        # Convert contract to draft
        contract.action_to_draft()
        self.assertEqual(contract.state, 'draft')

    def test_convert_to_draft_closed(self):
        contract = self.customer_template.create_contract(
            partner=self.partner_customer,
            date_start=self.today,
        )

        self.assertEqual(
            contract.template_id, self.customer_template)

        self.assertEqual(contract.partner_type, 'customer')
        self.assertEqual(contract.state, 'draft')
        self.assertEqual(contract.date_start, self.today)

        # Confirm contract
        contract.action_confirm_contracts()

        self.assertEqual(contract.state, 'active')

        contract.action_close()

        # Cannot convert to draft closed contract
        with self.assertRaises(exceptions.UserError):
            contract.action_to_draft()

    @mute_logger('odoo.sql_db')
    def test_contract_number_unique(self):
        # test constraint contract_number_unique:
        contract = self.Contract.create({
            'partner_type': 'customer',
            'partner_id': self.customer_contract.partner_id.id,
            'date_start': self.today,
            'date_end': self.today,
            'name': 'test_4',
        })
        with self.assertRaises(psycopg2.IntegrityError):
            contract.write({
                'number': self.customer_contract.number,
            })
            contract.flush()
