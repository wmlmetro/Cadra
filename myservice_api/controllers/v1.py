"""
Cadra API v1 — JWT-protected REST endpoints (PRD §10.7 shape).

All endpoints return the PRD envelope directly (no JSON-RPC wrapper):
    success: {"data": ..., "meta": {request_id, timestamp, version}}
    error:   {"error": {"code", "message", "details", "request_id"}}

REST conventions:
    GET    /resource              → list with cursor pagination + filters (query string)
    GET    /resource/<id>         → fetch single
    POST   /resource              → create (201 Created)
    PATCH  /resource/<id>         → partial update (200 OK)
    POST   /resource/<id>/<verb>  → action (move, transition, comment, etc.)

JWT auth — two flows. Both return the same JWT shape; differ only in how
the caller proves identity:
    - Human users    → POST /api/v1/auth/login with {login, password}
                       (validated against Odoo res.users, same creds as the web UI).
                       Issued with `aud: "frontend"` so list endpoints
                       expose the full data set (up to MAX_PAGE_LIMIT/page).
    - Service / M2M  → POST /api/v1/auth/token with {client_id, client_secret}
                       (myservice.api.client records, scoped per consumer).
                       No `aud` claim — list endpoints expose only the first
                       EXTERNAL_TOTAL_CAP (100) records of any resource and
                       per-request limit is clamped to EXTERNAL_MAX_PAGE_LIMIT
                       (100). Bulk export endpoints honour the same cap.
                       This is the paywall safeguard against external
                       consumers pulling the full dataset.
Send `Authorization: Bearer <token>` on every subsequent call. Scopes use
the resource:action format from the Cadra API spec (assets:read,
requests:write, etc.) — see utils.SCOPE_* for the list.

Write endpoints (POST/PUT/PATCH/DELETE) support idempotency via the
`X-Idempotency-Key` header. Two requests with the same key on the same
endpoint within 24h return the same cached response.
"""
import base64
import csv
import io
import json
import re
import time

from odoo import fields, http
from odoo.exceptions import AccessDenied
from odoo.http import request

from .utils import (
    API_VERSION,
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    ERR_UNAUTHORIZED,
    EXTERNAL_TOTAL_CAP,
    SCOPE_ASSETS_READ,
    SCOPE_ASSETS_WRITE,
    SCOPE_DASHBOARDS_READ,
    SCOPE_INTEGRATIONS_WRITE,
    SCOPE_REQUESTS_READ,
    SCOPE_REQUESTS_WRITE,
    _http_response,
    _request_is_frontend,
    cadra_endpoint,
    err,
    get_params,
    jwt_encode,
    jwt_secret,
    ok,
    require_jwt,
    turnstile_error,
)


# ─── route metadata registry (drives the OpenAPI generator) ─────────
#
# Each entry: {path, method, summary, scopes, idempotent, success_status}.
# Populated by the @cadra_route helper at import time; consumed by openapi_json().

_ROUTE_REGISTRY = []


# Shared cursor-pagination query params — spread into any list endpoint.
PAGINATION_QUERY_PARAMS = (
    {"name": "limit", "schema": {"type": "integer", "default": 50, "maximum": 200, "minimum": 1},
     "description": "Page size (1–200, default 50)"},
    {"name": "cursor", "schema": {"type": "string"},
     "description": "Opaque cursor from a previous response's pagination.next_cursor"},
)


def cadra_route(path, *, method="GET", summary="", scopes=(), idempotent=False,
                success_status=None, request_schema=None, request_example=None,
                query_params=None):
    """REST route registrar + auth/envelope wrapper.

    method:          "GET" | "POST" | "PATCH" | "PUT" | "DELETE"
    success_status:  HTTP status on success. Defaults:
                       - 201 for POST on resource collections (no path-id)
                       - 200 otherwise
    request_schema:  OpenAPI JSON-schema dict for the request body
                     (POST/PATCH/PUT only). When omitted, Swagger shows
                     a generic free-form object stub.
    request_example: Example body Swagger renders in the "Try it out"
                     panel. Highly recommended whenever request_schema
                     is supplied so users see realistic input.
    query_params:    Iterable of OpenAPI parameter dicts to render as
                     query-string inputs in Swagger. Each entry should
                     be a partial spec — `in: "query"` is filled in if
                     omitted. Example:
                       [{"name": "q", "schema": {"type": "string"},
                         "description": "Free-text search"}]
                     PAGINATION_QUERY_PARAMS provides limit+cursor for
                     list endpoints.
    """
    method = method.upper()

    if success_status is None:
        # POST /<resource> with no path placeholders = resource creation → 201.
        # POST /<resource>/<int:id>/<action> = action → 200.
        if method == "POST" and "<" not in path:
            success_status = 201
        else:
            success_status = 200

    def decorator(fn):
        _ROUTE_REGISTRY.append({
            "path": path,
            "method": method,
            "summary": summary or (fn.__doc__ or fn.__name__).strip().splitlines()[0],
            "scopes": list(scopes),
            "idempotent": idempotent,
            "success_status": success_status,
            "request_schema": request_schema,
            "request_example": request_example,
            "query_params": list(query_params or ()),
        })
        wrapped = cadra_endpoint(
            scopes=scopes,
            idempotent=idempotent,
            success_status=success_status,
        )(fn)
        return http.route(
            path,
            type="http",
            auth="none",
            methods=[method],
            csrf=False,
        )(wrapped)
    return decorator


# ─── controller ──────────────────────────────────────────────────────

