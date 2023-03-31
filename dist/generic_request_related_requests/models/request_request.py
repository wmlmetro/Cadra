from odoo import models, fields, api


class RequestRequest(models.Model):
    _inherit = 'request.request'

    related_request_ids = fields.Many2many(
        'request.request',
        'request_request_rel', 'related_id', 'related_to_id',
        string='Related requests',
        help="Other requests referenced from this request")
    related_reverse_request_ids = fields.Many2many(
        'request.request',
        'request_request_rel', 'related_to_id', 'related_id',
        string='Related to requests',
        help="Requests that have references to this request")
    related_request_count = fields.Integer(
        compute="_compute_related_requests")
    related_reverse_request_count = fields.Integer(
        compute="_compute_related_requests")
    related_request_total_count = fields.Integer(
        compute="_compute_related_requests")

    @api.depends('related_request_ids', 'related_reverse_request_ids')
    def _compute_related_requests(self):
        for request in self:
            request.related_request_count = len(request.related_request_ids)
            request.related_reverse_request_count = len(
                request.related_reverse_request_ids)
            request.related_request_total_count = len(set(
                request.related_request_ids +
                request.related_reverse_request_ids))

    def action_view_related_requests(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            domain=[
                '|',
                ('related_request_ids', '=', self.id),
                ('related_reverse_request_ids', '=', self.id),
            ],
        )
