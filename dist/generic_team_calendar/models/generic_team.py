import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class GenericTeam(models.Model):
    _inherit = 'generic.team'

    calendar_event_ids = fields.One2many(
        'calendar.event',
        'res_id',
        string='Meetings',
        domain=lambda self, *a, **k: [('res_model', '=', self._name)]
        )

    meeting_count = fields.Integer(compute='_compute_meeting_count')

    def _compute_meeting_count(self):
        meeting_data = self.env['calendar.event'].sudo().read_group(
            [('res_model', '=', self._name), ('res_id', 'in', self.ids)],
            ['res_id'], ['res_id']
        )
        mapped_data = {m['res_id']: m['res_id_count'] for m in meeting_data}
        for request in self:
            request.meeting_count = mapped_data.get(request.id, 0)

    def action_view_related_meeting(self):
        self.ensure_one()

        default_partners = [
            (4, self.leader_id.id),
            (4, self.env.user.partner_id.id),
        ]

        if self.task_manager_id.id:
            default_partners += [(4, self.task_manager_id.id)]

        default_partners += [(4, team_member.user_id.partner_id.id)
                             for team_member in self.team_member_ids]

        return self.get_action_by_xmlid(
            'calendar.action_calendar_event',
            context=dict(
                default_partner_ids=default_partners,
                default_res_id=self.id,
                default_res_model=self._name,
            ),
            domain=[('res_id', '=', self.id)],
        )
