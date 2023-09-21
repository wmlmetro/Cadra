from odoo import models, api


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    def _generic_system_event_trigger(self, event_type_code):
        for activity in self:
            event_source = self.env[
                'generic.system.event.source'
            ].get_event_source(activity.res_model)
            if event_source:
                record = self.env[activity.res_model].browse(activity.res_id)
                if record.exists():
                    record.trigger_event(event_type_code, {
                        'mail_activity_id': activity.id,
                        'mail_activity_type_id': activity.activity_type_id.id,
                    })

    @api.model_create_multi
    def create(self, values):
        activities = super().create(values)
        activities._generic_system_event_trigger('mail-activity-new')
        return activities

    def write(self, values):
        res = super().write(values)

        if self.env.context.get('_system_event_write_protection_', False):
            return res

        self._generic_system_event_trigger('mail-activity-changed')

        return res

    def unlink(self):
        if self.env.context.get('_system_event_mail_activity_done'):
            # TODO: Try to save message that will be created by completed
            # activity
            self._generic_system_event_trigger('mail-activity-done')
        else:
            self._generic_system_event_trigger('mail-activity-delete')

        return super(MailActivity, self).unlink()

    def _action_done(self, feedback=False, attachment_ids=None):
        # This is needed to indicate that mail activity is completed with (or
        # without) feedback
        return super(
            MailActivity,
            self.with_context(
                _system_event_write_protection_=True,
                _system_event_mail_activity_done=True,
            )
        )._action_done(feedback=feedback, attachment_ids=attachment_ids)
