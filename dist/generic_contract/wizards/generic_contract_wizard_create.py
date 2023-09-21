import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class GenericContractWizardCreate(models.TransientModel):
    _name = 'generic.contract.wizard.create'
    _description = 'Generic Wizard: Create Contract'

    partner_type = fields.Selection(
        required=True, default='customer',
        selection=[('customer', 'Customer'),
                   ('supplier', 'Supplier')])
    template_id = fields.Many2one(
        'generic.contract.template', required=True, ondelete='cascade')
    partner_id = fields.Many2one(
        'res.partner', required=True, ondelete='cascade')
    user_id = fields.Many2one(
        'res.users', string='Responsible', ondelete='cascade')
    date_begin = fields.Date(
        index=True, required=True,
        default=fields.Date.today)
    date_end = fields.Date(index=True)

    @api.onchange('partner_type')
    def _onchange_partner_type(self):
        ctx = self.env.context
        for rec in self:
            if rec.template_id.id != ctx.get('default_template_id'):
                rec.template_id = False
            rec.partner_id = False
            if rec.template_id.partner_type != rec.partner_type:
                rec.template_id = False

    def _create_contract(self):
        return self.template_id.create_contract(
            self.partner_id,
            user=self.user_id,
            date_begin=self.date_begin,
            date_end=self.date_end,
        )

    def create_contract(self):
        self.ensure_one()
        main_contract = self._create_contract()
        if self.partner_type == 'customer':
            action = self.env['generic.mixin.get.action'].get_action_by_xmlid(
                'generic_contract.generic_contract_action_customer_contracts')
        elif self.partner_type == 'supplier':
            action = self.env['generic.mixin.get.action'].get_action_by_xmlid(
                'generic_contract.generic_contract_action_supplier_contracts')
        else:
            action = self.env['generic.mixin.get.action'].get_action_by_xmlid(
                'generic_contract.generic_contract_action')
        action['domain'] = [('id', '=', main_contract.id)]
        return action
