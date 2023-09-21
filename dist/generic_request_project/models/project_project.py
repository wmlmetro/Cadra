from odoo import models, fields, api

from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class ProjectProject(models.Model):
    _inherit = 'project.project'

    request_ids = fields.One2many(
        'request.request', 'project_id', 'Requests',
        readonly=True)
    request_count = fields.Integer(compute='_compute_request_count')

    @api.depends('request_ids')
    def _compute_request_count(self):
        mapped_data = read_counts_for_o2m(
            records=self.sudo(), field_name='request_ids')
        for record in self:
            record.request_count = mapped_data.get(record.id, 0)

    def action_button_show_project_requests(self):
        action = self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            context={'default_project_id': self.id},
            domain=[('project_id', '=', self.id)])
        return action
