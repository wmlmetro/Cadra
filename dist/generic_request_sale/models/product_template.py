from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_create_request = fields.Boolean(
        help="Do we need to create requests when sale order is confirmed?")
    request_creation_template_id = fields.Many2one(
        'request.creation.template',
        help="Use this request creation template to create requests "
             "from sale order when it will be confirmed.")
    request_delivered_stage_type_ids = fields.Many2many(
        'request.stage.type',
        help="When request reaches stage with one of selected stage types, "
             "then this request is considered as delivered.")
    request_text_template = fields.Html(
        help="Use this template to fill request text for requests "
             "created from sale orders.")

    @api.onchange('is_create_request')
    def _onchange_is_create_request(self):
        for rec in self:
            if not rec.is_create_request:
                rec.request_creation_template_id = False
