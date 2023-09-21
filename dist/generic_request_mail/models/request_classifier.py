from odoo import models


class RequestClassifier(models.Model):
    _inherit = 'request.classifier'

    # Overriden to update mail template when request creation template changes
    def write(self, vals):
        res = super().write(vals)
        self.env['request.mail.source'].search([
            ('request_creation_template_id.request_classifier_id',
             'in',
             self.ids),
        ]).update_alias_defaults()
        return res
