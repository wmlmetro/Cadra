"""
Cadra API shared utilities — envelope, JWT, scopes, idempotency, request-id.

This module is imported by every Cadra controller. The intent is that the
controller layer stays thin: parse request -> call a service function ->
serialize via these helpers. Nothing here should reach into Odoo internals
that aren't documented; the goal is portability to a non-Odoo runtime later.
"""
import base64
import functools
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid

from odoo import fields
from odoo.http import request

_logger = logging.getLogger(__name__)

API_VERSION = "v1"


# ─── envelope ────────────────────────────────────────────────────────

def _meta():
    """Common `meta` block on every success response (PRD §10.7)."""
    return {
        "request_id": getattr(request, "cadra_request_id", None) or _new_request_id(),
        "timestamp": fields.Datetime.now().isoformat(),
        "version": API_VERSION,
    }


def ok(data=None, pagination=None):
    """Wrap a successful response in the PRD envelope.

    Use as the sole return value of a JSON endpoint:
        return ok({"id": 42, "name": "..."})

    For list endpoints, pass `pagination`:
        return ok(items, pagination={"next_cursor": "...", "total_estimate": 1200})
    """
    body = {"data": data, "meta": _meta()}
    if pagination is not None:
        body["pagination"] = pagination
    return body


def err(code, message, *, status=400, details=None):
    """Wrap an error response in the PRD envelope.

    Codes are stable, lowercase_snake strings. Reuse existing codes where
    possible (see ERR_*); only add new codes when no existing one fits.

    `status` is an HTTP-style code the caller can use to set the response
    status — Odoo's JSON-RPC layer always returns 200, so we surface the
    intended status inside the error object too (under `details.http_status`)
    for clients that want to act on it.
    """
    body = {
        "error": {
            "code": code,
            "message": message,
            "request_id": _meta()["request_id"],
        }
    }
    extras = dict(details or {})
    extras["http_status"] = status
    body["error"]["details"] = extras
    return body


# Canonical error codes — keep this list short and reuse before adding.
ERR_UNAUTHORIZED         = "unauthorized"
ERR_FORBIDDEN            = "forbidden"
ERR_INVALID_REQUEST      = "invalid_request"
ERR_VALIDATION_FAILED    = "validation_failed"
ERR_NOT_FOUND            = "not_found"
ERR_CONFLICT             = "conflict"
ERR_RATE_LIMITED         = "rate_limited"
ERR_INTERNAL             = "internal_error"
ERR_NOT_IMPLEMENTED      = "not_implemented"
ERR_IDEMPOTENCY_MISMATCH = "idempotency_mismatch"
ERR_MISCONFIGURED        = "server_misconfigured"


# ─── request id ──────────────────────────────────────────────────────

def _new_request_id():
    """Mint or recover the per-request correlation id.

    Pulls from `X-Request-Id` if the client sent one; otherwise generates a
    fresh UUID. Stored on `request.cadra_request_id` so subsequent helpers
    (logging, envelope) all see the same value.
    """
    if not hasattr(request, "cadra_request_id") or not request.cadra_request_id:
        inbound = (request.httprequest.headers.get("X-Request-Id") or "").strip()
        request.cadra_request_id = inbound or uuid.uuid4().hex
    return request.cadra_request_id


# ─── scopes ──────────────────────────────────────────────────────────
#
# Match the resource tags in docs/cadra-api-docs.html. Format is
# `<resource>:<action>` where action is one of read | write | admin.
# `*` is a wildcard reserved for trusted internal tooling.

SCOPE_ASSETS_READ        = "assets:read"
SCOPE_ASSETS_WRITE       = "assets:write"
SCOPE_LOCATIONS_READ     = "locations:read"
SCOPE_LOCATIONS_WRITE    = "locations:write"
SCOPE_REQUESTS_READ      = "requests:read"
SCOPE_REQUESTS_WRITE     = "requests:write"
SCOPE_APPROVALS_WRITE    = "approvals:write"
SCOPE_INGESTION_WRITE    = "ingestion:write"
SCOPE_INTEGRATIONS_WRITE = "integrations:write"
SCOPE_WEBHOOKS_ADMIN     = "webhooks:admin"
SCOPE_DASHBOARDS_READ    = "dashboards:read"
SCOPE_IDENTITY_READ      = "identity:read"
SCOPE_ADMIN              = "admin"

