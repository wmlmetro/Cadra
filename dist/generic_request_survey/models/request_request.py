from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class RequestRequest(models.Model):
    _inherit = 'request.request'

    answer_ids = fields.One2many(
        'survey.user_input', 'request_id',
        string="Answers")
    answer_count = fields.Integer(
        compute='_compute_answer_count',
        readonly=True, compute_sudo=True)
    stage_allow_send_survey = fields.Boolean(
        related='stage_id.allow_send_survey', readonly=True)

    @api.depends('answer_ids', 'answer_ids.state')
    def _compute_answer_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='answer_ids',
            domain=[('state', '=', 'done')])
        for record in self:
            record.answer_count = mapped_data.get(record.id, 0)

    def action_show_survey_answers(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'survey.action_survey_user_input',
            context=dict(
                self.env.context,
                search_default_completed=1),
            domain=[('request_id', '=', self.id)],
        )

    def action_send_request_survey(self):
        self.ensure_one()

        # create default partner recipient list:
        # add followers, exclude request author, creator, assignee
        request_follower_ids = self.message_partner_ids.ids
        if self.author_id.id in request_follower_ids:
            request_follower_ids.remove(self.author_id.id)
        if self.created_by_id.partner_id.id in request_follower_ids:
            request_follower_ids.remove(self.created_by_id.partner_id.id)
        if self.user_id.partner_id.id:
            if self.user_id.partner_id.id in request_follower_ids:
                request_follower_ids.remove(self.user_id.partner_id.id)
        _ctx = dict(
            self.env.context,
            default_use_template=True,
            default_request_id=self.id,
            default_partner_ids=[(6, 0, request_follower_ids)])
        _default_template = self.env.ref(
            'generic_request_survey.email_template_survey',
            raise_if_not_found=False)
        if _default_template:
            _ctx.update({
                'default_template_id': _default_template.id,
            })

        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request_survey.request_request_send_survey_action',
            context=_ctx
        )
