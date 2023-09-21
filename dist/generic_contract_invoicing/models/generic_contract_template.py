import logging

try:
    from first import first
except (ImportError, IOError):
    logging.getLogger(__name__).error(
        "Please, install python package 'first'!")

from odoo import models, fields, api, exceptions, _
from .generic_contract import JOURNAL_TYPE_MAP
from ..utils import get_recurring_next_date

_logger = logging.getLogger(__name__)


class GenericContractTemplate(models.Model):
    _inherit = 'generic.contract.template'

    recurring_invoices = fields.Boolean(
        string='Automatically generate invoices', default=False)
    recurring_type = fields.Selection(
        [('daily', 'Day(s)'),
         ('weekly', 'Week(s)'),
         ('monthly', 'Month(s)'),
         ('monthly-last-day', 'Month(s) last day'),
         ('yearly', 'Year(s)')],
        default='monthly', string='Recurrence',
        help="Specify Interval for automatic invoice generation.")
    recurring_invoicing_type = fields.Selection(
        [('post-paid', 'Post-paid')],
        default='post-paid', readonly=True)
    recurring_period = fields.Integer(
        default=1, string='Repeat Every',
        help="Repeat every (Days/Week/Month/Year)")
    recurring_invoices_offset_date = fields.Integer(
        default=0,
        tracking=True,
        help="Specify offset days for automatic invoice generation. For "
             "example, if recurring_next_date equals 01-01-2021 and offset "
             "date equals 2, then invoice_date equals 30-12-2020.")
    journal_type = fields.Selection(
        selection=[
            ('sale', 'Sale'),
            ('purchase', 'Purchase'),
        ], compute='_compute_journal_type',
        store=True, readonly=True, index=True
    )
    journal_id = fields.Many2one(
        'account.journal', string='Journal')
    payment_term_id = fields.Many2one(
        'account.payment.term', string='Payment Terms',
        help="If you use payment terms, the due date will be computed "
             "automatically at the generation of accounting entries. "
             "If you keep the payment terms and the due date empty, "
             "it means direct payment. The payment terms may compute "
             "several due dates, for example 50% now, 50% in one month.")
    pricelist_id = fields.Many2one(
        comodel_name='product.pricelist', string='Pricelist')
    currency_id = fields.Many2one(
        comodel_name='res.currency')
    recurring_invoice_line_ids = fields.One2many(
        'generic.contract.template.invoice.line', 'contract_template_id',
        string='Invoice Lines', copy=True)
    auto_accept = fields.Boolean(default=False)
    auto_send = fields.Boolean(default=False)
    auto_send_template_id = fields.Many2one(
        'mail.template',
        'Email Template',
        ondelete='restrict',
        domain="[('model_id.model', '=', 'account.invoice')]")

    @api.constrains('auto_send_template_id')
    def check_auto_send_template_id(self):
        for record in self:
            if not record.auto_send_template_id:
                continue
            template_model = record.auto_send_template_id.model_id.model
            if template_model != 'account.invoice':
                raise exceptions.ValidationError(_(
                    "Cannot use template that is not "
                    "bound to 'account.invoice' model!"))

    @api.depends('partner_type')
    def _compute_journal_type(self):
        for rec in self:
            rec.journal_type = JOURNAL_TYPE_MAP[rec.partner_type]

    @api.onchange('partner_type')
    def _onchange_partner_type(self):
        for rec in self:
            rec.journal_id = self.env['account.journal'].search([
                ('type', '=', JOURNAL_TYPE_MAP[rec.partner_type])
            ], limit=1)

    @api.onchange('pricelist_id', 'journal_id')
    def _onchange_pricelist_journal(self):
        for record in self:
            record.currency_id = first([
                self.pricelist_id.currency_id,
                self.journal_id.currency_id,
                self.env.user.company_id.currency_id])

    def _prepare_contract_values(self, partner, user, date_begin, date_end):
        data = super(
            GenericContractTemplate, self
        )._prepare_contract_values(partner, user, date_begin, date_end)

        if not self.recurring_invoices:
            return data

        data.update({
            'recurring_invoices': self.recurring_invoices,
            'recurring_type': self.recurring_type,
            'recurring_period': self.recurring_period,
            'recurring_next_date': get_recurring_next_date(
                date_begin,
                self.recurring_type,
                self.recurring_period),
            'recurring_invoice_line_ids': [],
            'journal_id': self.journal_id.id,
            'pricelist_id': self.pricelist_id.id,
            'currency_id': self.currency_id.id,
            'payment_term_id': self.payment_term_id.id,
            'recurring_invoices_offset_date':
                self.recurring_invoices_offset_date,
            'auto_accept': self.auto_accept,
            'auto_send': self.auto_send,
            'auto_send_template_id': self.auto_send_template_id.id,
        })

        for recurring_invoice_line in self.recurring_invoice_line_ids:
            data['recurring_invoice_line_ids'].append(
                (0, 0, recurring_invoice_line._prepare_contract_invoice_line(
                    partner)),
            )
        return data

    def _postprocess_created_contract(self, contract):
        """ Could be called by third-party modules, to add some postprocessing
            of created contract
        """
        for line in contract.recurring_invoice_line_ids:
            line._postprocess_after_template()
