from odoo.osv import expression
from odoo import models, fields, api


class Website(models.Model):
    _inherit = 'website'

    broadcast_message_ids = fields.Many2many(
        'crnd.wsd.broadcast.message',
        compute='_compute_broadcast_messages',
        compute_sudo=True)

    @api.depends()
    def _compute_broadcast_messages(self):
        for rec in self:
            messages = self.env['crnd.wsd.broadcast.message'].sudo().search(
                expression.AND([
                    [('date_beg', '<=', fields.Datetime.now())],
                    [('date_end', '>=', fields.Datetime.now())],
                    expression.OR([
                        [('website_ids', '=', rec.id)],
                        [('website_ids', '=', False)],
                    ]),
                ])
            )
            rec.broadcast_message_ids = messages
