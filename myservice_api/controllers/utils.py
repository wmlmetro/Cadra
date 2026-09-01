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
import time
import uuid

import psycopg2
import requests

from odoo import fields
from odoo.exceptions import (
    AccessError,
    MissingError,
    UserError,
    ValidationError,
)
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


# ─── Cloudflare Turnstile ────────────────────────────────────────────

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_TIMEOUT = 5


def turnstile_secret(env):
    """Return the Turnstile secret key, or "" when protection is off.

    Read from the `myservice_api.turnstile_secret` ir.config_parameter,
    which bootstrap seeds from the CADRA_TURNSTILE_SECRET env var. Empty
    is a valid, deliberate state: it means this tenant has no Turnstile
    site configured and the challenge is skipped entirely. That is the
    default, and it is how every tenant provisioned before this feature
    keeps logging in.
    """
    return (env["ir.config_parameter"].sudo().get_param(
        "myservice_api.turnstile_secret", "") or "").strip()


def turnstile_error(env, token):
    """Verify a Turnstile response token; return an error envelope or None.

    Returns None when the challenge passes *or* when Turnstile is not
    configured — so callers can gate an endpoint with two lines and the
    unprotected path stays the no-op it was before.
    """
    secret = turnstile_secret(env)
    if not secret:
        return None

    if not token:
        return err(ERR_INVALID_REQUEST, "`turnstile_token` is required")

    try:
        # `remoteip` is deliberately omitted. It is optional, and behind the
        # cluster ingress (Cloudflare → load balancer → ingress → Odoo)
        # proxy_mode's ProxyFix only unwinds one hop, so the address we see
        # is a proxy's rather than the visitor's. Sending a mismatched IP
        # makes Cloudflare reject an otherwise valid token; the token is
        # already bound to the sitekey and single-use without it.
        response = requests.post(
            TURNSTILE_VERIFY_URL,
            data={"secret": secret, "response": token},
            timeout=TURNSTILE_TIMEOUT,
        )
        body = response.json()
    except Exception as e:
        # Cloudflare unreachable or answering with something that isn't
        # JSON. Fail closed — an open failure mode would let anyone turn
        # the challenge off by making siteverify time out.
        _logger.warning("Turnstile siteverify call failed: %s", e)
        return err(ERR_INTERNAL, "Could not verify the Turnstile challenge",
                   status=502)

    if not body.get("success"):
        # Cloudflare's error-codes distinguish a stale token from a bad
        # secret key — useful in the log, not something to hand a caller
        # who may be probing for a misconfiguration.
        _logger.info("Turnstile rejected a challenge: %s",
                     body.get("error-codes") or "no error-codes returned")
        return err(ERR_INVALID_REQUEST, "Turnstile verification failed")

    return None


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
    except (AttributeError, ValueError):
        raise JwtError("Malformed token")

    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        if header.get("alg") != "HS256":
            raise JwtError("Unsupported alg")

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected, actual):
            raise JwtError("Bad signature")

        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except JwtError:
        raise
    except Exception:
        # Catch base64 padding errors, JSON decode errors, unicode errors —
        # anything that signals "this is not a well-formed JWT". Maps them
        # all onto JwtError so require_jwt returns 401 instead of 500.
        raise JwtError("Malformed token")

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
    except JwtError as e:
        _logger.info(
            "JWT rejected (%s) — token_prefix=%r token_len=%d dots=%d",
            e, token[:24], len(token), token.count("."),
        )
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

# ─── cursor pagination ───────────────────────────────────────────────

DEFAULT_PAGE_LIMIT = 50
# Lifted from 200 → 2000 so the frontend can pull resources that have to be
# eager-loaded (Locations, ~1.2k rows, used to build the tree + zone lookups)
# in a single round-trip. The list endpoints don't fan out N+1 work, so a
# bigger page is just a longer SELECT, not a longer wall-clock per record.
# External tokens are still clamped to EXTERNAL_MAX_PAGE_LIMIT (100) below.
MAX_PAGE_LIMIT = 2000
# Hard caps for tokens NOT issued to the Cadra web frontend (service
# accounts via POST /auth/token, partner integrations, ad-hoc curl).
#   - EXTERNAL_MAX_PAGE_LIMIT clamps the per-request `limit=` query param
#     (parse_limit). Asking for more silently returns this many.
#   - EXTERNAL_TOTAL_CAP clamps the *cumulative* records visible across
#     all cursor pages (paginate). External callers can never see more
#     than this many records of any resource — paginating with cursor
#     just exhausts the cap and then next_cursor goes to null. This is
#     the paywall safeguard.
# The Cadra web frontend lifts both limits by carrying `"aud": "frontend"`
# in its JWT claims (stamped by POST /auth/login at issuance time).
EXTERNAL_MAX_PAGE_LIMIT = 100
EXTERNAL_TOTAL_CAP      = 100
FRONTEND_AUDIENCE       = "frontend"


