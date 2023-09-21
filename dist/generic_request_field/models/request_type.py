from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class RequestType(models.Model):
    _inherit = 'request.type'

    field_ids = fields.One2many(
        'request.field', 'request_type_id', string='Fields', copy=True)
    field_count = fields.Integer(compute='_compute_field_count')

    @api.depends('field_ids')
    def _compute_field_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='field_ids')
        for record in self:
            record.field_count = mapped_data.get(record.id, 0)
