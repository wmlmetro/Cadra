import logging
from odoo import models
from odoo.osv import expression
from odoo.addons.generic_system_event import on_event

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = "request.request"

    @on_event('*')
    def _on_any_event__run_event_actions(self, event):
        domain = expression.AND([
            [('event_type_ids.id', '=', event.event_type_id.id)],
            expression.OR([
                [('request_type_id', '=', self.sudo().type_id.id)],
                [('request_type_id', '=', False)],
            ]),
        ])
        if event.route_id:
            domain = expression.AND([
                domain,
                expression.OR([
                    [('route_id', '=', False)],
                    [('route_id', '=', event.route_id.id)],
                ]),
            ])

        actions = self.env['request.event.action'].sudo().search(domain)
        # Run actions in original env
        self.env['request.event.action'].browse(actions.ids).with_context(
            request_event_ctx=event.get_context(),
            request_event=event,
        ).run(self, event)
