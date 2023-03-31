import logging

from odoo import models, api, _, exceptions

_logger = logging.getLogger(__name__)


class RequestType(models.Model):
    _inherit = 'request.type'

    @api.constrains('service_ids')
    def _check_service_in_field_service(self):
        for rec in self:
            type_request_service = rec.service_ids
            fields_service = rec.mapped('field_ids.service_ids')
            if not fields_service <= type_request_service:
                excepted_services = (
                    fields_service - type_request_service
                ).mapped('display_name')
                raise exceptions.ValidationError(_(
                    "The request services %(services)s used in the "
                    "request fields do not belong to the services allowed"
                    " for the request type '%(request_type)s'."
                ) % {
                    'services': excepted_services,
                    'request_type': rec.name,
                })
