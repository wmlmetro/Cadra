import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    request_ids = fields.One2many(
        'request.request', 'sale_order_line_id', readonly=True)

    def _get_delivered_request_qty(self):
        self.ensure_one()
        qty = 0.0
        for request in self.request_ids:
            if (request.stage_id.type_id in
                    self.product_id.request_delivered_stage_type_ids):
                qty += 1.0
        return qty
