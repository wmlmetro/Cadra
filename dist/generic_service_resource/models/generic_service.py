from odoo import models, fields, api


class GenericService(models.Model):
    _inherit = 'generic.service'

    resource_ids = fields.Many2many(
        'generic.resource', 'generic_service_resource_rel', 'service_id',
        'resource_id', string="Resources")
    resource_count = fields.Integer(
        compute='_compute_resource_count', readonly=True)

    @api.depends('resource_ids')
    def _compute_resource_count(self):
        for service in self:
            service.resource_count = len(service.resource_ids)

    def action_show_service_resources(self):
        self.ensure_one()
        return self.get_action_by_xmlid(
            'generic_resource.generic_resource_action',
            context=dict(
                self.env.context,
                default_service_ids=[(4, self.id)]),
            domain=[('service_ids.id', '=', self.id)],
        )
