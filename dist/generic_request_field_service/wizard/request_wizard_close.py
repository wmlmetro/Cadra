import logging

from odoo import models, api

_logger = logging.getLogger(__name__)


class RequestWizardClose(models.TransientModel):
    _inherit = 'request.wizard.close'

    @api.onchange(
        'request_id',
        'new_request_type_id',
        'new_request_category_id',
        'new_request_service_id',
        'wizard_fields_json_top', 'wizard_fields_json_bottom')
    def _onchange_wizard_fields(self):
        return super(RequestWizardClose, self)._onchange_wizard_fields()
