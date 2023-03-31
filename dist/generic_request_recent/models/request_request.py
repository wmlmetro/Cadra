from odoo import models, fields

from odoo.addons.generic_mixin.tools.sql import create_sql_view


class RelatedRequest(models.Model):
    _inherit = 'request.request'

    recent_related_request_ids = fields.Many2manyView(
        comodel_name='request.request',
        relation='request_request_recent_related_request_rel_view',
        column1='request_id',
        column2='related_request_id',
        string='Related requests',
        readonly=True, copy=False)

    def init(self):
        res = super().init()
        create_sql_view(
            self._cr, 'request_request_recent_related_request_rel_view',
            """
                WITH recent_request_min_date AS (
                    SELECT CURRENT_DATE - (
                        SELECT CAST(value AS INT)
                        FROM ir_config_parameter
                        WHERE key = 'request.recent_related_request_period'
                    ) AS min_date
                )
                SELECT rr.id AS request_id,
                       rr_related.id AS related_request_id
                FROM request_request AS rr
                LEFT JOIN request_request AS rr_related ON (
                    (rr.author_id = rr_related.author_id
                     OR
                     rr.partner_id = rr_related.partner_id)
                    AND rr.id != rr_related.id
                    AND rr_related.date_created >= (
                        SELECT min_date FROM recent_request_min_date)
                )
            """)
        return res

    def action_open_request_form_view(self):
        return self.env['generic.mixin.get.action'].get_form_action_by_xmlid(
            'generic_request.action_request_window',
            res_id=self.id)
