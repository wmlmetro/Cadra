from odoo import models, fields, api, http


class RequestField(models.Model):
    _inherit = "request.field"

    website_name = fields.Char(
        compute='_compute_website_name', readonly=True,
        help='Name of field in website form. Based on field code. '
             'This is helper field to simplify code that will process '
             'request fields on website.')

    @api.depends('code')
    def _compute_website_name(self):
        for record in self:
            record.website_name = "request_field_%s_%d" % (
                record.code.lower(), record.id)

    def get_website_field_attrs(self):
        """ Return dictionary with attributes for request field (input)
            on website

            :return dict: dictionary with attributes for input element of field
        """
        self.ensure_one()
        res = {
            'id': self.website_name,
            'name': self.website_name,
            'placeholder': (
                self.field_placeholder if self.field_placeholder else ''),
        }
        if self.mandatory:
            res['required'] = 'required'

        website = http.request.website
        if website and website.is_request_restricted_ui():
            res['disabled'] = 'disabled'
        return res
