from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class RequestType(models.Model):
    _inherit = 'request.type'

    survey_answer_ids = fields.One2many(
        'survey.user_input', 'request_type_id',
        string="Answers")
    survey_answer_count = fields.Integer(
        compute='_compute_survey_answer_count',
        readonly=True)

    @api.depends('survey_answer_ids', 'survey_answer_ids.state')
    def _compute_survey_answer_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='survey_answer_ids',
            domain=[('state', '=', 'done')], sudo=True)
        for record in self:
            record.survey_answer_count = mapped_data.get(record.id, 0)

    def action_show_survey_answers(self):
        action = self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'survey.action_survey_user_input',
            domain=[('request_type_id', '=', self.id)])
        return action
