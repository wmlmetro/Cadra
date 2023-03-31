from odoo import models, fields


class ResourceWizardLinkService(models.TransientModel):
    _name = 'generic.resource.wizard.link.service'
    _inherit = [
        'generic.resource.wizard.mixin',
    ]
    _description = 'Resource Wizard: Link Services'

    resource_ids = fields.Many2many(
        'generic.resource', required=True)
    service_ids = fields.Many2many(
        'generic.service', required=True)
    action = fields.Selection(
        [('link', 'Link'),
         ('set', 'Set'),
         ('remove', 'Remove')],
        required=True, default='link')

    def do_link(self):
        self.ensure_one()
        for resource in self.resource_ids:
            if self.action == 'link':
                resource.service_ids += self.service_ids
            elif self.action == 'set':
                resource.service_ids = self.service_ids
            elif self.action == 'remove':
                resource.service_ids -= self.service_ids
