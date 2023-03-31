from odoo import models, fields, api

from odoo.addons.generic_resource.tools.utils import resource_proxy
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class GenericResource(models.Model):
    _inherit = 'generic.resource'

    timesheet_line_ids = fields.One2many(
        'generic.resource.timesheet.line', 'resource_id', string="Timesheets")
    timesheet_line_count = fields.Integer(
        string="Count of Timesheets", compute='_compute_timesheet_line_count')

    @api.depends('timesheet_line_ids')
    def _compute_timesheet_line_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='timesheet_line_ids')
        for record in self:
            record.timesheet_line_count = mapped_data.get(record.id, 0)

    @resource_proxy
    def action_view_resource_timesheet(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_resource_timesheet'
            '.generic_resource_timesheet_line_action',
            context=dict(
                self.env.context,
                default_resource_id=self.id,
                default_resource_type_id=self.res_type_id.id,
                default_resource_res_id=self.res_id),
            domain=[('resource_id', '=', self.id)],
        )
