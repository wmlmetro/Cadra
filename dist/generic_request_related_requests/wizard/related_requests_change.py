from odoo import models, fields


class RequestsWizardManageRelatedRequests(models.TransientModel):
    _name = "request.wizard.manage.related.requests"
    _description = 'Request Wizard: Manage related requests'

    def _get_related_request_ids_domain(self):
        return [('id', '!=', self.env.context.get('default_request_id'))]

    def _get_default_related_request_ids(self):
        Request = self.env['request.request']
        default_request_id = self.env.context.get('default_request_id')
        return Request.browse(default_request_id).related_request_ids

    request_id = fields.Many2one('request.request', 'Request')
    related_request_ids = fields.Many2many(
        'request.request', domain=_get_related_request_ids_domain,
        default=_get_default_related_request_ids,
        string='Related requests')

    def action_change_related_requests(self):
        for rec in self:
            rec.request_id.related_request_ids = rec.related_request_ids
