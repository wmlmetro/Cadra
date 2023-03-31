from odoo import fields, models, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class GenericLocation(models.Model):
    _inherit = 'generic.location'

    located_resource_ids = fields.One2many(
        'generic.resource',
        'placed_on_location_id',
        string='Located Resources',
        readonly=True)
    located_resource_count = fields.Integer(
        string='Resources',
        compute='_compute_located_resource_count',
        readonly=True)
    located_resource_total_count = fields.Integer(
        compute='_compute_located_resource_count',
        string='Total Located Resources',
        readonly=True)

    @api.depends('located_resource_ids', 'child_all_ids')
    def _compute_located_resource_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='located_resource_ids')
        for record in self:
            record.located_resource_count = mapped_data.get(record.id, 0)
            record.located_resource_total_count = len(
                record.child_all_ids.mapped('located_resource_ids'))

    def action_view_resource_total_location(self):
        self.ensure_one()
        loc_ids = (self + self.child_all_ids).ids
        return self.get_action_by_xmlid(
            'generic_resource_location.'
            'action_view_generic_resource_related_location',
            domain=[('placed_on_location_id', 'in', loc_ids)])
