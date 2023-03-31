from odoo import models


class RequestCreationTemplate(models.Model):
    _inherit = 'request.creation.template'

    # Overriden to update mail template when request creation template changes
    def write(self, vals):
        res = super(RequestCreationTemplate, self).write(vals)
        self.env['request.mail.source'].search([
            ('request_creation_template_id', 'in', self.ids),
        ]).update_alias_defaults()
        return res
