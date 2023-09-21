import logging
from odoo import models, api

_logger = logging.getLogger(__name__)


class Message(models.Model):
    _inherit = "mail.message"

    def _update_create_vals_from_request_mail_source(self, vals):
        if vals.get('model') == 'request.request' and vals.get('res_id'):
            request = self.sudo().env['request.request'].browse(vals['res_id'])
            if request.mail_source_id:
                # In case if it is request, and request has mail source,
                # we have to update settings due to mail source configuration
                # TODO: may be it have sense to take into account email_from
                #       provided in vals (if present)
                author_id = vals.get('author_id', self.env.user.partner_id.id)
                author = (
                    self.env['res.partner'].browse(author_id)
                    if author_id else None)
                vals = dict(
                    vals,
                    email_from=request.mail_source_id.get_email_from_address(
                        author=author,
                        company=request.company_id,
                    )
                )
        return vals

    @api.model_create_multi
    def create(self, vals):
        vals = [
            self._update_create_vals_from_request_mail_source(v) for v in vals
        ]
        return super().create(vals)
