from odoo import models, fields


class RequestCreationTemplate(models.Model):
    _name = 'request.creation.template'
    _description = 'Request creation template'
    _inherit = [
        'generic.mixin.track.changes',
    ]
    _order = 'name'

    name = fields.Char(required=True)
    request_classifier_id = fields.Many2one(
        comodel_name='request.classifier', required=True)
    request_service_id = fields.Many2one(
        comodel_name='generic.service',
        related='request_classifier_id.service_id',
        readonly=True)
    request_category_id = fields.Many2one(
        comodel_name='request.category',
        related='request_classifier_id.category_id',
        readonly=True)
    request_type_id = fields.Many2one(
        comodel_name='request.type',
        related='request_classifier_id.type_id',
        readonly=True, required=False)
    request_text = fields.Html()
    active = fields.Boolean(default=True, index=True)

    request_tag_ids = fields.Many2many(
        'generic.tag', string='Request Tags',
        domain=[('model_id.model', '=', 'request.request')],
        help="Assign tags to requests created from this mail source")

    def _prepare_request_data(self):
        """
        :return: dictionary with default request values
        from creation template
        """
        return {
            'service_id': self.request_service_id.id,
            'category_id': self.request_category_id.id,
            'type_id': self.request_type_id.id,
            'request_text': self.request_text,
            'tag_ids': [(4, t.id) for t in self.request_tag_ids],
        }

    def prepare_request_data(self, values=None):
        """ :param dict values: request values
            :return dict: dictionary with data for request creation with
                default values from creation template
        """
        data = self._prepare_request_data()
        if values:
            data.update(values)
        return data

    def do_create_request(self, values):
        """
        Do actual creation of request based on this template.

        :param dict values: request values used to create request.
                            these value could overwrite template's defaults.
        :return: request.request recordset with created request.
        """
        data = self.prepare_request_data(values)
        request = self.env['request.request'].create(data)
        return request
