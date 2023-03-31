import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ContractRecourceWizardAddLines(models.TransientModel):
    _name = 'contract.resource.lines.wizard'
    _inherit = [
        'generic.resource.related.mixin',
    ]
    _description = 'Contract Wizard: Add Resource Lines'

    contract_id = fields.Many2one(
        'generic.contract', required=True, readonly=True)

    # TODO: Need add compability for datetime in resource lines
    # and contract resource lines.
    datetime_added = fields.Datetime(
        default=fields.Datetime.now, required=True)
    datetime_end = fields.Datetime()

    resource_service_line_ids = fields.One2many(
        'contract.resource.service.line.wizard',
        'contract_resource_wizard_add_lines_id',
        string='Resource Service Lines')
    resource_id = fields.Many2one(ondelete='cascade')

    @api.onchange('resource_type_id', 'resource_res_id')
    def _onchange_resource(self):
        # for clear resource_service_line_ids
        for rec in self:
            rec.resource_service_line_ids = False

    def do_add_line(self):
        self.ensure_one()
        line = self.contract_id.add_resource_line(
            resource=self.resource_id, date=self.datetime_added)

        if not self.resource_service_line_ids:
            return line

        services = []
        for wizard_line in self.resource_service_line_ids:
            services.append(
                (0, 0, {
                    'contract_id': self.contract_id.id,
                    'service_id': wizard_line.service_id.id,
                    'service_level_id': wizard_line.service_level_id.id,
                })
            )

        line.write({
            'resource_service_line_ids': services
        })

        return line


class ContractResourceServiceLineWizard(models.TransientModel):
    _name = 'contract.resource.service.line.wizard'
    _description = "Generic Contract Resource Service Line Wizard"

    contract_resource_wizard_add_lines_id = fields.Many2one(
        'contract.resource.lines.wizard', required=True, index=True,
        ondelete='cascade')

    service_id = fields.Many2one(
        'generic.service', index=True, ondelete='cascade')
    service_level_id = fields.Many2one(
        'generic.service.level', index=True, ondelete='cascade')
