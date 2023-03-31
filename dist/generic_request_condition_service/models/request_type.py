from odoo import models, fields


class RequestType(models.Model):
    _inherit = 'request.type'

    change_service_condition_ids = fields.Many2many(
        'generic.condition', 'request_type_change_service_cond_rel',
        'type_id', 'condition_id', string='Can change service')
