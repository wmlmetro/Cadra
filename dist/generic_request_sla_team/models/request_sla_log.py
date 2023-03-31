from odoo import models, fields


class GenReqSLALog(models.Model):

    _inherit = 'request.sla.log'

    team_id = fields.Many2one('generic.team', index=True, readonly=True)
