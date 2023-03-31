from odoo import models


class GenericTeamMember(models.Model):
    _name = "generic.team"
    _inherit = [
        'generic.team',
        'generic.tag.mixin',
    ]
