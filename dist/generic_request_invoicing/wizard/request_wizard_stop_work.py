from odoo import models, fields, api


class RequestWizardStopWork(models.TransientModel):
    _inherit = 'request.wizard.stop.work'

    is_billable = fields.Boolean()
    enable_invoicing = fields.Boolean(
        related='request_id.enable_invoicing',
        readonly=True)

    def _prepare_timesheet_line_data(self):
        res = super(
            RequestWizardStopWork,
            self,
        )._prepare_timesheet_line_data()
        res.update({
            'is_billable': self.is_billable,
        })
        return res

    @api.onchange('activity_id', 'request_id')
    def _onchange_activity_id(self):
        for record in self:
            if not record.activity_id:
                continue
            if not record.request_id.type_id.enable_invoicing:
                continue

            record.is_billable = record.activity_id.is_billable
