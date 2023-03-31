import logging

from odoo import models, fields, api, _, exceptions
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

_logger = logging.getLogger(__name__)


class RequestType(models.Model):
    _inherit = 'request.type'

    field_ids = fields.One2many(
        'request.field', 'request_type_id', string='Fields', copy=True)
    field_count = fields.Integer(compute='_compute_field_count')

    @api.depends('field_ids')
    def _compute_field_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='field_ids')
        for record in self:
            record.field_count = mapped_data.get(record.id, 0)

    @api.constrains('category_ids')
    def _check_category_in_field_category(self):
        for rec in self:
            type_request_categ = rec.category_ids
            fields_categ = rec.mapped('field_ids.category_ids')
            if not fields_categ <= type_request_categ:
                excepted_category = (
                    fields_categ - type_request_categ
                ).mapped('display_name')
                raise exceptions.ValidationError(_(
                    "The request categories %(categories)s used in the "
                    "request fields do not belong to the categories allowed"
                    " for the request type '%(request_type)s'."
                ) % {
                    'categories': excepted_category,
                    'request_type': rec.name,
                })
