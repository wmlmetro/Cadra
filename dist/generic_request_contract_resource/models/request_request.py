import logging
from odoo import models
from odoo.osv import expression

from odoo.addons.generic_mixin import post_write

from odoo.addons.generic_request import service_level_guesser

_logger = logging.getLogger(__name__)


class RequestRequest(models.Model):
    _inherit = 'request.request'

    @classmethod
    def _get_contract_id_dependency_fields(cls):
        """ Return list of fields that have to trigger contract recomputation.
            Could be extended by other addons
        """
        return super(
            RequestRequest, cls
        )._get_contract_id_dependency_fields() + [
            'resource_type_id', 'resource_res_id', 'resource_id']

    def _guess_contract_get_domain_optional(self):
        """ Return list of optional domains.
            This domains will be joined via OR condition
        """
        domains = super(
            RequestRequest, self
        )._guess_contract_get_domain_optional()

        if not self.resource_type_id:
            return domains

        resource = self.resource_type_id.get_resource_by_id(
            self.resource_res_id)

        if resource:
            domains += [
                expression.OR([
                    [('contract_resource_line_ids.resource_id',
                      '=',
                      resource.id)],
                ])
            ]

        return domains

    @classmethod
    def _get_service_level_dependency_fields(cls):
        return super(
            RequestRequest, cls
        )._get_service_level_dependency_fields() + [
            'resource_type_id', 'resource_res_id', 'resource_id']

    @service_level_guesser(priority=300)
    def _get_service_level__from_resource(self):
        if self.resource_type_id:
            # Here we get resource implementation
            resource = self.resource_type_id.get_resource_by_id(
                self.resource_res_id)
            if resource and self.contract_id and self.service_id:
                resource_service_line = (
                    self.contract_id.sudo().get_resource_service_line_for(
                        self.service_id, resource)
                )
                if resource_service_line:
                    return resource_service_line.service_level_id
        return self.env['generic.service.level'].browse()

    @post_write('resource_type_id', 'resource_res_id', 'resource_id')
    def _update_service_level_on_write(self, changes):
        return super(RequestRequest, self)._update_service_level_on_write(
            changes)
