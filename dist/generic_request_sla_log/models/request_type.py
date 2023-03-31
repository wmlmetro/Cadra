from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class RequestType(models.Model):
    _inherit = 'request.type'

    sla_calendar_id = fields.Many2one(
        'resource.calendar', string="Working time")
    sla_log_ids = fields.One2many('request.sla.log', 'request_type_id')
    sla_log_count = fields.Integer(compute='_compute_sla_log_count')

    @api.depends('sla_log_ids')
    def _compute_sla_log_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='sla_log_ids')
        for record in self:
            record.sla_log_count = mapped_data.get(record.id, 0)
