import logging

from odoo import models, fields, api
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m
from odoo.addons.generic_mixin.tools.sql import create_sql_view

_logger = logging.getLogger(__name__)


class GenericService(models.Model):
    _inherit = 'generic.service'

    request_type_ids = fields.Many2manyView(
        'request.type', 'generic_service_request_type_view',
        'service_id', 'type_id', string='Request types',
        readonly=True, copy=False)
    request_type_count = fields.Integer(
        compute="_compute_request_type_count")
    request_ids = fields.One2many(
        'request.request', 'service_id', string='Requests')
    request_count = fields.Integer(
        compute='_compute_request_count')

    # TODO: rename to `request_category_ids`
    # TODO: remove category relation after switch to classifiers completed
    category_ids = fields.Many2manyView(
        'request.category',
        'service_category_view', 'service_id', 'category_id',
        'Request Categories',
        readonly=True, copy=False)
    category_count = fields.Integer(
        'Request Categories (Count)', compute="_compute_category_count")

    request_classifier_ids = fields.One2many(
        comodel_name='request.classifier',
        inverse_name='service_id',
        string='Classifiers',
        required=False, index=True)
    request_classifier_count = fields.Integer(
        compute='_compute_request_classifier_count')

    @api.model
    def init(self):
        res = super().init()

        create_sql_view(
            self._cr, 'generic_service_request_type_view',
            """
                SELECT DISTINCT service_id,
                       type_id
                FROM request_classifier
                WHERE service_id IS NOT NULL AND type_id IS NOT NULL
                    AND active = TRUE
            """)

        create_sql_view(
            self._cr, 'service_category_view',
            """
                SELECT DISTINCT service_id,
                       category_id
                FROM request_classifier
                WHERE service_id IS NOT NULL AND category_id IS NOT NULL
                    AND active = TRUE
            """)
        return res

    @api.depends('request_ids')
    def _compute_request_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='request_ids')
        for record in self:
            record.request_count = mapped_data.get(record.id, 0)

    @api.depends('request_classifier_ids')
    def _compute_request_classifier_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='request_classifier_ids')
        for record in self:
            record.request_classifier_count = mapped_data.get(record.id, 0)

    @api.depends('category_ids')
    def _compute_category_count(self):
        for rec in self:
            rec.category_count = len(rec.category_ids)

    @api.depends('request_type_ids')
    def _compute_request_type_count(self):
        for rec in self:
            rec.request_type_count = len(rec.request_type_ids)

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

    def action_show_classifiers(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_classifier_window',
            context={'default_service_id': self.id},
            domain=[('service_id', '=', self.id)],
        )
