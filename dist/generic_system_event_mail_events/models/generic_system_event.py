from odoo import models, fields


class GenericSystemEvent(models.Model):
    _inherit = "generic.system.event"

    mail_message_id = fields.Many2one('mail.message', readonly=True)
    mail_activity_id = fields.Many2one('mail.activity', readonly=True)
    mail_activity_type_id = fields.Many2one(
        'mail.activity.type', readonly=True)
