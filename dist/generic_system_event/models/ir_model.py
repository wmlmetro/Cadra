from odoo import models, fields, api


class IrModel(models.Model):
    _inherit = 'ir.model'

    system_event_source_ids = fields.One2many(
        'generic.system.event.source', 'model_id', readonly=True,
        string="Generic System Event Sources")
    system_event_source_id = fields.Many2one(
        'generic.system.event.source', readonly=True, store=False,
        compute='_compute_system_event_source_id',
        string="Generic System Event Source")

    @api.depends('system_event_source_ids')
    def _compute_system_event_source_id(self):
        for record in self:
            # We have unique constraint on event sources,
            # thus we always have zero or one
            # event source per model
            record.system_event_source_id = record.system_event_source_ids