def encode_cursor(payload):
    """Opaque base64url JSON cursor. Don't decode on the client side —
    treat as an opaque token."""
    return _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))


def decode_cursor(token):
    """Decode a cursor token, returning the payload dict. Returns {} on
    invalid input rather than raising — callers treat empty as 'start
    from beginning'."""
    if not token:
        return {}
    try:
        return json.loads(_b64url_decode(token).decode("utf-8"))
    except Exception:
        return {}


def _request_is_frontend():
    """True when the validated JWT claims identify the Cadra web frontend
    (i.e. issued via POST /auth/login with `aud=frontend`). False for
    service accounts, external integrations, or when the auth layer
    didn't run (e.g. open endpoints that don't gate on token claims)."""
    claims = getattr(request, "jwt_claims", None) or {}
    return claims.get("aud") == FRONTEND_AUDIENCE


def parse_limit(kwargs):
    """Read and clamp `limit` from kwargs. Default DEFAULT_PAGE_LIMIT;
    cap at MAX_PAGE_LIMIT for the Cadra web frontend and at
    EXTERNAL_MAX_PAGE_LIMIT for everyone else.

    External callers (service accounts, partner integrations, ad-hoc curl)
    therefore can never pull more than EXTERNAL_MAX_PAGE_LIMIT records per
    page — they can still paginate via `cursor` if they need the rest.
    """
    raw = kwargs.get("limit", DEFAULT_PAGE_LIMIT)
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        limit = DEFAULT_PAGE_LIMIT
    ceiling = MAX_PAGE_LIMIT if _request_is_frontend() else EXTERNAL_MAX_PAGE_LIMIT
    return max(1, min(limit, ceiling))


def paginate(model, domain, *, limit, cursor=None, order="id"):
    """Cursor-paginate `model.search(domain)`.

    Returns (records, next_cursor_or_None, total_estimate).
    `total_estimate` is a separate search_count — fine at our scale, but
    expensive on very large tables. Suppress it via `?total=0` from the
    caller if needed.

    External (non-frontend) tokens are bounded to the first
    EXTERNAL_TOTAL_CAP records of the domain (sorted by `order`).
    Pagination still works inside that window; once the cumulative
    records served exceed the cap, next_cursor goes to null and the
    total_estimate reflects the cap rather than the true count.
    """
    cursor_data = decode_cursor(cursor) if cursor else {}
    effective_domain = list(domain)

    # Compute the visible window for external tokens once, before any
    # cursor filtering. We do this even when the cursor is set so the
    # cap survives across pages.
    external_cap = None
    allowed_total = None
    if not _request_is_frontend():
        external_cap = EXTERNAL_TOTAL_CAP
        allowed = model.search(domain, order=order, limit=external_cap)
        allowed_total = len(allowed)
        if not allowed_total:
            return model.browse([]), None, 0
        effective_domain.append(("id", "in", allowed.ids))

    if "last_id" in cursor_data:
        effective_domain.append(("id", ">", int(cursor_data["last_id"])))

    # Fetch one extra to know if there's a next page
    records = model.search(effective_domain, order=order, limit=limit + 1)
    has_more = len(records) > limit
    page = records[:limit]

    next_cursor = None
    if has_more and page:
        next_cursor = encode_cursor({"last_id": page[-1].id})

    if external_cap is not None:
        total_estimate = allowed_total
    else:
        total_estimate = model.search_count(domain)
    return page, next_cursor, total_estimate


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


# ─── request param accessor ──────────────────────────────────────────

def get_params():
    """Return a dict of params for the current request body or query string.

    GET / DELETE / HEAD → query string (werkzeug MultiDict → plain dict;
                          values are strings, callers coerce types as needed)
    POST / PATCH / PUT  → parsed JSON body (flat, no `params` wrapper)

    Path parameters (e.g. <int:id>) are NOT in here — Odoo's router passes
    them as named method args. Use this helper for everything else.
    """
    method = request.httprequest.method.upper()
    if method in ("GET", "DELETE", "HEAD"):
        return dict(request.httprequest.args)
    # Try werkzeug's get_json first; fall back to manual JSON.loads on the
    # raw body. Odoo's HttpRequest sometimes consumes the body stream before
    # the controller runs, so we can't always rely on get_json() at the
    # werkzeug layer — use raw data as a safety net.
    try:
        body = request.httprequest.get_json(silent=True, force=True, cache=False)
    except Exception:
        body = None
    if not isinstance(body, dict):
        raw = request.httprequest.get_data(cache=True, as_text=False)
        if raw:
            try:
                body = json.loads(raw)
            except Exception:
                body = None
    return body if isinstance(body, dict) else {}


