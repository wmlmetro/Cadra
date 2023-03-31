from odoo import models, fields, api, _

from odoo.addons.generic_m2o import generic_m2o_get


class RequestRelatedDocument(models.Model):
    _name = 'request.related.document'
    _description = 'Request Related Document'
    _order = 'request_id'

    request_id = fields.Many2one(
        'request.request', string='Request', readonly=True, required=True,
        index=True, ondelete='cascade')
    request_type_id = fields.Many2one(
        'request.type', string='Request Type', readonly=True,
        related='request_id.type_id', store=False)
    doc_type_id = fields.Many2one(
        'request.related.document.type', string='Document Type',
        required=True, index=True, ondelete='cascade')
    model_id = fields.Many2one(
        'ir.model', string='Model', related='doc_type_id.model_id',
        index=True, required=False, readonly=True,
        store=True, compute_sudo=True, ondelete='cascade')
    doc_model = fields.Char(
        related='doc_type_id.model_id.model', compute_sudo=True,
        string="Model Name", readonly=True)
    doc_id = fields.Many2oneReference(
        string='Document', required=True, model_field='doc_model')
    comment = fields.Text()

    _sql_constraints = [
        ('doc_unique', 'unique(request_id, doc_type_id, doc_id)',
         'Can be one unique document!')]

    @api.onchange('doc_type_id')
    def _onchange_model_id_(self):
        for rec in self:
            rec.doc_id = False

    def get_document(self):
        return generic_m2o_get(
            self, field_res_model='doc_model', field_res_id='doc_id')

    def name_get(self):
        """ name_get() -> [(id, name), ...]

        Returns a textual representation for the records in ``self``.
        By default this is the value of the ``display_name`` field.

        :return: list of pairs ``(id, text_repr)`` for each records
        :rtype: list(tuple)
        """
        result = []
        for rec in self:
            doc = self.get_document()
            if doc:
                result.append((rec.id, doc.display_name))
            else:
                result.append((rec.id, _("Unknown document")))
        return result

    def action_open_document_object(self):
        """ Open related document
        """
        self.ensure_one()
        if self.doc_model and self.doc_id:
            doc = self.sudo().env[self.doc_model].browse(self.doc_id)
            return doc.get_formview_action()
        return None
