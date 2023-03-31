from odoo import models, fields, api, exceptions, _

from odoo.addons.generic_request.tools.jinja import render_jinja_string

INVOICE_LINE_DESCRIPTION = """
Activity: {{ tline.activity_id.display_name }}
Date: {{ tline.date }}
User: {{ tline.user_id.display_name }}
---
{{ tline.description }}
"""


class RequestTimesheetLine(models.Model):
    _inherit = 'request.timesheet.line'

    enable_invoicing = fields.Boolean(
        related='request_id.type_id.enable_invoicing', readonly=True)
    request_invoice_line_ids = fields.One2many(
        'request.invoice.line', 'timesheet_line_id', readonly=True,
        help='Technical field to keep reference to related '
             'request invoice line')
    request_invoice_line_id = fields.Many2one(
        'request.invoice.line', readonly=True, store=True,
        compute='_compute_request_invoice_lines')
    is_billable = fields.Boolean(
        compute='_compute_is_billable',
        inverse='_inverse_is_billable',
        store=True,
    )

    @api.depends('request_invoice_line_ids',
                 'request_invoice_line_ids.timesheet_line_id')
    def _compute_request_invoice_lines(self):
        for record in self:
            if len(record.request_invoice_line_ids) == 1:
                record.request_invoice_line_id = (
                    record.request_invoice_line_ids[0])
            else:
                record.request_invoice_line_id = False

    @api.depends('request_invoice_line_ids',
                 'request_invoice_line_ids.timesheet_line_id')
    def _compute_is_billable(self):
        for record in self:
            if len(record.request_invoice_line_ids) == 1:
                record.is_billable = True
            else:
                record.is_billable = False

    def _get_default_product_for_invoice_line(self):
        """ Determine default product for time tracking.
            Could be overredden by thirdparty addons
        """
        self.ensure_one()
        return self.request_id.type_id.default_timetracking_product_id

    def _prepare_request_invoice_line_data(self):
        self.ensure_one()
        product = self._get_default_product_for_invoice_line()
        partner = self.request_id.partner_id.commercial_partner_id
        if self.request_id.pricelist_id:
            price = product.with_context(
                pricelist=self.request_id.pricelist_id.id,
                partner=partner.id,
            ).price
        else:
            price = product.with_context(partner=partner.id).price
        if not price:
            price = product.lst_price

        custom_tmpl = (self.env.user.company_id.
                       request_invoice_line_description_tmpl)
        if custom_tmpl:
            template = custom_tmpl
        else:
            template = INVOICE_LINE_DESCRIPTION

        return {
            'request_id': self.request_id.id,
            'product_id': product.id,
            'timesheet_line_id': self.id,
            'description': render_jinja_string(
                template, dict(self.env.context, tline=self)),
            'quantity': self.amount,
            'uom_id': product.uom_id.id,
            'price_unit': price,
        }

    def _inverse_is_billable(self):
        for record in self:
            if record.is_billable and not record.request_invoice_line_ids:
                invoice_line_data = record._prepare_request_invoice_line_data()
                record.request_invoice_line_ids = (
                    self.env['request.invoice.line'].new(invoice_line_data))

                # Trigger recomputation of `request_invoice_line_id`
                # TODO: Do we need this line, after separation of computation
                #       of 'request_invoice_line_id' moved to separate method?
                self.env.add_to_compute(
                    record._fields['request_invoice_line_id'], record)
            elif not record.is_billable and record.request_invoice_line_ids:
                inv_line = record.request_invoice_line_id.invoice_line_id
                if inv_line:
                    raise exceptions.UserError(_(
                        "Cannot make line unbillable if it is already "
                        "included in invoice %(invoice)s[%(invoice_id)d]"
                    ) % {
                        'invoice': inv_line.move_id.display_name,
                        'invoice_id': inv_line.move_id.id,
                    })
                record.request_invoice_line_ids.unlink()
