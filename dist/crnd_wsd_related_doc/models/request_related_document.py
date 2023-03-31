from odoo import models


class RequestRelatedDocument(models.Model):
    _inherit = 'request.related.document'

    def get_website_url(self):
        self.ensure_one()
        doc = self.sudo().env[self.doc_model].browse(self.doc_id)
        if hasattr(doc, 'website_url'):
            return doc.website_url
        if hasattr(doc, 'portal_url'):
            return doc.portal_url
        if hasattr(doc, 'access_url'):
            return doc.access_url
        return False
