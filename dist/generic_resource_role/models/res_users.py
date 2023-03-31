from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def action_view_resource_role_links(self):
        return self.partner_id.action_view_resource_role_links()
