from odoo import fields, models, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class GenericLocation(models.Model):
    _inherit = 'generic.location'

    related_request_ids = fields.One2many(
        'request.request',
        'generic_location_id',
        string='Related Requests',
        readonly=True)
    related_request_count = fields.Integer(
        string='Requests',
        compute='_compute_related_request_count',
        readonly=True)

    @api.depends('related_request_ids')
    def _compute_related_request_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='related_request_ids')
        for record in self:
            record.related_request_count = mapped_data.get(record.id, 0)

    def action_view_request_for_location(self):
        self.ensure_one()
        return self.get_action_by_xmlid(
            'generic_request.action_request_window',
            domain=[('generic_location_id', '=', self.id)],
            context={
                'default_generic_location_id': self.id,
            })
