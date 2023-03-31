from odoo import models, fields


class RequestWizardClose(models.TransientModel):
    _inherit = 'request.wizard.close'

    reopen_as = fields.Selection(selection_add=[
        ('related-request', 'Related Request'),
    ])

    def _reopen_prepare_data(self):
        res = {}
        if self.reopen_as == 'related-request':
            res.update({'related_request_ids': [(4, self.request_id.id)]})
        res.update(super()._reopen_prepare_data())
        return res
