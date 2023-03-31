from odoo import api, fields, models


class GenericContractTemplateInvoiceLine(models.Model):
    _name = 'generic.contract.template.invoice.line'
    _description = 'Contract Template Invoice Lines'
    _order = "sequence,id"

    name = fields.Text(translate=True, required=True)
    product_id = fields.Many2one(
        'product.product', string='Product', required=False)
    contract_template_id = fields.Many2one(
        'generic.contract.template', string='Contract',
        required=True, ondelete='cascade')
    currency_id = fields.Many2one(
        'res.currency', related='contract_template_id.currency_id',
        store=True, readonly=True)
    quantity = fields.Char(
        default="1.0", required=True,
        help="Python expressiong that have to be used to compute quantity.")
    uom_id = fields.Many2one(
        'uom.uom', string='Unit of Measure', required=False)
    sequence = fields.Integer(
        default=5,
        help="Gives the sequence order when displaying of contract.")
    price_type = fields.Selection(
        [('fixed', 'Fixed Price'),
         ('employee_rate', 'Employee Rate'),
         ('pricelist', 'Pricelist Price'),
         ('py_expr', 'Python Expression')],
        required=True, default='fixed')
    price_fixed = fields.Monetary(
        digits='Account',
        string='Price (Fixed)')
    price_py_expr = fields.Char('Price (Py Expr)')
    price_er_employee_expr = fields.Char('Price Rate Employee')
    price_er_default_rate = fields.Monetary(
        currency_field='currency_id',
        string="Default Employee Rate",
        help="Default rate of employees per hour.")
    price_pricelist = fields.Monetary(
        compute="_compute_pricelist_price",
        digits='Account',
        string='Price (Pricelist)')
    price_display = fields.Char(
        compute='_compute_price_display',
        readonly=True)
    display_type = fields.Selection(
        [('line_section', "Section"),
         ('line_note', "Note")], default=False,
        help="Technical field for UX purpose.")

    @api.depends(
        'product_id', 'currency_id',
        'contract_template_id.pricelist_id')
    def _compute_pricelist_price(self):
        for rec in self:
            product = rec.product_id.with_context(
                pricelist=rec.contract_template_id.pricelist_id.id)
            if rec.contract_template_id.pricelist_id:
                rec.price_pricelist = product.price
            else:
                rec.price_pricelist = product.price

    @api.depends('price_type', 'price_fixed', 'price_pricelist',
                 'price_py_expr', 'contract_template_id.pricelist_id',
                 'contract_template_id.currency_id')
    def _compute_price_display(self):
        for rec in self:
            if rec.price_type == 'fixed':
                rec.price_display = "%s %s" % (
                    rec.price_fixed,
                    rec.contract_template_id.currency_id.symbol,
                )
            elif rec.price_type == 'pricelist':
                rec.price_display = "%s %s" % (
                    rec.price_pricelist,
                    rec.contract_template_id.currency_id.symbol,
                )
            elif rec.price_type == 'py_expr':
                rec.price_display = rec.price_py_expr
            elif rec.price_type == 'employee_rate':
                rec.price_display = 'Rate: %s' % rec.price_er_employee_expr
            else:
                rec.price_display = "UNKNOWN"

    @api.onchange('product_id', 'uom_id')
    def _onchange_product_id(self):
        if not self.product_id:
            return {'domain': {'uom_id': []}}
        if not self.uom_id or (self.product_id.uom_id.category_id.id !=
                               self.uom_id.category_id.id):
            self.uom_id = self.product_id.uom_id
        product = self.product_id
        name = product.display_name
        if product.description_sale:
            name += '\n' + product.description_sale
        self.name = name
        return {
            'domain': {
                'uom_id':
                    [('category_id', '=', self.uom_id.category_id.id)],
            },
        }

    def _prepare_contract_invoice_line(self, partner):
        return {
            'product_id': self.product_id.id,
            'quantity': self.quantity,
            'uom_id': self.uom_id.id,
            'sequence': self.sequence,
            'name': self.name,
            'display_type': self.display_type,
            'template_line_id': self.id,
            'price_type': self.price_type,
            'price_fixed': self.price_fixed,
            'price_py_expr': self.price_py_expr,
            'price_er_employee_expr': self.price_er_employee_expr,
            'price_er_default_rate': self.price_er_default_rate,
        }
