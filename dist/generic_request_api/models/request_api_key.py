import logging

from odoo import http
from odoo import models, fields

from ..constants import KEY_CRYPT_CONTEXT

_logger = logging.getLogger(__name__)

verify_api_key = getattr(KEY_CRYPT_CONTEXT, 'verify', None)
if not verify_api_key:
    _logger.debug('No loaded verification method')


class RequestApiKey(models.Model):
    _name = 'request.api.key'
    _description = "Request API Key"
    _order = 'name'

    name = fields.Char(required=True)
    api_endpoint_id = fields.Many2one(
        'request.api.endpoint', required=True, index=True)

    # API Key field
    key_value = fields.Char(index=True, required=True, copy=False)
    use_sudo = fields.Boolean()
    sudo_user_id = fields.Many2one('res.users')
    create_date = fields.Datetime("Creation Date", readonly=True)

    def _ensure_authorized__api_key(self):
        self.ensure_one()
        header_vals = http.request.httprequest.headers.get_all(
            'X-API-Key'
        )
        for header_value in header_vals:
            if verify_api_key(header_value, self.key_value):
                return True
        return False

    def _ensure_authorized__query_parameter(self):
        self.ensure_one()
        api_key = http.request.params.get('api_key', False)
        if api_key and verify_api_key(api_key, self.key_value):
            return True
        return False

    def ensure_authorized(self):
        self.ensure_one()
        if self._ensure_authorized__api_key():
            return True
        if self._ensure_authorized__query_parameter():
            return True

        return False
