import logging
import traceback

from datetime import timedelta
from datetime import datetime
from dateutil.relativedelta import relativedelta

try:
    from first import first
except (ImportError, IOError):
    logging.getLogger(__name__).error(
        "Please, install python package 'first'!")

from odoo import models, fields, api, exceptions, _
from odoo.osv import expression
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

from ..utils import get_recurring_next_date, StackProcessor

_logger = logging.getLogger(__name__)

JOURNAL_TYPE_MAP = {
    'customer': 'sale',
    'supplier': 'purchase',
}


class GenericContract(models.Model):
    _inherit = 'generic.contract'

    recurring_invoices = fields.Boolean(
        string='Automatically generate invoices', default=False,
        readonly=True, states={'draft': [('readonly', False)]})
    recurring_invoices_offset_date = fields.Integer(
        default=0,
        tracking=True,
        readonly=True, states={'draft': [('readonly', False)]},
        help="Specify offset days for automatic invoice generation. For "
             "example, if recurring_next_date equals 01-01-2021 and offset "
             "date equals 2, then invoice_date equals 30-12-2020.")
    recurring_next_date = fields.Date(
        default=fields.Date.today,
        copy=False, string='Next Invoice Date',
        readonly=True, states={'draft': [('readonly', False)]},
        tracking=True)
    recurring_next_invoice_date = fields.Date(
        compute='_compute_next_invoice_date'
    )
    recurring_type = fields.Selection(
        [('daily', 'Day(s)'),
         ('weekly', 'Week(s)'),
         ('monthly', 'Month(s)'),
         ('monthly-last-day', 'Month(s) last day'),
         ('yearly', 'Year(s)')],
        default='monthly', string='Recurrence',
        help="Specify Interval for automatic invoice generation.",
        readonly=True, states={'draft': [('readonly', False)]})
    recurring_invoicing_type = fields.Selection(
        [('post-paid', 'Post-paid')],
        default='post-paid', readonly=True,
        states={'draft': [('readonly', False)]})
    recurring_period = fields.Integer(
        default=1, string='Repeat Every',
        help="Repeat every (Days/Week/Month/Year)",
        readonly=True, states={'draft': [('readonly', False)]})
    journal_type = fields.Selection(
        selection=[
            ('sale', 'Sale'),
            ('purchase', 'Purchase'),
        ], compute='_compute_journal_type',
        store=True, readonly=True, index=True
    )
    journal_id = fields.Many2one(
        'account.journal', string='Journal',
        readonly=True, states={'draft': [('readonly', False)]})
    payment_term_id = fields.Many2one(
        'account.payment.term', string='Payment Terms',
        tracking=True,
        readonly=True, states={'draft': [('readonly', False)]},
        help="If you use payment terms, the due date will be computed "
             "automatically at the generation of accounting entries. "
             "If you keep the payment terms and the due date empty, "
             "it means direct payment. The payment terms may compute "
             "several due dates, for example 50% now, 50% in one month.")
    pricelist_id = fields.Many2one(
        comodel_name='product.pricelist', string='Pricelist',
        readonly=True, states={'draft': [('readonly', False)]})
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        readonly=True, states={'draft': [('readonly', False)]})
    recurring_invoice_line_ids = fields.One2many(
        'generic.contract.invoice.line', 'contract_id', string='Invoice Lines',
        copy=True, readonly=True, states={'draft': [('readonly', False)]})
    account_invoice_ids = fields.One2many(
        'account.move', 'generic_contract_id',
        string='Invoices', readonly=True)
    account_invoice_count = fields.Integer(
        'Invoices', compute='_compute_account_invoice_count', readonly=True,
        compute_sudo=True)
    recurring_invoices_last_error = fields.Text(readonly=True)
    auto_accept = fields.Boolean(
        default=False,
        tracking=True,
        states={'draft': [('readonly', False)]})
    auto_send = fields.Boolean(
        default=False, tracking=True,
        states={'draft': [('readonly', False)]})
    auto_send_template_id = fields.Many2one(
        'mail.template',
        'Email Template',
        ondelete='restrict',
        tracking=True,
        domain="[('model_id.model', '=', 'account.invoice')]",
        states={'draft': [('readonly', False)]})
    email_from = fields.Char(
        tracking=True,
        readonly=True,
        states={'draft': [('readonly', False)]}
    )
    recipient_ids = fields.Many2many(
        'res.partner',
        tracking=True,
        readonly=True,
        states={'draft': [('readonly', False)]}
    )
    payer_id = fields.Many2one(
        'res.partner',
        tracking=True,
        readonly=True,
        states={'draft': [('readonly', False)]})
    contract_employee_rate_ids = fields.One2many(
        'generic.contract.employee.rate', 'generic_contract_id',
        string='Employee Rates', readonly=True, copy=True,
        states={'draft': [('readonly', False)]})

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

    @api.depends('account_invoice_ids')
    def _compute_account_invoice_count(self):
        mapped_data = read_counts_for_o2m(
            records=self.sudo(),
            field_name='account_invoice_ids')
        for record in self:
            record.account_invoice_count = mapped_data.get(record.id, 0)

    @api.constrains('recurring_invoices', 'recurring_period')
    def _check_recurring_period(self):
        for record in self:
            if record.recurring_invoices and record.recurring_period <= 0:
                raise exceptions.ValidationError(_(
                    "Recurring Period (Repeat Every) must be greater then 0"))

    @api.constrains('date_start', 'recurring_next_date', 'recurring_invoices')
    def _check_recurring_dates(self):
        for rec in self:
            if not rec.recurring_invoices:
                continue
            if not rec.recurring_next_date:
                continue
            if not rec.date_start:
                continue

            if rec.date_start > rec.recurring_next_date:
                raise exceptions.ValidationError(
                    _("Next Invoicing Date of the contract '[%s]' can`t be"
                      " less than Date Start! Check it, please.") % rec.name)

    @api.depends('recurring_invoices_offset_date', 'recurring_next_date')
    def _compute_next_invoice_date(self):
        for rec in self:
            rec.recurring_next_invoice_date = \
                rec.recurring_next_date - \
                timedelta(rec.recurring_invoices_offset_date)

    @api.depends('partner_type')
    def _compute_journal_type(self):
        for rec in self:
            rec.journal_type = JOURNAL_TYPE_MAP[rec.partner_type]

    @api.onchange('partner_type')
    def _onchange_partner_type_set_journal(self):
        for rec in self:
            rec.journal_id = self.sudo().env['account.journal'].search([
                ('type', '=', JOURNAL_TYPE_MAP[rec.partner_type])
            ], limit=1)

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        for record in self:
            if record.partner_id.property_product_pricelist:
                record.pricelist_id = (
                    record.partner_id.property_product_pricelist)

    @api.onchange('pricelist_id', 'journal_id', 'partner_id')
    def _onchange_pricelist_journal_partner(self):
        for record in self:
            record.currency_id = first([
                self.pricelist_id.currency_id,
                self.partner_id.property_product_pricelist.currency_id,
                self.journal_id.currency_id,
                self.env.user.company_id.currency_id])

    @api.onchange('date_start')
    def _onchange_date_start(self):
        for record in self:
            if record.date_start and not record.recurring_next_date:
                record.recurring_next_date = record.date_start
            elif record.date_start and record.recurring_next_date:
                record.recurring_next_date = max(
                    record.date_start, record.recurring_next_date)

    def _validate_field_by_name(
            self, field_model, field_name, field_types=None):
        """
        Checks field field_name exist for field_model model and (if not None)
            is one from field_types. Returns record of 'ir.model.fields'.

            :param field_model: string: name of model of field_name
            :param field_name: string: name of field_name
            :param field_types: tuple of strings or None:
                                Tuple of types of fields

            :return: record of 'ir.model.fields'
        """

        field = self.sudo().env['ir.model.fields']._get(
            field_model, field_name)
        if not field or field.ttype not in field_types:
            raise exceptions.UserError(
                _('Model "%(model)s" do not have field %(name)s')
                % {'model': field_model, 'name': field_name})
        return field

    def _validate_date_range(
            self, date_field_model, date_field, date_start, date_end):
        """
        Checks date_field exist and returns tuple of synchronized to the same
            type (date or datetime) date_start and date_end.

            :param date_field_model: string: name of model of date_field
            :param date_field: string: name of date_field
            :param date_start: datetime.date instance
            :param date_end: datetime.date instance

            :return: tuple of
                     (datetime.date, datetime.date) or
                     (datetime.datetime, datetime.datetime)
        """
        date_field_valid = self._validate_field_by_name(
            date_field_model, date_field, ('datetime', 'date'))
        if date_field_valid.ttype == 'datetime':
            date_start = datetime.combine(date_start, datetime.min.time())
            date_end = datetime.combine(date_end, datetime.max.time())
        return date_start, date_end

    def _get_data_for_period(
            self, model, date_field, date_start, date_end, domain=None,
            contract_field='contract_id'):
        """
            Returns recordset of 'model' restricted of
                date_start and date_end dates range by date_field of 'model'
                and restricted by domain.

            :param model: string: name of model where searched
            :param date_field: string: name of date field of 'model'
            :param date_start: datetime.date instance
            :param date_end: datetime.date instance
            :param domain: list, domain to be added to base domain
            :param contract_field: name of field that points to contract.
                could be dotted name (project_id.contract_id)

            :return: recordset of model with records that have to be invoiced
        """
        range_date_start, range_date_end = self._validate_date_range(
            model, date_field, date_start, date_end)
        res_domain = [
            (date_field, '<', range_date_end),
            (date_field, '>=', range_date_start),
            (contract_field, '=', self.id),
        ]
        if domain is not None:
            res_domain = expression.AND([
                domain,
                res_domain])
        return self.env[model].sudo().search(res_domain)

    def _calc_period_dates(self, invoice_date):
        """ Compute period dates for specified invoice date.
            Used to determine start and end dates of current period
        """
        # TODO: implement computation for post-paid
        date_end = invoice_date
        if self.recurring_type == 'daily':
            delta = relativedelta(days=self.recurring_period)
        elif self.recurring_type == 'weekly':
            delta = relativedelta(weeks=self.recurring_period)
        elif self.recurring_type == 'monthly':
            delta = relativedelta(months=self.recurring_period)
        elif self.recurring_type == 'monthly-last-day':
            delta = relativedelta(months=self.recurring_period, day=31)
        elif self.recurring_type == 'yearly':
            delta = relativedelta(years=self.recurring_period)
        else:
            delta = relativedelta()

        date_start = date_end - delta
        if date_start < self.date_start:
            date_start = self.date_start

        return date_start, date_end

    def _validate_employee(self, employee):
        """
        Method serializes variable 'employee' to instance of
            'hr.employee' class.
        If the method received 'employee' as 'res.users'
            class that will return employee related to the user.
        If the method received 'employee' as 'hr.employee'
            class that will return first instance of employee from 'employee'.
        If the method received 'employee' as integer (id of employee) that
            will return record of 'hr.employee' related to this id if exist.
        If the method received 'employee' as any other that
            will return empty record of 'hr.employee'.

        :param employee: can by any but processed
                         - recordset of 'res.users' class
                         - recordset of 'hr.employee' class
                         - integer
        :return: recordset of 'hr.employee' class
        """
        if not employee:
            # return empty recordset
            return self.env['hr.employee'].browse()
        if isinstance(employee, models.Model) and \
                employee._name == 'res.users':
            if employee.employee_ids:
                return employee.employee_ids[0]
        if isinstance(employee, models.Model) and \
                employee._name == 'hr.employee':
            return employee[0]
        if isinstance(employee, int):
            return self.env['hr.employee'].browse(employee).exists()
        # any other cases return empty recordset
        return self.env['hr.employee'].browse()

    def get_employee_rate(self, employee):
        """
        Returns employee rate for current contract searched from model
            'generic.contract.employee.rate' model, that have relation
            between contract and employee and info about rate. If we haven`t
            validated employee (method _validate_employee) will return zero
            (will be processed further).
        :param employee: employee: can by any but processed
                         - recordset of 'res.users' class
                         - recordset of 'hr.employee' class
                         - integer
                         will send to _validate_employee method
        :return: int: rate of employee from 'generic.contract.employee.rate'
                      model for contract or zero
        """
        self.ensure_one()
        employee_id = self._validate_employee(employee)
        employee_contract_rates = self.contract_employee_rate_ids.filtered(
            lambda rate: rate.employee_id == employee_id)
        if employee_contract_rates:
            return employee_contract_rates[0].rate
        return 0

    @api.model
    def prepare_invoice_lines(self, invoice):
        self.ensure_one()
        ContractInvoiceLine = self.env['generic.contract.invoice.line']

        date_start, date_end = self._calc_period_dates(
            self.recurring_next_date)
        template_ctx = {
            'contract': self,
            'invoice': invoice,
            'invoice_date': self.recurring_next_invoice_date,
            'period_date_start': date_start,
            'period_date_end': date_end,
        }
        processor = StackProcessor(
            code_field='name',
            preprocess_fields={
                'name': 'jinja2',
                'quantity': 'python',
                'price_py_expr': 'python',
                'price_er_employee_expr': 'python',
            },
            extra_context=template_ctx,
        )
        for line in self.recurring_invoice_line_ids.sorted():
            line_data = line.prepare_invoice_line_data(invoice)
            processor.parse_line(line_data)

        data = processor.run()
        data = [
            ContractInvoiceLine.postprocess_invoice_line_data(
                self, invoice, line)
            for line in data
        ]
        return data

    def _prepare_invoice_data(self):
        invoice_type = 'out_invoice'
        if self.partner_type == 'customer':
            invoice_type = 'out_invoice'
        elif self.partner_type == 'supplier':
            invoice_type = 'in_invoice'
        if self.payer_id:
            partner_id = self.payer_id
        else:
            partner_id = self.partner_id
        return {
            'ref': self.number,
            'move_type': invoice_type,
            'partner_id': partner_id.address_get(['invoice'])['invoice'],
            'currency_id': self.currency_id.id,
            'journal_id': self.journal_id.id,
            'invoice_date': self.recurring_next_invoice_date,
            'invoice_origin': self.name,
            'company_id': self.env.user.company_id.id,
            'generic_contract_id': self.id,
            'invoice_user_id': self.user_id.id,
            'invoice_payment_term_id': self.payment_term_id.id,
        }

    def prepare_invoice_data(self):
        self.ensure_one()
        invoice = self.sudo().env['account.move'].new(
            self._prepare_invoice_data())
        # Get other invoice values from partner onchange
        invoice._onchange_partner_id()
        return invoice._convert_to_write(invoice._cache)

    def _create_invoice(self):
        self.ensure_one()
        old_date = first([
            self.recurring_next_date, fields.Date.today()])
        new_date = get_recurring_next_date(
            old_date, self.recurring_type, self.recurring_period)
        invoice_data = self.prepare_invoice_data()
        invoice_lines = self.prepare_invoice_lines(
            self.sudo().env['account.move'].new(invoice_data))

        # TODO: there may be a better way.
        # this is added to bypass the logic of deleting the list of lines
        # from the invoice creation data in method
        # [account.move]._move_autocomplete_invoice_lines_create()
        invoice_data.pop('line_ids', None)

        for line in invoice_lines:
            invoice_data['invoice_line_ids'] += [(0, 0, line)]

        invoice = self.sudo().env['account.move'].create(invoice_data)

        self.write({
            'recurring_next_date': new_date,
            'recurring_invoices_last_error': False,
        })
        self.remove_tag(code='cannot-generate-invoice')
        if self.auto_accept:
            invoice.action_post()
            if self.auto_send and self.auto_send_template_id:
                email_values = {}
                t = invoice.generic_contract_id.sudo().auto_send_template_id
                recipient_ids = [(4, i.id) for i in self.recipient_ids]
                if recipient_ids:
                    email_values['recipient_ids'] = recipient_ids
                if self.email_from:
                    email_values['email_from'] = self.email_from
                email_values['auto_delete'] = True
                t.send_mail(invoice.id,
                            force_send=False,
                            raise_exception=False,
                            email_values=email_values)

    def create_invoice(self):
        for contract in self:
            contract._create_invoice()
        return True

    def action_recurring_create_invoices(self):
        today = fields.Date.today()
        contracts = self.search([
            ('id', 'in', self.ids),
            ('state', '=', 'active'),
            ('recurring_invoices', '=', True),
            ('recurring_next_date', '<=', today),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', today),
        ])
        return contracts.create_invoice()

    @api.model
    def schedule_recurring_create_invoice(self):
        today = fields.Date.today()
        contracts = self.search([
            ('state', '=', 'active'),
            ('recurring_invoices', '=', True),
            ('recurring_next_date', '<=', fields.Date.to_string(today)),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', fields.Date.to_string(today)),
        ])
        for contract in contracts._iter_in_transact(True, True):
            try:
                contract.create_invoice()
            except Exception:
                _logger.error(
                    "Cannot generate invoices for contract %s",
                    contract.display_name,
                    exc_info=True)
                # Rollback transaction to avoid partially generated invoices
                contract.env.cr.rollback()
                contract.add_tag(code='cannot-generate-invoice')
                contract.recurring_invoices_last_error = traceback.format_exc()

    def action_generic_contract_account_invoice(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_contract_invoicing.action_generic_contract_invoices',
            domain=[('generic_contract_id', '=', self.id)])
