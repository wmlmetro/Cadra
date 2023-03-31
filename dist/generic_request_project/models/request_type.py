from odoo import models, fields


class RequestType(models.Model):
    _inherit = 'request.type'

    use_subtasks = fields.Boolean(default=False)
    use_worklog = fields.Boolean(default=False)
