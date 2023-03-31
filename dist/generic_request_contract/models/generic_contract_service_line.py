import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class GenericContractServiceLine(models.Model):
    _inherit = 'generic.contract.service.line'

    request_category_ids = fields.Many2many(
        comodel_name='request.category',
        relation='generic_contract_service_line_req_categ_rel',
        column1='service_line_id',
        column2='request_category_id',)

    @api.onchange('service_id', 'request_category_ids')
    def _onchange_service_id_clean_categs(self):
        for record in self:
            if record.service_id:
                record.request_category_ids = (
                    record.request_category_ids.filtered(
                        lambda r: record.service_id in r.service_ids))
            else:
                record.request_category_ids = False