class MyserviceApiV1(http.Controller):

    # ── Auth ────────────────────────────────────────────────────────

    def _mint_access(self, secret, *, sub, uid, scopes, aud=None, ttl=3600):
        """Build and sign the short-lived access JWT. Returns the token string."""
        now = int(time.time())
        claims = {
            "iss": "myservice_api",
            "sub": sub,
            "uid": uid,
            "scopes": scopes,
            "iat": now,
            "exp": now + ttl,
        }
        if aud:
            claims["aud"] = aud
        return jwt_encode(claims, secret)

    def _session_payload(self, secret, *, sub, user, scopes, aud=None,
                         access_ttl=3600, client=None):
        """Mint an access JWT + a fresh refresh-token family and return the
        PRD `data` block shared by /auth/token, /auth/login and /auth/refresh.
        """
        access_token = self._mint_access(
            secret, sub=sub, uid=user.id, scopes=scopes, aud=aud, ttl=access_ttl,
        )
        rec, raw = request.env["myservice.api.refresh_token"].sudo()._issue(
            user=user, scopes=scopes, aud=aud, client=client,
            ip=request.httprequest.remote_addr,
        )
        refresh_ttl = int((rec.expires_at - fields.Datetime.now()).total_seconds())
        return {
            "token_type": "Bearer",
            "access_token": access_token,
            "expires_in": access_ttl,
            "refresh_token": raw,
            "refresh_token_expires_in": refresh_ttl,
            "scope": " ".join(scopes),
        }

    @http.route("/api/v1/auth/token", type="http", auth="none",
                methods=["POST"], csrf=False)
    def token(self, **kwargs):
        """Exchange client credentials for a JWT bearer token + refresh token.

        Body (flat JSON): {"client_id": "...", "client_secret": "..."}
        Response: PRD envelope with data = {token_type, access_token,
        expires_in, refresh_token, refresh_token_expires_in, scope}.
        """
        data = get_params()

        client_id = data.get("client_id")
        client_secret = data.get("client_secret")
        if not client_id or not client_secret:
            return _http_response(err(
                ERR_INVALID_REQUEST,
                "`client_id` and `client_secret` are required",
            ))

        client = request.env["myservice.api.client"].sudo().search(
            [("client_id", "=", client_id), ("active", "=", True)], limit=1
        )
        if not client or not client.check_client_secret(client_secret):
            return _http_response(err(
                ERR_UNAUTHORIZED, "Invalid client credentials", status=401,
            ))

        try:
            secret = jwt_secret(request.env)
        except Exception as e:
            return _http_response(err("server_misconfigured", str(e), status=500))

        scopes = (client.scopes or "").split() or ["*"]
        payload = self._session_payload(
            secret, sub=client.client_id, user=client.user_id, scopes=scopes,
            access_ttl=int(client.token_ttl_seconds or 3600), client=client,
        )
        client.sudo().write({
            "last_used_at": fields.Datetime.now(),
            "last_used_ip": request.httprequest.remote_addr,
        })

        return _http_response(ok(payload))

    # ── Auth: user login (OAuth2 ROPC) ─────────────────────────────

    @http.route("/api/v1/auth/login", type="http", auth="none",
                methods=["POST"], csrf=False)
    def login(self, **kwargs):
        """Exchange res.users credentials (Odoo username + password) for a
        JWT bearer token.

        Body (flat JSON): {"login": "user@example.com", "password": "..."}
        Response: PRD envelope with data = {token_type, access_token, expires_in, scope}.

        This is the OAuth2 "password grant" / ROPC flow — only safe for
        first-party clients (we control both the React frontend and this
        backend). Third-party integrations should keep using
        POST /api/v1/auth/token with client_id/secret.

        Scopes: currently every authenticated user gets ["*"]. Mapping
        Odoo groups to API scopes is a deliberate follow-up — needs a
        product decision on which groups gate which resources.
        """
        data = get_params()
        login = (data.get("login") or data.get("username") or "").strip()
        password = data.get("password") or ""

        if not login or not password:
            return _http_response(err(
                ERR_INVALID_REQUEST,
                "`login` and `password` are required",
            ))

        # Cloudflare Turnstile. A no-op unless this tenant has a secret key
        # configured; checked after the field validation above so a
        # malformed request never costs a round-trip to Cloudflare.
        challenge_error = turnstile_error(request.env, data.get("turnstile_token"))
        if challenge_error:
            return _http_response(challenge_error)

        # Odoo 19's `authenticate(credential, user_agent_env)` takes a
        # credential dict (no db arg) and returns an `auth_info` dict
        # ({'uid': ..., 'auth_method': ...}) instead of a bare uid; it raises
        # AccessDenied on failure. It uses Odoo's standard password
        # verification (hash check, MFA hooks, etc).
        try:
            auth_info = request.env["res.users"].authenticate(
                {"type": "password", "login": login, "password": password},
                {"interactive": False},
            )
            uid = auth_info.get("uid") if isinstance(auth_info, dict) else auth_info
        except AccessDenied:
            uid = False

        if not uid:
            return _http_response(err(
                ERR_UNAUTHORIZED, "Invalid login or password", status=401,
            ))

        user = request.env["res.users"].sudo().browse(uid)
        if not user.exists() or not user.active:
            return _http_response(err(
                ERR_UNAUTHORIZED, "Account is disabled", status=401,
            ))

        try:
            secret = jwt_secret(request.env)
        except Exception as e:
            return _http_response(err("server_misconfigured", str(e), status=500))

        scopes = ["*"]  # TODO: derive from user's Odoo groups
        # `aud: "frontend"` marks this token as belonging to the Cadra web
        # frontend; utils.parse_limit lets it pull up to MAX_PAGE_LIMIT
        # records per page (200). Service tokens issued via /auth/token
        # deliberately don't carry this claim and are clamped to
        # EXTERNAL_MAX_PAGE_LIMIT (100).
        payload = self._session_payload(
            secret, sub=user.login, user=user, scopes=scopes,
            aud="frontend", access_ttl=3600,
        )
        return _http_response(ok(payload))

    # ── Auth: refresh (exchange a refresh token for a fresh pair) ───

    @http.route("/api/v1/auth/refresh", type="http", auth="none",
                methods=["POST"], csrf=False)
    def refresh(self, **kwargs):
        """Exchange a refresh token for a new access token + rotated refresh token.

        Body (flat JSON): {"refresh_token": "..."}
        Response: PRD envelope with the same data shape as /auth/login and
        /auth/token. The presented refresh token is single-use: this call
        revokes it and returns its successor. Replaying a spent token revokes
        the whole family (theft response) and returns 401.
        """
        data = get_params()
        raw = data.get("refresh_token")
        if not raw:
            return _http_response(err(
                ERR_INVALID_REQUEST, "`refresh_token` is required",
            ))

        try:
            secret = jwt_secret(request.env)
        except Exception as e:
            return _http_response(err("server_misconfigured", str(e), status=500))

        result, error = request.env["myservice.api.refresh_token"].sudo().verify_and_rotate(
            raw, ip=request.httprequest.remote_addr,
        )
        if error:
            # One generic 401 for every failure mode — don't leak which check
            # tripped (unknown vs expired vs revoked vs disabled account).
            return _http_response(err(
                ERR_UNAUTHORIZED, "Invalid or expired refresh token", status=401,
            ))

        user = result["user"]
        client = result["client"]
        scopes = result["scopes"]
        access_ttl = int((client.token_ttl_seconds if client else 3600) or 3600)
        access_token = self._mint_access(
            secret,
            sub=client.client_id if client else user.login,
            uid=user.id, scopes=scopes, aud=result["aud"], ttl=access_ttl,
        )
        new_rec = result["new_record"]
        refresh_ttl = int((new_rec.expires_at - fields.Datetime.now()).total_seconds())

        return _http_response(ok({
            "token_type": "Bearer",
            "access_token": access_token,
            "expires_in": access_ttl,
            "refresh_token": result["new_raw"],
            "refresh_token_expires_in": refresh_ttl,
            "scope": " ".join(scopes),
        }))

    # ── Auth: revoke (logout — kill a refresh-token family) ─────────

    @http.route("/api/v1/auth/revoke", type="http", auth="none",
                methods=["POST"], csrf=False)
    def revoke(self, **kwargs):
        """Revoke a refresh token (and its whole rotation family).

        Body (flat JSON): {"refresh_token": "..."}
        Always returns 200 {"revoked": true} — revocation is idempotent and
        the response never reveals whether the token existed. Outstanding
        access tokens remain valid until their short TTL elapses; this stops
        any further refresh.
        """
        data = get_params()
        raw = data.get("refresh_token")
        if not raw:
            return _http_response(err(
                ERR_INVALID_REQUEST, "`refresh_token` is required",
            ))
        request.env["myservice.api.refresh_token"].sudo().revoke(raw, reason="logout")
        return _http_response(ok({"revoked": True}))

    # ── Auth: whoami (resolve current bearer token to user profile) ─

    @cadra_route("/api/v1/auth/whoami", method="GET",
                 summary="Resolve the current bearer token to the caller's profile",
                 scopes=[])
    def whoami(self, **kwargs):
        """Return the caller's basic profile + token claims.

        Any authenticated bearer token works (scopes=[] means "no
        additional scope required beyond a valid token"). Useful for the
        frontend after a refresh to recover {user_id, name, email, scopes,
        exp} without re-logging in.
        """
        claims = getattr(request, "jwt_claims", {}) or {}
        user = request.env["res.users"].sudo().browse(request.env.user.id)
        if not user.exists():
            # Token decoded fine but the uid no longer points to a row.
            return err(ERR_UNAUTHORIZED, "Token subject no longer exists", status=401)
        rows = user.read(["id", "login", "name", "email", "partner_id"])
        row = rows[0] if rows else {}
        # res.users.read returns partner_id as [id, display_name]; flatten to id.
        partner = row.get("partner_id")
        partner_id = partner[0] if isinstance(partner, (list, tuple)) and partner else partner
        return {
            "id": row.get("id"),
            "login": row.get("login"),
            "name": row.get("name"),
            "email": row.get("email"),
            "partner_id": partner_id,
            "scopes": claims.get("scopes") or [],
            "token_type": "Bearer",
            "expires_at": claims.get("exp"),
        }

    # ── OpenAPI + Swagger UI ────────────────────────────────────────

    @http.route("/api/v1/openapi.json", type="http", auth="none",
                methods=["GET"], csrf=False)
    def openapi_json(self, **kwargs):
        """Auto-generated OpenAPI 3.0 spec from the route registry."""
        spec = {
            "openapi": "3.0.3",
            "info": {
                "title": "Cadra API",
                "version": API_VERSION,
                "description": (
                    "Cadra REST API"
                ),
            },
            "servers": [{"url": (request.httprequest.url_root or "/").rstrip("/") or "/",
                         "description": "Current host"}],
            "components": {
                "securitySchemes": {
                    "bearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "JWT",
                    }
                },
                "schemas": {
                    "Envelope": {
                        "type": "object",
                        "properties": {
                            "data": {"type": "object", "nullable": True},
                            "meta": {
                                "type": "object",
                                "properties": {
                                    "request_id": {"type": "string"},
                                    "timestamp": {"type": "string", "format": "date-time"},
                                    "version": {"type": "string"},
                                },
                            },
                            "pagination": {
                                "type": "object",
                                "nullable": True,
                                "properties": {
                                    "next_cursor": {"type": "string", "nullable": True},
                                    "previous_cursor": {"type": "string", "nullable": True},
                                    "total_estimate": {"type": "integer", "nullable": True},
                                },
                            },
                        },
                    },
                    "Error": {
                        "type": "object",
                        "properties": {
                            "error": {
                                "type": "object",
                                "required": ["code", "message", "request_id"],
                                "properties": {
                                    "code": {"type": "string"},
                                    "message": {"type": "string"},
                                    "request_id": {"type": "string"},
                                    "details": {"type": "object"},
                                },
                            }
                        },
                    },
                    "SapEmployee": {
                        "type": "object",
                        "description": ("SuccessFactors employee payload. Either "
                                        "`ir_number` or `userId` must be present so "
                                        "the row can be matched."),
                        "properties": {
                            "ir_number": {"type": "string", "description": "Cadra IR/staff number"},
                            "userId": {"type": "string", "description": "SAP user id (fallback match key)"},
                            "firstName": {"type": "string"},
                            "lastName": {"type": "string"},
                            "email": {"type": "string", "format": "email"},
                            "department": {"type": "string"},
                            "jobTitle": {"type": "string"},
                            "status": {"type": "string",
                                       "enum": ["active", "inactive", "terminated"]},
                        },
                    },
                },
            },
            "paths": {},
        }

        # Always-on auth endpoints (declared manually since they're not in the registry).
        spec["paths"]["/api/v1/auth/token"] = {
            "post": {
                "summary": "Exchange client credentials for a JWT bearer token (service accounts / integrations)",
                "tags": ["Auth"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {
                        "type": "object",
                        "required": ["client_id", "client_secret"],
                        "properties": {
                            "client_id": {"type": "string"},
                            "client_secret": {"type": "string"},
                        },
                    }, "example": {"client_id": "test_client", "client_secret": "..."}}},
                },
                "responses": _standard_responses(),
            }
        }
        spec["paths"]["/api/v1/auth/login"] = {
            "post": {
                "summary": "Exchange res.users credentials for a JWT bearer token (human users)",
                "tags": ["Auth"],
                "description": (
                    "OAuth2 password grant (ROPC). Validates `login` + "
                    "`password` against the Odoo `res.users` model (same "
                    "credentials as the Odoo web UI) and returns a 1-hour "
                    "JWT. Intended for first-party clients like the Cadra "
                    "web frontend. Third-party integrations should use "
                    "`/auth/token` with client credentials instead.\n\n"
                    "Tenants with Cloudflare Turnstile configured also "
                    "require `turnstile_token`; a missing or rejected "
                    "challenge returns 400 `invalid_request`."
                ),
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {
                        "type": "object",
                        "required": ["login", "password"],
                        "properties": {
                            "login": {"type": "string", "description": "Odoo username (typically an email address)"},
                            "password": {"type": "string", "format": "password"},
                            "turnstile_token": {
                                "type": "string",
                                "description": (
                                    "Cloudflare Turnstile response token. Required only on "
                                    "tenants with a Turnstile secret key configured; ignored "
                                    "everywhere else."
                                ),
                            },
                        },
                    }, "example": {"login": "admin", "password": "..."}}},
                },
                "responses": _standard_responses(),
            }
        }
        spec["paths"]["/api/v1/auth/refresh"] = {
            "post": {
                "summary": "Rotate a refresh token for a fresh access + refresh token pair",
                "tags": ["Auth"],
                "description": (
                    "Exchange an opaque, single-use refresh token (issued by "
                    "`/auth/token` and `/auth/login`) for a new access token "
                    "and a rotated refresh token. The presented token is "
                    "revoked on use; replaying a spent token revokes the whole "
                    "token family (theft detection) and returns 401. Clients "
                    "must store the newly returned `refresh_token` after each "
                    "call. 30-day sliding window."
                ),
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {
                        "type": "object",
                        "required": ["refresh_token"],
                        "properties": {
                            "refresh_token": {"type": "string"},
                        },
                    }, "example": {"refresh_token": "..."}}},
                },
                "responses": _standard_responses(),
            }
        }
        spec["paths"]["/api/v1/auth/revoke"] = {
            "post": {
                "summary": "Revoke a refresh token and its whole rotation family (logout)",
                "tags": ["Auth"],
                "description": (
                    "Revoke the presented refresh token and every token "
                    "rotated from it. Idempotent and constant-response: an "
                    "unknown token still returns 200 `{\"revoked\": true}`, so "
                    "the endpoint never reveals whether a token existed. "
                    "Outstanding access tokens stay valid until their short "
                    "TTL elapses; this only stops further refresh."
                ),
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {
                        "type": "object",
                        "required": ["refresh_token"],
                        "properties": {
                            "refresh_token": {"type": "string"},
                        },
                    }, "example": {"refresh_token": "..."}}},
                },
                "responses": _standard_responses(),
            }
        }
        # /auth/whoami is declared via @cadra_route (so the runtime decorator
        # enforces auth), but we override its OpenAPI entry below the
        # registry loop so we can pin the `bearerAuth` security tag — the
        # registry generator omits security when `scopes=[]` and we want
        # Swagger to know this endpoint requires a token.

        # Routes from the @cadra_route registry
        for entry in _ROUTE_REGISTRY:
            spec_path, params = _openapi_path_and_params(entry["path"])
            method_lc = entry["method"].lower()
            op = {
                "summary": entry["summary"],
                "tags": [_tag_from_path(entry["path"])],
                "security": [{"bearerAuth": []}] if entry["scopes"] else [],
                "x-cadra-scopes": entry["scopes"],
                "responses": _standard_responses(success_status=entry["success_status"]),
            }
            if params:
                op["parameters"] = list(params)

            # Query-string params declared on the route.
            for qp in entry.get("query_params") or ():
                qp = dict(qp)
                qp.setdefault("in", "query")
                qp.setdefault("required", False)
                op.setdefault("parameters", []).append(qp)

            # Idempotency header on write methods that declare it.
            if entry["idempotent"]:
                op.setdefault("parameters", []).append({
                    "name": "X-Idempotency-Key",
                    "in": "header",
                    "schema": {"type": "string"},
                    "required": False,
                    "description": ("Optional client-supplied dedup key. Same "
                                    "key on same endpoint within 24h returns "
                                    "the cached response."),
                })

            # Request body — only for POST/PATCH/PUT.
            if entry["method"] in ("POST", "PATCH", "PUT"):
                schema = entry.get("request_schema") or {
                    "type": "object",
                    "description": (
                        "Flat JSON body. See the route summary "
                        "for the expected fields."
                    ),
                }
                media = {"schema": schema}
                if entry.get("request_example") is not None:
                    media["example"] = entry["request_example"]
                else:
                    media["example"] = {}
                op["requestBody"] = {
                    "required": True,
                    "content": {"application/json": media},
                }

            spec["paths"].setdefault(spec_path, {})[method_lc] = op

        # Override the auto-generated /auth/whoami entry so it advertises
        # bearerAuth (the registry strips security tags when scopes=[]).
        spec["paths"].setdefault("/api/v1/auth/whoami", {})["get"] = {
            "summary": "Resolve the current bearer token to the caller's profile",
            "tags": ["Auth"],
            "security": [{"bearerAuth": []}],
            "description": (
                "Returns the calling user's basic profile and the active "
                "token claims. Any valid bearer token works — no extra "
                "scope is required. Useful after a page refresh to "
                "recover the session without re-prompting for credentials."
            ),
            "responses": _standard_responses(),
        }

        return request.make_response(
            json.dumps(spec, indent=2),
            headers=[("Content-Type", "application/json; charset=utf-8")],
        )

    @http.route("/api/v1/docs", type="http", auth="none",
                methods=["GET"], csrf=False)
    def swagger_ui(self, **kwargs):
        """CDN-hosted Swagger UI rendering the auto-generated OpenAPI spec."""
        spec_url = "/api/v1/openapi.json"
        html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Cadra API Docs</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
    <style> body {{ margin: 0; background: #fafafa; }} </style>
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
    <script>
      window.ui = SwaggerUIBundle({{
        url: {json.dumps(spec_url)},
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
        layout: "StandaloneLayout"
      }});
    </script>
  </body>
</html>"""
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])

    # ── Dashboards (read-only aggregations) ────────────────────────

    @cadra_route("/api/v1/dashboard/kpis", method="GET",
                 summary="Operations dashboard KPIs",
                 scopes=[SCOPE_DASHBOARDS_READ])
    def dashboard_kpis(self, **kwargs):
        return request.env["myservice.dashboard"].get_kpis()

    @cadra_route("/api/v1/dashboard/map", method="GET",
                 summary="Operations dashboard map data",
                 scopes=[SCOPE_DASHBOARDS_READ])
    def dashboard_map(self, **kwargs):
        return request.env["myservice.dashboard"].get_map_data()

    @cadra_route("/api/v1/dashboard/fleet-command", method="GET",
                 summary="Fleet command payload",
                 scopes=[SCOPE_DASHBOARDS_READ])
    def dashboard_fleet_command(self, **kwargs):
        return request.env["myservice.dashboard"].get_fleet_command()

    @cadra_route("/api/v1/security/kpis", method="GET",
                 summary="Security KPIs", scopes=[SCOPE_DASHBOARDS_READ])
    def security_kpis(self, **kwargs):
        from odoo.addons.myservice_security.controllers.main import SecurityDashboardController
        return SecurityDashboardController().get_kpis()

    @cadra_route("/api/v1/security/map-data", method="GET",
                 summary="Security map data", scopes=[SCOPE_DASHBOARDS_READ])
    def security_map_data(self, **kwargs):
        from odoo.addons.myservice_security.controllers.main import SecurityDashboardController
        return SecurityDashboardController().get_map_data()

    @cadra_route("/api/v1/security/trend", method="GET",
                 summary="Security incident trend", scopes=[SCOPE_DASHBOARDS_READ])
    def security_trend(self, **kwargs):
        from odoo.addons.myservice_security.controllers.main import SecurityDashboardController
        return SecurityDashboardController().get_trend()

    @cadra_route("/api/v1/security/recent", method="GET",
                 summary="Recent security incidents", scopes=[SCOPE_DASHBOARDS_READ])
    def security_recent(self, **kwargs):
        from odoo.addons.myservice_security.controllers.main import SecurityDashboardController
        return SecurityDashboardController().get_recent()

    @cadra_route("/api/v1/fleet/dashboard", method="GET",
                 summary="Fleet dashboard data", scopes=[SCOPE_DASHBOARDS_READ])
    def fleet_dashboard(self, **kwargs):
        from odoo.addons.myservice_fleet_maintenance.controllers.fleet_dashboard import FleetDashboardController
        return FleetDashboardController().fleet_dashboard_data(**(kwargs or {}))

    @cadra_route("/api/v1/fm/dashboard", method="GET",
                 summary="Facilities management dashboard data",
                 scopes=[SCOPE_DASHBOARDS_READ])
    def fm_dashboard(self, **kwargs):
        from odoo.addons.myservice_fm_dashboard.controllers.dashboard import FMDashboardController
        return FMDashboardController().dashboard_data(**(kwargs or {}))

    # ── Asset lookup (barcode + portal) ────────────────────────────

    @cadra_route("/api/v1/barcode/lookup", method="GET",
                 summary="Lookup asset by tag/barcode",
                 scopes=[SCOPE_ASSETS_READ],
                 query_params=[
                     {"name": "query", "schema": {"type": "string"},
                      "description": "Tag, asset code, or serial number to look up"},
                 ])
    def barcode_lookup(self, **kwargs):
        from odoo.addons.myservice_barcode_station.controllers.main import BarcodeStationController
        return BarcodeStationController().lookup_tag(query=kwargs.get("query", ""))

    @cadra_route("/api/v1/barcode/kpis", method="GET",
                 summary="Barcode station KPIs", scopes=[SCOPE_ASSETS_READ])
    def barcode_kpis(self, **kwargs):
        from odoo.addons.myservice_barcode_station.controllers.main import BarcodeStationController
        return BarcodeStationController().get_kpis()

    @cadra_route("/api/v1/barcode/recent-tags", method="GET",
                 summary="Recently scanned/printed tags",
                 scopes=[SCOPE_ASSETS_READ],
                 query_params=[
                     {"name": "domain_filter", "schema": {"type": "string"},
                      "description": "Optional domain filter (e.g. asset domain)"},
                     {"name": "limit", "schema": {"type": "integer", "default": 50, "minimum": 1},
                      "description": "Max rows to return (default 50)"},
                 ])
    def barcode_recent_tags(self, **kwargs):
        from odoo.addons.myservice_barcode_station.controllers.main import BarcodeStationController
        try:
            limit = int(kwargs.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        return BarcodeStationController().get_recent_tags(
            domain_filter=kwargs.get("domain_filter", ""),
            limit=limit,
        )

    @cadra_route("/api/v1/barcode/print-url", method="GET",
                 summary="Generate a tag print URL",
                 scopes=[SCOPE_ASSETS_READ],
                 query_params=[
                     {"name": "tag_id", "required": True, "schema": {"type": "integer"},
                      "description": "nrs.asset.tag id to render a label for"},
                     {"name": "size", "schema": {"type": "string",
                      "enum": ["small", "medium", "large"], "default": "medium"}},
                 ])
    def barcode_print_url(self, **kwargs):
        from odoo.addons.myservice_barcode_station.controllers.main import BarcodeStationController
        return BarcodeStationController().get_print_url(
            tag_id=kwargs.get("tag_id"),
            size=kwargs.get("size", "medium"),
        )

    @cadra_route("/api/v1/barcode/untagged", method="GET",
                 summary="Assets with no active barcode tag",
                 scopes=[SCOPE_ASSETS_READ],
                 query_params=[
                     {"name": "q", "schema": {"type": "string"},
                      "description": "Filter by asset name, asset code, or serial number"},
                     {"name": "limit", "schema": {"type": "integer", "default": 100,
                                                  "minimum": 1, "maximum": 500},
                      "description": "Max rows to return (default 100, max 500)"},
                 ])
    def barcode_untagged(self, **kwargs):
        from odoo.addons.myservice_barcode_station.controllers.main import BarcodeStationController
        return BarcodeStationController().get_untagged(
            q=kwargs.get("q", ""),
            limit=kwargs.get("limit", 100),
        )

    @cadra_route("/api/v1/barcode/generate", method="POST",
                 summary="Generate barcode tags for the given assets",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 success_status=200,  # action endpoint, not a resource create
                 request_schema={
                     "type": "object",
                     "required": ["asset_ids"],
                     "properties": {
                         "asset_ids": {
                             "type": "array",
                             "items": {"type": "integer"},
                             "maxItems": 500,
                             "description": "nrs.asset ids to mint a barcode for. Assets "
                                            "that already have an active tag are skipped, "
                                            "so the call is safe to retry.",
                         },
                     },
                 },
                 request_example={"asset_ids": [124, 125, 126]})
    def barcode_generate(self, **kwargs):
        from odoo.addons.myservice_barcode_station.controllers.main import BarcodeStationController
        body = get_params()
        return BarcodeStationController().generate_tags(
            asset_ids=body.get("asset_ids") or [],
        )

    @cadra_route("/api/v1/tags/lookup", method="GET",
                 summary="Public-style tag lookup (JWT-protected)",
                 scopes=[SCOPE_ASSETS_READ],
                 query_params=[
                     {"name": "query", "schema": {"type": "string"},
                      "description": "Tag, asset code, or serial to look up"},
                 ])
    def tags_lookup(self, **kwargs):
        from odoo.addons.myservice_barcode_station.controllers.main import BarcodeStationController
        return BarcodeStationController().portal_lookup(query=kwargs.get("query", ""))

    # ── Assets bulk export (legacy / CSV) ──────────────────────────

    @cadra_route("/api/v1/assets/export", method="GET",
                 summary="Export all assets as JSON (paginated externally if needed)",
                 scopes=[SCOPE_ASSETS_READ])
    def assets_export(self, **kwargs):
        # External (non-frontend) tokens see only the first EXTERNAL_TOTAL_CAP
        # records — same paywall safeguard as the cursor-paginated endpoints.
        # The frontend always receives the full set.
        cap = None if _request_is_frontend() else EXTERNAL_TOTAL_CAP
        assets = request.env["nrs.asset"].sudo().search([], limit=cap)
        items = [{
            "asset_code": a.asset_code,
            "name": a.name,
            "category": a.category_id.name if a.category_id else None,
            "condition": a.condition,
            "state": a.state,
            "location": a.location_id.name if a.location_id else None,
            "assigned_to": a.custodian_id.name if a.custodian_id else None,
            "assigned_ir": a.assigned_ir_number or None,
            "assigned_dept": a.assigned_employee_dept or None,
            "assignment_date": str(a.assignment_date) if a.assignment_date else None,
            "retrieval_flag": a.retrieval_flag,
            "serial_number": a.serial_number or None,
        } for a in assets]
        return {"count": len(items), "assets": items,
                "exported_at": str(fields.Datetime.now())}

    @http.route("/api/v1/assets/export.csv", type="http", auth="none",
                methods=["GET"], csrf=False)
    def assets_export_csv(self, **kwargs):
        """CSV export — non-JSON response, so it bypasses the PRD envelope.
        Auth is enforced inline."""
        _, envelope, _ = require_jwt(scopes=[SCOPE_ASSETS_READ])
        if envelope is not None:
            return _http_response(envelope)

        # External (non-frontend) tokens see only the first EXTERNAL_TOTAL_CAP
        # rows — same paywall safeguard as the JSON paths.
        cap = None if _request_is_frontend() else EXTERNAL_TOTAL_CAP
        assets = request.env["nrs.asset"].sudo().search([], limit=cap)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Asset Code", "Name", "Category", "Condition", "State",
            "Location", "Assigned To", "IR Number", "Department",
            "Assignment Date", "Retrieval Flag", "Serial Number",
        ])
        for a in assets:
            writer.writerow([
                a.asset_code,
                a.name,
                a.category_id.name if a.category_id else "",
                a.condition or "",
                a.state or "",
                a.location_id.name if a.location_id else "",
                a.custodian_id.name if a.custodian_id else "",
                a.assigned_ir_number or "",
                a.assigned_employee_dept or "",
                str(a.assignment_date) if a.assignment_date else "",
                "YES" if a.retrieval_flag else "NO",
                a.serial_number or "",
            ])
        return request.make_response(
            output.getvalue(),
            headers=[
                ("Content-Type", "text/csv"),
                ("Content-Disposition", "attachment; filename=nrs_assets.csv"),
            ],
        )

    # ── Service requests (portal / quick submit) ───────────────────

    @cadra_route("/api/v1/home/form-data", method="GET",
                 summary="Homepage form dropdown data",
                 scopes=[SCOPE_REQUESTS_READ])
    def home_form_data(self, **kwargs):
        from odoo.addons.myservice_website_theme.controllers.api import NRSHomepageAPI
        return NRSHomepageAPI().get_form_data(**(kwargs or {}))

    @cadra_route("/api/v1/home/quick-submit", method="POST",
                 summary="Submit a service request from the homepage",
                 scopes=[SCOPE_REQUESTS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "required": ["type_id", "description"],
                     "properties": {
                         "type_id": {"type": "integer", "description": "request.type id"},
                         "service_id": {"type": "integer", "nullable": True},
                         "location_id": {"type": "integer", "nullable": True,
                                         "description": "generic.location id"},
                         "priority": {"type": "string", "enum": ["0", "1", "2", "3"],
                                      "description": "0=low, 1=normal, 2=high, 3=urgent"},
                         "description": {"type": "string"},
                         "reporter_name": {"type": "string", "nullable": True},
                         "reporter_contact": {"type": "string", "nullable": True,
                                              "description": "Phone or email"},
                     },
                 },
                 request_example={
                     "type_id": 1,
                     "service_id": 4,
                     "location_id": 12,
                     "priority": "2",
                     "description": "Leaking pipe in the cafeteria sink",
                     "reporter_name": "Jane Doe",
                     "reporter_contact": "jane.doe@example.com",
                 })
    def home_quick_submit(self, **kwargs):
        from odoo.addons.myservice_website_theme.controllers.api import NRSHomepageAPI
        return NRSHomepageAPI().quick_submit(**(get_params() or {}))

    # ── Integrations ───────────────────────────────────────────────

    @cadra_route("/api/v1/integrations/sap/employee-sync", method="POST",
                 summary="Receive SAP SuccessFactors employee sync events",
                 scopes=[SCOPE_INTEGRATIONS_WRITE],
                 idempotent=True,
                 success_status=200,  # action endpoint, not a resource create
                 request_schema={
                     "oneOf": [
                         {"$ref": "#/components/schemas/SapEmployee"},
                         {"type": "array",
                          "items": {"$ref": "#/components/schemas/SapEmployee"}},
                     ],
                     "description": "Single employee object or a list of employee objects.",
                 },
                 request_example=[{
                     "ir_number": "IR123456",
                     "userId": "u-123",
                     "firstName": "Ada",
                     "lastName": "Lovelace",
                     "email": "ada@example.com",
                     "department": "Engineering",
                     "jobTitle": "Principal Engineer",
                     "status": "active",
                 }])
    def sap_employee_sync(self, **kwargs):
        payload = get_params()
        # Allow either a single object or a list of employee dicts
        body = request.httprequest.get_json(silent=True)
        if isinstance(body, list):
            employees = body
        elif payload:
            employees = [payload]
        else:
            return err(ERR_INVALID_REQUEST, "Empty payload")

        results = []
        SyncLog = request.env["nrs.sap.sync.log"].sudo()
        for emp_data in employees:
            employee, log = SyncLog.process_sap_payload(emp_data, sync_type="api")
            results.append({
                "ir_number": emp_data.get("ir_number") or emp_data.get("userId", "unknown"),
                "status": log.status,
                "employee_id": employee.id if employee else None,
                "changes": log.changes_applied or "",
            })
        return {"processed": len(results), "results": results}

    # Bulk employee import — xlsx multipart upload, async processing.
    # Bypasses @cadra_route because that path expects JSON, not multipart.
    # JWT + scope check is done inline (same pattern as assets_export_csv).
    @http.route("/api/v1/integrations/employees/import", type="http",
                auth="none", methods=["POST"], csrf=False)
    def employees_import(self, **kwargs):
        """POST an xlsx nominal-roll file; returns 202 + a job id.

        Body: multipart/form-data with `file` (the xlsx) and optional
              `sheet` (sheet name; first sheet if omitted).
        Auth: Bearer JWT with `integrations:write` scope.
        Response (202): {"data": {"job_id": <int>, "state": "pending"}, "meta": {...}}

        Processing runs in a background thread; poll
        GET /api/v1/integrations/employees/import/<job_id> for status.
        """
        _, envelope, _ = require_jwt(scopes=[SCOPE_INTEGRATIONS_WRITE])
        if envelope is not None:
            return _http_response(envelope)

        uploaded = request.httprequest.files.get("file")
        if uploaded is None or not uploaded.filename:
            return _http_response(err(
                ERR_INVALID_REQUEST,
                "`file` form field is required (multipart upload)",
            ))

        filename = uploaded.filename
        if not filename.lower().endswith(".xlsx"):
            return _http_response(err(
                ERR_INVALID_REQUEST,
                "Only .xlsx files are supported in v1",
                details={"received_filename": filename},
            ))

        raw = uploaded.read()
        if not raw:
            return _http_response(err(ERR_INVALID_REQUEST, "Uploaded file is empty"))

        sheet = (request.httprequest.form.get("sheet") or "").strip() or False

        job = request.env["nrs.employee.import.job"].sudo().create({
            "file_name": filename,
            "file_data": base64.b64encode(raw),
            "sheet_name": sheet,
        })
        job.start_async()

        return _http_response(
            ok({"job_id": job.id, "state": job.state}),
            success_status=202,
        )

    @cadra_route("/api/v1/integrations/employees/import/<int:job_id>",
                 method="GET",
                 summary="Poll status of an employee bulk-import job",
                 scopes=[SCOPE_INTEGRATIONS_WRITE])
    def employees_import_status(self, job_id, **kwargs):
        job = request.env["nrs.employee.import.job"].sudo().browse(job_id)
        if not job.exists():
            return err(ERR_NOT_FOUND, "Import job not found", status=404)
        return job.to_status_dict()

    @cadra_route("/api/v1/integrations/workflow/callback", method="POST",
                 summary="Apply an external workflow engine's decision to a request",
                 scopes=[SCOPE_INTEGRATIONS_WRITE],
                 idempotent=True,
                 success_status=200,  # action endpoint, not a resource create
                 request_schema={
                     "type": "object",
                     "required": ["reference", "outcome"],
                     "properties": {
                         "reference": {"type": "string",
                                       "description": "request.request.name (e.g. INCIDENT-052026-0000002)"},
                         "outcome": {"type": "string",
                                     "enum": ["approved", "rejected", "queried"]},
                         "workspace_ref": {"type": "string", "nullable": True,
                                           "description": "External workflow engine's workspace identifier"},
                         "payment_ref": {"type": "string", "nullable": True,
                                         "description": "Optional payment reference (approved outcomes)"},
                         "comment": {"type": "string", "nullable": True,
                                     "description": "Reviewer comment / reason"},
                     },
                 },
                 request_example={
                     "reference": "INCIDENT-052026-0000002",
                     "outcome": "approved",
                     "workspace_ref": "WSP-7788",
                     "payment_ref": "PAY-2026-04412",
                     "comment": "Approved by finance",
                 })
    def workflow_callback_v1(self, **kwargs):
        data = get_params()
        if not isinstance(data, dict):
            return err(ERR_INVALID_REQUEST, "Invalid payload")

        ref = data.get("reference", "")
        workspace_ref = data.get("workspace_ref", "")
        outcome = (data.get("outcome") or data.get("status") or "").lower().strip()
        payment_ref = data.get("payment_ref", "")
        comment = data.get("comment") or data.get("reason") or data.get("message") or ""

        if not ref:
            return err(ERR_INVALID_REQUEST, "`reference` field is required")
        if outcome not in ("approved", "rejected", "queried"):
            return err(ERR_INVALID_REQUEST, f"Unknown outcome '{outcome}'",
                       details={"allowed_outcomes": ["approved", "rejected", "queried"]})

        req_rec = request.env["request.request"].sudo().search(
            [("name", "=", ref)], limit=1)
        if not req_rec:
            return err(ERR_NOT_FOUND, f"Request '{ref}' not found", status=404)

        log = request.env["workflow.dispatch.log"].sudo().create({
            "request_id": req_rec.id,
            "direction": "inbound",
            "status": outcome,
            "workspace_ref": workspace_ref,
            "response_received": json.dumps(data, default=str),
        })

        if outcome == "approved":
            req_rec._workflow_callback_approved(
                workspace_ref=workspace_ref,
                payment_ref=payment_ref or None,
                comment=comment or None,
                log=log,
            )
        elif outcome == "rejected":
            req_rec._workflow_callback_rejected(
                workspace_ref=workspace_ref,
                comment=comment or None,
                log=log,
            )
        else:
            req_rec._workflow_callback_queried(
                workspace_ref=workspace_ref,
                comment=comment,
                log=log,
            )

        return {"applied_outcome": outcome, "request_reference": ref}


# ─── OpenAPI helpers ────────────────────────────────────────────────

_PATH_PARAM_RE = re.compile(r"<(?:(?P<conv>[a-zA-Z_][a-zA-Z0-9_]*):)?(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)>")


def _openapi_path_and_params(odoo_path):
    """Translate an Odoo route pattern (e.g. /api/v1/locations/<int:id>)
    into the OpenAPI {path, parameters} pair (e.g. /api/v1/locations/{id}
    with a path parameter `id: integer`)."""
    params = []
    type_map = {"int": "integer", "string": "string", None: "string"}

    def _replace(m):
        name = m.group("name")
        conv = m.group("conv")
        params.append({
            "name": name,
            "in": "path",
            "required": True,
            "schema": {"type": type_map.get(conv, "string")},
        })
        return "{" + name + "}"

    spec_path = _PATH_PARAM_RE.sub(_replace, odoo_path)
    return spec_path, params


def _tag_from_path(path):
    """Pick an OpenAPI tag from the URL: /api/v1/<tag>/... → <Tag>."""
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3:
        return parts[2].capitalize().replace("-", " ")
    return "Other"


def _standard_responses(success_status=200):
    """Standard set of responses for any endpoint. `success_status` tells
    Swagger which 2xx code to expect on success (200 vs 201)."""
    responses = {
        str(success_status): {
            "description": "OK" if success_status == 200 else "Created",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Envelope"}}},
        },
        "400": {
            "description": "Bad Request",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
        },
        "401": {
            "description": "Unauthorized",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
        },
        "403": {
            "description": "Forbidden",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
        },
        "404": {
            "description": "Not Found",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
        },
        "500": {
            "description": "Server Error",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
        },
    }
    return responses
