import logging
import secrets

from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError
from werkzeug.security import check_password_hash, generate_password_hash

_logger = logging.getLogger(__name__)


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

    # ── Pagination limits ─────────────────────────────────────────────
    #
    # The external caps in `controllers/utils.py` used to key off the `aud`
    # claim, which only POST /auth/login stamps — so the rule in force was
    # "browsers are trusted, programs are not" when the rule intended was
    # "our own systems are trusted, third parties are not". Vendra holds a
    # machine credential; so will Audit. The paywall was pointed at our own
    # customer.
    #
    # 0 keeps today's behaviour exactly, so this is invisible until somebody
    # deliberately raises a limit on one client.

    is_test_credential = fields.Boolean(
        string='Test Credential', default=False,
        help="Records written under this credential are TEST ARTEFACTS and "
             "are labelled as such where the record is audit-grade. Set on "
             "the smoke-test client that bootstrap provisions; leave off for "
             "every credential a real system authenticates with.")

    max_page_limit = fields.Integer(
        default=0,
        help="Most records this client may pull in ONE page. "
             "0 = the external default (100). -1 = uncapped. "
             "Capped in all cases by the server's own per-request ceiling.")

    total_record_cap = fields.Integer(
        default=0,
        help="Most records of any one resource this client may see across "
             "all cursor pages — the paywall safeguard. "
             "0 = the external default (100). -1 = uncapped.")

    @api.constrains('max_page_limit', 'total_record_cap')
    def _check_limits_are_sane(self):
        """Only 0, -1 and positive integers mean anything.

        A -2 typed into the form would fall through every branch in
        `record_cap()` and land on the external default — a limit that
        silently does not do what it says, which is the defect this whole
        change exists to remove.
        """
        for record in self:
            for field_name in ('max_page_limit', 'total_record_cap'):
                value = record[field_name]
                if value < -1:
                    raise ValidationError(_(
                        "%(field)s must be 0 (use the external default), "
                        "-1 (uncapped) or a positive number. Got %(value)s."
                    ) % {"field": field_name, "value": value})

    #: A client whose pagination limits differ from the default may not hold
    #: an access token for longer than this.
    NON_DEFAULT_LIMIT_TTL_CEILING = 3600

    @api.constrains('token_ttl_seconds', 'max_page_limit', 'total_record_cap')
    def _check_a_raised_limit_cannot_outlive_its_decision(self):
        """Bound the window in which a withdrawn limit is still in force.

        Reducing a limit revokes the client's refresh families (handoff 13
        B1), so the family stops re-minting under the old ceiling at once.
        What that does NOT close is the access token already in the caller's
        hand: the cap is stamped into the JWT as a claim, and an access token
        is unrevocable for its lifetime by design. So the raised limit
        survives exactly as long as the TTL — a raised limit that outlives
        the decision to lower it again.

        The window cannot be removed; it can be bounded. One hour is what
        every client on every tenant already carries, so this changes nothing
        today; the 86400 a client CAN be configured with is the indefensible
        case, and it is now unreachable.

        `-1` (uncapped) is a non-default limit like any other — a credential
        granted an unbounded view of the register on a token nobody can call
        back for a day is the worst instance of this, not an exemption from
        it. `0` on BOTH fields is the external default and is untouched: the
        ceiling exists to bound a decision, and no decision has been made.

        The rule bites on whichever field is written last, which is why all
        three are in the trigger list — raising the TTL first and the limit
        afterwards must be refused just as surely as the other order.
        """
        for record in self:
            defaulted = (record.max_page_limit == 0
                         and record.total_record_cap == 0)
            if defaulted:
                continue
            if record.token_ttl_seconds <= self.NON_DEFAULT_LIMIT_TTL_CEILING:
                continue
            raise ValidationError(_(
                "A client whose pagination limits differ from the default "
                "may not hold a token for longer than %(ceiling)s seconds. "
                "%(client)s asks for %(ttl)s, with max_page_limit "
                "%(page)s and total_record_cap %(cap)s (0 = the external "
                "default, -1 = uncapped).\n\n"
                "The cap is stamped into the access JWT as a claim and an "
                "access token cannot be revoked before it expires, so a "
                "token minted under a raised limit keeps that limit for its "
                "whole life: a raised limit that outlives the decision to "
                "lower it again. Reducing the limit already revokes this "
                "client's refresh families; bounding the TTL bounds what is "
                "left.\n\n"
                "Either lower %(field)s to %(ceiling)s or below, or return "
                "both limits to 0."
            ) % {"ceiling": self.NON_DEFAULT_LIMIT_TTL_CEILING,
                 "client": record.client_id or record.name or _("This client"),
                 "ttl": record.token_ttl_seconds,
                 "page": record.max_page_limit,
                 "cap": record.total_record_cap,
                 "field": "token_ttl_seconds"})

    last_used_at = fields.Datetime(readonly=True)
    last_used_ip = fields.Char(readonly=True)

    # ── The client's own identity ─────────────────────────────────────

    CLIENT_USER_LOGIN_PREFIX = 'cadra_client_'

    @api.model
    @tools.ormcache('user_id')
    def _is_test_credential_user(self, user_id):
        """Is this the Odoo user behind a credential flagged as a test one?

        The canonical reader, and it sits on the model that OWNS the column
        rather than on one of its consumers. It used to live on
        `nrs.asset.custody`, which was fine while custody was the only thing
        asking; handoff 26 added `cadra.test.fixture.mixin`, and two copies
        of a safety derivation is how the two answers start disagreeing.
        `nrs.asset.custody._is_test_credential_user` now delegates here and
        keeps its name, because `scripts/` and the docs cite it.

        Cached on the user id because the mixin's `create` calls it once per
        batch and custody's `_record` calls it once per ROW — ten thousand of
        them on a bulk import with custodians. The answer depends only on the
        user and on a field an administrator changes about once, so the cache
        is invalidated by writes to this model (`create`, `write`, `unlink`
        all call `registry.clear_cache()`) rather than by time.

        `active_test=False`: an archived credential's artefacts are still
        artefacts. `Handoff23 Approver` is archived on `jaizbankplc`, and a
        plain `search` is what made `scripts/mark_test_fixtures.py` report a
        clean run while doing nothing.
        """
        if not user_id:
            return False
        return bool(self.sudo().with_context(active_test=False).search_count([
            ('user_id', '=', user_id),
            ('is_test_credential', '=', True),
        ]))

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
        records = super().create(vals_list)
        # `nrs.asset.custody._is_test_credential_user` is ormcached on the
        # user id, because it runs once per custody link and a bulk import
        # would otherwise issue one query per row. A new client can change
        # that answer, so the cache goes with it.
        self.env.registry.clear_cache()
        return records

    def unlink(self):
        # Same cache as create/write. A stale entry here would keep saying
        # "test credential" for a user whose credential is gone, which
        # mislabels a real change of custodian in a record that refuses
        # correction by design.
        result = super().unlink()
        self.env.registry.clear_cache()
        return result

    def set_client_secret(self, raw_secret):
        self.ensure_one()
        self.client_secret_hash = generate_password_hash(raw_secret)

    def check_client_secret(self, raw_secret):
        self.ensure_one()
        if not self.client_secret_hash:
            return False
        return check_password_hash(self.client_secret_hash, raw_secret)

    #: Changing either of these invalidates every token already minted for
    #: this client — the cap is stamped into the access JWT as a claim.
    LIMIT_FIELDS = ('max_page_limit', 'total_record_cap')

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
        # Snapshot BEFORE the write: a limit that is set to the value it
        # already had must not revoke anything. Saving the form is not an
        # administrative decision.
        moved = [name for name in self.LIMIT_FIELDS if name in vals]
        previous = ({record.id: {name: record[name] for name in moved}
                     for record in self} if moved else {})

        result = super().write(vals)

        # See `create`: the custody provenance lookup is ormcached on the
        # user id, and `is_test_credential` or `user_id` moving changes it.
        # Cleared unconditionally rather than on those two keys — a client
        # write is rare, and a cache that is only sometimes invalidated is
        # the harder thing to reason about.
        self.env.registry.clear_cache()

        if moved:
            changed = self.filtered(
                lambda r: any(r[name] != previous[r.id][name] for name in moved))
            if changed:
                # The access JWT carries the cap as a claim and is
                # unrevocable for its TTL; the refresh FAMILY is the part
                # that would otherwise go on re-minting under the old
                # ceiling for a 30-day sliding window. /auth/refresh already
                # re-reads the limits off this record, so this closes the
                # remaining case: a caller that never refreshes and simply
                # keeps its family alive.
                revoked = self.env['myservice.api.refresh_token'].sudo(
                )._revoke_client_families(changed, 'limits_changed')
                _logger.info(
                    "api client limits changed on %s; revoked %d refresh "
                    "token(s)", ", ".join(changed.mapped('client_id')), revoked)

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
