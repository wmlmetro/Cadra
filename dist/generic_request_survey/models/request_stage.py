from odoo import fields, models


class RequestStage(models.Model):
    _inherit = 'request.stage'

    allow_send_survey = fields.Boolean(
        help='"Send Survey" button will be visible only when this'
             ' option is enabled at the current Request stage.'
    )
