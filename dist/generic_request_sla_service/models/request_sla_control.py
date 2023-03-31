from odoo import fields, models


class RequestSlaControl(models.Model):
    _inherit = 'request.sla.control'

    request_service_id = fields.Many2one(
        'generic.service', readonly=True,
        related='request_id.service_id', store=True)
    request_service_level_id = fields.Many2one(
        'generic.service.level', readonly=True,
        related='request_id.service_level_id', store=True)
