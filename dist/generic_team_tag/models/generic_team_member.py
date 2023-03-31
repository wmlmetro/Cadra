from odoo import models


class GenericTeamMember(models.Model):
    _name = "generic.team.member"
    _inherit = [
        'generic.team.member',
        'generic.tag.mixin',
    ]
