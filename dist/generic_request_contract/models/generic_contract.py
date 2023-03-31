import logging

from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

_logger = logging.getLogger(__name__)


class GenericContract(models.Model):
    _inherit = 'generic.contract'

    contract_request_ids = fields.One2many(
        'request.request', 'contract_id', 'Requests')
    contract_request_count = fields.Integer(
        'All Requests', compute='_compute_contract_requests',
        compute_sudo=True)
    contract_request_open_count = fields.Integer(
        'Open requests', compute='_compute_contract_requests',
        compute_sudo=True)

    @api.depends('contract_request_ids')
    def _compute_contract_requests(self):
        mapped_data_all = read_counts_for_o2m(
            records=self,
            field_name='contract_request_ids', sudo=True)
        mapped_data_open = read_counts_for_o2m(
            records=self,
            field_name='contract_request_ids',
            domain=[('closed', '=', False)], sudo=True)
        for rec in self:
            rec.contract_request_count = mapped_data_all.get(rec.id, 0)
            rec.contract_request_open_count = mapped_data_open.get(rec.id, 0)

    def action_view_contract_requests(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            context={
                'default_contract_id': self.id,
                'default_partner_id': self.partner_id.id,
            },
            domain=[('contract_id', '=', self.id)])