# ─── HTTP response helper ────────────────────────────────────────────

def _http_response(body, success_status=200):
    """Render the PRD envelope as a real HTTP response.

    Status code derivation:
      - if body has an `error` key, pull `error.details.http_status`
      - else, `success_status` (the @cadra_route default — usually 200,
        201 for resource-create POSTs without a path id)

    Note on Odoo 15 quirk: `request.make_response(data, headers, cookies)`
    does NOT accept a `status=` kwarg. We set the status on the returned
    werkzeug Response after construction.
    """
    if isinstance(body, dict) and "error" in body:
        status = body.get("error", {}).get("details", {}).get("http_status", 400)
    else:
        status = success_status
    response = request.make_response(
        json.dumps(body, default=str),
        headers=[("Content-Type", "application/json; charset=utf-8")],
    )
    response.status_code = status
    return response


# ─── endpoint decorator ──────────────────────────────────────────────

def cadra_endpoint(scopes=(), idempotent=False, success_status=200):
    """Auth + scope-check + idempotency + envelope-wrap + JSON HTTP response.

    Apply BELOW Odoo's @http.route decorator (or use the `cadra_route`
    convenience wrapper in v1.py which does both). The wrapped function
    returns one of:
      - a plain dict  → wrapped via ok() as the `data` payload
      - a plain list  → wrapped via ok() as the `data` payload
      - a result of ok()/err() → passed through unchanged

    The wrapper turns that into a real HTTP response with Content-Type:
    application/json and the right status code.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            _new_request_id()

            # Auth + scope
            _, envelope, _ = require_jwt(scopes)
            if envelope is not None:
                return _http_response(envelope)

            # Idempotency (only for write methods — read methods are naturally
            # idempotent and don't need caching)
            method = request.httprequest.method.upper()
            is_write = method in ("POST", "PUT", "PATCH", "DELETE")
            ikey = idempotency_key() if (idempotent and is_write) else None
            endpoint_path = request.httprequest.path

            if ikey:
                cached = idempotency_check(ikey, endpoint_path)
                if cached is not None:
                    return _http_response(cached, success_status=success_status)

            # Call the endpoint
            try:
                result = fn(*args, **kwargs)
            except (UserError, ValidationError) as e:
                # Odoo-level validation: ondelete, @api.constrains,
                # explicit raise UserError in business code.
                request.env.cr.rollback()
                return _http_response(err(
                    ERR_VALIDATION_FAILED, str(e) or e.__class__.__name__,
                    status=400,
                ))
            except MissingError as e:
                request.env.cr.rollback()
                return _http_response(err(ERR_NOT_FOUND, str(e), status=404))
            except AccessError as e:
                request.env.cr.rollback()
                return _http_response(err(ERR_FORBIDDEN, str(e), status=403))
            except psycopg2.errors.UniqueViolation as e:
                request.env.cr.rollback()
                return _http_response(err(
                    ERR_CONFLICT, "Unique constraint violation",
                    status=409,
                    details={"db_detail": (e.diag.message_detail or "").strip() or None,
                             "constraint": e.diag.constraint_name},
                ))
            except psycopg2.errors.ForeignKeyViolation as e:
                request.env.cr.rollback()
                return _http_response(err(
                    ERR_VALIDATION_FAILED,
                    "Referenced record does not exist",
                    status=400,
                    details={"db_detail": (e.diag.message_detail or "").strip() or None,
                             "constraint": e.diag.constraint_name},
                ))
            except psycopg2.errors.NotNullViolation as e:
                request.env.cr.rollback()
                return _http_response(err(
                    ERR_VALIDATION_FAILED,
                    f"Required field missing: {e.diag.column_name}",
                    status=400,
                    details={"column": e.diag.column_name,
                             "table": e.diag.table_name},
                ))
            except psycopg2.IntegrityError as e:
                # Catch-all for any other DB integrity issue (check
                # constraints, exclusion constraints, etc.).
                request.env.cr.rollback()
                return _http_response(err(
                    ERR_VALIDATION_FAILED, "Database constraint violation",
                    status=400,
                    details={"db_detail": (e.diag.message_detail or "").strip() or None,
                             "constraint": e.diag.constraint_name},
                ))
            except Exception:
                _logger.exception("Unhandled error in %s", endpoint_path)
                request.env.cr.rollback()
                return _http_response(err(ERR_INTERNAL, "Unhandled server error", status=500))

            # If the function already returned an envelope (ok()/err()), keep it.
            # Otherwise, wrap plain dicts/lists into the `data` slot.
            if isinstance(result, dict) and ("data" in result or "error" in result):
                body = result
            else:
                body = ok(result)

            if ikey and "error" not in body:
                idempotency_store(ikey, endpoint_path, body)

            return _http_response(body, success_status=success_status)
        return wrapper
    return decorator
