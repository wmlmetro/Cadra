import logging

from odoo import models, api

_logger = logging.getLogger(__name__)


class GenericWizardAssign(models.TransientModel):
    _inherit = 'generic.wizard.assign'

    @api.model
    def default_get(self, fields_list):
        res = super(GenericWizardAssign, self).default_get(fields_list)

        model = res.get('assign_model', False)
        if model and model == 'request.request':
            res.update({
                'unsubscribe_prev_assignee': (
                    self.env.user.company_id.
                    request_autoset_unsubscribe_prev_assignee),
            })

        return res
