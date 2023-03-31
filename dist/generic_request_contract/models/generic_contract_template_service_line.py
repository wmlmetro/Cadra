import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class GenericContractTemplateServiceLine(models.Model):
    _inherit = 'generic.contract.template.service.line'

    request_category_ids = fields.Many2many(
        comodel_name='request.category',
        relation='generic_contract_template_service_line_req_categ_rel',
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

    def prepare_contract_service_line(self):
        res = super(
            GenericContractTemplateServiceLine, self
        ).prepare_contract_service_line()
        res['request_category_ids'] = [(6, 0, self.request_category_ids.ids)]
        return res
