from odoo import models, fields, api


class RequestApiEnpointFieldMap(models.Model):
    _name = 'request.api.endpoint.field.map'
    _description = "API Endpoint Field Map"

    endpoint_id = fields.Many2one(
        'request.api.endpoint', string="Endpoint",
        required=True, index=True, ondelete='cascade')
    field_id = fields.Many2one(
        'request.field', string="Field", required=True, ondelete='restrict')
    data_field = fields.Char(required=True)
    default_value = fields.Char()

    _sql_constraints = [
        ('data_field_ascii_only',
         r"CHECK (data_field ~ '^[a-z0-9\-_]+$')",
         'Data field must be lowercase ascii only'),
    ]

    @api.onchange('field_id')
    def _onchange_field_id(self):
        for record in self:
            if record.field_id:
                record.data_field = record.field_id.code.lower()
            else:
                record.data_field = False
