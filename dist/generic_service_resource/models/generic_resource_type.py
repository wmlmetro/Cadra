from odoo import models, fields


class GenericResourceType(models.Model):
    _inherit = 'generic.resource.type'

    default_service_ids = fields.Many2many(
        'generic.service', string="Default services")
    resource_act_link_services_id = fields.Many2one(
        'ir.actions.act_window', readonly=True)

    def _create_context_action_for_target_model_single(self):
        if not self.resource_act_link_services_id:
            self.resource_act_link_services_id = self.env.ref(
                'generic_service_resource.'
                'action_resource_open_wizard_link_service'
            ).copy({
                'binding_model_id': self.model_id.id,
            })
        return super(
            GenericResourceType, self
        )._create_context_action_for_target_model_single()

    def _get_resource_defaults(self):
        defaults = super(GenericResourceType, self)._get_resource_defaults()
        defaults.update({
            'service_ids': [
                (4, srv.id) for srv in self.default_service_ids
            ],
        })
        return defaults

    def unlink(self):
        self.mapped('resource_act_link_services_id').unlink()
        return super(GenericResourceType, self).unlink()
