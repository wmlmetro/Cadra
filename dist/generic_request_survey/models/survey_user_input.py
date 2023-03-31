from odoo import models, fields, api


class SurveyUserInput(models.Model):
    _inherit = 'survey.user_input'

    request_id = fields.Many2one(
        'request.request',
        index=True,
        ondelete="cascade",
    )
    request_type_id = fields.Many2one(
        related='request_id.type_id',
        string="Request Type",
        store=True, index=True, ondelete='cascade', readonly=True)

    @api.model
    def create(self, *args, **kwargs):
        user_input = super(SurveyUserInput, self).create(*args, **kwargs)
        for record in user_input:
            if record.request_id:
                record.request_id.trigger_event('survey_sent', {
                    'survey_id': record.survey_id.id,
                    'survey_user_input_id': record.id,
                })
        return user_input

    def write(self, vals):
        if vals.get('state', False) != 'done':
            return super(SurveyUserInput, self).write(vals)
        state_change = []
        for record in self:
            if record.request_id and record.state != vals['state']:
                state_change.append(record)
        res = super(SurveyUserInput, self).write(vals)
        for record in state_change:
            if record.state == 'done':
                record.request_id.trigger_event('survey_answer_received', {
                    'survey_id': record.survey_id.id,
                    'survey_user_input_id': record.id,
                })
                # check if all survey answers completed
                if all(answer.state == 'done' for answer in
                       record.request_id.answer_ids.filtered(
                           lambda answ: answ.survey_id == record.survey_id
                       )):
                    record.request_id.trigger_event('survey_completed', {
                        'survey_id': record.survey_id.id,
                    })
        return res
