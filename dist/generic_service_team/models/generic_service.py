from odoo import models, fields


class GenericSerivce(models.Model):
    _inherit = [
        'generic.service',
    ]

    team_id = fields.Many2one('generic.team', "Service Team", index=True)
