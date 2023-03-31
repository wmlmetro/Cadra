from psycopg2 import sql

from odoo import models, fields, tools


class GenericResourceRoleLinkSecView(models.Model):
    _name = 'generic.resource.role.link.sec.view'
    _description = 'Resource Role Link (Sec View)'
    _auto = False

    role_link_id = fields.Many2one('generic.resource.role.link', readonly=True)
    role_id = fields.Many2one('generic.resource.role', readonly=True)
    resource_id = fields.Many2one('generic.resource', readonly=True)
    partner_id = fields.Many2one('res.partner', readonly=True)
    user_id = fields.Many2one('res.users', readonly=True)
    can_write = fields.Boolean(readonly=True)
    can_unlink = fields.Boolean(readonly=True)
    can_manage_roles = fields.Boolean(readonly=True)

    def init(self):
        # pylint: disable=sql-injection
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(sql.SQL("""
            CREATE or REPLACE VIEW {table_name} AS (
                SELECT grrl.id,
                    grrl.id AS role_link_id,
                    grrl.resource_id,
                    grrl.role_id,
                    grrl.partner_id,
                    u.id AS user_id,
                    grr.can_write,
                    grr.can_unlink,
                    grr.can_manage_roles
                FROM generic_resource_role_link AS grrl
                LEFT JOIN generic_resource_role AS grr ON grr.id = grrl.role_id
                LEFT JOIN res_users AS u ON u.partner_id = grrl.partner_id
                WHERE grrl.active = True
                AND (grrl.date_start IS NULL OR grrl.date_start <= now())
                AND (grrl.date_end IS NULL OR grrl.date_end >= now())
            )
        """).format(
            table_name=sql.Identifier(self._table),
        ))

    def action_edit_role_link(self):
        self.ensure_one()
        action = self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_resource_role.generic_resource_role_link_action_view'
        )
        action['res_id'] = self.role_link_id.id
        action['views'] = [(False, 'form')]
        return action

    def action_expire_role_link(self):
        self.ensure_one()
        self.role_link_id.write({
            'date_end': fields.Date.today(),
        })
