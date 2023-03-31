from odoo import models, api


class Message(models.Model):
    _inherit = "mail.message"

    @api.model
    def create(self, vals):
        if vals.get('model') == 'request.request' and vals.get('res_id'):
            request = self.sudo().env['request.request'].browse(vals['res_id'])
            if request.mail_source_id:
                # If mailsource selected, than we have to send all email using
                # mailsource's address as 'email_from'
                vals = dict(
                    vals,
                    email_from=request.mail_source_id.get_email_address())
        return super().create(vals)
