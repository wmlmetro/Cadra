from odoo import fields
from odoo import exceptions
from odoo.addons.generic_contract.tests.common import (
    TestGenericContractCommon,
    freeze_time,
)


class ContractInvoicingTest(TestGenericContractCommon):

    @classmethod
    def setUpClass(cls):
        super(ContractInvoicingTest, cls).setUpClass()

        cls.product_consulting = cls.env.ref(
            'generic_contract_invoicing.product_consulting')

    def setUp(self):
        super(ContractInvoicingTest, self).setUp()

        self.registry.enter_test_mode(self.cr)
        self.addCleanup(self.registry.leave_test_mode)

    def test_constraint_recurring_period_raise(self):
        self.assertTrue(self.customer_contract.recurring_invoices)
        self.assertEqual(self.customer_contract.recurring_period, 1)

        with self.assertRaises(exceptions.ValidationError):
            self.customer_contract.recurring_period = 0

    def test_constraint_recurring_period_no_raise(self):
        self.assertTrue(self.customer_contract.recurring_invoices)
        self.assertEqual(self.customer_contract.recurring_period, 1)

        # When recurring invoices is False, then we do not check recurring
        # period
        self.customer_contract.recurring_invoices = False
        self.customer_contract.recurring_period = 0
        self.customer_contract.recurring_period = -1

    def test_contract_template_invoice_line_onchange_product(self):
        new_line = self.env['generic.contract.template.invoice.line'].new({
            'contract_template_id': self.template_basic_support.id,
        })
        res = new_line._onchange_product_id()
        self.assertEqual(res, {'domain': {'uom_id': []}})

        new_line.product_id = self.product_consulting
        res = new_line._onchange_product_id()
        self.assertEqual(
            res['domain']['uom_id'],
            [('category_id', '=', self.env.ref('uom.uom_categ_wtime').id)])
        self.assertEqual(
            new_line.uom_id,
            self.env.ref('uom.product_uom_hour'))

    def test_contract_invoice_line_onchange_product(self):
        new_line = self.env['generic.contract.invoice.line'].new({
            'contract_id': self.customer_contract.id,
        })
        res = new_line._onchange_product_id()
        self.assertEqual(res, {'domain': {'uom_id': []}})

        new_line.product_id = self.product_consulting
        res = new_line._onchange_product_id()
        self.assertEqual(
            res['domain']['uom_id'],
            [('category_id', '=', self.env.ref('uom.uom_categ_wtime').id)])
        self.assertEqual(
            new_line.uom_id,
            self.env.ref('uom.product_uom_hour'))
        self.assertEqual(
            new_line.name,
            "Consulting\nConsulting Services")

    def test_contract_template_journal_type(self):
        self.assertEqual(self.template_basic_support.journal_type, 'sale')
        self.assertEqual(self.supplier_template.journal_type, 'purchase')

    def test_basic_flow(self):
        # pylint: disable=too-many-statements

        # Test pre-conditions for test
        self.assertEqual(
            len(self.template_basic_support.recurring_invoice_line_ids), 1)
        self.assertEqual(
            self.template_basic_support.recurring_invoice_line_ids.product_id,
            self.product_consulting)
        self.assertEqual(
            self.template_basic_support.recurring_invoice_line_ids.quantity,
            '50')
        self.assertEqual(
            self.template_basic_support.recurring_invoice_line_ids.price_fixed,
            42.78)

        # Create contract from template
        with freeze_time('2019-05-10'):
            wizard = self.ContractCreateWizard.new({
                'partner_type': 'customer',
                'partner_id': self.partner_customer.id,
                'template_id': self.template_basic_support.id,
                'user_id': self.env.user.id,
                'date_start': fields.Date.from_string('2019-05-14'),
            })
            contract = wizard._create_contract()
            contract.action_confirm()

            self.assertEqual(contract.state, 'pending')
            self.assertTrue(contract.recurring_invoices)
            self.assertEqual(contract.recurring_type, 'monthly-last-day')
            self.assertEqual(contract.recurring_period, 1)
            self.assertEqual(
                contract.recurring_next_date,
                fields.Date.from_string('2019-05-31'))
            self.assertEqual(
                len(contract.recurring_invoice_line_ids), 1)
            self.assertEqual(
                contract.recurring_invoice_line_ids.product_id,
                self.product_consulting)
            self.assertEqual(
                contract.recurring_invoice_line_ids.quantity, '50')
            self.assertEqual(
                contract.recurring_invoice_line_ids.price_fixed, 42.78)

            contract.activate_contract()
            self.assertEqual(contract.state, 'pending')

        with freeze_time('2019-05-14'):
            contract.activate_contract()
            self.assertEqual(contract.state, 'active')

            self.assertEqual(contract.account_invoice_count, 0)

            # Run scheduler
            self.env.ref(
                'generic_contract_invoicing.'
                'generic_contract_recurring_create_invoice'
            ).method_direct_trigger()

            # See no invoices generated
            self.assertEqual(contract.account_invoice_count, 0)

        with freeze_time('2019-05-31'):
            self.assertEqual(contract.account_invoice_count, 0)

            # Run scheduler
            self.env.ref(
                'generic_contract_invoicing.'
                'generic_contract_recurring_create_invoice'
            ).method_direct_trigger()
            contract.invalidate_cache()

            # See no invoices generated
            self.assertEqual(contract.account_invoice_count, 1)

            # Check generated invoice
            invoice = contract.account_invoice_ids
            self.assertEqual(invoice.partner_id, self.partner_customer)
            self.assertEqual(invoice.move_type, 'out_invoice')
            self.assertEqual(invoice.currency_id, self.env.ref('base.USD'))
            # Taxes applied on invoice, thus total price is increased
            self.assertEqual(invoice.amount_total, 2459.85)
            self.assertEqual(len(invoice.invoice_line_ids), 1)
            self.assertEqual(
                invoice.invoice_line_ids.product_id, self.product_consulting)
            self.assertEqual(invoice.invoice_line_ids.quantity, 50)
            self.assertEqual(invoice.invoice_line_ids.price_unit, 42.78)
            self.assertEqual(invoice.invoice_line_ids.price_subtotal, 2139.00)
            self.assertEqual(
                invoice.invoice_date,
                fields.Date.from_string('2019-05-31'))

            # Check that next recurring date changed
            self.assertEqual(
                contract.recurring_next_date,
                fields.Date.from_string('2019-06-30'))

        with freeze_time('2019-07-05'):
            self.assertEqual(contract.account_invoice_count, 1)

            old_invoices = contract.account_invoice_ids

            # Run manual trigger
            contract.action_recurring_create_invoices()
            self.assertEqual(contract.account_invoice_count, 2)

            # Check generated invoice
            invoice = contract.account_invoice_ids - old_invoices
            self.assertEqual(invoice.partner_id, self.partner_customer)
            self.assertEqual(invoice.move_type, 'out_invoice')
            self.assertEqual(invoice.currency_id, self.env.ref('base.USD'))
            self.assertEqual(invoice.amount_total, 2459.85)
            self.assertEqual(len(invoice.invoice_line_ids), 1)
            self.assertEqual(
                invoice.invoice_line_ids.product_id, self.product_consulting)
            self.assertEqual(invoice.invoice_line_ids.quantity, 50)
            self.assertEqual(invoice.invoice_line_ids.price_unit, 42.78)
            self.assertEqual(invoice.invoice_line_ids.price_subtotal, 2139.00)
            self.assertEqual(
                invoice.invoice_date,
                fields.Date.from_string('2019-06-30'))

            # Check that next recurring date changed
            self.assertEqual(
                contract.recurring_next_date,
                fields.Date.from_string('2019-07-31'))
