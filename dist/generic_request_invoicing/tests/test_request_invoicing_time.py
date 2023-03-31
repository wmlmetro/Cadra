from odoo import exceptions, fields
from odoo.tools.float_utils import float_round
from odoo.addons.generic_request.tests.common import (
    RequestCase,
    freeze_time
)


class TestWizardLogTime(RequestCase):

    @classmethod
    def setUpClass(cls):
        super(TestWizardLogTime, cls).setUpClass()
        cls.request_type = cls.env.ref(
            'generic_request.request_type_simple')
        cls.activity_id_1 = cls.env.ref(
            'generic_request.request_timesheet_activity_coding')
        cls.activity_id_2 = cls.env.ref(
            'generic_request.request_timesheet_activity_analysis')
        cls.user = cls.env.ref('generic_request.user_demo_request')
        cls.default_product = cls.env.ref(
            'generic_request_invoicing.product_timetracking')

    # pylint: disable=too-many-statements
    def test_log_time_start_stop(self):
        Timesheet = self.env['request.timesheet.line']
        request = self.env['request.request'].create({
            'type_id': self.request_type.id,
            'request_text': 'test request',
            'partner_id': self.env.ref('base.res_partner_4').id,
        })
        self.assertTrue(request.pricelist_id)

        self.assertEqual(len(request.timesheet_line_ids), 0)
        self.assertEqual(request.timesheet_start_status, 'not-started')
        self.assertFalse(Timesheet._find_running_lines())

        # Add unbillable line
        with freeze_time("2020-01-14 03:00:00"):
            request.action_start_work()
            self.assertEqual(request.timesheet_start_status, 'started')
            self.assertEqual(len(request.timesheet_line_ids), 1)

            running = Timesheet._find_running_lines()
            self.assertEqual(running.request_id, request)
            self.assertEqual(
                running.date_start,
                fields.Datetime.from_string("2020-01-14 03:00:00"))
            self.assertEqual(
                running.date_end,
                False)
            self.assertEqual(running.amount, 0.0)

        with freeze_time("2020-01-14 05:00:00"):
            action = request.action_stop_work()
            wizard = self.env[action['res_model']].with_context(
                **action['context']
            ).create({
                'activity_id': self.activity_id_2.id,
                'is_billable': False,
            })
            self.assertEqual(wizard.amount, 2.0)
            wizard.do_stop_work()
            tline = wizard.timesheet_line_id

            self.assertEqual(len(request.timesheet_line_ids), 1)
            self.assertEqual(tline.amount, 2)
            self.assertEqual(
                tline.date_start,
                fields.Datetime.from_string("2020-01-14 03:00:00"))
            self.assertEqual(
                tline.date_end,
                fields.Datetime.from_string("2020-01-14 05:00:00"))
            self.assertTrue(tline.enable_invoicing)
            self.assertFalse(tline.is_billable)
            self.assertFalse(tline.request_invoice_line_id)

        # Add billable line
        with freeze_time("2020-01-14 06:00:00"):
            request.action_start_work()
            self.assertEqual(request.timesheet_start_status, 'started')
            self.assertEqual(len(request.timesheet_line_ids), 2)

            running = Timesheet._find_running_lines()
            self.assertEqual(running.request_id, request)
            self.assertEqual(
                running.date_start,
                fields.Datetime.from_string("2020-01-14 06:00:00"))
            self.assertEqual(
                running.date_end,
                False)
            self.assertEqual(running.amount, 0.0)

        with freeze_time("2020-01-14 07:30:00"):
            action = request.action_stop_work()
            wizard = self.env[action['res_model']].with_context(
                **action['context']
            ).create({
                'activity_id': self.activity_id_2.id,
                'is_billable': True,
            })
            self.assertEqual(wizard.amount, 1.5)
            wizard.do_stop_work()
            tline_1 = wizard.timesheet_line_id

            self.assertEqual(len(request.timesheet_line_ids), 2)
            self.assertEqual(tline_1.amount, 1.5)
            self.assertEqual(
                tline_1.date_start,
                fields.Datetime.from_string("2020-01-14 06:00:00"))
            self.assertEqual(
                tline_1.date_end,
                fields.Datetime.from_string("2020-01-14 07:30:00"))
            self.assertTrue(tline_1.enable_invoicing)
            self.assertTrue(tline_1.is_billable)
            self.assertTrue(tline_1.request_invoice_line_id)
            self.assertEqual(
                tline_1.request_invoice_line_id.product_id,
                self.default_product)
            self.assertEqual(
                tline_1.request_invoice_line_id.quantity, 1.5)
            self.assertEqual(
                tline_1.request_invoice_line_id.price_unit, 41.34)
            self.assertEqual(
                tline_1.request_invoice_line_id.price_subtotal,
                float_round(41.34 * 1.5, 2))
            self.assertFalse(tline_1.request_invoice_line_id.is_invoiced)
            self.assertEqual(
                request.price_total,
                float_round(41.34 * 1.5, 2))

        # Add invoice line manually
        ri_line1 = self.env['request.invoice.line'].new({
            'request_id': request.id,
            'product_id': self.default_product.id,
            'quantity': 3.4,
        })
        ri_line1._onchange_product_id()
        ri_line1 = self.env['request.invoice.line'].create(
            ri_line1._convert_to_write(ri_line1._cache))
        self.assertEqual(
            ri_line1.uom_id, self.env.ref('uom.product_uom_hour'))
        self.assertEqual(ri_line1.price_unit, 41.34)
        self.assertEqual(ri_line1.price_subtotal, float_round(41.34 * 3.4, 2))
        self.assertFalse(ri_line1.is_invoiced)
        self.assertEqual(
            ri_line1.description,
            "[REQTIMETRACK] Time Tracking\nTime tracked on requests")
        self.assertEqual(
            request.price_total,
            float_round(41.34 * 3.4 + 41.34 * 1.5, 2))

        # Generate invoice
        request.action_generate_invoice()

        self.assertEqual(request.invoice_count, 1)
        invoice = request.invoice_ids

        # Clean up taxes (to simplify tests logic)
        # invoice.invoice_line_ids.write({'tax_ids': [(5, 0)]})
        # invoice.write({'tax_line_ids': [(5, 0)]})

        self.assertEqual(
            invoice.amount_total,
            float_round(41.34 * 3.4 + 41.34 * 1.5 + 30.3849, 2))
        self.assertTrue(tline_1.request_invoice_line_id.is_invoiced)
        self.assertTrue(ri_line1.is_invoiced)

        # Try to generate invoice again
        with self.assertRaises(exceptions.UserError):
            # Nothing to invoice
            request.action_generate_invoice()

        # Make unbillable line billable
        tline.is_billable = True

        # Recompute fields on record, because in Odoo 13, in may not be
        # recomputed yet
        tline.recompute()

        self.assertTrue(tline.is_billable)
        self.assertTrue(tline.request_invoice_line_ids)
        self.assertTrue(tline.request_invoice_line_id)
        self.assertEqual(
            tline.request_invoice_line_id.product_id,
            self.default_product)
        self.assertEqual(
            tline.request_invoice_line_id.quantity, 2.0)
        self.assertEqual(
            tline.request_invoice_line_id.price_unit, 41.34)
        self.assertEqual(
            tline.request_invoice_line_id.price_subtotal,
            float_round(41.34 * 2.0, 2))
        self.assertFalse(tline.request_invoice_line_id.is_invoiced)
        self.assertEqual(
            request.price_total,
            float_round(41.34 * 3.4 + 41.34 * 1.5 + 41.34 * 2.0, 2))

        # Try to generate one more invoice
        invoice2 = request._action_generate_invoice()

        # Clean up taxes (to simplify tests logic)
        invoice2.invoice_line_ids.write({'tax_ids': [(5, 0)]})
        # invoice2.write({'tax_line_ids': [(5, 0)]})

        self.assertEqual(request.invoice_count, 2)
        self.assertEqual(
            invoice2.amount_total,
            float_round(41.34 * 2.0 + 12.402, 2))
        self.assertTrue(tline.request_invoice_line_id.is_invoiced)
