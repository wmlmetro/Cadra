from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class GenericResourceTimesheetActivity(models.Model):
    _name = 'generic.resource.timesheet.activity'
    _description = 'Generic Resource Timesheet Activity'

    name = fields.Char(required=True, translate=True, index=True)
    active = fields.Boolean(index=True, default=True)
    model_id = fields.Many2one(
        'ir.model', 'Model', index=True, domain=[('transient', '=', False)],
        ondelete='set null')
    description = fields.Text()

    timesheet_line_ids = fields.One2many(
        'generic.resource.timesheet.line', 'activity_id', readonly=True,
        string='Timesheet Lines')
    timesheet_line_count = fields.Integer(
        compute='_compute_timesheet_line_count', readonly=True)

    color = fields.Char(default='rgba(124,123,173,1)')

    @api.depends('timesheet_line_ids')
    def _compute_timesheet_line_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='timesheet_line_ids')
        for record in self:
            record.timesheet_line_count = mapped_data.get(record.id, 0)

    def action_open_timesheet_lines(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            "generic_resource_timesheet."
            "generic_resource_timesheet_line_action",
            domain=[('activity_id', '=', self.id)],
            context={'default_activity_id': self.id})
