import logging
from odoo.addons.generic_request.tests.common import AccessRightsCase

_logger = logging.getLogger(__name__)


class TestRequestSaleAccessRights(AccessRightsCase):

    def _read_sale_order_fields(self, user, sale_order):
        sale_order_action = self.env.ref('sale.action_orders')
        fields = list(
            self.env['sale.order'].with_user(
                user
            ).load_views(
                sale_order_action.views
            )['fields_views']['form']['fields']
        )
        return sale_order.with_user(user).read(fields)

    def test_read_request_with_sale_order(self):
        sale_order = self.env.ref(
            'generic_request_sale.sale_order_1')
        sale_order.action_confirm()
        requests = sale_order.request_ids
        requests.message_subscribe(self.demo_user.partner_id.ids)

        # ensure demo user can read all fields of parent request
        self._read_request_fields(self.demo_user, requests)

    def test_read_sale_order_with_requests(self):
        sale_order = self.env.ref(
            'generic_request_sale.sale_order_1')
        sale_order.user_id = self.env.ref('base.user_demo')
        self._read_sale_order_fields(
            self.env.ref('base.user_demo'),
            sale_order)