ALL_SCOPES = frozenset({
    SCOPE_ASSETS_READ, SCOPE_ASSETS_WRITE,
    SCOPE_LOCATIONS_READ, SCOPE_LOCATIONS_WRITE,
    SCOPE_REQUESTS_READ, SCOPE_REQUESTS_WRITE,
    SCOPE_APPROVALS_WRITE,
    SCOPE_INGESTION_WRITE,
    SCOPE_INTEGRATIONS_WRITE,
    SCOPE_WEBHOOKS_ADMIN,
    SCOPE_DASHBOARDS_READ,
    SCOPE_IDENTITY_READ,
    SCOPE_ADMIN,
})


# ─── JWT ─────────────────────────────────────────────────────────────

class JwtError(Exception):
    pass


class JwtSecretMissing(Exception):
    """Raised when the server has no JWT signing secret configured.

    Fail-closed: token mint and verify both refuse to operate rather than
    quietly using a placeholder secret. The previous code defaulted to
    "CHANGE_ME__..." which made forged tokens trivial in any deployment
    where the operator forgot to set the config parameter.
    """


_JWT_PLACEHOLDERS = frozenset({
    "", "CHANGE_ME__MYservice_API_JWT_SECRET", "CHANGE_ME", "changeme",
    "secret", "your-secret-here",
})


def jwt_secret(env):
    """Return the JWT signing secret, or raise JwtSecretMissing.

    Read from `myservice_api.jwt_secret` ir.config_parameter. Refuses to
    return a placeholder. Operators should set this to a 32+ char random
    string at deployment:
        odoo config:
          docker exec ... odoo shell:
            env['ir.config_parameter'].sudo().set_param(
                'myservice_api.jwt_secret', secrets.token_urlsafe(48))
    """
    value = env["ir.config_parameter"].sudo().get_param("myservice_api.jwt_secret", "")
    if not value or value in _JWT_PLACEHOLDERS or len(value) < 16:
        raise JwtSecretMissing(
            "myservice_api.jwt_secret is unset or too short. Set it to a "
            "32+ character random string before using the API."
        )
    return value


def _b64url_encode(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw):
    raw_bytes = raw.encode("ascii")
    padding = b"=" * (-len(raw_bytes) % 4)
    return base64.urlsafe_b64decode(raw_bytes + padding)


def jwt_encode(payload, secret):
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}"


def jwt_decode(token, secret):
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise JwtError("Malformed token")

    header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
    if header.get("alg") != "HS256":
        raise JwtError("Unsupported alg")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected, actual):
        raise JwtError("Bad signature")

    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    exp = payload.get("exp")
    if exp and int(exp) < int(time.time()):
        raise JwtError("Token expired")
    return payload


def _bearer_token():
    auth = request.httprequest.headers.get("Authorization", "")
    if not auth:
        return None
    parts = auth.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _set_request_user(uid):
    if hasattr(request, "update_env"):
        request.update_env(user=uid)
    else:
        # Fallback for older Odoo 15.x where update_env wasn't yet exposed.
        request._env = request.env(user=uid)


def require_jwt(scopes=()):
    """Validate the bearer token and apply scope check.

    Returns (claims_dict, None, None) on success.
    Returns (None, err_envelope, _) on failure — caller returns the envelope.
    """
    _new_request_id()  # ensure the id exists before any logging

    token = _bearer_token()
    if not token:
        return None, err(ERR_UNAUTHORIZED, "Missing bearer token", status=401), None

    try:
        secret = jwt_secret(request.env)
    except JwtSecretMissing as e:
        _logger.error("API misconfiguration: %s", e)
        return None, err(ERR_MISCONFIGURED, str(e), status=500), None

    try:
        claims = jwt_decode(token, secret)
    except JwtError:
        return None, err(ERR_UNAUTHORIZED, "Invalid token", status=401), None

    uid = claims.get("uid")
    if not uid:
        return None, err(ERR_UNAUTHORIZED, "Token missing subject", status=401), None

    token_scopes = claims.get("scopes") or []
    if isinstance(token_scopes, str):
        token_scopes = token_scopes.split()
    token_scopes = set(token_scopes)
    wildcard = SCOPE_ADMIN in token_scopes or "*" in token_scopes

    if scopes and not wildcard:
        missing = [s for s in scopes if s not in token_scopes]
        if missing:
            return None, err(
                ERR_FORBIDDEN,
                f"Missing required scope(s): {' '.join(missing)}",
                status=403,
                details={"required_scopes": list(scopes), "granted_scopes": sorted(token_scopes)},
            ), None

    _set_request_user(int(uid))
    request.jwt_claims = claims
    return claims, None, None


