from odoo import models, fields


class RequestEvent(models.Model):
    _inherit = 'request.event'

    survey_id = fields.Many2one('survey.survey', readonly=True)
    survey_user_input_id = fields.Many2one('survey.user_input', readonly=True)
