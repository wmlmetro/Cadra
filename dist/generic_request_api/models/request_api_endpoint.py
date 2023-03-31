import logging
import json
from urllib.parse import urljoin
import werkzeug
from odoo import models, fields, api
from odoo.osv import expression
from odoo.addons.http_routing.models.ir_http import slugify
from odoo.addons.generic_mixin.tools.x2m_agg_utils import read_counts_for_o2m

from ..constants import (
    API_PREFIX_PUBLIC,
    API_PREFIX_INTERNAL,
    API_PREFIX_REST,
)

_logger = logging.getLogger(__name__)


class RequestApiEndpoint(models.Model):
    _name = 'request.api.endpoint'
    _description = "Request API Endpoint"
    _inherit = ['generic.mixin.get.action']

    name = fields.Char(required=True, translate=True)
    slug = fields.Char(required=True)
    url = fields.Char(compute="_compute_url", readonly=True, store=False)
    url_full = fields.Char(compute="_compute_url", readonly=True, store=False)
    url_api_help = fields.Char(
        compute="_compute_url", readonly=True, store=False)
    active = fields.Boolean(index=True, default=True)

    type = fields.Selection([
        ('internal', 'Internal'),
        ('public', 'Public'),
        ('rest', 'REST')
    ], required=True)
    on_success = fields.Selection([
        ('return_req_id', 'Return Request ID'),
        ('redirect_url', 'Redirect to URL'),
    ], required=False)

    on_success_redirect_url = fields.Char(
        "Redirect URL (Success)",
        help="Url to redirect to on request created. "
             "String formatting could be used here with *request* in context.")

    request_creation_template_id = fields.Many2one(
        'request.creation.template', required=True,
        ondelete='restrict')

    # Used in 'generic_request_api_field' to restrict visible fields
    request_type_id = fields.Many2one(
        related='request_creation_template_id.request_type_id',
        readonly=True, store=False)

    public_sudo_user_id = fields.Many2one('res.users')

    request_ids = fields.One2many(
        'request.request', 'api_endpoint_id', 'Requests',
        readonly=True)

    request_count = fields.Integer(compute='_compute_request_count')

    api_key_ids = fields.One2many(
        'request.api.key', 'api_endpoint_id')

    _sql_constraints = [
        ('unique_type_slug',
         'UNIQUE(type, slug)',
         'Slug must be unique per API type'),
        ('slug_ascii_only',
         r"CHECK (slug ~ '^[a-z0-9\-_]+$')",
         'Slug must be lowercase ascii only'),
    ]

    @api.depends('slug', 'type')
    def _compute_url(self):
        base_url = self.sudo().env['ir.config_parameter'].get_param(
            'web.base.url')
        for record in self:
            if record.slug:
                if record.type == "internal":
                    record.url = "%s/%s" % (API_PREFIX_INTERNAL, record.slug)
                    record.url_full = urljoin(base_url, record.url)
                    record.url_api_help = False
                elif record.type == "public":
                    record.url = "%s/%s" % (API_PREFIX_PUBLIC, record.slug)
                    record.url_full = urljoin(base_url, record.url)
                    record.url_api_help = False
                elif record.type == "rest":
                    record.url = "%s/%s" % (API_PREFIX_REST, record.slug)
                    record.url_full = urljoin(base_url, record.url)
                    record.url_api_help = "%s/%s/api_help" % (
                        API_PREFIX_REST, record.slug)
            else:
                record.url = False

    @api.onchange('name')
    def _onchange_name(self):
        for record in self:
            record.slug = slugify(record.name or '', max_length=0)

    def ensure_authorized(self):
        self.ensure_one()
        if not self.api_key_ids:
            if self.public_sudo_user_id:
                return self.with_user(self.public_sudo_user_id)
            return self.sudo()
        for api_key in self.api_key_ids:
            if api_key.ensure_authorized():
                if api_key.use_sudo and api_key.sudo_user_id:
                    return self.with_user(api_key.sudo_user_id)
                return self.sudo()
        raise werkzeug.exceptions.Unauthorized()

    def _get_find_domain(self, request_id=None, request_name=None):
        if request_id:
            return [('id', '=', request_id)]
        if request_name:
            return [('name', '=', request_name)]
        return False

    def _find_request(self, request_id=None, request_name=None):
        self.ensure_one()
        base_domain = [
            ('api_endpoint_id', '=', self.id),
        ]
        domain = self._get_find_domain(request_id, request_name)
        if domain:
            return self.env['request.request'].sudo().search(expression.AND([
                base_domain, domain
            ]), limit=1)
        return False

    def _prepare_default_request_data(self):
        request_data = {
            'api_endpoint_id': self.id,
        }
        channel_api = self.env.ref(
            'generic_request.request_channel_api',
            raise_if_not_found=False)
        if channel_api and channel_api.sudo().active:
            request_data['channel_id'] = channel_api.id
        return self.request_creation_template_id.prepare_request_data(
            request_data)

    def _prepare_request_data(self, data):
        """ Prepare request's data based on related request template

            :param dict data: Incoming date received from external source.
            :return dict: Dictionary with data suitable for request creation
        """
        # Data is not safe, so we do not initialize request with data.
        # Data may contain http or json fields, that we cannot directly forward
        # to request creation procedure.
        return self.request_creation_template_id.prepare_request_data(
            self._prepare_default_request_data())

    def handle_simple_api_call(self, data):
        self.ensure_one()
        Request = self.env['request.request']
        if self.public_sudo_user_id:
            Request = Request.with_user(self.public_sudo_user_id)

        return Request.create(self._prepare_request_data(data))

    # -------------------
    # REST endpoint logic
    # -------------------
    def _rest_parse_data__author(self, author_info):
        res = {
            'author_id': False
        }
        # TODO: guess author
        partner = self.env['res.partner']

        author_email = author_info.get('email', False)
        if author_email:
            res['email_from'] = author_email
            # Looking for a partner with this email
            partner = self.env['res.partner'].search([
                ('email', '=', author_email)], limit=1)

        author_phone = author_info.get('phone', False)
        if author_phone:
            res['author_phone'] = author_phone
            # We search for a partner with this phone only if it was not
            # found by email
            if not partner:
                partner = self.env['res.partner'].search([
                    ('email', '=', author_email)], limit=1)

        author_name = author_info.get('name', False)
        if partner:
            res.update({
                'author_id': partner.id,
                'author_name': partner.name,
                'author_phone': partner.phone,
            })
        else:
            if author_name:
                res['author_name'] = author_name

        return res

    def _rest_parse_data(self, operation, data, request=None):
        """ Parse data received via controller.

            :param str operation: one of (create|update)
            :param dict data: Date received on this endpoint
            :param request: if operation is 'update', then this param
                will contain request that have to be updated
            :return dict: Dictionary with data suitable for for create/write
               on request.
        """
        res = self._prepare_default_request_data()
        if not data:
            return res
        author_info = data.get('author', False)
        if author_info:
            res.update(self._rest_parse_data__author(author_info))
        if data.get('request_text', False):
            res['request_text'] = data['request_text']
        return res

    def _rest_prepare_request_info(self, request):
        """ Prepare request info to be displayed to external service
            by this endpoint
        """
        return {
            "name": request.name,
            "author": {
                "name": (
                    request.author_id.name
                    if request.author_id
                    else request.author_name),
                "email": (
                    request.author_id.email
                    if request.author_id
                    else request.email_from),
            },
            "stage": {
                "name": request.stage_id.name,
                "code": request.stage_id.code,
                "is_closed": request.stage_id.closed,
            },
            "type": {
                "name": request.type_id.name,
                "code": request.type_id.code,
            },
            "request_text": request.request_text,
            "response_text": request.response_text,
        }

    def _rest_get_request_info(self, request, what=None):
        """ Return dictionary with request information for REST api.

            :param request: request to prepare info about.
            :param list[str] what: list of sections to display.
                If not specified, then all data will be returned.
            :return dict: dictionary with info about request and sections
                described in 'what' param, but 'name' section is always present
        """
        if what is None:
            show_all = True
        else:
            show_all = False
            what = set(['name'] + list(what))
        request_info = self._rest_prepare_request_info(request)

        return {
            "request": {
                section: value
                for section, value in request_info.items()
                if show_all or section in what
            }
        }

    def handle_rest_create_request(self, data, what=('type', 'stage')):
        data = self._rest_parse_data('create', data)
        request = self.request_creation_template_id.do_create_request(data)
        return self._rest_get_request_info(request, what=what)

    def handle_rest_get_request(self, request, what=None):
        return self._rest_get_request_info(request, what=what)

    def handle_rest_put_request(self, request, data, what=('type', 'stage')):
        if request.closed:
            raise Exception(
                "It is not allowed to update completed/closed request")
        data_to_write = self._rest_parse_data('update', data, request=request)
        request.write(data_to_write)
        return self._rest_get_request_info(request, what=what)

    ################
    # Docs Section #
    ################
    # POST
    def api_help_post_request_urls(self):
        self.ensure_one()
        return ('<h4>POST <code>%(url)s</code></h4>') % {'url': self.url}

    def _api_help_post_request_json(self):
        """Return request body as python dict()"""
        return {
            'author': {
                'email': 'example@example.com',
                'name': 'Author first name (optional)',
                'phone': 'Author phone (optional)',
            },
            'request_text': 'Text of request (optional).',
        }

    def api_help_post_request_json(self):
        """Return pretty view of data dict."""
        self.ensure_one()
        return json.dumps(
            self._api_help_post_request_json(), sort_keys=True, indent=4)

    def _api_help_post_response_json(self):
        """Return response body as python dict()"""
        return {
            'request': {
                'name': 'Req-052022-0015',
                'stage': {
                    'name': 'Draft',
                    'code': 'draft',
                    'is_closed': False
                },
                'type': {
                    'name': 'Simple Request',
                    'code': 'simple'
                }
            }
        }

    def api_help_post_response_json(self):
        """Return pretty view of data dict."""
        self.ensure_one()
        return json.dumps(
            self._api_help_post_response_json(), sort_keys=True, indent=4)

    # GET
    def api_help_get_request_urls(self):
        self.ensure_one()
        return (
            '<h4>GET <code>%(url)s/{ id }</code></h4>'
            '<h4>GET <code>%(url)s/{ request_name }</code></h4>') % {
                'url': self.url}

    def _api_help_get_request_json(self):
        """Return request body as python dict()"""
        # TODO: At this moment is empty dict. May be need add some parameters?
        return {}

    def api_help_get_request_json(self):
        """Return pretty view of data dict."""
        self.ensure_one()
        return json.dumps(
            self._api_help_get_request_json(), sort_keys=True, indent=4)

    def _api_help_get_response_json(self):
        """Return response body as python dict()"""
        return {
            'request': {
                'name': 'Req-052022-0015',
                'author': {
                    'name': 'Author first name',
                    'email': 'example@example.com'
                },
                'stage': {
                    'name': 'Draft',
                    'code': 'draft',
                    'is_closed': False
                },
                'type': {
                    'name': 'Simple Request',
                    'code': 'simple'
                },
                'request_text': 'Simple request created from API',
                'response_text': False
            }
        }

    def api_help_get_response_json(self):
        """Return pretty view of data dict."""
        self.ensure_one()
        return json.dumps(
            self._api_help_get_response_json(), sort_keys=True, indent=4)

    # PUT
    def api_help_put_request_urls(self):
        self.ensure_one()
        return (
            '<h4>PUT <code>%(url)s/{ id }</code></h4>'
            '<h4>PUT <code>%(url)s/{ request_name }</code></h4>') % {
                'url': self.url}

    def _api_help_put_request_json(self):
        """Return request body as python dict()"""
        return {
            'request_text': 'Add this Text to request.',
        }

    def api_help_put_request_json(self):
        """Return pretty view of data dict."""
        self.ensure_one()
        return json.dumps(
            self._api_help_put_request_json(), sort_keys=True, indent=4)

    def _api_help_put_response_json(self):
        """Return response body as python dict()"""
        return {
            'request': {
                'name': 'Req-052022-0015',
                'stage': {
                    'name': 'Draft',
                    'code': 'draft',
                    'is_closed': False
                },
                'type': {
                    'name': 'Simple Request',
                    'code': 'simple'
                }
            }
        }

    def api_help_put_response_json(self):
        """Return pretty view of data dict."""
        self.ensure_one()
        return json.dumps(
            self._api_help_put_response_json(), sort_keys=True, indent=4)

    @api.depends('request_ids')
    def _compute_request_count(self):
        mapped_data = read_counts_for_o2m(
            records=self,
            field_name='request_ids')
        for record in self:
            record.request_count = mapped_data.get(record.id, 0)

    def action_button_show_api_requests(self):
        action = self.get_action_by_xmlid(
            'generic_request.action_request_window',
            domain=[('api_endpoint_id', '=', self.id)],
        )
        return action

    def action_add_access_key(self):
        self.ensure_one()
        return self.env['generic.mixin.get.action'].get_action_by_xmlid(
            'generic_request_api.action_request_api_wizard_add_access_key',
            context={
                'default_api_endpoint_id': self.id,
            })
