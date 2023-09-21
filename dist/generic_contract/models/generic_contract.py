import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

from odoo.addons.generic_mixin import post_write, post_create

_logger = logging.getLogger(__name__)


class GenericContract(models.Model):
    _name = 'generic.contract'
    _inherit = [
        'mail.thread',
        'mail.activity.mixin',
        'generic.tag.mixin',
        'generic.mixin.transaction.utils',
        'generic.system.event.source.mixin',
    ]
    _description = 'Generic Contract'
    _order = 'name, number'

    name = fields.Char(
        index=True, translate=True, tracking=True, required=True,
        readonly=True, states={'draft': [('readonly', False)]})
    ref = fields.Char(
        index=True, tracking=True, readonly=True,
        states={'draft': [('readonly', False)]})
    company_id = fields.Many2one(
        'res.company', string='Company', index=True,
        required=True, readonly=True,
        states={'draft': [('readonly', False)]},
        default=lambda self: self.env.company)
    partner_type = fields.Selection(
        required=True, default='customer',
        selection=[('customer', 'Customer'),
                   ('supplier', 'Supplier')],
        tracking=True,
        readonly=True, states={'draft': [('readonly', False)]})
    number = fields.Char(
        index=True, tracking=True, readonly=True,
        states={'draft': [('readonly', False)]})
    template_id = fields.Many2one(
        'generic.contract.template', readonly=True,
        states={'draft': [('readonly', False)]})
    partner_id = fields.Many2one(
        'res.partner', index=True, tracking=True,
        required=True, readonly=True, states={'draft': [('readonly', False)]})
    state = fields.Selection(
        selection=[('draft', 'Draft'),
                   ('pending', 'Pending'),
                   ('active', 'Active'),
                   ('closed', 'Closed')],
        string='Status', readonly=True, index=True,
        tracking=True, default='draft')
    user_id = fields.Many2one(
        'res.users', index=True, tracking=True,
        string="Responsible")
    date = fields.Date(
        index=True, required=True, default=fields.Date.today, readonly=True,
        tracking=True, states={'draft': [('readonly', False)]})
    # TODO: Rename to date_begin
    date_begin = fields.Date(
        index=True, required=True, default=fields.Date.today, readonly=True,
        tracking=True, states={'draft': [('readonly', False)]})
    date_end = fields.Date(
        index=True, tracking=True, readonly=True,
        states={'draft': [('readonly', False)]})
    date_closed = fields.Date(
        index=True, readonly=True, tracking=True)

    description = fields.Html(translate=True)

    service_contract_line_ids = fields.One2many(
        'generic.contract.service.line', 'contract_id', readonly=True,
        string='Service Lines', states={'draft': [('readonly', False)]},
        copy=True, auto_join=True)

    contracts_service_ids = fields.Many2many(
        'generic.service', string='All Services',
        relation='generic_contract_all_services_rel',
        column1='contract_id',
        column2='service_id',
        compute='_compute_contracts_service_line_ids',
        store=True,
        readonly=True)

    _sql_constraints = [
        ('contract_number_unique',
         'UNIQUE(number)',
         "Number of contract must be unique!")]

    @api.depends(
        'service_contract_line_ids',
        'service_contract_line_ids.service_id',
        'state')
    def _compute_contracts_service_line_ids(self):
        for rec in self:
            rec.contracts_service_ids = (
                rec.service_contract_line_ids.mapped('service_id')
            )

    @api.constrains('date_begin', 'date_end', 'state')
    def _check_date_begin_date_end_order(self):
        for rec in self:
            d_begin = fields.Date.to_date(rec.date_begin)
            d_end = fields.Date.to_date(rec.date_end)
            if rec.date_end and d_end < d_begin:
                raise ValidationError(
                    _('Date begin can`t be less than date end of contract!'
                      ' Check it, please'))

    @post_create()
    def _after_create_update_contract_number(self, changes):
        number_sequence_map = {
            'customer': self.env.ref(
                'generic_contract.seq_generic_contract_customer_contracts'),
            'supplier': self.env.ref(
                'generic_contract.seq_generic_contract_supplier_contracts'),
        }
        if self.template_id and self.template_id.number_sequence_id:
            self.number =\
                self.template_id.number_sequence_id.next_by_id()
        elif number_sequence_map.get(self.partner_type):
            self.number =\
                number_sequence_map[self.partner_type].next_by_id()

    def unlink(self):
        for contract in self:
            if contract.state != 'draft':
                raise UserError(
                    _('You can`t delete contract: %s,'
                      ' because it is not in "draft" state.'
                      ' You can delete only draft contracts.') %
                    contract.display_name)
        return super(GenericContract, self).unlink()

    @post_write('user_id')
    def _after_assignee_changed(self, changes):
        old_user, new_user = changes['user_id']
        self.trigger_event('assignee-changed', {
            'old_user_id': old_user.id,
            'new_user_id': new_user.id})

    def name_get(self):
        names_data = []
        for rec in self:
            name = '%s ' % (rec.name or '') + '[%s]' % rec.number
            names_data.append((rec.id, name))
        return names_data

    def get_service_line_for(self, service):
        """ Get service line for service. Assumed to be used outside.

            Always returns single record or empty recordset

            :param service: Single record of 'generic.service' to return
                            service line for.
            :return: Recordset of 'generic.contract.service.line'.
        """
        self.ensure_one()
        # computed only in active or pending
        # contract states and priority has active state
        return self.env['generic.contract.service.line'].search(
            [('service_id', '=', service.id),
             ('contract_state', 'in', ('pending', 'active')),
             ('contract_id', '=', self.id)],
            order='contract_state',
            limit=1)

    def activate_contract(self):
        for contract in self:
            d_start = fields.Date.to_date(contract.date_begin)
            if d_start <= fields.Date.today() and contract.state == 'pending':
                contract.state = 'active'
                contract.trigger_event('contract-activated')
        return True

    def close_contract(self, date_closed=None):
        """ This method closes contract with provided date_closed (if provided)

            It is assumed that this method could be called from scheduler.

            If contract was closed, it returns true, otherwise, returns False.
        """
        self.ensure_one()
        date_closed = fields.Date.to_date(
            date_closed or self.date_end or fields.Date.today())
        if self.state == 'closed':
            return True
        if self.state in ('draft', 'pending'):
            # Contract not started, so we do not need to close it.
            return False
        if date_closed <= fields.Date.today() and self.state == 'active':
            self.write({
                'state': 'closed',
                'date_end': self.date_end or date_closed,
                'date_closed': date_closed,
            })
            self.trigger_event('contract-closed')
            return True
        # Contract was not closed, returning False
        return False

    def close_contracts(self):
        """ Try to close multiple contracts
        """
        for contract in self:
            contract.close_contract()
        return True

    def confirm_contract(self):
        self.ensure_one()
        if self.state == 'draft':
            if fields.Date.to_date(self.date_begin) <= fields.Date.today():
                self.state = 'active'
                self.trigger_event('contract-confirmed')
                self.trigger_event('contract-activated')
            else:
                self.state = 'pending'
                self.trigger_event('contract-confirmed')
            return True
        return False

    def action_to_draft(self):
        is_manager = self.user_has_groups(
            'generic_contract.group_generic_contract_manager')
        for record in self:
            if record.state not in ('pending', 'active'):
                raise UserError(_(
                    "You can convert to draft only pending contracts."))
            if record.state == 'active' and not is_manager:
                raise UserError(_(
                    "Only manager can convert active contracts to draft"))

            record.state = 'draft'

    def action_confirm(self):
        for record in self:
            if record.state == 'draft':
                record.confirm_contract()

    def action_confirm_contracts(self):
        """ Confirm contracts.
        """
        for contract in self:
            confirmed = contract.confirm_contract()
            if not confirmed:
                _logger.warning(
                    'Contract (%s) not confirmed, because it has state: %s,'
                    ' check it please.', contract.display_name, contract.state)
                continue

    def action_close(self):
        for record in self:
            closed = record.close_contract(date_closed=fields.Date.today())
            if not closed:
                raise UserError(_('You can`t close this contract.'))

    @api.model
    def scheduler_activate_contracts(self):
        return self.search([
            ('state', '=', 'pending'),
            ('date_begin', '<=', fields.Date.today()),
        ]).activate_contract()

    @api.model
    def scheduler_close_contracts(self):
        return self.search([
            ('state', '=', 'active'),
            ('date_end', '<=', fields.Date.today()),
        ]).close_contracts()
