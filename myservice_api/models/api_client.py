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
        help='API calls using this client run as this user, and every record '
             'they write carries it. Left blank on create, a dedicated user is '
             'provisioned for the client — never Administrator, or the audit '
             'trail cannot tell one client from another.',
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

    # ── The client's own identity ─────────────────────────────────────

    CLIENT_USER_LOGIN_PREFIX = 'cadra_client_'

    @api.model
    def _provision_client_user(self, client_id, name=None, scopes=None):
        """Create — or re-sync the groups of — one client's dedicated user.

        Every client was provisioned pointing at `base.user_admin`, so every
        row the API has ever written says `Administrator`: the client that
        creates an asset and the Tag-Issuing Unit that certifies its label
        were indistinguishable in the record. Scope separation is what stops
        one credential doing both; naming the actor is what makes the result
        evidence. Half a control is not a control.

        The user cannot log in. No password is ever set, so
        `_check_credentials` fails for the Odoo web client and for
        `POST /auth/login` alike — the client's credential stays the
        client_id/secret pair, checked by `/auth/token`. It stays `active`
        because `verify_and_rotate` revokes the whole token family of an
        inactive user.
        """
        from ..controllers.utils import groups_for_scopes

        login = f'{self.CLIENT_USER_LOGIN_PREFIX}{client_id}'
        groups = groups_for_scopes(self.env, (scopes or '').split())
        # Odoo 19 renamed res.users.groups_id -> group_ids; the 15 stack is
        # still in production, so accept both rather than pinning a version.
        Users = self.env['res.users'].sudo().with_context(
            # A reset-password mail for a login that can never be used would
            # be noise at best, and on a tenant with a real mail server it
            # would be an email to nobody.
            no_reset_password=True,
        )
        groups_field = 'group_ids' if 'group_ids' in Users._fields else 'groups_id'

        user = Users.with_context(active_test=False).search(
            [('login', '=', login)], limit=1)
        if user:
            user.write({groups_field: [(6, 0, groups.ids)], 'active': True})
            return user
        # `password` is left OUT of the vals, not set to False. `res.users`
        # gives the field an inverse that hashes whatever it is handed, and
        # passlib refuses a bool — `TypeError: secret must be unicode or
        # bytes, not bool`. Omitting it leaves the column null, which is the
        # state that makes `_check_credentials` fail: the user has no
        # password rather than an unguessable one.
        return Users.create({
            'name': f'{name or client_id} (API client)',
            'login': login,
            groups_field: [(6, 0, groups.ids)],
        })

    def action_provision_user(self):
        """Re-home an existing client onto its own user (form button)."""
        for record in self:
            record.user_id = record._provision_client_user(
                record.client_id, record.name, record.scopes)
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('client_id'):
                vals['client_id'] = 'cli_' + secrets.token_urlsafe(18)
            # `user_id` stays required — a client with no identity is what
            # this change exists to stop — but the caller no longer has to
            # supply one, because the only thing every caller ever supplied
            # was `base.user_admin`.
            if not vals.get('user_id'):
                vals['user_id'] = self._provision_client_user(
                    vals['client_id'], vals.get('name'), vals.get('scopes')).id
        return super().create(vals_list)

    def set_client_secret(self, raw_secret):
        self.ensure_one()
        self.client_secret_hash = generate_password_hash(raw_secret)

    def check_client_secret(self, raw_secret):
        self.ensure_one()
        if not self.client_secret_hash:
            return False
        return check_password_hash(self.client_secret_hash, raw_secret)

    def write(self, vals):
        """Keep a client user's groups honest when its scopes move.

        Narrowing a client's scopes and leaving its user in the group the old
        scope justified would leave a widened identity behind a narrowed
        token — the drift that makes a group listing stop meaning anything.
        Only clients on their OWN user are re-synced: one deliberately
        pointed at a shared or hand-built user is an operator's decision, and
        rewriting that person's groups from a scope string would be an
        escalation nobody asked for.
        """
        result = super().write(vals)
        if 'scopes' in vals:
            prefix = self.CLIENT_USER_LOGIN_PREFIX
            for record in self:
                login = f'{prefix}{record.client_id}'
                if record.user_id.sudo().login == login:
                    record._provision_client_user(
                        record.client_id, record.name, record.scopes)
        return result

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
