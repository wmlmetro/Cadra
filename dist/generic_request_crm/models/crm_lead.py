import logging

from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

_logger = logging.getLogger(__name__)


class Lead(models.Model):
    _inherit = 'crm.lead'

    request_ids = fields.One2many(
        'request.request',
        'crm_lead_id',
        string='Related requests')
    request_count = fields.Integer(compute='_compute_request_count')

    @api.depends()
    def _compute_request_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='request_ids')
        for record in self:
            record.request_count = mapped_data.get(record.id, 0)

    def action_view_related_requests(self):
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            context=dict(
                default_author_id=self.partner_id.id,
                default_crm_lead_id=self.id,
            ),
            domain=[('crm_lead_id', '=', self.id)])

    def action_create_request(self):
        return self.env['generic.mixin.get.action'].get_form_action_by_xmlid(
            'generic_request.action_request_window',
            context=dict(
                default_author_id=self.partner_id.id,
                default_crm_lead_id=self.id,
            ))
