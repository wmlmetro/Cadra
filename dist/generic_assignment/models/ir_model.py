from odoo import models, fields


class IrModel(models.Model):
    _inherit = 'ir.model'

    assignment_model_ids = fields.One2many(
        'generic.assign.policy.model', 'model_id')
