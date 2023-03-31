from odoo import models, fields


class GenReqSLARule(models.Model):

    _inherit = 'request.sla.rule'

    assigned_team = fields.Selection(
        required=True,
        selection=[('none', 'None'), ('yes', 'Yes'), ('no', 'No')],
        default='none',
    )
