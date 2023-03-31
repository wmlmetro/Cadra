from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import (
    ReduceLoggingMixin,
)


class TestSaleOrder(ReduceLoggingMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super(TestSaleOrder, cls).setUpClass()
        cls.sale_order = cls.env.ref(
            'generic_request_sale.sale_order_1')
        cls.sale_order_line1 = cls.env.ref(
            'generic_request_sale.sale_order_line_1')
        cls.request_type = cls.env.ref(
            'generic_request.request_type_simple')
        cls.request_category = cls.env.ref(
            'generic_request.request_category_demo_technical')
        cls.request_stage_draft = cls.env.ref(
            'generic_request.request_stage_type_simple_draft')
        cls.request_stage_sent = cls.env.ref(
            'generic_request.request_stage_type_simple_sent')
        cls.request_stage_confirmed = cls.env.ref(
            'generic_request.request_stage_type_simple_confirmed')

    def test_sale_order(self):
        self.sale_order.action_confirm()
        request = self.sale_order.request_ids
        self.assertEqual(len(request), 2)
        self.assertEqual(request[0].type_id, self.request_type)
        self.assertEqual(request[0].category_id, self.request_category)
        self.assertEqual(request[0].author_id, self.sale_order.partner_id)
        self.assertEqual(
            request[0].request_text,
            '<p>New request created from SO (%s): %s</p>' % (
                request[0].sale_order_id.name,
                request[0].sale_order_line_id.name))

        self.assertEqual(request[1].type_id, self.request_type)
        self.assertEqual(request[1].category_id, self.request_category)
        self.assertEqual(request[1].author_id, self.sale_order.partner_id)
        self.assertEqual(
            request[0].request_text,
            '<p>New request created from SO (%s): %s</p>' % (
                request[0].sale_order_id.name,
                request[0].sale_order_line_id.name))

        self.assertEqual(self.sale_order_line1.qty_delivered, 0.0)

        self.assertEqual(request[0].stage_id, self.request_stage_draft)

        request[0].stage_id = self.request_stage_sent
        self.assertEqual(request[0].stage_id, self.request_stage_sent)

        request[0].stage_id = self.request_stage_confirmed
        self.assertEqual(request[0].stage_id, self.request_stage_confirmed)

        self.assertEqual(self.sale_order_line1.qty_delivered, 1.0)
