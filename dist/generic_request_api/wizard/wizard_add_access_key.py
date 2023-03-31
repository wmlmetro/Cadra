import logging
import secrets

from odoo import models, fields, _
from odoo.exceptions import AccessError

from ..constants import API_KEY_SIZE, KEY_CRYPT_CONTEXT

_logger = logging.getLogger(__name__)

hash_api_key = (
    getattr(KEY_CRYPT_CONTEXT, 'hash', None) or KEY_CRYPT_CONTEXT.encrypt
)


class RequestApiWizardAddAccessKey(models.TransientModel):
    _name = 'request.api.wizard.add.access.key'
    _description = 'Request Api Wizard Add Access Key'

    name = fields.Char(required=True)
    api_endpoint_id = fields.Many2one(
        'request.api.endpoint', required=True, readonly=True)

    # API Key field
    use_sudo = fields.Boolean()
    sudo_user_id = fields.Many2one('res.users')

    def _generate(self, name, api_endpoint_id, use_sudo, sudo_user_id):
        k = secrets.token_hex(API_KEY_SIZE)
        vals = {
            'name': name,
            'api_endpoint_id': api_endpoint_id.id,
            'key_value': hash_api_key(k),
            'use_sudo': use_sudo,
        }
        if sudo_user_id:
            vals.update({'sudo_user_id': sudo_user_id.id})

        self.env['request.api.key'].create(vals)

        _logger.info(
            "API key generated: for '%s' (#%s)",
            api_endpoint_id.name, api_endpoint_id.id)

        return k

    def do_generate_and_add_access_key(self):
        self.ensure_one()
        # only create keys for users who can delete their keys
        if not self.user_has_groups('base.group_user'):
            raise AccessError(_("Only internal users can create API keys"))
        wizard = self.sudo()

        k = self.env['request.api.wizard.add.access.key']._generate(
            self.name,
            self.api_endpoint_id,
            self.use_sudo,
            self.sudo_user_id)
        wizard.unlink()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'request.api.wizard.add.access.key.show',
            'name': 'Endpoint API Key Ready',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_key': k,
            }
        }


class EndpointAPIKeyShow(models.TransientModel):
    _name = _description = 'request.api.wizard.add.access.key.show'

    # We add store=False for security reasons
    # so that the key is not stored anywhere
    key = fields.Char(readonly=True, store=False)
