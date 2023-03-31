import logging
from dateutil.relativedelta import relativedelta

from odoo import api, models, fields
from odoo.addons.generic_mixin import post_write

_logger = logging.getLogger(__name__)


class ProjectTask(models.Model):
    _name = 'project.task'

    _inherit = [
        'project.task',
        'generic.system.event.source.mixin',
    ]

    _generic_system_event_source__auto_create = True
    _generic_system_event_source__event_data_model = 'project.task.event.data'

    # Keep info about events related to deadline,
    # to avoid sending same event multiple times
    deadline_event_tomorrow_sent = fields.Boolean(readonly=True, default=False)
    deadline_event_today_sent = fields.Boolean(readonly=True, default=False)
    deadline_event_overdue_sent = fields.Boolean(readonly=True, default=False)

    @post_write('date_deadline')
    def _after_deadline_changed(self, changes):
        old_date, new_date = changes['date_deadline']
        self.trigger_event('deadline-changed', {
            'old_deadline': old_date,
            'new_deadline': new_date,
        })

        # Update event sent status on task
        # By default cleanup info about events already triggered.
        event_status = {
            'deadline_event_tomorrow_sent': False,
            'deadline_event_today_sent': False,
            'deadline_event_overdue_sent': False,
        }

        # This comment was added in version 12.
        # The method below should be reinvestigated
        # when migrating to a version 14 and higher.
        # From odoo 14 in model `project.task.type` there is a field
        # called `is_closed` that defines closed stage of task.
        # Reuse it here instead of `fold` field.
        if new_date and not self.stage_id.fold:
            # Immediately trigger deadline-related date-based events
            # if needed. We do not trigger events when task closed (folded)
            if new_date == fields.Date.today():
                self.trigger_event('deadline-today')
                event_status['deadline_event_today_sent'] = True
            elif new_date < fields.Date.today():
                self.trigger_event('deadline-overdue')
                event_status['deadline_event_overdue_sent'] = True
            elif new_date == fields.Date.today() + relativedelta(days=1):
                self.trigger_event('deadline-tomorrow')
                event_status['deadline_event_tomorrow_sent'] = True
        self.write(event_status)

    @post_write('stage_id')
    def _after_stage_id_changed(self, changes):
        old_stage, new_stage = changes['stage_id']
        self.trigger_event('stage-changed', {
            'old_stage_id': old_stage.id,
            'new_stage_id': new_stage.id,
        })

    @api.model
    def _scheduler_check_deadlines(self):
        """ Check deadline dates and trigger events:
            - Deadline Tomorrow
            - Deadline Today
            - Deadline Overdue
            if needed
        """
        today = fields.Date.today()
        tomorrow = today + relativedelta(days=1)
        tasks_deadline_tomorrow = self.sudo().search([
            ('stage_id.fold', '=', False),
            ('date_deadline', '=', tomorrow),
            ('deadline_event_tomorrow_sent', '=', False)])
        tasks_deadline_today = self.sudo().search([
            ('stage_id.fold', '=', False),
            ('date_deadline', '=', today),
            ('deadline_event_today_sent', '=', False)])
        tasks_deadline_yesterday = self.sudo().search([
            ('stage_id.fold', '=', False),
            ('date_deadline', '<', today),
            ('deadline_event_overdue_sent', '=', False)])
        for task in tasks_deadline_tomorrow:
            task.trigger_event('deadline-tomorrow')
            task.deadline_event_tomorrow_sent = True
        for task in tasks_deadline_today:
            task.trigger_event('deadline-today')
            task.deadline_event_today_sent = True
        for task in tasks_deadline_yesterday:
            task.trigger_event('deadline-overdue')
            task.deadline_event_overdue_sent = True
