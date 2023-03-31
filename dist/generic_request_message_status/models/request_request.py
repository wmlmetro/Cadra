import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = 'request.request'

    request_messaging_state = fields.Selection(selection=[
        ('new_comment', 'New comment'),
        ('new_customer_message', 'New customer message'),
        ('waiting_customer_response', 'Waiting customer response')
        ], compute='_compute_request_messaging_state')
    request_messaging_state_highlight = fields.Boolean(
        compute='_compute_request_messaging_state')
    request_messaging_date = fields.Datetime(
        'Last Message Date',
        help='Date of the last message posted on the record.',
        compute='_compute_request_messaging_state')

    @api.depends('message_discussion_ids')
    def _compute_request_messaging_state(self):
        for rec in self:
            if rec.message_discussion_ids:
                last_message = rec.message_discussion_ids.sorted()[0]
                rec.request_messaging_date = last_message.date
                if last_message.author_id in (rec.author_id, rec.partner_id):
                    rec.request_messaging_state = 'new_customer_message'
                elif last_message.author_id == rec.user_id.partner_id:
                    rec.request_messaging_state = 'waiting_customer_response'
                else:
                    rec.request_messaging_state = 'new_comment'
                rec.request_messaging_state_highlight = last_message.needaction
            else:
                rec.request_messaging_state = False
                rec.request_messaging_state_highlight = False
                rec.request_messaging_date = False
