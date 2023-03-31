from odoo import models, fields, api

from odoo.addons.generic_resource.tools.utils import resource_proxy


class GenericResource(models.Model):
    _inherit = 'generic.resource'

    service_ids = fields.Many2many(
        'generic.service', 'generic_service_resource_rel', 'resource_id',
        'service_id', string="Services")
    service_count = fields.Integer(
        compute='_compute_service_count', string="Count of services",
        readonly=True)

    @api.depends('service_ids')
    def _compute_service_count(self):
        for resource in self:
            resource.service_count = len(resource.service_ids)

    @resource_proxy
    def action_show_resource_services(self):
        self.ensure_one()
        return self.get_action_by_xmlid(
            'generic_service.generic_service_action',
            context=dict(
                self.env.context,
                default_resource_ids=[(4, self.id)]),
            domain=[('resource_ids.id', '=', self.id)],
        )
