import logging

from odoo import models, api

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = "request.request"

    @api.onchange('type_id', 'category_id', 'service_id',
                  'request_fields_json_top', 'request_fields_json_bottom')
    def onchange_type_id_fields(self):
        return super(
            RequestRequest, self
        ).onchange_type_id_fields()

    def _request_fields__get_fields(self, position=None):
        """ Return request fields for request
        """
        return super()._request_fields__get_fields(position=position).filtered(
            lambda f: (
                not f.sudo().service_ids or self.service_id in f.service_ids))
