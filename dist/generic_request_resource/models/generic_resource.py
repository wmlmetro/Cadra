from odoo import models, fields, api, exceptions, _

from odoo.addons.generic_resource.tools.utils import resource_proxy
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


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
        data = read_counts_for_o2m(
            records=self.sudo(),
            field_name='resource_request_ids')
        open_data = read_counts_for_o2m(
            records=self.sudo(),
            field_name='resource_request_ids',
            domain=[('closed', '=', False)])
        for record in self:
            record.resource_request_count = data.get(record.id, 0)
            record.resource_request_open_count = open_data.get(record.id, 0)

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
        return self.get_action_by_xmlid(
            'generic_request.action_request_window',
            domain=[('resource_id', '=', self.id)],
            context={
                'default_resource_res_id': self.res_id,
                'default_resource_type_id': self.res_type_id.id,
                'default_resource_res_model': self.res_type_id.model,
                'search_default_filter_open': 1,
            })
