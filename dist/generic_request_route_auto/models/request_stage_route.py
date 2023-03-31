import logging
import traceback
from odoo import models, fields, api, exceptions, _
from odoo.tools import ustr
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m
from odoo.addons.generic_mixin import post_write

_logger = logging.getLogger(__name__)


class RequestStageRoute(models.Model):
    _inherit = "request.stage.route"

    trigger_ids = fields.One2many(
        'request.stage.route.trigger', 'route_id', string='Triggers')
    trigger_count = fields.Integer(
        compute='_compute_trigger_count', readonly=True)

    auto_only = fields.Boolean(
        help="Auto-only route. "
             "Requests could be moved by this route only by triggers",
        tracking=True)

    @api.depends('trigger_ids')
    def _compute_trigger_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='trigger_ids')
        for record in self:
            record.trigger_count = mapped_data.get(record.id, 0)

    @post_write('stage_from_id')
    def _after_stage_from_id_changed__clear_trigger_caches(self, changes):
        # Here we need to clear cache of triggers, because, otherwise,
        # this change could break the triggers logic
        self.env[
            'request.stage.route.trigger'
        ]._get_auto_on_write_trigger_ids_for_stage.clear_cache(
            self.env['request.stage.route.trigger']
        )

    def _ensure_can_move(self, request):
        if self.auto_only and not self.env.context.get('_trigger_move', False):
            raise exceptions.AccessError(
                _("This route (%s) is auto-only, "
                  "thus could not be triggered manually."
                  "") % self.display_name)
        return super(RequestStageRoute, self)._ensure_can_move(request)

    def trigger_route(self, req, trigger, event):
        """ Try to move specified request via route 'self'.

            :return: True if request moved,
                     False if if is not possible to move via this route
        """
        try:
            with self.env.cr.savepoint():
                req.with_context(_trigger_move=True).write({
                    'stage_id': self.stage_to_id.id,
                })
        except (exceptions.ValidationError, exceptions.AccessError) as exc:
            event.write({
                'message': ustr(exc),
                'error': "<pre>%s</pre>" % traceback.format_exc(),
            })
            return False

        return True

    def action_request_stage_route_trigger_actions(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request_route_auto.action_request_stage_route_triggers',
            context={'default_route_id': self.id},
            domain=[('route_id', '=', self.id)])
