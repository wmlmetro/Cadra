import json
import logging

from odoo import models, fields, api
from odoo.osv import expression
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

_logger = logging.getLogger(__name__)


class GenericService(models.Model):
    _inherit = 'generic.service'

    request_type_ids = fields.Many2many(
        'request.type', 'generic_service_request_type_rel',
        'service_id', 'type_id', string='Request types')
    request_type_count = fields.Integer(
        compute="_compute_request_type_count")
    request_ids = fields.One2many(
        'request.request', 'service_id', string='Requests')
    request_count = fields.Integer(
        compute='_compute_request_count')

    # TODO: rename to `request_category_ids`
    category_ids = fields.Many2many(
        'request.category',
        'service_category_rel', 'service_id', 'category_id',
        'Request Categories', required=False, index=True)
    category_count = fields.Integer(
        'Request Categories (Count)', compute="_compute_category_count")

    @api.depends('request_ids')
    def _compute_request_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='request_ids')
        for record in self:
            record.request_count = mapped_data.get(record.id, 0)

    @api.depends('category_ids')
    def _compute_category_count(self):
        for rec in self:
            rec.category_count = len(rec.category_ids)

    @api.depends('request_type_ids')
    def _compute_request_type_count(self):
        for rec in self:
            rec.request_type_count = len(rec.request_type_ids)

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        # The method is overridden to provide dynamic domain for service_id
        # field on request. There are field 'service_id_domain' on request,
        # that is compute and provides json-encoded domain for service.
        # So, when user tries to search for service in request, then the domain
        # computed by 'service_id_domain' will be used
        args = list(args or [])
        if self.env.context.get('request_service_id_domain'):
            try:
                extra_args = json.loads(
                    self.env.context['request_service_id_domain'])
            except json.JSONDecodeError:
                _logger.warning(
                    "Cannot decode request_service_id_domain from context!"
                    "The domain is: %r",
                    self.env.context['request_service_id_domain'],
                    exc_info=True)
            else:
                args = expression.AND([
                    args,
                    extra_args,
                ])

        return super(GenericService, self).name_search(
            name=name, args=args, operator=operator, limit=limit)

    def action_show_service_request_types(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_type_window',
            context=dict(
                self.env.context,
                default_service_ids=[(4, self.id)]),
            domain=[('service_ids.id', '=', self.id)],
        )

    def action_show_service_requests(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            context=dict(
                self.env.context,
                default_service_id=self.id),
            domain=[('service_id.id', '=', self.id)],
        )

    def action_show_service_categories(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_categories_window',
            context=dict(
                self.env.context,
                default_service_ids=[(4, self.id)]),
            domain=[('service_ids.id', '=', self.id)],
        )
