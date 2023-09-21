import logging
from psycopg2 import sql
from odoo import models, fields, api, tools, _
from odoo.exceptions import AccessError

from odoo.addons.generic_resource.tools.utils import resource_proxy

_logger = logging.getLogger(__name__)

GROUP_RESOURCE_MANAGER = 'generic_resource.group_generic_resource_manager'


class GenericResource(models.Model):
    _inherit = 'generic.resource'

    resource_role_link_ids = fields.One2many(
        'generic.resource.role.link', 'resource_id', 'Role links')
    resource_role_link_count = fields.Integer(
        'Role links (Count)', compute='_compute_resource_role_link_count',
        readonly=True, compute_sudo=False)
    resource_user_role_ids = fields.Many2many(
        comodel_name='generic.resource.role',
        string='User roles',
        compute='_compute_resource_user_roles',
        readonly=True, compute_sudo=False,
        help="Roles that have current user for this resource")
    resource_role_sec_view_ids = fields.One2many(
        comodel_name='generic.resource.role.link.sec.view',
        inverse_name='resource_id',
        # We have to explicitly specify domain here to be compatible with 14.0.
        # This is needed because otherwise in Odoo 14.0 it will try to read
        # all records in this field, and then apply access rules that will
        # raise errors
        domain=lambda s: [
            '|',
            (int(s.env.user.has_group(
                'generic_resource.group_generic_resource_manager')), '=', 1),
            ('user_id', '=', s.env.user.id)
        ],
        readonly=True)
    resource_visibility = fields.Selection(
        selection_add=[('role-based', 'Access restricted by roles')],
        default='role-based', ondelete={'role-based': 'cascade'})
    resource_role_manager_ids = fields.Many2manyView(
        comodel_name='res.users',
        relation='generic_resource_role_managers_rel',
        column1='resource_id',
        column2='user_id',
        string="Manager Role Links",
        readonly=True, copy=False)
    resource_is_role_manager = fields.Boolean(
        compute='_compute_resource_is_role_manager',
        string="Current user is role manager",
        readonly=True,
        help="Technical field to determine if current user is role manager. "
             "This field mostly use for UI."
    )

    def _compute_resource_is_role_manager(self):
        for record in self:
            record.resource_is_role_manager = (
                self.env.user.has_group(
                    "generic_resource.group_generic_resource_manager"
                ) or self.env.user in record.resource_role_manager_ids
            )

    def has_permission(self, code):
        """ This method check that the current user has permission specified
            in the variable 'code'.
            Returns True if such permission exists, otherwise returns False.
        """
        if self.env.su:
            # no access rights checks for superuser
            return True

        return bool(self.env['generic.resource.role.link.sec.view'].search([
            ('resource_id', '=', self.id),
            ('user_id', '=', self.env.user.id),
            ('role_id.resource_permission_ids.code', '=', code),
        ], limit=1))

    def require_permission(self, code):
        """ This method check that the current user has permission specified
            in the variable 'code'.
            Raises an access error if there is no such permission.
        """
        if not self.has_permission(code):
            raise AccessError(_(
                "Permission '%(permission)s' is not allowed for this "
                "resource(s) (%(resources)s) !"
            ) % {
                'permission': code,
                'resources': ", ".join([r.display_name for r in self]),
            })

    @api.depends('resource_role_link_ids.partner_id',
                 'resource_role_link_ids')
    def _compute_resource_user_roles(self):
        for rec in self:
            rec.resource_user_role_ids = rec.resource_role_link_ids.filtered(
                lambda r: r.partner_id == self.env.user.partner_id
            ).mapped('role_id')

    @api.depends('resource_role_link_ids')
    def _compute_resource_role_link_count(self):
        for rec in self:
            rec.resource_role_link_count = len(rec.resource_role_link_ids)

    def init(self):
        # pylint: disable=sql-injection
        tools.drop_view_if_exists(
            self.env.cr, 'generic_resource_role_managers_rel')
        self.env.cr.execute(sql.SQL("""
            CREATE or REPLACE VIEW generic_resource_role_managers_rel AS (
                SELECT DISTINCT
                    grrl.resource_id,
                    grrl.user_id
                FROM generic_resource_role_link AS grrl
                WHERE grrl.active = True
                  AND grrl.can_manage_roles = True
                  AND (grrl.date_start IS NULL OR grrl.date_start <= now())
                  AND (grrl.date_end IS NULL OR grrl.date_end >= now())
            )
        """))

    def check_access_role(self, operation):
        """ Check access to resource based on roles
        """
        if self.env.su:
            return True

        if self.env.user.has_group(GROUP_RESOURCE_MANAGER):
            # Do not check resource roles for resource manager
            return True

        # Dict {<operatioon>: <field>}
        operations_map = {
            # 'create': 'can_write',
            'write': 'can_write',
            'unlink': 'can_unlink',
            'manage_roles': 'can_manage_roles',
        }

        if operation in operations_map and self.ids:
            # pylint: disable=sql-injection
            query = sql.SQL("""
                SELECT (
                    SELECT COUNT(*)
                    FROM (
                        SELECT DISTINCT rl.resource_id
                        FROM generic_resource_role_link_sec_view AS rl
                        WHERE rl.{field_to_check} = True
                            AND rl.user_id = %(user_id)s
                            AND rl.resource_id IN %(resource_ids)s
                    ) AS allowed_resources
                ) = (
                    SELECT COUNT(*)
                    FROM generic_resource
                    WHERE generic_resource.id IN %(resource_ids)s
                )
            """).format(
                field_to_check=sql.Identifier(operations_map[operation]),
            )
            for sub_ids in self.env.cr.split_for_in_conditions(self.ids):
                self.env.cr.execute(query, {
                    'user_id': self.env.user.id,
                    'resource_ids': sub_ids,
                })
                if not self.env.cr.fetchone()[0]:
                    return False
        return True

    def check_access_rule(self, operation):
        # pylint: disable=missing-return
        super(GenericResource, self).check_access_rule(operation)
        if not self.check_access_role(operation):
            raise AccessError(_(
                "Operation '%(operation)s' is not allowed for this "
                "resource(s) (%(resources)s) !"
            ) % {
                'operation': operation,
                'resources': ", ".join([r.display_name for r in self]),
            })

    @api.model_create_multi
    def create(self, vals):
        # Post-process role links (do not create sub-roles during resource
        # creation
        resources = super(
            GenericResource,
            self.with_context(__post_process_role_links__=True)).create(vals)
        return resources

    def on_resource_created(self):
        # TODO: test this method without sudo
        self.ensure_one()
        res = super(GenericResource, self).on_resource_created()

        # Sync subroles
        self.sudo().resource_role_link_ids._subrole__update_subroles()

        # Update role links from subroles
        sub_roles = self.env['generic.resource.sub.role'].sudo().search([
            ('sub_type_id', '=', self.res_type_id.id),
        ])
        for sub_role in sub_roles:
            master_resource = self.sudo().resource[sub_role.sub_field_id.name]
            master_rls = master_resource.with_context(
                active_test=False).mapped('resource_role_link_ids')
            for master_rl in master_rls:
                if master_rl.role_id == sub_role.master_role_id:
                    master_rl._subrole__create_role_link(
                        sub_role, self)

        self.check_access_rule('read')

        return res

    def _postprocess_resource_changes(self, changes):
        res = super(GenericResource, self)._postprocess_resource_changes(
            changes)
        RoleLink = self.env['generic.resource.role.link']
        sub_roles = self.env['generic.resource.sub.role'].sudo().search([
            ('sub_type_id', '=', self.res_type_id.id),
        ])
        for sub_role in sub_roles:
            if sub_role.sub_field_id.name not in changes:
                continue

            old_records, new_records = changes[sub_role.sub_field_id.name]
            if old_records:
                RoleLink.sudo().with_context(
                    active_test=False
                ).search([
                    ('resource_id', '=', self.id),
                    ('parent_id.resource_id', 'in',
                     old_records.sudo().mapped('resource_id').ids),
                ]).unlink()
            if new_records:
                new_master_role_links = new_records.sudo().mapped(
                    'resource_role_link_ids')
                for master_rl in new_master_role_links:
                    if master_rl.role_id == sub_role.master_role_id:
                        master_rl._subrole__create_role_link(
                            sub_role, self)
        return res

    @resource_proxy
    def action_view_resource_role_links(self):
        self.ensure_one()
        return self.get_action_by_xmlid(
            'generic_resource_role.generic_resource_role_link_action_view',
            context={
                'default_resource_id': self.id,
                'default_resource_type_id': self.res_type_id.id,
                'default_resource_res_id': self.res_id,
                'default_resource_res_model': self.res_model,
                'set_readonly_resource': True,
            },
            domain=[('resource_id', '=', self.id)],
        )

    @resource_proxy
    def action_add_resource_role_link(self):
        self.ensure_one()
        return self.get_form_action_by_xmlid(
            'generic_resource_role.generic_resource_role_link_action_view',
            context={
                'default_resource_id': self.id,
                'default_resource_type_id': self.res_type_id.id,
                'default_resource_res_id': self.res_id,
                'default_resource_res_model': self.res_model,
                'set_readonly_resource': True,
            })
