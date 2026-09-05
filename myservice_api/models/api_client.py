import secrets

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from werkzeug.security import check_password_hash, generate_password_hash


class MyserviceApiClient(models.Model):
    _name = 'myservice.api.client'
    _description = 'myservice API Client'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    client_id = fields.Char(
        required=True, index=True, copy=False,
        default=lambda self: 'cli_' + secrets.token_urlsafe(18),
    )
    client_secret_hash = fields.Char(string='Client Secret Hash', copy=False)

    user_id = fields.Many2one(
        'res.users',
        string='Run As User',
        required=True,
        help='API calls using this client will run with this user and its permissions.',
    )

    scopes = fields.Char(
        help="Space-separated scopes, e.g. 'assets:read assets:write'. "
             "LEAVING THIS EMPTY GRANTS NOTHING — the client will authenticate "
             "and then be refused by every scoped endpoint. Grant everything "
             "only by writing it out: 'admin' (or the literal '*').")

    @api.constrains('scopes')
    def _check_scopes_are_known(self):
        """Reject a scope name we do not recognise.

        Nothing validated this before, so `taging:write` was accepted, minted
        into a token, and produced a 403 on every call with no hint that the
        name was wrong — the caller could not tell a typo from a permission
        decision. That is the silent-degradation rule, and it bites hardest
        exactly where scopes are handed to a third party such as the
        Tag-Issuing Unit.
        """
        from ..controllers.utils import ALL_SCOPES
        for record in self:
            unknown = sorted(
                {s for s in (record.scopes or "").split()} - ALL_SCOPES - {"*"}
            )
            if unknown:
                raise ValidationError(_(
                    "Unknown API scope(s): %(unknown)s\n\nValid scopes are: "
                    "%(valid)s"
                ) % {"unknown": " ".join(unknown),
                     "valid": " ".join(sorted(ALL_SCOPES))})

    token_ttl_seconds = fields.Integer(default=3600)

    last_used_at = fields.Datetime(readonly=True)
    last_used_ip = fields.Char(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('client_id'):
                vals['client_id'] = 'cli_' + secrets.token_urlsafe(18)
        return super().create(vals_list)

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
