from odoo import models, fields, api


class RequestSlaLog(models.Model):
    _name = 'request.sla.log'
    _description = 'Request SLA Log'
    _order = 'date DESC, id DESC'

    def _get_selection_kanban_state(self):
        return self.env['request.request']._fields['kanban_state'].selection

    request_id = fields.Many2one(
        'request.request', required=True, index=True, readonly=True,
        ondelete='cascade')
    date_prev = fields.Datetime(
        required=True, index=True, readonly=True)
    date = fields.Datetime(
        required=True, index=True, readonly=True, default=fields.Datetime.now)
    request_type_id = fields.Many2one(
        related='request_id.type_id', index=True, readonly=True, store=True)
    stage_id = fields.Many2one(
        'request.stage', required=True, index=True, readonly=True)
    stage_type_id = fields.Many2one(
        'request.stage.type', string="Stage Types", index=True,
        ondelete='restrict', readonly=True)
    kanban_state = fields.Selection(
        selection='_get_selection_kanban_state', index=True, readonly=True)
    assignee_id = fields.Many2one('res.users', index=True, readonly=True)
    user_id = fields.Many2one(
        'res.users', index=True, required=True, readonly=True)

    time_spent_total = fields.Float(
        readonly=True, compute='_compute_time_spent', store=True)

    # TODO: Do we need to compute this field here, in case multiple calendar
    # could be used for different service levels? may be in would be enough to
    # compute in in SLA control lines?
    time_spent_calendar = fields.Float(
        readonly=True, compute='_compute_time_spent', store=True)
    calendar_id = fields.Many2one('resource.calendar', 'Working time')

    @api.depends('date_prev', 'date', 'calendar_id')
    def _compute_time_spent(self):
        for record in self:
            date_prev = fields.Datetime.from_string(record.date_prev)
            date = fields.Datetime.from_string(record.date)
            delta = date - date_prev
            record.time_spent_total = delta.total_seconds() / float(60 * 60)
            record.time_spent_calendar = record.get_time_spent_calendar(
                record.calendar_id)

    def get_time_spent_calendar(self, calendar):
        """ Return time spent by this line using selected calendar

            :param RecordSer calendar: single record for calendar to use
        """
        self.ensure_one()
        if not calendar:
            return 0.0
        return calendar.get_work_hours_count(
            start_dt=self.date_prev,
            end_dt=self.date,
            compute_leaves=True,
        )
