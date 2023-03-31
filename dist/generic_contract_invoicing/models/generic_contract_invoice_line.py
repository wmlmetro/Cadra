import logging
from odoo import api, fields, models

try:
    from first import first
except (ImportError, IOError):
    logging.getLogger(__name__).error(
        "Please, install python package 'first'!")

_logger = logging.getLogger(__name__)


class GenericContractInvoiceLine(models.Model):
    _name = 'generic.contract.invoice.line'
    _description = 'Contract Invoice Lines'
    _order = "sequence,id"

    name = fields.Char(required=True, string="Description")
    product_id = fields.Many2one(
        'product.product', string='Product', required=False)
    contract_id = fields.Many2one(
        'generic.contract', string='Contract',
        required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(
        'res.currency', related='contract_id.currency_id',
        store=True, readonly=True)
    quantity = fields.Char(
        default="1.0", required=True,
        help="Python expressiong that have to be used to compute quantity.")
    uom_id = fields.Many2one(
        'uom.uom', string='Unit of Measure', required=False)
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
    price_er_employee_expr = fields.Char('Price (Employee Expr)')
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
    sequence = fields.Integer(
        default=5,
        help="Gives the sequence order when displaying inside contract.")
    template_line_id = fields.Many2one(
        'generic.contract.template.invoice.line')

    display_type = fields.Selection(
        [('line_section', "Section"),
         ('line_note', "Note")], default=False,
        help="Technical field for UX purpose.")

    @api.depends(
        'product_id', 'currency_id',
        'contract_id.pricelist_id')
    def _compute_pricelist_price(self):
        for rec in self:
            product = rec.product_id.with_context(
                pricelist=rec.contract_id.pricelist_id.id,
                partner=rec.contract_id.partner_id.id)
            if rec.contract_id.pricelist_id:
                rec.price_pricelist = product.price
            else:
                rec.price_pricelist = product.price

    @api.depends('price_type', 'price_fixed', 'price_pricelist',
                 'price_py_expr', 'contract_id.pricelist_id',
                 'contract_id.currency_id')
    def _compute_price_display(self):
        for rec in self:
            if rec.price_type == 'fixed':
                rec.price_display = "%s %s" % (
                    rec.price_fixed,
                    rec.contract_id.currency_id.symbol,
                )
            elif rec.price_type == 'pricelist':
                rec.price_display = "%s %s" % (
                    rec.price_pricelist,
                    rec.contract_id.currency_id.symbol,
                )
            elif rec.price_type == 'py_expr':
                rec.price_display = rec.price_py_expr
            elif rec.price_type == 'employee_rate':
                rec.price_display = 'Rate: %s' % rec.price_er_employee_expr
            else:
                rec.price_display = "UNKNOWN"

    @api.onchange('product_id', 'price_type', 'contract_id')
    def _onchange_product_id(self):
        if not self.product_id:
            return {'domain': {'uom_id': []}}
        if not self.uom_id or (self.product_id.uom_id.category_id.id !=
                               self.uom_id.category_id.id):
            self.uom_id = self.product_id.uom_id

        product = self.product_id.with_context(
            lang=self.contract_id.partner_id.lang,
            pricelist=self.contract_id.pricelist_id.id,
            partner=self.contract_id.partner_id.id)
        name = product.name_get()[0][1]
        if product.description_sale:
            name += '\n' + product.description_sale
        self.name = name

        if self.price_type == 'fixed':
            self.price_fixed = product.price
        return {
            'domain': {
                'uom_id': [
                    ('category_id', '=', product.uom_id.category_id.id)],
            }
        }

    def prepare_invoice_line_data(self, invoice):
        """ Prepare initial data for invoice line.
            This data will be forwarded to template processor,
            then it will be postprocessed.
        """
        res = {
            'move_id': invoice.id,
            'product_id': self.product_id.id,
            'quantity': self.quantity,
            'product_uom_id': self.uom_id.id,
            'name': self.name,
            'display_type': self.display_type,
            'price_type': self.price_type,
            'price_fixed': self.price_fixed,
            'price_py_expr': self.price_py_expr,
            'price_er_employee_expr': self.price_er_employee_expr,
            'price_er_default_rate': self.price_er_default_rate,
        }

        return res

    @api.model
    def _post_process_invoice_line__fix_price(self, contract, invoice, data):
        """ Return changed data
        """
        result = dict(data)
        price_type = result.pop('price_type')
        price_fixed = result.pop('price_fixed')
        price_py_expr = result.pop('price_py_expr')
        price_er_employee_expr = result.pop('price_er_employee_expr')
        price_er_default_rate = result.pop('price_er_default_rate')

        if price_type == 'fixed':
            result['price_unit'] = price_fixed
        elif price_type == 'pricelist' and result.get('product_id'):
            result['price_unit'] = self.env['product.product'].browse(
                result['product_id']
            ).with_context(
                lang=contract.partner_id.lang,
                pricelist=contract.pricelist_id.id,
                partner=contract.partner_id.id,
            ).price
        elif price_type == 'py_expr':
            result['price_unit'] = float(price_py_expr)
        elif price_type == 'employee_rate':
            price_unit = contract.get_employee_rate(price_er_employee_expr)
            result['price_unit'] = \
                float(price_unit) or float(price_er_default_rate)
        else:
            result['price_unit'] = 0.0

        return result

    @api.model
    def postprocess_invoice_line_data(self, contract, invoice, data):
        """ Return dictionary with data prepared for writing to invoice lines.
            This data will be processed via StackProcess later
        """
        company_id = invoice.company_id

        # Fix price (compute price_unit)
        result = self._post_process_invoice_line__fix_price(
            contract, invoice, data)
        invoice_line = self.env['account.move.line'].new(result)
        if not invoice_line.product_id:
            invoice_line.price_unit = False
            return invoice_line._convert_to_write(invoice_line._cache)

        #  Guess account and set taxes for invocie lines
        account = invoice_line._get_computed_account()
        # invoice.type, invoice_line.product_id,
        # invoice.fiscal_position_id, company_id)
        if account:
            invoice_line.account_id = account.id

        # Keep only taxes of the company
        # Copy and past from original Odoo code (_set_taxes)
        if invoice_line.move_id.move_type in ('out_invoice', 'out_refund'):
            taxes = first([
                invoice_line.product_id.taxes_id.filtered(
                    lambda r: r.company_id == company_id),
                invoice_line.account_id.tax_ids,
                invoice_line.move_id.company_id.account_sale_tax_id,
            ])
        else:
            taxes = first([
                invoice_line.product_id.supplier_taxes_id.filtered(
                    lambda r: r.company_id == company_id),
                invoice_line.account_id.tax_ids,
                invoice_line.move_id.company_id.account_purchase_tax_id,
            ])

        # Fix taxes: in some cases taxes is None, so convert it to empty
        # recordset
        taxes = taxes if taxes else self.env['account.tax'].browse()

        invoice_line.tax_ids = fp_taxes = (
            invoice_line.move_id.fiscal_position_id.map_tax(
                taxes,
            )
        )

        # Fix price (tax included).
        # TODO: Do we need this in contracts?
        invoice_line.price_unit = (
            self.env['account.tax']._fix_tax_included_price(
                invoice_line.price_unit, taxes, fp_taxes)
        )

        return invoice_line._convert_to_write(invoice_line._cache)

    def _postprocess_after_template(self):
        """ Run post-processing routines after this line was generated from
            contract template
        """
        self.ensure_one()
