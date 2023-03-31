import collections
from odoo import models, fields


class ResourceWizardManageRoles(models.TransientModel):
    _name = 'generic.resource.wizard.manage.roles'
    _inherit = [
        'generic.resource.wizard.mixin',
    ]
    _description = 'Resource Wizard: Manage Roles'

    resource_ids = fields.Many2many(
        'generic.resource', required=True)
    partner_ids = fields.Many2many(
        'res.partner', required=False)
    role_ids = fields.Many2many(
        'generic.resource.role', required=False)
    action = fields.Selection(
        [('grant', 'Grant'),
         ('revoke', 'Revoke'),
         ('set_visibility', 'Set Visibility')],
        required=True, default='grant')
    date_expire = fields.Date()

    resource_visibility = fields.Selection(
        selection="_get_selection_resource_visibility",
    )

    def _get_selection_resource_visibility(self):
        return self.env[
            'generic.resource']._fields['resource_visibility'].selection

    def _do_iter_actions(self):
        for resource in self.resource_ids:
            for partner in self.partner_ids:
                for role in self.role_ids:
                    yield resource, partner, role

    def _do_grant_revoke_roles(self):
        RLink = self.env['generic.resource.role.link']

        rlinks = self.env['generic.resource.role.link.sec.view'].search([
            ('resource_id', 'in', self.resource_ids.ids),
            ('partner_id', 'in', self.partner_ids.ids),
            ('role_id', 'in', self.role_ids.ids),
        ]).mapped('role_link_id')

        rlinks_map = collections.defaultdict(RLink.browse)
        for rlink in rlinks:
            if not rlink.parent_id:
                rlinks_map[(
                    rlink.resource_id.id,
                    rlink.partner_id.id,
                    rlink.role_id.id)] += rlink

        for resource, partner, role in self._do_iter_actions():
            rl = rlinks_map[(resource.id, partner.id, role.id)]
            if rl and self.action == 'revoke':
                rl.write({
                    'date_end': fields.Date.today(),
                })
            elif self.action == 'grant' and not rl:
                rl_data = {
                    'resource_id': resource.id,
                    'partner_id': partner.id,
                    'role_id': role.id,
                    'date_start': fields.Date.today(),
                }
                if self.date_expire:
                    rl_data['date_end'] = self.date_expire
                rl = RLink.create(
                    rl_data)
                rlinks_map[(resource.id, partner.id, role.id)] = rl
                rlinks += rl

        RLink.flush(records=rlinks)

    def _do_set_resource_visibility(self):
        self.resource_ids.write({
            'resource_visibility': self.resource_visibility
        })

    def do_apply(self):
        self.ensure_one()

        if self.action in ('grant', 'revoke'):
            self._do_grant_revoke_roles()
        elif self.action == 'set_visibility':
            self._do_set_resource_visibility()
