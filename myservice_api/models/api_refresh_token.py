import hashlib
import secrets
from datetime import timedelta

from odoo import api, fields, models

# Default sliding-window lifetime. Each successful /auth/refresh rotates the
# token and resets this window, so an active session stays alive indefinitely
# while an idle one dies 30 days after its last use.
REFRESH_TOKEN_TTL_DAYS = 30


class MyserviceApiRefreshToken(models.Model):
    """Opaque, rotating, revocable refresh token (RFC 6749 §1.5 / §6).

    Unlike the access JWT (stateless, ~1h, unrevocable), refresh tokens are
    server-side state: we store only the SHA-256 of the raw token, so a DB
    leak never exposes a usable credential. Each refresh rotates the token
    (the presented one is revoked, a successor is issued in the same family).
    Presenting an already-rotated token signals theft and revokes the whole
    family — RFC 6819 §5.2.2.3 refresh-token rotation with reuse detection.
    """

    _name = "myservice.api.refresh_token"
    _description = "Cadra API Refresh Token"
    _order = "create_date desc"

    # SHA-256 hex of the raw token. The raw value is returned to the caller
    # once at issue time and never persisted.
    token_hash = fields.Char(required=True, index=True, copy=False)
    token_prefix = fields.Char(help="First chars of the raw token — log correlation only, not a secret.")

    user_id = fields.Many2one(
        "res.users", string="User", required=True, ondelete="cascade", index=True,
        help="The account access tokens minted from this refresh token run as.")
    client_id = fields.Many2one(
        "myservice.api.client", string="API Client", ondelete="cascade", index=True,
        help="Set for the client-credentials grant (/auth/token); empty for the user login grant (/auth/login).")

    scopes = fields.Char(help="Space-separated scopes captured when the token was first issued.")
    aud = fields.Char(string="Audience", help="Audience claim stamped on access tokens from this family (e.g. 'frontend').")

    # All tokens rotated from one login/exchange share a family id. Reuse of a
    # rotated member revokes every live token in the family.
    family_id = fields.Char(required=True, index=True, copy=False)

    expires_at = fields.Datetime(required=True, index=True)
    revoked = fields.Boolean(default=False, index=True)
    revoked_reason = fields.Char(help="rotated | reuse_detected | logout | user_disabled | client_disabled")

    replaced_by_id = fields.Many2one(
        "myservice.api.refresh_token", string="Rotated Into", ondelete="set null")

    last_used_at = fields.Datetime(readonly=True)
    last_used_ip = fields.Char(readonly=True)

    @staticmethod
    def _hash(raw):
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @api.model
    def _issue(self, *, user, scopes, aud=None, client=None, family_id=None,
               ttl_days=REFRESH_TOKEN_TTL_DAYS, ip=None):
        """Mint a new opaque refresh token. Returns (record, raw_token).

        Pass family_id to extend an existing rotation chain; omit it to start
        a fresh family (a brand-new login / credential exchange).
        """
        raw = secrets.token_urlsafe(40)
        if isinstance(scopes, (list, tuple)):
            scopes = " ".join(scopes)
        rec = self.sudo().create({
            "token_hash": self._hash(raw),
            "token_prefix": raw[:8],
            "user_id": user.id,
            "client_id": client.id if client else False,
            "scopes": scopes or "",
            "aud": aud or False,
            "family_id": family_id or secrets.token_urlsafe(16),
            "expires_at": fields.Datetime.now() + timedelta(days=ttl_days),
            "last_used_ip": ip or False,
        })
        return rec, raw

    @api.model
    def _revoke_family(self, family_id, reason):
        self.sudo().search([
            ("family_id", "=", family_id),
            ("revoked", "=", False),
        ]).write({"revoked": True, "revoked_reason": reason})

    @api.model
    def verify_and_rotate(self, raw, *, ip=None, ttl_days=REFRESH_TOKEN_TTL_DAYS):
        """Validate a presented refresh token and rotate it.

        Returns (payload, None) on success where payload is a dict:
            {user, scopes (list), aud, client, new_raw, new_record}
        Returns (None, error_code) on failure. error_code is one of:
            missing | invalid | revoked | expired | user_disabled | client_disabled
        Callers should map every failure onto a single generic 401 so they
        don't leak which check failed.
        """
        if not raw:
            return None, "missing"

        rec = self.sudo().search([("token_hash", "=", self._hash(raw))], limit=1)
        if not rec:
            return None, "invalid"

        # Reuse of an already-rotated token => the family is compromised.
        if rec.revoked:
            if rec.revoked_reason == "rotated":
                self._revoke_family(rec.family_id, "reuse_detected")
            return None, "revoked"

        if rec.expires_at and rec.expires_at < fields.Datetime.now():
            return None, "expired"

        user = rec.user_id
        if not user.exists() or not user.active:
            self._revoke_family(rec.family_id, "user_disabled")
            return None, "user_disabled"

        client = rec.client_id if rec.client_id else None
        if client and not client.active:
            self._revoke_family(rec.family_id, "client_disabled")
            return None, "client_disabled"

        scopes = (rec.scopes or "").split() or ["*"]

        # Rotate: issue a successor in the same family, then revoke this one.
        new_rec, new_raw = self._issue(
            user=user, scopes=scopes, aud=rec.aud or None, client=client,
            family_id=rec.family_id, ttl_days=ttl_days, ip=ip,
        )
        rec.write({
            "revoked": True,
            "revoked_reason": "rotated",
            "replaced_by_id": new_rec.id,
            "last_used_at": fields.Datetime.now(),
            "last_used_ip": ip or rec.last_used_ip,
        })

        return {
            "user": user,
            "scopes": scopes,
            "aud": rec.aud or None,
            "client": client,
            "new_raw": new_raw,
            "new_record": new_rec,
        }, None

    @api.model
    def revoke(self, raw, *, reason="logout"):
        """Revoke the whole family a presented refresh token belongs to.

        Idempotent: an unknown token is a no-op. Returns True if a matching
        token was found (regardless of prior state), False otherwise. Callers
        should respond 200 either way so they don't reveal token existence.
        """
        if not raw:
            return False
        rec = self.sudo().search([("token_hash", "=", self._hash(raw))], limit=1)
        if not rec:
            return False
        self._revoke_family(rec.family_id, reason)
        return True

    @api.model
    def _gc(self, keep_revoked_days=7):
        """Purge dead rows so the table doesn't grow without bound.

        Deletes anything already expired, plus revoked tokens older than
        keep_revoked_days (kept briefly so reuse-detection can still fire on a
        just-rotated token). Wired to a daily ir.cron.
        """
        now = fields.Datetime.now()
        cutoff = now - timedelta(days=keep_revoked_days)
        stale = self.sudo().search([
            "|",
            ("expires_at", "<", now),
            "&", ("revoked", "=", True), ("write_date", "<", cutoff),
        ])
        count = len(stale)
        stale.unlink()
        return count
