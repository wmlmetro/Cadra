from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class GenericTeam(models.Model):
    _inherit = 'generic.team'

    request_ids = fields.One2many(
        'request.request', 'team_id', string='Requests')
    request_count = fields.Integer(
        compute='_compute_request_count', readonly=True)

    @api.depends('request_ids')
    def _compute_request_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='request_ids')
        for record in self:
            record.request_count = mapped_data.get(record.id, 0)

    def action_show_all_requests(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            context=dict(
                self.env.context,
                search_default_team_id=self.id),
            domain=[('team_id', '=', self.id)])
