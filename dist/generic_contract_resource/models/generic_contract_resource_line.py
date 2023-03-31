import logging

from odoo import models, fields, api

from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

_logger = logging.getLogger(__name__)


class GenericContractResourceLine(models.Model):
    _name = 'generic.contract.resource.line'
    _inherit = [
        'generic.resource.related.mixin',
    ]
    _description = 'Generic Contract Resource Line'

    contract_id = fields.Many2one(
        'generic.contract', required=True, index=True, readonly=True,
        ondelete='cascade')
    contract_partner_id = fields.Many2one(
        'res.partner', readonly=True, store=True,
        related='contract_id.partner_id')
    contract_state = fields.Selection(
        related='contract_id.state',
        readonly=True, store=True, index=True)
    contract_date_start = fields.Date(
        related='contract_id.date_start',
        store=True, index=True, readonly=True)
    contract_date_end = fields.Date(
        related='contract_id.date_end',
        store=True, index=True, readonly=True)

    datetime_added = fields.Datetime()

    resource_service_line_ids = fields.One2many(
        'generic.contract.resource.service.line', 'contract_resource_line_id',
        string='Resource Service Lines')
    resource_service_line_count = fields.Integer(
        'Services', compute='_compute_resource_service_line_count',
        readonly=True)

    @api.depends('resource_service_line_ids')
    def _compute_resource_service_line_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='resource_service_line_ids')
        for record in self:
            record.resource_service_line_count = mapped_data.get(record.id, 0)

    @api.model
    def default_get(self, fields_list):
        # Fix bug, where no added default contract to resource line
        # TODO: We need to find the reason for this behavior.
        default_contract_id = (
            self.env.context.get('default_contract_id', False))
        if default_contract_id and 'contract_id' not in fields_list:
            fields_list.append('contract_id')
        return super(
            GenericContractResourceLine, self).default_get(fields_list)

    @api.onchange('resource_type_id', 'resource_res_id')
    def _onchange_resource(self):
        # TODO: rewrite without returning dict
        # several modules can be inherited from this
        resource_service_lines = [
            (2, service_line_id) for
            service_line_id in
            self.resource_service_line_ids.ids
        ]
        return {
            'value': {
                'resource_service_line_ids': resource_service_lines
            },
        }

    def name_get(self):
        names_data = []
        for rec in self:
            name = '%s-[%s]' % (rec.contract_id.display_name,
                                rec.resource_id.display_name)
            names_data.append((rec.id, name))
        return names_data

    @property
    def resource(self):
        """ Return instance of resource
        """
        self.ensure_one()
        return self.resource_id.resource

    def action_remove_resource_line(self):
        self.ensure_one()
        if self.contract_id.state == 'draft':
            self.unlink()
