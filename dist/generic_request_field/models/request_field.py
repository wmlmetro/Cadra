import logging

from odoo import api, fields, models, _, exceptions
from odoo.addons.generic_mixin.tools.jinja import render_jinja_string

_logger = logging.getLogger(__name__)


class RequestField(models.Model):
    _name = "request.field"
    _inherit = [
        'generic.mixin.name_with_code',
    ]
    _order = "sequence ASC, code ASC, id ASC"
    _description = "Request Field"

    # Defined in generic.mixin.name_with_code
    name = fields.Char()
    code = fields.Char(help="System field name, not translatable, ASCII-only")

    sequence = fields.Integer(default=5, index=True)
    mandatory = fields.Boolean(index=True)
    default = fields.Char(
        help="Default value for field. "
             "It is possible to use here Jinja2 template placeholders. "
             "Currently, it is possible to compute default value for the field"
             " based on current user. For example, you can use following "
             "example of default value: {{ current_user.name }}")
    request_type_id = fields.Many2one(
        'request.type', 'Request Type', ondelete='cascade',
        required=True, index=True)
    category_ids = fields.Many2many(
        'request.category', 'request_field_request_category_rel',
        string='Request Categories', index=True)
    position = fields.Selection(selection=[
        ('before', 'Before request text'),
        ('after', 'After request text')], default='before', required=True)

    field_help = fields.Char(
        help="Help message for the field")
    field_placeholder = fields.Char(
        help="Placeholder for the field")
    grid_classes = fields.Char(
        default='col-md-4',
        help="You can use bootstrap grid classes, "
             "that could be applied to this field")
    active = fields.Boolean(default=True, index=True)

    _sql_constraints = [
        ('name_uniq',
         'UNIQUE (request_type_id, name)',
         'Field name must be unique.'),
        ('code_uniq',
         'UNIQUE (request_type_id, code)',
         'Field code must be unique.'),
    ]

    @api.constrains('category_ids')
    def _check_category_in_request_type_category(self):
        for rec in self:
            fields_categ = rec.category_ids
            type_request_categ = rec.request_type_id.category_ids
            if not fields_categ <= type_request_categ:
                excepted_category = (
                    fields_categ - type_request_categ
                ).mapped('display_name')
                raise exceptions.ValidationError(_(
                    "The request categories %(categories)s used in the "
                    "'%(field)s' field do not belong to the categories "
                    "allowed for the request type '%(request_type)s'."
                ) % {
                    'categories': excepted_category,
                    'field': rec.name,
                    'request_type': rec.request_type_id.name,
                })

    def name_get(self):
        res = []
        for rec in self:
            res += [(
                rec.id,
                "%s (%s)" % (rec.sudo().request_type_id.name, rec.name)
            )]
        return res

    def _get_default_value(self):
        """ Compute default value for this field
        """
        self.ensure_one()
        # If default is not set, then we have to use empty string,
        # to avoid implicit conversion of false -> string in field's
        # xml template
        if self.default:
            return render_jinja_string(self.default, {
                'current_user': self.env.user,
            })
        return ''

    def _get_value_or_default(self, value=None):
        """ Return provided value if it is specified,
            otherwise return default value.

            :param str value: value to be checked
        """
        self.ensure_one()
        if value in (None, False):
            return self._get_default_value()

        return value

    def _get_request_field_info(self, value=None):
        """ Field info to be provided for JS widget
        """
        self.ensure_one()

        return {
            'name': self.name,
            'code': self.code,
            'mandatory': self.mandatory,
            'default': self._get_default_value(),
            'sequence': self.sequence,
            'position': self.position,
            'value': self._get_value_or_default(value),
            'field_id': self.id,
            'grid_classes': (
                self.grid_classes
                if self.grid_classes
                else 'col-md-4'),
            'help': self.field_help,
            'placeholder': self.field_placeholder,
        }
