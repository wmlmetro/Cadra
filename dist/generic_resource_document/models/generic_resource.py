from odoo import models, fields, api

from odoo.addons.generic_resource.tools.utils import resource_proxy
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class GenericResource(models.Model):
    _inherit = 'generic.resource'

    resource_attachment_ids = fields.One2many(
        'ir.attachment', 'res_id', string='Attachments',
        domain=lambda self: [('res_model', '=', self._name)],
        auto_join=True)
    resource_attachment_count = fields.Integer(
        'Attachments Count', compute='_compute_attachment_count')

    @api.depends('resource_attachment_ids')
    def _compute_attachment_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='resource_attachment_ids')
        for record in self:
            record.resource_attachment_count = mapped_data.get(record.id, 0)

    @resource_proxy
    def action_show_resource_attachments(self):
        self.ensure_one()
        return self.get_action_by_xmlid(
            "base.action_attachment",
            domain=[
                ('res_model', '=', self._name),
                ('res_id', 'in', self.ids),
            ],
            context={
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
        )
