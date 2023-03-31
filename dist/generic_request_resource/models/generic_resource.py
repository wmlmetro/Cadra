from odoo import models, fields, api, exceptions, _

from odoo.addons.generic_resource.tools.utils import resource_proxy


class GenericResource(models.Model):
    _inherit = "generic.resource"

    resource_request_ids = fields.One2many(
        'request.request', 'resource_id', 'Requests')
    resource_request_count = fields.Integer(
        'All Requests', compute='_compute_resource_requests',
        compute_sudo=True)
    resource_request_open_count = fields.Integer(
        'Open requests', compute='_compute_resource_requests',
        compute_sudo=True)

    @api.depends('resource_request_ids')
    def _compute_resource_requests(self):
        for rec in self.sudo():
            rec.resource_request_count = len(rec.resource_request_ids)
            rec.resource_request_open_count = len(
                rec.resource_request_ids.filtered(lambda r: not r.closed))

    def unlink(self):
        for rec in self:
            if rec.resource_request_ids:
                raise exceptions.UserError(_(
                    'Unable to unlink! '
                    'There is a reference to this resource from requests'))
        return super(GenericResource, self).unlink()

    @resource_proxy
    def action_view_resource_requests(self):
        self.ensure_one()
        ctx = dict(self.env.context)
        ctx.update({
            'default_resource_res_id': self.res_id,
            'default_resource_type_id': self.res_type_id.id,
            'default_resource_res_model': self.res_type_id.model,
        })
        return {
            'name': _('Requests'),
            'res_model': 'request.request',
            'type': 'ir.actions.act_window',
            'view_id': False,
            'view_mode': 'kanban,tree,form',
            'limit': 80,
            'domain': [('resource_id', '=', self.id)],
            'context': ctx,
        }
