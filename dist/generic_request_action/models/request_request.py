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
            [('event_type_ids', '=', event.event_type_id.id)],
            expression.OR([
                [('request_type_id', '=', self.type_id.id)],
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

        self.env['request.event.action'].search(domain).with_context(
            request_event_ctx=event.get_context(),
            request_event=event,
        ).run(self, event)
