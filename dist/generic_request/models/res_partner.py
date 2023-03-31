from odoo import models, fields, api
from odoo.osv import expression

from odoo.addons.crnd_web_m2o_info_widget import helper_get_many2one_info_data
from odoo.addons.generic_mixin.tools.sql import create_sql_view


class ResPartner(models.Model):
    _inherit = 'res.partner'

    request_by_partner_ids = fields.One2many(
        'request.request', 'partner_id',
        readonly=True, copy=False)
    request_by_author_ids = fields.One2many(
        'request.request', 'author_id',
        readonly=True, copy=False)
    request_ids = fields.Many2manyView(
        comodel_name='request.request',
        relation='request_partner_author_requests_rel_view',
        column1='partner_id',
        column2='request_id',
        readonly=True, copy=False, store=True)
    request_count = fields.Integer(
        'Requests', compute='_compute_request_data',
        store=True, readonly=True)
    service_agent_id = fields.Many2one('res.users', ondelete='restrict')

    @api.depends('request_by_partner_ids', 'request_by_author_ids')
    def _compute_request_data(self):
        if self.ids:
            # Use SQL here to improve perfomance in case when large amount of
            # requests related to single partner (author)
            self.env['request.request'].flush(['author_id', 'partner_id'])
            self.env.cr.execute("""
                SELECT partner_id, count(request_id) AS count
                FROM (
                    SELECT DISTINCT partner_id,
                                    request_id
                    FROM (
                        SELECT author_id AS partner_id,
                               id        AS request_id
                        FROM request_request
                        WHERE author_id IN %(partner_ids)s
                        UNION
                        SELECT partner_id AS partner_id,
                               id         AS request_id
                        FROM request_request
                        WHERE partner_id IN %(partner_ids)s
                    ) AS t
                ) AS t2
                GROUP BY partner_id
            """, {
                'partner_ids': tuple(self.ids),
            })
            data = dict(self.env.cr.fetchall())
        else:
            data = {}
        for record in self:
            record.request_count = data.get(record.id, 0)

    @api.model
    def init(self):
        res = super().init()

        # Making this view to improve performance on
        # computation of request_ids field on partner.
        create_sql_view(
            self._cr, 'request_partner_author_requests_rel_view',
            """
                SELECT DISTINCT partner_id,
                                request_id
                FROM (
                    SELECT author_id AS partner_id,
                           id        AS request_id
                    FROM request_request
                    WHERE author_id IS NOT NULL
                    UNION
                    SELECT partner_id AS partner_id,
                           id         AS request_id
                    FROM request_request
                    WHERE partner_id IS NOT NULL
                ) AS t
            """)
        return res

    def action_show_related_requests(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            domain=expression.OR([
                [('partner_id', 'in', self.ids)],
                [('author_id', 'in', self.ids)],
            ]),
            context=dict(
                self.env.context,
                default_partner_id=self.commercial_partner_id.id,
                default_author_id=self.id,
            ))

    def _request_helper_m2o_info_get_fields(self):
        """ Find list of fields, that have to be displayed as partner info
            on request form view in 'm2o_info' fields.

            Could be overridden by third-party modules.
        """
        return [
            'name', 'commercial_company_name', 'website',
            'email', 'phone', 'mobile'
        ]

    def request_helper_m2o_info(self):
        """ Technical method, that is used to perepear data for
            m2o_info fields.
        """
        return helper_get_many2one_info_data(
            self,
            self._request_helper_m2o_info_get_fields())
