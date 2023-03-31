import logging

from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = 'request.request'

    calendar_event_ids = fields.One2many(
        'calendar.event',
        'res_id',
        string='Meetings',
        domain=lambda self, *a, **k: [('res_model', '=', self._name)]
        )
    meeting_count = fields.Integer(compute='_compute_meeting_count')

    @api.depends()
    def _compute_meeting_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='calendar_event_ids',
            domain=[('res_model', '=', self._name)],
            sudo=True,
        )
        for request in self:
            request.meeting_count = mapped_data.get(request.id, 0)

    def _get_view_related_meeting_context(self):
        default_partners = [
            (4, self.env.user.partner_id.id),
        ]
        if self.author_id:
            default_partners += [(4, self.author_id.id)]
        if self.user_id:
            default_partners += [(4, self.user_id.partner_id.id)]

        return {
            'default_partner_ids': default_partners,
            'default_res_id': self.id,
            'default_res_model': self._name,
            'default_name': self.name,
            'default_description': self.request_text_sample,
        }

    def action_view_related_meeting(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'calendar.action_calendar_event',
            context=self._get_view_related_meeting_context())
