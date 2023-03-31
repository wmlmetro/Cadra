import logging

from odoo import fields, models, api, exceptions, _

_logger = logging.getLogger(__name__)


class RequestField(models.Model):
    _inherit = "request.field"

    service_ids = fields.Many2many(
        'generic.service', 'request_field_generic_service_rel',
        string='Request Services', index=True)

    @api.constrains('service_ids')
    def _check_service_in_request_type_service(self):
        for rec in self:
            fields_service = rec.service_ids
            type_request_service = rec.request_type_id.service_ids
            if not fields_service <= type_request_service:
                excepted_service = (
                    fields_service - type_request_service
                ).mapped('display_name')
                raise exceptions.ValidationError(_(
                    "The request services %(services)s used in the "
                    "'%(field)s' field do not belong to the services "
                    "allowed for the request type '%(request_type)s'."
                ) % {
                    'services': excepted_service,
                    'field': rec.name,
                    'request_type': rec.request_type_id.name,
                })
