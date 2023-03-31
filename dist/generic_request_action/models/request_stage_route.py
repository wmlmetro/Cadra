from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class RequestStageRoute(models.Model):
    _inherit = "request.stage.route"

    action_ids = fields.One2many(
        'request.event.action', 'route_id', 'Actions')
    action_count = fields.Integer(
        compute='_compute_action_count', readonly=True)

    @api.depends('action_ids')
    def _compute_action_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='action_ids')
        for record in self:
            record.action_count = mapped_data.get(record.id, 0)

    def action_show_request_actions(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request_action.action_request_event_actions',
            domain=[('route_id', '=', self.id)],
            context={
                'default_route_id': self.id,
                'default_request_type_id': self.request_type_id.id,
            })
