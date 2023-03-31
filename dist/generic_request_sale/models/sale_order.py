from odoo import models, fields, api

from odoo.addons.generic_request.tools.jinja import render_jinja_string
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    request_ids = fields.One2many(
        'request.request', 'sale_order_id')
    request_count = fields.Integer(
        compute='_compute_request_count', store=True,
        compute_sudo=True)

    @api.depends('request_ids')
    def _compute_request_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='request_ids')
        for record in self:
            record.request_count = mapped_data.get(record.id, 0)

    def action_confirm(self):
        result = super(SaleOrder, self).action_confirm()
        for so_line in self.order_line:
            if so_line.product_id.type != 'service':
                continue
            if not so_line.product_id.is_create_request:
                continue

            # Generate requests for this order line
            template = so_line.product_id
            for __ in range(int(so_line.product_uom_qty)):
                template.request_creation_template_id.do_create_request({
                    'sale_order_line_id': so_line.id,
                    'author_id': so_line.order_id.partner_id.id,
                    'request_text': render_jinja_string(
                        template.request_text_template, {
                            'sale_order': so_line.order_id,
                            'sale_order_line': so_line,
                        }),
                })
        return result

    def action_show_request(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            domain=[('sale_order_id', '=', self.id)],
        )
