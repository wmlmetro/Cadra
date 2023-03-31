from odoo import models, fields, api
from odoo.addons.generic_request.models.request_request import (
    TRACK_FIELD_CHANGES
)
from odoo.addons.generic_mixin import post_write


TRACK_FIELD_CHANGES.update(
    ['resource_id', 'resource_type_id', 'resource_res_id'])


class RequestRequest(models.Model):
    _name = "request.request"
    _inherit = [
        "request.request",
        "generic.resource.related.mixin",
    ]

    resource_required = fields.Boolean(
        related='type_id.resource_required', readonly=True)
    resource_invisible = fields.Boolean(
        related='type_id.resource_invisible', readonly=True)

    @api.onchange('type_id')
    def _onchange_type_id_restrict_resource_types(self):
        if self.type_id.resource_type_ids:
            return {
                'domain': {
                    'resource_type_id': [
                        ('id', 'in', self.type_id.resource_type_ids.ids),
                    ],
                },
            }
        return {
            'domain': {
                'resource_type_id': [],
            }
        }

    @post_write('resource_id')
    def _after_resource_id_changed(self, changes):
        self.trigger_event('resource-changed', {
            'old_resource_id': changes['resource_id'][0].id,
            'new_resource_id': changes['resource_id'][1].id,
        })
