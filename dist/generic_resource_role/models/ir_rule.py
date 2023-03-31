from odoo import models
from odoo.osv import expression


class IrRule(models.Model):
    _inherit = 'ir.rule'

    def _generic_res__get_domain(self, mode):
        return expression.OR([
            super(IrRule, self)._generic_res__get_domain(mode),
            [('resource_role_sec_view_ids.user_id', '=', self.env.user.id)],
        ])
