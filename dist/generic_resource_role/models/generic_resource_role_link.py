import logging
from odoo import models, fields, api, exceptions, _

from odoo.addons.generic_mixin import post_write, pre_create
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

_logger = logging.getLogger(__name__)

SUBROLE_COPY_FIELDS = set([
    'date_start',
    'date_end',
    'active',
    'partner_id',
])


def str2date(date_str):
    return fields.Date.from_string(date_str)


class GenericResourceRoleID(int):
    pass


class GenericResourceRoleLink(models.Model):
    _name = 'generic.resource.role.link'
    _description = 'Resource Role Link'

    _inherit = [
        'generic.resource.related.mixin',
        'generic.mixin.data.updatable',
        'generic.mixin.track.changes',
    ]

    # TODO: add constrains to check if role and resource_id are set correctly
    role_id = fields.Many2one(
        'generic.resource.role', 'Role', ondelete='cascade',
        index=True, required=True)
    role_type_id = fields.Many2one(
        'generic.resource.role.type', 'Role Type',
        related='role_id.role_type_id', readonly=True, store=True)
    date_start = fields.Date(index=True)
    date_end = fields.Date(index=True)
    active = fields.Boolean(index=True, default=True)
    partner_id = fields.Many2one(
        'res.partner', domain=[('type', 'not in', ('invoice', 'delivery'))],
        required=True, index=True, string="Partner")
    view_partner_id = fields.Many2one(
        'res.partner', related='partner_id', string="Partner", readonly=True)
    view_resource_type_id = fields.Many2one(
        'generic.resource.type', string='Resource type',
        related='resource_type_id', readonly=True)
    view_resource_res_id = fields.Many2oneReference(
        string="Resource", related='resource_res_id', readonly=True,
        model_field="resource_res_model")
    user_id = fields.Many2one(
        'res.users', compute='_compute_user_id', compute_sudo=True,
        readonly=True, index=True, store=True)

    # Subroles data
    parent_id = fields.Many2one(
        'generic.resource.role.link', index=True, readonly=True,
        ondelete='cascade')
    sub_role_id = fields.Many2one(
        'generic.resource.sub.role', ondelete='cascade', readonly=True)
    child_ids = fields.One2many(
        'generic.resource.role.link', 'parent_id', readonly=True)
    child_count = fields.Integer(
        compute='_compute_child_count', compute_sudo=True, readonly=True)

    # Related role access settings. Theoretically this will simplify searches
    can_write = fields.Boolean(
        index=True, related='role_id.can_write', store=True, readonly=True)
    can_unlink = fields.Boolean(
        index=True, related='role_id.can_unlink', store=True, readonly=True)
    can_manage_roles = fields.Boolean(
        index=True, related='role_id.can_manage_roles',
        store=True, readonly=True)

    # Update resource_id field defined by 'generic.resource.related.mixin'
    resource_id = fields.Many2one(ondelete='cascade')

    doc_model = fields.Char(index=True)
    doc_id = fields.Integer(string='Origin document', index=True)

    @api.constrains('date_start', 'date_end')
    def _check_is_date_start_less_date_end(self):
        for rec in self:
            if (rec.date_start and rec.date_end and
                    str2date(rec.date_start) > str2date(rec.date_end)):
                raise exceptions.ValidationError(
                    _("The start date can not exceed the end date."))

    @api.depends('partner_id', 'partner_id.user_ids.partner_id')
    def _compute_user_id(self):
        for record in self:
            if len(record.partner_id.user_ids) == 1:
                record.user_id = record.partner_id.user_ids
            else:
                record.user_id = False

    @api.depends('child_ids')
    def _compute_child_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='child_ids')
        for record in self:
            record.child_count = mapped_data.get(record.id, 0)

    def name_get(self):
        res = []
        for rec in self:
            name = "%s - %s of %s" % (
                rec.partner_id.display_name,
                rec.role_id.display_name,
                rec.resource_id.display_name,
            )
            res.append(
                (rec.id, name)
            )

        return res

    def _subrole__prepare_role_link(self, sub_role, gresource):
        """ :param sub_role: record('generic.resource.sub.role')
            :param gresource: record('generic.resource')
        """
        self.ensure_one()
        return {
            'date_start': self.date_start,
            'date_end': self.date_end,
            'active': self.active,
            'partner_id': self.partner_id.id,
            'parent_id': self.id,
            'sub_role_id': sub_role.id,
            'role_id': sub_role.sub_role_id.id,
            # We have to use res type and res_id instead of resoruce_id fields
            # here. The reason is that if resource_type_id or resource_res_id
            # has default values in context, then that values will be used
            # instead of resource_id.
            'resource_type_id': gresource.res_type_id.id,
            'resource_res_id': gresource.res_id,

        }

    def _subrole__create_role_link(self, sub_role, gresource):
        """ :param sub_role: record('generic.resource.sub.role')
            :param gresource: record('generic.resource')
        """
        return self.create(
            self._subrole__prepare_role_link(
                sub_role, gresource))

    def _subrole__update_subroles_single(self):
        """ Regenerate subroles of single role link
        """
        self.ensure_one()

        # Get concreet implementation of selected resource
        resource = self.resource_id.resource

        # Clean old subroles first
        self.child_ids.unlink()

        # Regenerate subroles
        for sub_role in self.role_id.sub_role_ids:
            if sub_role.sub_model_id.model not in self.env:
                _logger.warning(
                    "Model (%s) for subrole (%s) does not exists in registry. "
                    "Possibly this is because module that implements "
                    "this model is not (yet) installed. "
                    "Skipping creation of subrole links",
                    sub_role.sub_model_id.model, sub_role.display_name)
                continue
            # NOTE: sub_resource contains list of concreet resource
            # implementations, NOT generic.resource
            if sub_role.sub_field_id.ttype == 'many2one':
                sub_resources = self.env[sub_role.sub_model_id.model].search(
                    [(sub_role.sub_field_id.name, '=', resource.id)])
            elif sub_role.sub_field_id.ttype in ('many2many', 'one2many'):
                # TODO: use different searches for many2many and many2one
                sub_resources = self.env[sub_role.sub_model_id.model].search(
                    [("%s.id" % sub_role.sub_field_id.name, '=', resource.id)])
            else:
                raise exceptions.ValidationError(_(
                    "Incorrect configuration of subrole %(subrole)s!\n"
                    "Incorrect field type %(field)s: %(field_type)s"
                ) % {
                    'subrole': sub_role.display_name,
                    'field': sub_role.sub_field_id.display_name,
                    'field_type': sub_role.sub_field_id.ttype,
                })

            for sub_resource in sub_resources:
                self._subrole__create_role_link(
                    sub_role, sub_resource.resource_id)

    def _subrole__update_subroles(self):
        """ Regenerate subroles for all rolelinks in self
        """
        for record in self.sudo():
            record._subrole__update_subroles_single()

    @post_write('date_start', 'date_end', 'active', 'partner_id')
    def _subrole__sync_subroles(self, changes):
        self_sudo = self.sudo()
        self_sudo.with_context(
            active_test=False
        ).child_ids.write({
            'date_start': self_sudo.date_start,
            'date_end': self_sudo.date_end,
            'active': self_sudo.active,
            'partner_id': self_sudo.partner_id.id,
        })

    def check_access_rule(self, operation):
        # Check if current user has 'Manage Roles' access on related resource.
        # If yes, then bypass access rights
        resources = self.sudo().mapped('resource_id').with_user(self.env.user)
        if resources.check_access_role('manage_roles'):
            return True
        return super(GenericResourceRoleLink, self).check_access_rule(
            operation)

    @pre_create('parent_id', 'sub_role_id')
    def _disallow_direct_creation_of_subroles(self, changes):
        if not self.env.su:
            if 'parent_id' in changes or 'sub_role_id' in changes:
                raise exceptions.AccessError(_(
                    "It is not allowed to create roles "
                    "sub-role-links manualy."))

    @api.model
    def create(self, vals):
        role_id = vals.get('role_id')
        if role_id and isinstance(role_id, GenericResourceRoleID):
            vals['role_id'] = int(role_id)
            role_links = super(
                GenericResourceRoleLink, self.sudo()).create(vals)
        else:
            role_links = super(GenericResourceRoleLink, self).create(vals)

        # Invalidate cache for 'resource_role_sec_view_ids' to make access
        # rights checks work
        self.env['generic.resource'].invalidate_cache(
            ['resource_role_sec_view_ids', 'resource_role_manager_ids'],
            role_links.mapped('resource_id').ids)

        # Sync sub_roles
        if not self.env.context.get('__post_process_role_links__', False):
            # There is special case, where we have no update subroles during
            # role link creation. This is case of creation of resource,
            # because, when role links passed as parameters to create resource,
            # then resource creation is not complete in this stage. In that
            # case '_subrole_update_subsubroles` will be called directly from
            # resource
            role_links._subrole__update_subroles()
        return role_links

    @post_write('resource_res_id', 'resource_id',
                'resource_type_id', 'role_id')
    def _post_write_update_subroles(self, changes):
        self._subrole__update_subroles()

    def write(self, vals):
        if not self.env.su:
            if any(r.parent_id for r in self):
                raise exceptions.AccessError(_(
                    "It is not allowed to change roles generated by "
                    "sub-roles."))
            if vals.get('parent_id') or vals.get('sub_role_id'):
                raise exceptions.AccessError(_(
                    "It is not allowed to change parent role link manualy."))
        return super(GenericResourceRoleLink, self).write(vals)

    def unlink(self):
        if not self.env.su and any(r.parent_id for r in self):
            raise exceptions.AccessError(_(
                "It is not allowed to delete roles generated by sub-roles."))

        resource_ids = self.mapped('resource_id').ids

        res = super(GenericResourceRoleLink, self).unlink()

        # Invalidate cache for 'resource_role_sec_view_ids' to make access
        # rights checks work
        self.env['generic.resource'].invalidate_cache(
            ['resource_role_sec_view_ids', 'resource_role_manager_ids'],
            resource_ids)

        return res

    def action_view_sub_role_links(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_resource_role.generic_resource_role_link_action_view',
            domain=[('parent_id', '=', self.id)],
        )