# ─── idempotency ─────────────────────────────────────────────────────

IDEMPOTENCY_HEADER = "X-Idempotency-Key"
IDEMPOTENCY_TTL_SECONDS = 24 * 3600


def idempotency_key():
    """Return the inbound Idempotency-Key, or None if absent.

    Empty strings and over-long keys are treated as absent. Keys are
    case-sensitive opaque tokens — typically UUIDs from the client.
    """
    raw = (request.httprequest.headers.get(IDEMPOTENCY_HEADER) or "").strip()
    if not raw or len(raw) > 128:
        return None
    return raw


def idempotency_check(key, endpoint_path):
    """Return a cached response body for (key, endpoint), or None.

    The caller is responsible for short-circuiting with the returned body.
    """
    if not key:
        return None
    rec = request.env["myservice.api.idempotency"].sudo().search(
        [("key", "=", key), ("endpoint", "=", endpoint_path)], limit=1
    )
    if not rec:
        return None
    if rec.expires_at and rec.expires_at < fields.Datetime.now():
        rec.unlink()
        return None
    try:
        return json.loads(rec.response_body)
    except Exception:
        return None


def idempotency_store(key, endpoint_path, body):
    """Persist the response body under (key, endpoint) for IDEMPOTENCY_TTL_SECONDS."""
    if not key:
        return
    now = fields.Datetime.now()
    request.env["myservice.api.idempotency"].sudo().create({
        "key": key,
        "endpoint": endpoint_path,
        "response_body": json.dumps(body, default=str),
        "expires_at": fields.Datetime.add(now, seconds=IDEMPOTENCY_TTL_SECONDS),
    })


# ─── endpoint decorator ──────────────────────────────────────────────

def cadra_endpoint(scopes=(), idempotent=False):
    """Decorator: scope-check + envelope-wrap + optional idempotency.

    Apply BELOW Odoo's @http.route decorator. The wrapped function should
    return either a plain dict (treated as the `data` payload) or a result
    of ok()/err() if it needs full control.

    Example:
        @http.route("/api/v1/assets/<id>", type="json", auth="none", methods=["GET"], csrf=False)
        @cadra_endpoint(scopes=[SCOPE_ASSETS_READ])
        def get_asset(self, id, **kw):
            asset = request.env["nrs.asset"].sudo().browse(id)
            if not asset.exists():
                return err(ERR_NOT_FOUND, f"Asset {id} not found", status=404)
            return {"id": asset.id, "tag": asset.asset_tag, "name": asset.name}
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            _new_request_id()

            # Auth + scope
            _, envelope, _ = require_jwt(scopes)
            if envelope is not None:
                return envelope

            # Idempotency (only for write methods — read methods are naturally
            # idempotent and don't need caching)
            method = request.httprequest.method.upper()
            is_write = method in ("POST", "PUT", "PATCH", "DELETE")
            ikey = idempotency_key() if (idempotent and is_write) else None
            endpoint_path = request.httprequest.path

            if ikey:
                cached = idempotency_check(ikey, endpoint_path)
                if cached is not None:
                    return cached

            # Call the endpoint
            try:
                result = fn(*args, **kwargs)
            except Exception:
                _logger.exception("Unhandled error in %s", endpoint_path)
                return err(ERR_INTERNAL, "Unhandled server error", status=500)

            # Auto-wrap plain dicts; pass through ok()/err() results unchanged
            if isinstance(result, dict) and ("data" in result or "error" in result):
                body = result
            else:
                body = ok(result)

            if ikey and "error" not in body:
                idempotency_store(ikey, endpoint_path, body)

            return body
        return wrapper
    return decorator
