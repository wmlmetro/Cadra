from odoo import models, fields, api, exceptions, _
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class RequestRequest(models.Model):
    _inherit = 'request.request'

    enable_invoicing = fields.Boolean(
        related='type_id.enable_invoicing', readonly=True)
    pricelist_id = fields.Many2one('product.pricelist', 'Pricelist')
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.user.company_id.currency_id,
    )
    price_total = fields.Monetary(compute='_compute_price_total')
    request_invoice_line_ids = fields.One2many(
        'request.invoice.line', 'request_id')
    request_to_invoice_line_ids = fields.One2many(
        'request.invoice.line', 'request_id',
        domain=[('is_invoiced', '=', False)],
        readonly=True,
        help='Contains list of request invoice lines that are not present '
             'in any active invoice')
    invoice_ids = fields.One2many(
        'account.move', 'request_id', readonly=True)
    invoice_count = fields.Integer(
        compute='_compute_invoice_count', compute_sudo=True)

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='invoice_ids', sudo=True)
        for record in self:
            record.invoice_count = mapped_data.get(record.id, 0)

    @api.depends('request_invoice_line_ids')
    def _compute_price_total(self):
        for rec in self:
            price_total = 0.0
            # TODO: use read_group to increase performance?
            for invoice_line in rec.request_invoice_line_ids:
                price_total += invoice_line.price_subtotal
            rec.price_total = price_total

    @api.model
    def _add_missing_default_values(self, values):
        res = super(RequestRequest, self)._add_missing_default_values(values)

        if res.get('partner_id') and 'pricelist_id' not in values:
            partner = self.env['res.partner'].browse(res['partner_id'])
            if partner.sudo().property_product_pricelist:
                pricelist = partner.sudo().property_product_pricelist
                res['pricelist_id'] = pricelist.id
        return res

    @api.onchange('partner_id')
    def _onchange_partner_id_set_pricelist(self):
        for record in self:
            record.pricelist_id = self.partner_id.property_product_pricelist

    @api.onchange('pricelist_id')
    def _onchange_pricelist_id(self):
        for record in self:
            if record.pricelist_id and record.pricelist_id.currency_id:
                record.currency_id = record.pricelist_id.currency_id
            else:
                record.currency_id = self.env.user.company_id.currency_id

    def action_show_all_invoices(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'account.action_move_out_invoice_type',
            context={'default_request_id': self.id},
            domain=[('request_id', '=', self.id)])

    def _prepare_invoice_data(self):
        invoice_type = 'out_invoice'
        # In version Odoo 14 we need to pass the "default_move_type"
        # instead of "default_type"
        journal_id = (self.env['account.move'].with_context(
            company_id=self.env.user.company_id.id,
            default_move_type=invoice_type,
        ).default_get(['journal_id'])['journal_id'])
        if not journal_id:
            raise exceptions.UserError(_(
                "Please define an accounting sales journal for this company."
            ))

        return {
            'move_type': invoice_type,
            'partner_id': self.partner_id.address_get(['invoice'])['invoice'],
            'currency_id': self.currency_id.id,
            'journal_id': journal_id,
            'invoice_origin': self.name,
            'company_id': self.env.user.company_id.id,
            'request_id': self.id,
            'invoice_line_ids': [],
        }

    def _action_generate_invoice(self, no_raise=False):
        self.ensure_one()
        if not self.partner_id:
            if no_raise:
                return False
            raise exceptions.UserError(_(
                "Cannot generate invoice unless partner selected!"))
        if not self.request_to_invoice_line_ids:
            if no_raise:
                return False
            raise exceptions.UserError(_(
                "Nothing to invoice"))

        invoice_data = self._prepare_invoice_data()

        for line in self.request_to_invoice_line_ids:
            inv_line_data = line.prepare_invoice_line(invoice_data)
            invoice_data['invoice_line_ids'] += [(0, 0, inv_line_data)]

        new_invoice = self.env['account.move'].with_context(
            default_move_type='out_invoice').sudo().new(invoice_data)

        for line in new_invoice.invoice_line_ids:
            name = line.name
            line._onchange_product_id()
            line._onchange_account_id()
            line._onchange_uom_id()
            line.name = name

        invoice_data = new_invoice._convert_to_write(new_invoice._cache)

        # TODO: there may be a better way.
        # this is added to bypass the logic of deleting the list of lines
        # from the invoice creation data in method
        # [account.move]._move_autocomplete_invoice_lines_create()
        invoice_data.pop('line_ids', None)

        invoice = self.env['account.move'].with_context(
            default_move_type='out_invoice'
        ).sudo().create(
            invoice_data
        )

        return invoice

    def action_generate_invoice(self):
        self.ensure_one()
        self._action_generate_invoice()
        return True

    def action_make_all_billable(self):
        self.env['request.timesheet.line'].search(
            [('request_id', '=', self.id), ('is_billable', '=', False)]
        ).write({'is_billable': True})

    def action_make_all_not_billable(self):
        self.env['request.timesheet.line'].search(
            [('request_id', '=', self.id),
             ('is_billable', '=', True),
             ('request_invoice_line_ids.invoice_line_id', '=', False)]
        ).write({'is_billable': False})
