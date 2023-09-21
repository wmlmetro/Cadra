from odoo import models, api


class Message(models.Model):
    _inherit = "mail.message"

    @api.model_create_multi
    def create(self, vals):
        messages = super().create(vals)
        if self._name != 'mail.message':
            return messages

        for message in messages:
            event_source = self.env[
                'generic.system.event.source'
            ].get_event_source(message.model)
            if event_source:
                record = self.env[message.model].browse(message.res_id)

                if message.subtype_id == self.env.ref('mail.mt_note'):
                    record.trigger_event('mail-note', {
                        'mail_message_id': message.id,
                    })
                elif message.subtype_id == self.env.ref('mail.mt_comment'):
                    record.trigger_event('mail-comment', {
                        'mail_message_id': message.id,
                    })

        return messages
