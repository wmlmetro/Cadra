import logging
from odoo import models, fields, api, exceptions, _
from odoo.addons.generic_mixin import pre_write, post_write
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

_logger = logging.getLogger(__name__)


class GenericResourceSubRole(models.Model):
    _name = 'generic.resource.sub.role'
    _inherit = [
        'generic.mixin.track.changes',
        'generic.mixin.data.updatable',
        'mail.thread',
    ]
    _description = 'Resource Sub Role'
    _order = 'name, id'

    name = fields.Char(required=True, tracking=True)
    master_role_id = fields.Many2one(
        'generic.resource.role', index=True, required=True, ondelete='cascade',
        tracking=True)
    master_type_id = fields.Many2one(
        'generic.resource.type', readonly=True,
        related='master_role_id.resource_type_id',
        string="Master Resource Type")
    master_model_id = fields.Many2one(
        'ir.model', related='master_type_id.model_id', readonly=True)
    master_model = fields.Char(
        'ir.model', related='master_type_id.model_id.model', readonly=True)

    sub_type_id = fields.Many2one(
        'generic.resource.type', required=True, index=True, ondelete='cascade',
        tracking=True)
    sub_model_id = fields.Many2one(
        'ir.model', related='sub_type_id.model_id', readonly=True)
    sub_field_id = fields.Many2one(
        'ir.model.fields', index=True, required=True, ondelete='cascade',
        tracking=True)
    sub_role_id = fields.Many2one(
        'generic.resource.role', 'Sub Role',
        required=True, index=True, ondelete='cascade',
        tracking=True)

    sub_role_link_ids = fields.One2many(
        'generic.resource.role.link', 'sub_role_id', readonly=True)
    sub_role_link_count = fields.Integer(
        compute='_compute_sub_role_link_count', readonly=True)

    description = fields.Text()

    _sql_constraints = [
        ('subrole_uniq',
         'UNIQUE (master_role_id, sub_type_id, sub_field_id, sub_role_id)',
         'Sub Role must be uniq by fields '
         '(Master Role, Sub Type, Sub Field, Sub Role).'),
    ]

    @api.depends('sub_role_link_ids')
    def _compute_sub_role_link_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='sub_role_link_ids')
        for record in self:
            record.sub_role_link_count = mapped_data.get(record.id, 0)

    @api.constrains('master_role_id', 'sub_type_id',
                    'sub_field_id', 'sub_role_id')
    def check_master_role_and_sub_data(self):
        for record in self.sudo():
            if record.master_model != record.sub_field_id.relation:
                raise exceptions.ValidationError(_(
                    "Incorrect combination of Master Role and Sub Field"))
            if record.sub_field_id.model_id != record.sub_type_id.model_id:
                raise exceptions.ValidationError(_(
                    "Incorrect combination of Sub Type and Sub Field"))
            if record.sub_type_id != record.sub_role_id.resource_type_id:
                raise exceptions.ValidationError(_(
                    "Incorrect combination of Sub Type and Sub Role"))
            sub_field_ttype = ('many2many', 'one2many', 'many2one')
            if record.sub_field_id.ttype not in sub_field_ttype:
                raise exceptions.ValidationError(_(
                    'Incorrect subfield (%(subfield)s) type: %(subfield_type)s'
                ) % {
                    'subfield': record.sub_field_id.display_name,
                    'subfield_type': record.sub_field_id.ttype,
                })

    @api.onchange('sub_type_id')
    def _onchange_subtype_id(self):
        for record in self:
            record.sub_role_id = False
            record.sub_field_id = False

    @api.model
    def _get_generic_tracking_fields(self):
        """ Get tracking fields
        """
        track_fields = super(
            GenericResourceSubRole, self)._get_generic_tracking_fields()
        return track_fields | set([
            'master_role_id',
            'sub_role_id',
            'sub_type_id',
            'sub_field_id',
        ])

    @pre_write('master_role_id', 'sub_field_id', 'sub_type_id')
    def _clean_up_subroles_on_subrole_changed(self, changes):
        """ Called before write

            :param dict changes: keys are changed field names,
                                 values are tuples (old_value, new_value)
            :rtype: dict
            :return: values to update record with.
                     These values will be written just after write
        """
        # Remove subroles (will be regenerated in post handler)
        self.master_role_id.sudo().mapped(
            'role_link_ids.child_ids').unlink()

    @post_write('master_role_id', 'sub_field_id', 'sub_type_id', 'sub_role_id')
    def _update_or_regenerate_sub_roles(self, changes):
        """ Called after write

            :param dict changes: keys are changed field names,
                                 values are tuples (old_value, new_value)
            :return: None

        """
        # We use elif here because when field change requires regeneration of
        # sub-role-links, then there is no sense to update role on
        # sub-role-links. And contrary, if only sub-role is changed, then we do
        # not need to regenerate sub-role-links.
        regen_subroles_fields = set((
            'master_role_id', 'sub_field_id', 'sub_type_id'))
        if regen_subroles_fields & set(changes):
            # If field change requires regeneration of sub-role-links
            self.master_role_id.role_link_ids._subrole__update_subroles()
        elif 'sub_role_id' in changes:
            # If sub-role changed, the we can only update sub-role-links with
            # new role
            self.sub_role_link_ids.sudo().write({
                'role_id': self.sub_role_id.id,
            })

    @api.model_create_multi
    def create(self, vals):
        sub_roles = super().create(vals)
        sub_roles.mapped(
            'master_role_id.role_link_ids')._subrole__update_subroles()
        return sub_roles

    def action_view_sub_role_links(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_resource_role.generic_resource_role_link_action_view',
            domain=[('sub_role_id', '=', self.id)])
