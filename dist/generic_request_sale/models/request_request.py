import logging
from odoo import models, fields
from odoo.addons.generic_system_event import on_event

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = 'request.request'

    sale_order_line_id = fields.Many2one('sale.order.line')
    sale_order_id = fields.Many2one(
        related='sale_order_line_id.order_id', store=True)

    @on_event('stage-changed', 'closed', 'reopened')
    def _on_stage_changed__update_so_line(self, event):
        if self.sale_order_line_id:
            # Trigger recomputation of delivered (completed) requests
            order_line = self.sale_order_line_id
            order_line.qty_delivered = order_line._get_delivered_request_qty()
