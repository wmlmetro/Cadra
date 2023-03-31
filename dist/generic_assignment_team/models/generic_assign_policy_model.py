import logging

from odoo import models, fields

# from odoo.addons.generic_mixin import post_write

_logger = logging.getLogger(__name__)


class GenericAssignPolicyModel(models.Model):
    _inherit = 'generic.assign.policy.model'

    assign_team_field_id = fields.Many2one(
        'ir.model.fields', readonly=True,
        ondelete='cascade',
        domain=(
            "[('ttype', '=', 'many2one'), ('relation', '=', 'generic.team')]")
    )
