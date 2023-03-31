from odoo import models, fields, http


class RequestType(models.Model):
    _inherit = 'request.type'

    # TODO: may be it have sense to move these fields to
    # generic_request_resource module
    resource_label = fields.Char(
        help='Label to be used for Resource field on website')
    resource_help = fields.Text(
        help='Short help message for Resource field on website')
    resource_placeholder = fields.Char(
        default='Start typing name of resource...',
        help='Placeholder for Resource field on website')

    def get_wsd_resource_field_attrs(self):
        self.ensure_one()
        res = {
            'placeholder': self.resource_placeholder,
        }
        if self.resource_required:
            res['required'] = 'required'
        if http.request.website.is_request_restricted_ui():
            res['disabled'] = 'disabled'
        return res
