from odoo import models, fields, api

from odoo.addons.generic_mixin import pre_write
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class RequestRequest(models.Model):
    _inherit = 'request.request'

    sla_log_ids = fields.One2many('request.sla.log', 'request_id', copy=False)
    sla_log_count = fields.Integer(compute='_compute_sla_log_count')

    @api.depends('sla_log_ids')
    def _compute_sla_log_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='sla_log_ids')
        for record in self:
            record.sla_log_count = mapped_data.get(record.id, 0)

    def _prepare_sla_log_vals(self):
        vals = {
            'stage_id': self.stage_id.id,
            'stage_type_id': self.stage_id.type_id.id,
            'assignee_id': self.user_id.id,
            'user_id': self.env.user.id,
            'calendar_id': self.sudo().type_id.sla_calendar_id.id,
            'kanban_state': self.kanban_state
        }
        return vals

    # Use pre_write, because we want to log state that was before write called.
    @pre_write('stage_id', 'user_id', 'kanban_state')
    def _generate_request_sla_log_line(self, changes):
        if self.sla_log_ids:
            date_prev = self.sla_log_ids.sorted()[0].date
        else:
            date_prev = self.date_created

        sla_log_vals = self._prepare_sla_log_vals()
        sla_log_vals.update({
            'date': fields.Datetime.now(),
            'date_prev': date_prev
        })

        return {
            'sla_log_ids': [(0, 0, sla_log_vals)],
        }

    def action_show_related_sla_log_lines(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request_sla_log.action_request_sla_log_view__tree_first',
            domain=[('request_id', '=', self.id)],
            context={'default_request_id': self.id},
        )
