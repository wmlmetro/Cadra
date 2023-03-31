import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class GenericContract(models.Model):
    _inherit = 'generic.contract'

    contract_resource_line_ids = fields.One2many(
        'generic.contract.resource.line', 'contract_id', readonly=True,
        string='Resource Lines')

    def get_resources(self, model_name):
        """ Return RecordSet with resources of specified type related to
            this contract.

            Note, that this method will return instances of
            resource implementation model, not generic.resource.

            :param str model_name: Name of model if resource type
            :return RecordSet(model_name): resources of specified type
        """
        self.ensure_one()
        resource_type = self.env['generic.resource.type'].get_resource_type(
            model_name)
        if not resource_type:
            raise ValueError("Specified model is not resource")

        result = self.env[model_name].browse()
        rlines = self.contract_resource_line_ids
        for rline in rlines:
            if rline.resource_type_id == resource_type:
                result += rline.resource
        return result

    def get_resource_line_for(self, resource):
        """ Get resource line for resource. Assumed to be used outside.

            Always returns single record or empty recordset

            :param resource: Single record of 'generic.resource' to return
                             resource line for. Possibly could be record of
                             resource implementation model
            :return: Recordset of 'generic.contract.resource.line'.
        """
        self.ensure_one()

        if resource._name != 'generic.resource':
            if not self.env['generic.resource.type'].get_resource_type(
                    resource._name):
                raise ValueError(
                    "Param 'resource' must be recordset of 'generic.resource' "
                    "model, or implementation model of resource.")
            resource = resource.resource_id

        # computed only in active or pending
        # contract states and priority has active state
        return self.env['generic.contract.resource.line'].search(
            [('resource_id', '=', resource.id),
             ('contract_state', 'in', ('pending', 'active')),
             ('contract_id', '=', self.id)],
            order='contract_state',
            limit=1)

    def add_resource_line(self, resource, date=None):
        """ Add resource line for resource. Assumed to be used outside.

            :param resource: Single record of 'generic.resource' to add
                             resource line for. Possibly could be record of
                             resource implementation model
            :return: Recordset of 'generic.contract.resource.line' created.
        """
        self.ensure_one()

        if resource._name != 'generic.resource':
            if not self.env['generic.resource.type'].get_resource_type(
                    resource._name):
                raise ValueError(
                    "Param 'resource' must be recordset of 'generic.resource' "
                    "model, or implementation model of resource.")
            resource = resource.resource_id

        resource_line = self.get_resource_line_for(resource)
        if not resource_line:
            resource_line = self.env['generic.contract.resource.line'].create({
                'contract_id': self.id,
                'resource_id': resource.id,
                'datetime_added': (
                    date if date is not None else fields.Datetime.now()),
            })
            self.trigger_event('contract-resource-added', {
                'resource_id': resource.id,
                'contract_resource_line_id': resource_line.id,
            })

        return resource_line

    def get_resource_service_line_for(self, service, resource):
        """ Get resource service line for service. Assumed to be used outside.

            Always returns single record or empty recordset

            :param service: Single record of 'generic.service' to return
                            resource service line for.
            :param resource: Single record of 'generic.resource' to return
                            resource service line for.
            :return: Recordset of 'generic.contract.resource.service.line'.
        """

        self.ensure_one()
        lines = self.contract_resource_line_ids.mapped(
            'resource_service_line_ids')
        for rsl in lines:
            if rsl.service_id == service and rsl.resource_id.id == resource.id:
                return rsl
        return self.env['generic.contract.resource.service.line'].browse()

    def _get_default_datetime_start_for_resource_lines(self):
        self.ensure_one()
        default_date_start = fields.Date.today()
        if default_date_start < self.date_start:
            default_date_start = self.date_start
        return default_date_start

    def action_add_resource_line(self):
        self.ensure_one()
        if self.state == 'closed':
            # Avoid to create any action if contract is 'Closed'
            return False

        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_contract_resource'
            '.action_contract_resource_lines_wizard',
            context={
                'default_contract_id': self.id,
                'default_date_added': (
                    self._get_default_datetime_start_for_resource_lines()),
                'default_datetime_end': (
                    fields.Datetime.to_datetime(self.date_end)),
            })
