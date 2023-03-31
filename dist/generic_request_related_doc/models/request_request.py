from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m
from odoo.addons.generic_mixin import pre_create


class RequestRequest(models.Model):
    _inherit = "request.request"

    related_doc_ids = fields.One2many(
        'request.related.document', 'request_id', string='Documents')
    related_docs_count = fields.Integer(
        compute='_compute_related_docs', string='Documents Count')
    related_doc_search = fields.Char(
        store=False, search='_search_related_doc')

    @api.depends('related_doc_ids')
    def _compute_related_docs(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='related_doc_ids')
        for record in self:
            record.related_docs_count = mapped_data.get(record.id, 0)

    def _search_related_doc(self, operator, value):
        try:
            doc_type_id, doc_id = value.split(',')
            doc_type_id, doc_id = int(doc_type_id), int(doc_id)
        except (TypeError, ValueError, AttributeError):
            return []
        related_docs = self.env['request.related.document'].search([
            ('doc_type_id', '=', doc_type_id),
            ('doc_id', '=', doc_id),
        ])
        return [('id', 'in', related_docs.mapped('request_id').ids)]

    @pre_create()
    def _before_create__handle_related_docs_from_context(self, changes):
        if self.env.context.get('default_related_doc_ids'):
            return {
                'related_doc_ids': self.env.context['default_related_doc_ids'],
            }
        return {}
