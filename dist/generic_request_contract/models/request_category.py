from odoo import models, fields


class RequestCategory(models.Model):
    _inherit = 'request.category'

    active_contract_ids = fields.Many2many(
        'generic.contract', string='Active contracts',
        relation='generic_contract_all_request_categs_rel',
        column1='categ_id',
        column2='contract_id',
        readonly=True,
        help="System field to get all active contracts related to this "
             "category")
