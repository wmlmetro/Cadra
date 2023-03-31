import logging
from odoo import fields, models, _

_logger = logging.getLogger(__name__)


class RequestFieldValue(models.Model):
    _name = "request.field.value"
    _order = "sequence ASC, id ASC"
    _description = "Request Field Value"

    request_id = fields.Many2one(
        'request.request', 'Request', ondelete='cascade',
        required=True, index=True)
    field_id = fields.Many2one(
        'request.field', 'Field', ondelete='restrict',
        required=True, index=True)
    sequence = fields.Integer(
        related='field_id.sequence',
        readonly=True, store=True, index=True)
    field_name = fields.Char(
        related='field_id.name', readonly=True)
    field_mandatory = fields.Boolean(
        'Mandatory', related='field_id.mandatory', readonly=True)
    value = fields.Char()

    def _validate_single_value(self):
        """ Validate field, and return error message or False
        """
        self.ensure_one()
        if self.field_id.mandatory and not self.value:
            return _(
                "Field %(field)s is required!") % {'field': self.field_id.name}
        return False

    def validate_values(self):
        """ Validate seected values and return dictionary with
            validation errors:

            {
                field_id: "Error",
            }
        """
        result = {}
        for record in self:
            err = record._validate_single_value()
            if err:
                result[record.field_id] = err
        return result

    def _get_request_field_info(self):
        """ Field infor to be provided for JS widget
        """
        self.ensure_one()
        return self.field_id._get_request_field_info(value=self.value)

    def convert_to_fields_info(self):
        # We have to use string keys here,
        # because json supports only string dict keys
        fields_info = {
            str(v.field_id.id): v._get_request_field_info() for v in self}
        fields_order = [
            str(v.field_id.id)
            for v in sorted(self, key=lambda x: x.sequence)
        ]
        res = {
            'fields_info': fields_info,
            'fields_order': fields_order,
        }
        return res
