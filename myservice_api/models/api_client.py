import secrets

from odoo import api, fields, models
from werkzeug.security import check_password_hash, generate_password_hash


class MyserviceApiClient(models.Model):
    _name = 'myservice.api.client'
    _description = 'myservice API Client'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    client_id = fields.Char(required=True, index=True, copy=False)
    client_secret_hash = fields.Char(string='Client Secret Hash', copy=False)

    user_id = fields.Many2one(
        'res.users',
        string='Run As User',
        required=True,
        help='API calls using this client will run with this user and its permissions.',
    )

    scopes = fields.Char(
        help="Space-separated scopes, e.g. 'dashboard security osint assets'. Leave empty to allow all.")

    token_ttl_seconds = fields.Integer(default=3600)

    last_used_at = fields.Datetime(readonly=True)
    last_used_ip = fields.Char(readonly=True)

    @api.model
    def create(self, vals):
        if not vals.get('client_id'):
            vals['client_id'] = 'cli_' + secrets.token_urlsafe(18)
        return super().create(vals)

    def set_client_secret(self, raw_secret):
        self.ensure_one()
        self.client_secret_hash = generate_password_hash(raw_secret)

    def check_client_secret(self, raw_secret):
        self.ensure_one()
        if not self.client_secret_hash:
            return False
        return check_password_hash(self.client_secret_hash, raw_secret)

    def rotate_secret(self):
        self.ensure_one()
        raw = secrets.token_urlsafe(40)
        self.set_client_secret(raw)
        return raw

    def action_rotate_secret(self):
        self.ensure_one()
        raw = self.rotate_secret()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Client secret rotated',
                'message': f"New secret (copy now): {raw}",
                'sticky': True,
                'type': 'warning',
            }
        }
