from email.utils import formataddr
from odoo import models, fields, api, exceptions, _

from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m


class RequestMailSource(models.Model):
    _name = 'request.mail.source'
    _description = 'Request Mail Source'
    _inherit = [
        'mail.thread',
        'mail.alias.mixin',
    ]

    def _get_alias_default_fields(self):
        return self._alias_defaults_fields

    def get_alias_defaults(self):
        res = self.request_creation_template_id.prepare_request_data({
            'mail_source_id': self.id,
        })
        if res.get('request_text'):
            # Enforce converting request text to str, because as it is HTML
            # field, it may come as Markup instance
            res['request_text'] = str(res['request_text'])
        return res

    def _alias_get_creation_values(self):
        values = super(RequestMailSource, self)._alias_get_creation_values()
        values['alias_model_id'] = self.env['ir.model']._get(
            'request.request').id
        if self.id:
            values['alias_defaults'] = self.get_alias_defaults()
        return values

    name = fields.Char(
        required=True, translate=True, tracking=True)
    request_creation_template_id = fields.Many2one(
        'request.creation.template', required=True, ondelete='restrict')

    mask_email_address = fields.Selection(
        [('none', 'None'),
         ('internal', 'Internal users only'),
         ('all', 'All emails')],
        default='all', required=True,
        help="Define when system have to mask email address (for emails "
             "sent via Odoo). If set to none, then user's email will be used "
             "in From header of outgoing message; if set to internal, then "
             "only emails from internal users will be replaced with email of "
             "this mail source; if set to all, then all outgoing emails will "
             "be masked with the email of this mail source."
    )
    mask_email_author_name = fields.Selection(
        [('none', 'None'),
         ('internal', 'Internal users only'),
         ('all', 'All emails')],
        default='internal', required=True,
        help="Define when system have to mask name of author of outgoing "
             "email (for emails sent via Odoo). "
             "If set to none, then user's name will be used "
             "in From header of outgoing message; if set to internal, then "
             "only emails from internal users will be replaced with name of "
             "this mail source; if set to all, then all outgoing emails will "
             "be masked with the name of this mail source."
    )

    request_ids = fields.One2many(
        'request.request', 'mail_source_id', 'Requests', readonly=True)
    request_count = fields.Integer(
        compute='_compute_request_count', readonly=True)
    request_open_count = fields.Integer(
        compute='_compute_request_count', readonly=True)
    request_closed_count = fields.Integer(
        compute='_compute_request_count', readonly=True)

    @api.depends('request_ids')
    def _compute_request_count(self):
        mapped_data_all = read_counts_for_o2m(
            records=self,
            field_name='request_ids')
        mapped_data_closed = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('closed', '=', True)])
        mapped_data_open = read_counts_for_o2m(
            records=self,
            field_name='request_ids',
            domain=[('closed', '=', False)])
        for record in self:
            record.request_count = mapped_data_all.get(record.id, 0)
            record.request_open_count = mapped_data_open.get(record.id, 0)
            record.request_closed_count = mapped_data_closed.get(record.id, 0)

    @api.constrains('mask_email_address', 'mask_email_author_name')
    def _check_mask_email_configuration(self):
        # Mapping: mask_email_address -> [mask_email_author_name]
        allowed_combinations_map = {
            'all': ('none', 'internal', 'all'),
            'internal': ('none', 'internal'),
            'none': ('none',),
        }
        for record in self:
            allowed_masks = allowed_combinations_map.get(
                record.mask_email_address, tuple())
            if record.mask_email_author_name not in allowed_masks:
                raise exceptions.ValidationError(_(
                    "Mask email address set to %(mask_address)s, thus "
                    "only following values allowed for maks author name: "
                    "%(allowed_mask_author_names)s. "
                    "But got: %(mask_author_name_val)s."
                ) % {
                    'mask_address': record.mask_email_address,
                    'allowed_mask_author_names': allowed_masks,
                    'mask_author_name_val': record.mask_email_author_name,
                })

    def update_alias_defaults(self):
        for record in self:
            record.alias_id.write({
                'alias_defaults': record.get_alias_defaults(),
            })

    def write(self, vals):
        # Overriden to regenerate aliase defaults
        res = super(RequestMailSource, self).write(vals)
        if 'request_creation_template_id' in vals:
            self.update_alias_defaults()
        return res

    def get_email_from_address(self, author=None, company=None):
        """ Prepare email address to be used as from header in emails.

            :param recordset author: Suggest author of email
            :param recordset company: Suggest company, to detect company name
        """
        self.ensure_one()
        author = author if author else self.env.user.partner_id
        author_internal = (
            not author.with_context(active_test=False).user_ids[0].share
            if author.with_context(active_test=False).user_ids
            else False
        )
        company = company if company else self.env.user.company_id

        # Handle configuration for masking the name
        if self.mask_email_author_name == 'all':
            email_name = '%s %s' % (company.name, self.display_name)
        elif self.mask_email_author_name == 'internal' and author_internal:
            email_name = '%s %s' % (company.name, self.display_name)
        else:
            email_name = author.name

        # Handle configuration for masking the email
        if self.mask_email_address == 'all':
            email_addr = '%s@%s' % (self.alias_name, self.alias_domain)
        elif self.mask_email_address == 'internal' and author_internal:
            email_addr = '%s@%s' % (self.alias_name, self.alias_domain)
        else:
            email_addr = author.email
        return formataddr((email_name, email_addr))

    def action_view_requests(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            context={},
            domain=[('mail_source_id', '=', self.id)])

    def action_show_open_requests(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            context={'search_default_filter_open': 1},
            domain=[('mail_source_id', '=', self.id)])

    def action_show_closed_requests(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request.action_request_window',
            context={'search_default_filter_closed': 1},
            domain=[('mail_source_id', '=', self.id)])
