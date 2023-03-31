from email.utils import formataddr
from odoo import models, fields, api


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
        for record in self:
            record.request_count = len(record.request_ids)
            record.request_open_count = len(
                record.request_ids.filtered(lambda r: not r.closed))
            record.request_closed_count = len(
                record.request_ids.filtered(lambda r: r.closed))

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

    def get_email_address(self, company=None):
        self.ensure_one()
        company = company if company else self.env.user.company_id
        company_name = company.name
        email_name = '%s %s' % (
            company_name, self.display_name)
        email_addr = '%s@%s' % (
            self.alias_name,
            self.alias_domain)
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
