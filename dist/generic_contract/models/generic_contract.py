import datetime
import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

from odoo.addons.generic_mixin import post_write

_logger = logging.getLogger(__name__)


def to_dt(date):
    """ Convert date (str) to datetime object
        It is sefe to pass datetime instance too.
        In this case it will be returned unchanged.
    """
    if isinstance(date, datetime.date):
        return date
    if isinstance(date, str):
        return fields.Date.from_string(date)
    return False


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
        required=True, default=lambda self: self.env.company)
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
    date_start = fields.Date(
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
            # TODO: Add services from lines
            rec.contracts_service_ids = (
                rec.service_contract_line_ids.mapped('service_id')
            )

    @api.constrains('date_start', 'date_end', 'state')
    def _check_date_start_date_end_order(self):
        for rec in self:
            if rec.date_end and to_dt(rec.date_end) < to_dt(rec.date_start):
                raise ValidationError(
                    _('Date start can`t be less than date end of contract!'
                      ' Check it, please'))

    @api.model
    def create(self, vals):
        contract = super(GenericContract, self).create(vals)
        number_sequence_map = {
            'customer': self.env.ref(
                'generic_contract.seq_generic_contract_customer_contracts'),
            'supplier': self.env.ref(
                'generic_contract.seq_generic_contract_supplier_contracts'),
        }
        if contract.template_id and contract.template_id.number_sequence_id:
            contract['number'] =\
                contract.template_id.number_sequence_id.next_by_id()
        elif number_sequence_map.get(contract.partner_type):
            contract['number'] =\
                number_sequence_map[contract.partner_type].next_by_id()

        return contract

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

    def add_service_line(self, service, service_level=None, date=None):
        """ This method have to be used to add new service line to contract by
            other modules.
        """
        self.ensure_one()
        service_line = self.get_service_line_for(service)
        if service_line and service_level:
            service_line.service_level_id = service_level
        elif not service_line:
            service_line = self.env['generic.contract.service.line'].create({
                'contract_id': self.id,
                'service_id': service.id,
                'service_level_id': (
                    service_level.id if service_level is not None else False),
                'date_added': (
                    date if date is not None else fields.Datetime.now()),
            })
        return service_line

    def activate_contract(self):
        for contract in self:
            if (to_dt(contract.date_start) <= to_dt(fields.Date.today()) and
                    contract.state == 'pending'):
                contract.state = 'active'
        return True

    def _close_contract(self, date_closed):
        self.ensure_one()
        date_closed = date_closed or self.date_end or fields.Date.today()
        if self.state == 'closed':
            return True
        if self.state in ('draft', 'pending'):
            # Contract not started, so we do not need to close it.
            return False
        if (to_dt(date_closed) <= to_dt(fields.Date.today()) and
                self.state == 'active'):
            self.write({
                'state': 'closed',
                'date_end': self.date_end or date_closed,
                'date_closed': date_closed,
            })
            self.trigger_event('contract-closed')
            return True
        return False

    def close_contract(self, date_closed=None):
        self.ensure_one()
        return self._close_contract(date_closed=date_closed)

    def close_contracts(self):
        for contract in self:
            contract.close_contract()
        return True

    def confirm_contract(self):
        self.ensure_one()
        if self.state == 'draft':
            if to_dt(self.date_start) <= to_dt(fields.Date.today()):
                self.state = 'active'
                self.trigger_event('contract-confirmed')
                self.trigger_event('contract-activated')
            else:
                self.trigger_event('contract-confirmed')
                self.state = 'pending'
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
            ('date_start', '<=', fields.Date.today()),
        ]).activate_contract()

    @api.model
    def scheduler_close_contracts(self):
        return self.search([
            ('state', '=', 'active'),
            ('date_end', '<=', fields.Date.today()),
        ]).close_contracts()
