from odoo import models, fields


class RequestClassifier(models.Model):
    _inherit = 'request.classifier'

    website_published = fields.Boolean(
        'Visible in Website', copy=False, index=True)
    website_ids = fields.Many2many(
        comodel_name='website',
        relation='request_classifier_website_rel',
        column1='request_classifier_id',
        column2='website_id')

    def website_publish_button(self):
        for rec in self:
            rec.website_published = not rec.website_published
        return True
