from odoo import models, fields


class GenericService(models.Model):
    _inherit = 'generic.service'

    generic_contract_ids = fields.Many2manyView(
        comodel_name='generic.contract',
        relation='generic_contract_service_line',
        column1='service_id',
        column2='contract_id',
        string='Contracts',
        readonly=True, copy=False,
        help="System field to show all contracts related to this service")
    active_contract_ids = fields.Many2many(
        'generic.contract', string='Active contracts',
        relation='generic_contract_all_services_rel',
        column1='service_id',
        column2='contract_id',
        readonly=True,
        help="System field to get all active contracts related to this "
             "service")
