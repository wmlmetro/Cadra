import logging

from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m
from odoo.addons.generic_system_event import on_event

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = "request.request"

    trigger_event_ids = fields.One2many(
        'request.stage.route.trigger.event', 'request_id', readonly=True)
    trigger_event_count = fields.Integer(
        string='Trigger Events', readonly=True,
        compute='_compute_trigger_event_count',
        compute_sudo=True)

    @api.depends('trigger_event_ids')
    def _compute_trigger_event_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='trigger_event_ids', sudo=True)
        for record in self:
            record.trigger_event_count = mapped_data.get(record.id, 0)

    def write(self, vals):
        res = super(RequestRequest, self).write(vals)

        # Trigger routes for requests found
        for request in self:
            triggers = self.env[
                'request.stage.route.trigger'
            ].get_auto_on_write_triggers_for_stage(request.stage_id)
            for trg in triggers:
                if trg.trigger != 'auto_on_write':
                    continue
                trg_fields = trg.sudo().trigger_on_write_field_ids
                trg_field_names = trg_fields.mapped('name')
                if not trg_field_names and trg._trigger(request):
                    break
                if set(trg_field_names) & set(vals) and trg._trigger(request):
                    break
        return res

    @on_event('*')
    def _on_any_event__trigger_request_routes(self, event):
        trigger_domain = [
            ('trigger', '=', 'event'),
            ('event_type_ids.id', '=', event.sudo().event_type_id.id),
            ('route_stage_from_id', '=', self.sudo().stage_id.id),
            ('request_type_id', '=', self.sudo().type_id.id),
        ]

        triggers = self.env['request.stage.route.trigger'].sudo().search(
            trigger_domain,
        )
        # Run triggers in original env
        triggers = self.env['request.stage.route.trigger'].browse(triggers.ids)
        for trigger in triggers:
            if trigger._trigger(self, event):
                # After first trigger have success, there is no sens
                # to check others
                break

    def action_show_trigger_events(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request_route_auto'
            '.action_request_stage_route_trigger_events',
            domain=[('request_id', '=', self.id)],
            context={'search_default_filter_errors': True}
        )
