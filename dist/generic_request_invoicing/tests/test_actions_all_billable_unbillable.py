from odoo import fields
from odoo.tools.float_utils import float_round
from odoo.addons.generic_request.tests.common import RequestCase


class TestActAllBillUnbil(RequestCase):

    @classmethod
    def setUpClass(cls):
        super(TestActAllBillUnbil, cls).setUpClass()
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
    def test_actions_all_billable_unbillable(self):
        Timesheet = self.env['request.timesheet.line']
        request = self.env['request.request'].create({
            'type_id': self.request_type.id,
            'request_text': 'test request',
            'partner_id': self.env.ref('base.res_partner_4').id,
        })

        timesheet_line1 = Timesheet.create({
            'activity_id': self.activity_id_1.id,
            'request_id': request.id,
            'is_billable': False,
            'amount': 1,
            'date_start': fields.Datetime.from_string("2021-07-14 12:07:35"),
            'date_end': fields.Datetime.from_string("2021-07-14 13:07:35"),
            })

        self.assertEqual(len(request.timesheet_line_ids), 1)
        self.assertEqual(timesheet_line1.amount, 1)
        self.assertEqual(
            timesheet_line1.date_start,
            fields.Datetime.from_string("2021-07-14 12:07:35"))
        self.assertEqual(
            timesheet_line1.date_end,
            fields.Datetime.from_string("2021-07-14 13:07:35"))
        self.assertTrue(timesheet_line1.enable_invoicing)
        self.assertFalse(timesheet_line1.is_billable)
        self.assertFalse(timesheet_line1.request_invoice_line_id)

        timesheet_line2 = Timesheet.create({
            'activity_id': self.activity_id_2.id,
            'request_id': request.id,
            'is_billable': False,
            'amount': 2,
            'date_start': fields.Datetime.from_string("2021-07-14 14:15:47"),
            'date_end': fields.Datetime.from_string("2021-07-14 16:15:47"),
        })

        self.assertEqual(len(request.timesheet_line_ids), 2)
        self.assertEqual(timesheet_line2.amount, 2)
        self.assertEqual(
            timesheet_line2.date_start,
            fields.Datetime.from_string("2021-07-14 14:15:47"))
        self.assertEqual(
            timesheet_line2.date_end,
            fields.Datetime.from_string("2021-07-14 16:15:47"))
        self.assertTrue(timesheet_line1.enable_invoicing)
        self.assertFalse(timesheet_line1.is_billable)
        self.assertFalse(timesheet_line1.request_invoice_line_id)

        request.action_make_all_billable()
        self.assertTrue(timesheet_line1.is_billable)
        self.assertTrue(timesheet_line1.request_invoice_line_id)
        self.assertTrue(timesheet_line2.is_billable)
        self.assertTrue(timesheet_line2.request_invoice_line_id)

        request.action_make_all_not_billable()
        self.assertFalse(timesheet_line1.is_billable)
        self.assertFalse(timesheet_line1.request_invoice_line_id)
        self.assertFalse(timesheet_line2.is_billable)
        self.assertFalse(timesheet_line2.request_invoice_line_id)

        timesheet_line1.is_billable = True
        self.assertTrue(timesheet_line1.is_billable)
        self.assertTrue(timesheet_line1.request_invoice_line_id)
        self.assertFalse(timesheet_line2.is_billable)
        self.assertFalse(timesheet_line2.request_invoice_line_id)

        invoice = request._action_generate_invoice()
        self.assertEqual(request.invoice_count, 1)
        self.assertEqual(invoice.amount_total,
                         float_round((41.34 * 1) * 1.15, 2))
        self.assertTrue(timesheet_line1.request_invoice_line_id.is_invoiced)
        self.assertTrue(
            timesheet_line1.request_invoice_line_ids.invoice_line_id)
        self.assertTrue(timesheet_line1.is_billable)
        self.assertTrue(timesheet_line1.request_invoice_line_id)
        self.assertFalse(timesheet_line2.is_billable)
        self.assertFalse(timesheet_line2.request_invoice_line_id)

        request.action_make_all_not_billable()
        self.assertTrue(timesheet_line1.is_billable)
        self.assertTrue(timesheet_line1.request_invoice_line_id)
        self.assertFalse(timesheet_line2.is_billable)
        self.assertFalse(timesheet_line2.request_invoice_line_id)

        request.action_make_all_billable()
        self.assertTrue(timesheet_line1.is_billable)
        self.assertTrue(timesheet_line1.request_invoice_line_id)
        self.assertTrue(timesheet_line2.is_billable)
        self.assertTrue(timesheet_line2.request_invoice_line_id)
