from odoo import models
from odoo.osv import expression


class RequestWizardClose(models.TransientModel):
    _inherit = 'request.wizard.close'

    def _get_next_route_domain(self):
        self.ensure_one()
        return expression.AND([
            super(RequestWizardClose, self)._get_next_route_domain(),
            [('auto_only', '=', False)],
        ])
