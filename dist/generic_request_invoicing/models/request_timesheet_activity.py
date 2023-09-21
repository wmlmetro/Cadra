from odoo import models, fields


class RequestTimesheetActivity(models.Model):
    _inherit = 'request.timesheet.activity'

    is_billable = fields.Boolean(
        default=False,
        help="If set, then all timesheet lines of this activity "
             "will be billable by default.")
