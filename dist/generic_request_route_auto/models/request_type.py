from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class RequestStageRouteTrigger(models.Model):
    _inherit = 'request.type'

    route_trigger_ids = fields.One2many(
        'request.stage.route.trigger', 'request_type_id', readonly=True)
    route_trigger_count = fields.Integer(
        compute='_compute_route_trigger_count', readonly=True)

    @api.depends('route_trigger_ids')
    def _compute_route_trigger_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='route_trigger_ids')
        for record in self:
            record.route_trigger_count = mapped_data.get(record.id, 0)

    def action_view_route_triggers(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request_route_auto.action_request_stage_route_triggers',
            domain=[('request_type_id', '=', self.id)],
            context={'default_dummy_request_type_id': self.id})
