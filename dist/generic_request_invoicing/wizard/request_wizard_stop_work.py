from odoo import models, fields


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
