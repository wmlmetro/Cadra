from odoo import models, fields, api


class RequestInvoiceLine(models.Model):
    _name = 'request.invoice.line'
    _description = 'Request Invoice Line'

    request_id = fields.Many2one('request.request', required=True, index=True)
    product_id = fields.Many2one(
        'product.product', domain=[('type', '=', 'service')],
        required=True)
    description = fields.Text(required=True)
    quantity = fields.Float(
        default=1.0, digits='Product Unit of Measure',
        required=True)
    uom_id = fields.Many2one(
        'uom.uom', string='Unit of Measure')
    price_unit = fields.Monetary(
        digits='Product Price', required=True)
    price_subtotal = fields.Monetary(
        compute='_compute_price_subtotal', readonly=True)
    currency_id = fields.Many2one(
        'res.currency', related='request_id.currency_id', readonly=True)
    timesheet_line_id = fields.Many2one(
        'request.timesheet.line', readonly=True)

    invoice_line_ids = fields.One2many(
        'account.move.line', 'request_invoice_line_id', readonly=True,
        groups="account.group_account_invoice")
    invoice_line_id = fields.Many2one(
        'account.move.line', readonly=True, store=True,
        compute='_compute_is_invoiced',
        groups="account.group_account_invoice")
    is_invoiced = fields.Boolean(
        compute='_compute_is_invoiced', readonly=True, store=True,
        help='Indicates whether this line is present in active invoice.')

    @api.depends('quantity', 'price_unit')
    def _compute_price_subtotal(self):
        for rec in self:
            rec.price_subtotal = rec.price_unit * rec.quantity

    @api.depends('invoice_line_ids', 'invoice_line_id',
                 'invoice_line_id.move_id.state')
    def _compute_is_invoiced(self):
        for record in self:
            ilines = record.sudo().invoice_line_ids.filtered(
                lambda r: r.move_id.state != 'cancel')
            iline = ilines if len(ilines) == 1 else False
            if iline:
                record.is_invoiced = True
                record.invoice_line_id = iline
            else:
                record.is_invoiced = False
                record.invoice_line_id = False

    @api.onchange('product_id', 'request_id', 'uom_id')
    def _onchange_product_id(self):
        if not self.product_id:
            return {'domain': {'uom_id': []}}
        if not self.uom_id or (self.product_id.uom_id.category_id.id !=
                               self.uom_id.category_id.id):
            self.uom_id = self.product_id.uom_id

        product = self.product_id.with_context(
            lang=self.request_id.partner_id.lang,
            pricelist=self.request_id.pricelist_id.id,
            partner=self.request_id.partner_id.id,
            uom=self.uom_id.id)
        name = product.name_get()[0][1]
        if product.description_sale:
            name += '\n' + product.description_sale
        self.description = name

        price_unit = product.price
        if not price_unit:
            price_unit = product.lst_price
        self.price_unit = price_unit
        return {
            'domain': {
                'uom_id': [
                    ('category_id', '=', product.uom_id.category_id.id)],
            }
        }

    def _prepare_invoice_line_data(self):
        """ Prepare initial data for invoice line.
        """
        return {
            'product_id': self.product_id.id,
            'quantity': self.quantity,
            'product_uom_id': self.uom_id.id,
            'name': self.description,
            'price_unit': self.price_unit,
            'request_invoice_line_id': self.id,
            'tax_ids': [],
        }

    def prepare_invoice_line(self, invoice_data):
        self.ensure_one()
        return self._prepare_invoice_line_data()

    def name_get(self):
        res = []
        for record in self:
            name = "%s [%s %s]" % (
                record.timesheet_line_id.display_name,
                record.price_subtotal,
                record.currency_id.display_name,
            )
            res += [(record.id, name)]
        return res
