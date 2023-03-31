from odoo import fields, models


class GenericContractEmployeeRate(models.Model):
    _name = 'generic.contract.employee.rate'
    _description = 'Generic Contract Employee Rate'

    generic_contract_id = fields.Many2one(
        'generic.contract', string='Contract', required=True,
        index=True, ondelete="cascade")
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True,
        index=True, ondelete="cascade")
    rate = fields.Monetary(
        default=0.0, currency_field='contract_currency_id',
        help="Rate of employee per hour.")
    contract_currency_id = fields.Many2one(
        'res.currency', related='generic_contract_id.currency_id',
        string="Contract Currency", readonly=True)
