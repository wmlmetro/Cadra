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
                       Bounded by the client record's own `total_record_cap`
                       and `max_page_limit`, defaulting to the first
                       EXTERNAL_TOTAL_CAP (100) records of any resource with
                       the per-request limit clamped to
                       EXTERNAL_MAX_PAGE_LIMIT (100). Bulk export endpoints
                       honour the same cap. This is the paywall safeguard
                       against external consumers pulling the full dataset —
                       and it always reports the TRUE total alongside the
                       truncated rows, plus a `_warnings.truncated` block.
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
import logging
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
    SCOPE_ADMIN,
    SCOPE_ASSETS_READ,
    SCOPE_ASSETS_WRITE,
    SCOPE_DASHBOARDS_READ,
    SCOPE_INTEGRATIONS_WRITE,
    SCOPE_REQUESTS_READ,
    SCOPE_REQUESTS_WRITE,
    _http_response,
    _new_request_id,
    cadra_endpoint,
    client_limit_claims,
    err,
    flag_truncation,
    get_params,
    jwt_encode,
    jwt_secret,
    log_safe as _log_safe,
    ok,
    record_cap,
    require_jwt,
    scopes_for_user,
    turnstile_error,
)


# Auth outcomes go to their own logger so `--log-handler cadra.auth:DEBUG` and
# a grep for "cadra.auth" both work without dragging in the rest of v1.
_auth_logger = logging.getLogger("cadra.auth")


# ─── route metadata registry (drives the OpenAPI generator) ─────────
#
# Each entry: {path, method, summary, scopes, idempotent, success_status}.
# Populated by the @cadra_route helper at import time; consumed by openapi_json().

_ROUTE_REGISTRY = []


# Shared cursor-pagination query params — spread into any list endpoint.
PAGINATION_QUERY_PARAMS = (
    # The documented maximum said 200 and had said so since before
    # MAX_PAGE_LIMIT was lifted to 2000 — so the published number matched
    # neither ceiling in force. It is caller-dependent, so say that instead
    # of naming a figure that is wrong for everyone.
    {"name": "limit", "schema": {"type": "integer", "default": 50, "minimum": 1},
     "description": (
         "Page size, default 50. Silently clamped to the ceiling for your "
         "credential: 100 for a service token unless its client record "
         "raises `max_page_limit`, 2000 for the Cadra web frontend.")},
    {"name": "cursor", "schema": {"type": "string"},
     "description": (
         "Opaque cursor from a previous response's pagination.next_cursor. "
         "A null next_cursor means either that you have reached the end or "
         "that your credential's record cap is exhausted — check "
         "`_warnings.truncated` and `pagination.total_estimate` to tell "
         "the two apart.")},
)


def cadra_route(path, *, method="GET", summary="", scopes=(), idempotent=False,
                success_status=None, request_schema=None, request_example=None,
                query_params=None, response_schema=None):
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
    response_schema: OpenAPI JSON-schema dict describing the `data`
                     member of the success envelope, e.g.
                       {"$ref": "#/components/schemas/Asset"}
                     or {"type": "array", "items": {"$ref": ...}}.
                     Omit and the generic Envelope stub is published.
                     This is where a field is marked `deprecated` — a
                     published response field cannot be removed without
                     breaking a consumer, so it is annotated instead.
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
            "response_schema": response_schema,
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

    def _mint_access(self, secret, *, sub, uid, scopes, aud=None, ttl=3600,
                     extra_claims=None):
        """Build and sign the short-lived access JWT. Returns the token string.

        `extra_claims` carries the per-client pagination limits so the hot
        list path reads a claim instead of re-reading the client record on
        every call. Only non-default values are ever passed, so an
        unconfigured client's token is byte-identical to the one it used to
        receive.
        """
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
        claims.update(extra_claims or {})
        return jwt_encode(claims, secret)

    def _session_payload(self, secret, *, sub, user, scopes, aud=None,
                         access_ttl=3600, client=None):
        """Mint an access JWT + a fresh refresh-token family and return the
        PRD `data` block shared by /auth/token, /auth/login and /auth/refresh.
        """
        access_token = self._mint_access(
            secret, sub=sub, uid=user.id, scopes=scopes, aud=aud, ttl=access_ttl,
            extra_claims=client_limit_claims(client),
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
        # Both go straight into an ORM domain, where a non-string raises
        # before any of our code runs — `{"client_id": {"$ne": null}}`
        # answered a raw HTML 500 from an UNAUTHENTICATED request, because
        # /auth/token is one of the nine routes that predate @cadra_route
        # and has no envelope handler under it. Found by the test written
        # for the diagnostic below, not by the diagnostic.
        if not isinstance(client_id, str) or not isinstance(client_secret, str):
            return _http_response(err(
                ERR_INVALID_REQUEST,
                "`client_id` and `client_secret` must be strings",
            ))

        Client = request.env["myservice.api.client"].sudo()
        client = Client.search(
            [("client_id", "=", client_id), ("active", "=", True)], limit=1
        )
        if not client or not client.check_client_secret(client_secret):
            # ONE body for all four causes, DELIBERATELY. Telling an
            # unauthenticated caller which half of the pair is wrong turns
            # this endpoint into a client-id enumeration oracle, and a 401
            # that distinguishes "no such client" from "wrong secret" is a
            # worse system than a slow debugging session. Do not "improve"
            # this by naming the cause in the response.
            #
            # The cause goes to the log instead, against the `request_id`
            # this response already carries — which is what makes that id
            # worth having.
            self._log_auth_failure(Client, client_id, client)
            return _http_response(err(
                ERR_UNAUTHORIZED, "Invalid client credentials", status=401,
            ))

        try:
            secret = jwt_secret(request.env)
        except Exception as e:
            return _http_response(err("server_misconfigured", str(e), status=500))

        # An empty scopes field means NO permissions, not every permission.
        # It used to fall through to `["*"]`, so a client created without
        # scopes — a typo, a half-finished record, an integration provisioned
        # by someone in a hurry — received the whole API including `admin`.
        # That is privilege escalation waiting for a slip, and the exact
        # opposite of what the Tag-Issuing Unit's own scoped client is for.
        # The token still mints: the client is refused per-route, with a
        # 403 that names the scope it is missing.
        scopes = (client.scopes or "").split()
        payload = self._session_payload(
            secret, sub=client.client_id, user=client.user_id, scopes=scopes,
            access_ttl=int(client.token_ttl_seconds or 3600), client=client,
        )
        client.sudo().write({
            "last_used_at": fields.Datetime.now(),
            "last_used_ip": request.httprequest.remote_addr,
        })

        # A log that records only failures cannot answer "did this
        # credential ever work", which is the second question anybody asks.
        _auth_logger.info(
            "request_id=%s client_id=%s outcome=ok",
            _new_request_id(), _log_safe(client_id),
        )
        return _http_response(ok(payload))

    def _log_auth_failure(self, Client, client_id, active_exact_match):
        """Name the cause of a /auth/token 401 in the server log.

        Four distinct causes answer with one identical body; without this
        the `request_id` we hand back is a token with nothing behind it.
        The extra queries run on the failure path only.

        The client id is logged as sent. It is half of a credential pair
        and it arrived in the clear, so it is not a secret — but it IS
        attacker-controlled text going into a log line, hence `_log_safe`.
        The secret never appears here: not hashed, not truncated, not as a
        length.
        """
        request_id = _new_request_id()
        safe_id = _log_safe(client_id)
        try:
            # A savepoint, not a bare try: `client_id` is unauthenticated
            # input and reaches the ORM as a DOMAIN VALUE, so a JSON object
            # or a number there raises a psycopg error that poisons the
            # transaction — and the 401 we are on our way to returning would
            # then fail at teardown. The diagnostic rolls back to here and
            # the response is unaffected.
            with request.env.cr.savepoint():
                outcome, extra = self._classify_auth_failure(
                    Client, client_id, active_exact_match)
        except Exception:
            # A diagnostic must never change the answer. A 401 that turns
            # into a 500 because we tried to explain it would be a worse bug
            # than the one this exists to fix.
            _auth_logger.exception(
                "request_id=%s client_id=%s outcome=unclassified",
                request_id, safe_id)
            return

        _auth_logger.warning(
            "request_id=%s client_id=%s outcome=%s%s",
            request_id, safe_id, outcome, extra,
        )

    def _classify_auth_failure(self, Client, client_id, active_exact_match):
        """Return (outcome, extra) for one failed /auth/token attempt."""
        if active_exact_match:
            return "bad_secret", ""
        else:
            # `active_test=False` — an archived client is a different fact
            # from a client that was never created, and only one of them is
            # fixed by reactivating it.
            inactive = Client.with_context(active_test=False).search(
                [("client_id", "=", client_id)], limit=1)
            if inactive:
                return "inactive", ""
            else:
                # `=` on a Postgres varchar is case-sensitive, so `Vendra`
                # and `vendra` are different clients and answer identically.
                # An hour was lost to exactly this on staging. `=ilike` is
                # a case-insensitive EXACT match — no wildcards are added.
                near = Client.with_context(active_test=False).search(
                    [("client_id", "=ilike", client_id)], limit=1)
                if near:
                    return ("case_mismatch",
                            " matched=%s" % _log_safe(near.client_id))
                return "no_such_client", ""

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

        Scopes: derived from the user's Odoo groups via
        `utils.GROUP_SCOPES` / `scopes_for_user`. A user holding none of the
        mapped groups gets an empty scope list — a token that authenticates
        and authorises nothing.
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

        # Derived from the user's Odoo groups. This used to be `["*"]`, which
        # meant the Tag-Issuing Unit separation held for API clients and not
        # for anyone with an Odoo password: a storekeeper could create an
        # asset and then confirm its own tag affixed. `scopes_for_user`
        # grants `tagging:write` from exactly one group, and grants nothing
        # at all to a user who holds no Cadra role.
        scopes = scopes_for_user(user)
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
            # Re-read off the client RECORD rather than replaying the claims
            # in the presented token — the same rule already applied to a
            # client family's user and to a session family's scopes. Raising
            # a client's cap must bite on its next refresh, not thirty days
            # later.
            extra_claims=client_limit_claims(client),
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

    # ── Diagnostics: GET /api/v1/meta/diagnostics ───────────────────

    @cadra_route("/api/v1/meta/diagnostics", method="GET",
                 summary="Server-state checks a deployment should be green on",
                 scopes=[SCOPE_ADMIN])
    def meta_diagnostics(self, **kwargs):
        """Assertable server state, for things a log line alone cannot guard.

        `dead_sql_constraints` is the one that exists today. Odoo 19 removed
        the `_sql_constraints` attribute and creates nothing for it, so a
        constraint declared that way silently stops existing — which is how
        `unique(asset_code)` was lost. `tests/test_source_guards.py` covers
        our own modules by parsing source; it cannot cover the vendored trees,
        where an upstream refresh could reintroduce the pattern. This reports
        the built registry's answer, so a test can assert zero against a real
        environment rather than a checkout.

        Admin-scoped: it names internal models.
        """
        return request.env["myservice.api.registry.diagnostics"].sudo().collect()

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
                            # Deliberately untyped. Routes narrow `data` with
                            # `response_schema`, composed onto this with
                            # `allOf` — and `type: object` here would make a
                            # list endpoint's `type: array` unsatisfiable, so
                            # a validator or a codegen run against this
                            # document would reject every list response.
                            "data": {"nullable": True},
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
                    "Asset": {
                        "type": "object",
                        "description": (
                            "An asset as Cadra serialises it. PARTIAL: only "
                            "the fields carrying a contract note are spelled "
                            "out here — the complete field list is in "
                            "docs/api/cadra_api_endpoint_reference.md. "
                            "Additional properties are returned."),
                        "additionalProperties": True,
                        "properties": {
                            "id": {"type": "integer"},
                            "asset_code": {"type": "string",
                                           "description": "Cadra's own asset "
                                                          "identity. Unique "
                                                          "and never null."},
                            "tag": {
                                "type": "string",
                                "nullable": True,
                                "deprecated": True,
                                "description": (
                                    "DEPRECATED — misleading name, kept "
                                    "because removing a published field "
                                    "breaks live consumers. It is the tag "
                                    "NUMBER Cadra minted at creation, and it "
                                    "is populated from the moment the asset "
                                    "exists, so it answers 'has a tag number "
                                    "been allocated', NOT 'is there a label "
                                    "on this asset'. Use "
                                    "`tagging.is_tagged` for the physical "
                                    "question and `tagging.tag_number` for "
                                    "the number. Read-only: it is absent "
                                    "from the writable-field allow-list."),
                            },
                            "provenance": {"$ref": "#/components/schemas/AssetProvenance"},
                            "tagging": {"$ref": "#/components/schemas/AssetTagging"},
                            "sap": {"$ref": "#/components/schemas/AssetSap"},
                        },
                    },
                    "AssetProvenance": {
                        "type": "object",
                        "description": "Where this record came from (INT-03).",
                        "properties": {
                            "grn_reference": {"type": "string", "nullable": True},
                            "purchase_order_reference": {"type": "string", "nullable": True},
                            "purchase_vendor": {"type": "string", "nullable": True},
                            "import_source": {"type": "string", "nullable": True,
                                              "enum": ["myservice", "sap", "redhubb",
                                                       "vendra", "excel", "other"]},
                            "import_date": {"type": "string", "format": "date", "nullable": True},
                            "import_ref": {"type": "string", "nullable": True},
                        },
                    },
                    "AssetTagging": {
                        "type": "object",
                        "description": (
                            "The physical label's lifecycle (INT-04/05). "
                            "Read-only over the API; `label_state` moves only "
                            "through printing and through "
                            "POST /api/v1/assets/{id}/tag-affixed."),
                        "properties": {
                            "label_id": {
                                "type": "integer", "nullable": True,
                                "description": (
                                    "The `nrs.asset.tag.label` id of the "
                                    "label on this asset — pass it as "
                                    "`tag_id` to GET /api/v1/barcode/"
                                    "print-url. NOT an asset id: the two id "
                                    "spaces collide, so using one where the "
                                    "other is wanted silently renders a real "
                                    "label for a different asset."),
                            },
                            "tag_number": {"type": "string", "nullable": True},
                            "label_state": {"type": "string", "nullable": True,
                                            "enum": ["issued", "printed",
                                                     "affixed", "scrapped"]},
                            "is_tagged": {
                                "type": "boolean",
                                "description": (
                                    "The single boolean to branch on. True "
                                    "only after an affix confirmation whose "
                                    "scanned tag number matched the one "
                                    "Cadra issued."),
                            },
                            # No `format: date-time`: these are Odoo naive
                            # datetimes rendered with .isoformat(), e.g.
                            # "2026-09-05T21:49:59" — no offset, so not the
                            # RFC 3339 that `date-time` promises. Claiming the
                            # format would make a strict parser reject a value
                            # that is otherwise perfectly readable.
                            "printed_at": {"type": "string", "nullable": True,
                                           "description": "ISO 8601, naive (server time), no offset"},
                            "printed_by": {"type": "object", "nullable": True},
                            "affixed_at": {"type": "string", "nullable": True,
                                           "description": "ISO 8601, naive (server time), no offset"},
                            "affixed_by": {"type": "object", "nullable": True},
                            "affixed_by_name": {"type": "string", "nullable": True},
                        },
                    },
                    "AssetSap": {
                        "type": "object",
                        # Read-only in its entirety, and marked so rather
                        # than left to the prose: none of these fields is in
                        # the writable-field allow-list, and a client able to
                        # PATCH `asset_number` could move an asset to
                        # `reconciled` without SAP having booked anything —
                        # the precise audit control this block publishes.
                        "readOnly": True,
                        "description": (
                            "What finance knows about this asset (INT-06/07) "
                            "and whether the two codes agree. Every figure "
                            "here is what SAP REPORTED, never what Cadra "
                            "computed: `financial.depreciation` is Cadra's "
                            "arithmetic and this is SAP's, the two are "
                            "allowed to disagree, and anything reconciling "
                            "them has to be able to see both. Read-only over "
                            "the API — written by the SAP integration and by "
                            "the legacy extract loader, never by a client."),
                        "properties": {
                            "asset_number": {
                                "type": "string", "nullable": True,
                                "description": (
                                    "The SAP half of the dual-code pair; "
                                    "`asset_code` at the top level is "
                                    "Cadra's half. NOT unique on its own — "
                                    "the same number can exist under two "
                                    "company codes — so anything matching on "
                                    "it needs `company_code` alongside."),
                            },
                            "asset_subnumber": {
                                "type": "string", "nullable": True,
                                "description": (
                                    "SAP fixed assets are identified by a "
                                    "main number and a sub-number; where "
                                    "sub-numbers are in use the main number "
                                    "alone does not identify the asset."),
                            },
                            "company_code": {"type": "string", "nullable": True},
                            "asset_class": {
                                "type": "string", "nullable": True,
                                "description": (
                                    "The class SAP actually posted under, "
                                    "which is not necessarily the one Cadra "
                                    "derived from the category. Where the "
                                    "two differ the mapping is wrong, and "
                                    "this is the field that shows it."),
                            },
                            "capitalisation_date": {
                                "type": "string", "format": "date", "nullable": True,
                                "description": (
                                    "The date SAP posted, which may differ "
                                    "from the tagging date Cadra proposed — "
                                    "period-close rules are SAP's to apply."),
                            },
                            "capitalised_amount": {
                                "type": "number", "nullable": True,
                                "description": (
                                    "The value SAP actually capitalised. "
                                    "Where it differs from the cost Cadra "
                                    "sent, SAP is the figure to show."),
                            },
                            "net_book_value": {
                                "type": "number", "nullable": True,
                                "description": (
                                    "As reported by SAP; never Cadra's own "
                                    "depreciation. `0` is an ANSWER — a "
                                    "fully written-down asset — and `null` "
                                    "is the absence of one; `synced_at` is "
                                    "what separates them."),
                            },
                            "accumulated_depreciation": {
                                "type": "number", "nullable": True,
                                "description": "As reported by SAP. Display only.",
                            },
                            "code_source": {
                                "type": "string", "nullable": True,
                                "enum": ["integration", "import", "manual"],
                                "description": (
                                    "How the SAP asset number got onto this "
                                    "record. `integration` means SAP "
                                    "returned it on INT-07 and is EVIDENCE "
                                    "that finance booked the asset; "
                                    "`import` (a legacy extract) and "
                                    "`manual` (typed in) are a CLAIM that "
                                    "they did. The dual-code control is an "
                                    "audit control, so the two must not look "
                                    "alike — only the integration itself may "
                                    "record `integration`."),
                            },
                            "posting_state": {
                                "type": "string",
                                "enum": ["none", "queued", "posted", "failed"],
                                "description": (
                                    "How far the INT-06 asset master posting "
                                    "has got, maintained by the outbound "
                                    "event queue. Always present, never "
                                    "null: the field carries a default."),
                            },
                            "reconciliation_state": {
                                "type": "string",
                                "enum": ["not_tagged", "pending", "reconciled",
                                         "exception"],
                                "description": (
                                    "The September Integration Flow "
                                    "completeness control: an asset is "
                                    "complete only when BOTH the Cadra Asset "
                                    "Code and the SAP asset code are linked "
                                    "on the register, and `reconciled` is "
                                    "that state. `exception` is the AUDIT "
                                    "FINDING — the asset is tagged, so it "
                                    "demonstrably exists, and finance has "
                                    "not booked it — and is the one value a "
                                    "reader should act on. `not_tagged` is "
                                    "not a finding: INT-06 fires on tagging "
                                    "confirmed, so an untagged asset is not "
                                    "yet due a SAP code. `pending` is posted "
                                    "and awaiting the code back. Always "
                                    "present, never null: it is a stored "
                                    "compute. Filterable with "
                                    "`?sap_reconciliation_state=`."),
                            },
                            # No `format: date-time`, for the reason spelled
                            # out on AssetTagging above: this is an Odoo
                            # naive datetime rendered with .isoformat(), e.g.
                            # "2026-09-05T21:49:59" — no offset, so not the
                            # RFC 3339 that `date-time` promises, and
                            # claiming the format would make a strict parser
                            # reject a perfectly readable value.
                            "synced_at": {
                                "type": "string", "nullable": True,
                                "description": (
                                    "When Cadra last received asset master "
                                    "figures from SAP. ISO 8601, naive "
                                    "(server time), no offset. On its own "
                                    "the answer to \"are these figures "
                                    "stale?\", and the discriminator "
                                    "between a reported 0.00 and no figure "
                                    "at all."),
                            },
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
                    "challenge returns 400 `invalid_request`.\n\n"
                    "**Scopes are derived from the user's Odoo groups.** The "
                    "returned `scope` is the union over the groups the "
                    "account holds, and can be empty — an account with no "
                    "Cadra role authenticates successfully and is refused by "
                    "every route. `tagging:write` comes from the "
                    "Tag-Issuing Unit group alone: the team that creates "
                    "asset records must not be able to confirm its own tags "
                    "(INT-04/05). Read `scope` off this response rather than "
                    "assuming; it was `*` for every user before "
                    "myservice_api 19.0.3.1.0."
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
                "responses": _standard_responses(
                    success_status=entry["success_status"],
                    data_schema=entry.get("response_schema"),
                ),
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
    #
    # These three used to be the only routes in the whole API that did not
    # `sudo()`, and it showed. `get_kpis` reads `fleet.vehicle` and
    # `generic.location` directly, so a caller holding `dashboards:read` but
    # not the matching Odoo groups got an AccessError — which, because
    # AccessError subclasses UserError in Odoo 19, surfaced as
    # `400 validation_failed` carrying an Odoo group name into the published
    # envelope. An error code that misdescribes the failure, and an internal
    # detail leaking through a contract.
    #
    # They sudo() now, which makes the SCOPE the gate here as it is everywhere
    # else: no scope is a 403 from `require_jwt` naming the scope it wanted,
    # and a caller with the scope gets data. That is a deliberate behaviour
    # change for SESSION tokens too — a Security Officer holding
    # `dashboards:read` but no fleet group used to get an error and now gets
    # data. Ruled correct: an Odoo group acting as a second, undeclared gate
    # behind a declared scope is the defect, not the protection.
    # (`utils.SCOPE_GROUPS` still grants those groups to client users. It is
    # the belt to this braces, not the control.)

    @cadra_route("/api/v1/dashboard/kpis", method="GET",
                 summary="Operations dashboard KPIs",
                 scopes=[SCOPE_DASHBOARDS_READ])
    def dashboard_kpis(self, **kwargs):
        return request.env["myservice.dashboard"].sudo().get_kpis()

    @cadra_route("/api/v1/dashboard/map", method="GET",
                 summary="Operations dashboard map data",
                 scopes=[SCOPE_DASHBOARDS_READ])
    def dashboard_map(self, **kwargs):
        return request.env["myservice.dashboard"].sudo().get_map_data()

    @cadra_route("/api/v1/dashboard/fleet-command", method="GET",
                 summary="Fleet command payload",
                 scopes=[SCOPE_DASHBOARDS_READ])
    def dashboard_fleet_command(self, **kwargs):
        return request.env["myservice.dashboard"].sudo().get_fleet_command()

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
        query = kwargs.get("query", "")
        result = BarcodeStationController().lookup_tag(query=query)
        return _delegate_failure(result, code=ERR_NOT_FOUND, status=404,
                                 details={"query": query}) or result

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
                      "description": (
                          "`nrs.asset.tag.label` id — the label to render, "
                          "available as `data.tagging.label_id` on the asset "
                          "or as `tag_id` from /barcode/recent-tags. This is "
                          "NOT the asset id, and the two id spaces collide: "
                          "passing an asset id here renders whichever "
                          "unrelated label shares that number. The id that "
                          "comes back inside the returned URL is the ASSET "
                          "id, because the label reports are registered on "
                          "nrs.asset — do not feed it back in here.")},
                     {"name": "size", "schema": {"type": "string",
                      "enum": ["small", "medium", "large", "sheet"],
                      "default": "medium"},
                      "description": (
                          "Label size. `sheet` is the A4 multi-label sheet; "
                          "it was always accepted and was missing from this "
                          "enum. An unrecognised value falls back to "
                          "`medium` rather than erroring.")},
                 ])
    def barcode_print_url(self, **kwargs):
        """Resolve the PDF URL for a tag label.

        The barcode station's own controller answers a browser with an ad-hoc
        `{"error": "..."}` dict, and `error` is the envelope's reserved key —
        so an unknown tag id used to come back as a bare werkzeug 500 HTML
        page with no code and no request_id. Translate its two failure shapes
        into the envelope instead of forwarding them.
        """
        from odoo.addons.myservice_barcode_station.controllers.main import BarcodeStationController
        raw_tag_id = kwargs.get("tag_id")
        # Malformed vs absent is decided here rather than by matching the
        # delegate's error prose: reword its message and a 400 would silently
        # start reporting as a 404.
        try:
            int(raw_tag_id)
        except (TypeError, ValueError):
            return err(ERR_INVALID_REQUEST,
                       "`tag_id` must be an integer tag-label id",
                       details={"tag_id": raw_tag_id})
        result = BarcodeStationController().get_print_url(
            tag_id=raw_tag_id,
            size=kwargs.get("size", "medium"),
        )
        return _delegate_failure(result, code=ERR_NOT_FOUND, status=404,
                                 details={"tag_id": raw_tag_id}) or result

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
        result = BarcodeStationController().generate_tags(
            asset_ids=body.get("asset_ids") or [],
        )
        return _delegate_failure(result, code=ERR_INVALID_REQUEST,
                                 status=400) or result

    @cadra_route("/api/v1/tags/lookup", method="GET",
                 summary="Public-style tag lookup (JWT-protected)",
                 scopes=[SCOPE_ASSETS_READ],
                 query_params=[
                     {"name": "query", "schema": {"type": "string"},
                      "description": "Tag, asset code, or serial to look up"},
                 ])
    def tags_lookup(self, **kwargs):
        from odoo.addons.myservice_barcode_station.controllers.main import BarcodeStationController
        query = kwargs.get("query", "")
        result = BarcodeStationController().portal_lookup(query=query)
        return _delegate_failure(result, code=ERR_NOT_FOUND, status=404,
                                 details={"query": query}) or result

    # ── Assets bulk export (legacy / CSV) ──────────────────────────

    @cadra_route("/api/v1/assets/export", method="GET",
                 summary="Export all assets as JSON (paginated externally if needed)",
                 scopes=[SCOPE_ASSETS_READ])
    def assets_export(self, **kwargs):
        # Capped callers see only the first `record_cap()` records — the same
        # paywall safeguard as the cursor-paginated endpoints. The frontend
        # and any client provisioned uncapped receive the full set.
        Asset = request.env["nrs.asset"].sudo()
        cap = record_cap()
        # `total` is the register, not the response. `count` used to be
        # len(items) on a capped search, so this endpoint answered "there
        # are 100 assets" to a tenant holding 2,363 — the same false
        # statement paginate() used to make, in a route that calls itself
        # "export ALL assets".
        total = Asset.search_count([])
        assets = Asset.search([], limit=cap)
        if cap is not None:
            flag_truncation(cap, total)
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
        return {"count": len(items), "total": total, "assets": items,
                "exported_at": str(fields.Datetime.now())}

    @http.route("/api/v1/assets/export.csv", type="http", auth="none",
                methods=["GET"], csrf=False)
    def assets_export_csv(self, **kwargs):
        """CSV export — non-JSON response, so it bypasses the PRD envelope.
        Auth is enforced inline."""
        _, envelope, _ = require_jwt(scopes=[SCOPE_ASSETS_READ])
        if envelope is not None:
            return _http_response(envelope)

        # Capped callers see only the first `record_cap()` rows — the same
        # paywall safeguard as the JSON paths.
        Asset = request.env["nrs.asset"].sudo()
        cap = record_cap()
        total = Asset.search_count([])
        assets = Asset.search([], limit=cap)
        truncated = cap is not None and total > cap
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
        headers = [
            ("Content-Type", "text/csv"),
            ("Content-Disposition", "attachment; filename=nrs_assets.csv"),
        ]
        if truncated:
            # A CSV bypasses the envelope, so it cannot carry `_warnings`.
            # It gets both halves instead: a header for anything reading the
            # response programmatically, and a final commented row for the
            # human who opens the file — because this is the artefact that
            # gets saved, emailed and cited, and a file that is silently a
            # twentieth of the register is the worst thing in this finding.
            headers.append(("X-Cadra-Truncated", "%d/%d" % (cap, total)))
            writer.writerow([
                "# TRUNCATED: this export contains the first %d of %d assets. "
                "This credential is limited to the first %d records of any "
                "query. Filter the query, or contact WestMetro to raise the "
                "limit." % (cap, total, cap)
            ])
        return request.make_response(output.getvalue(), headers=headers)

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
        result = NRSHomepageAPI().quick_submit(**(get_params() or {}))
        return _delegate_failure(result, code=ERR_INVALID_REQUEST,
                                 status=400) or result

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


def _delegate_failure(result, *, code, status, details=None):
    """Translate a non-API controller's ad-hoc failure dict into the envelope.

    Several `@cadra_route` handlers delegate to controllers written to answer a
    browser, and those signal failure in shapes of their own: `{"error": ...}`,
    `{"found": False, "error": ...}`, `{"success": False, "error": ...}`.
    `error` is the envelope's reserved key, so forwarding one verbatim escapes
    the contract — the caller used to get a bare werkzeug HTML 500 with no code
    and no request_id.

    And the status matters as much as the shape. An unknown barcode is an
    ordinary negative answer, not a server fault; a 500 tells an integration
    the fault is ours and the request is worth retrying, so a scanner pointed
    at a peeled-off label would retry forever.

    Returns an error envelope, or None when the delegate succeeded — so a
    caller reads `return _delegate_failure(...) or result`.
    """
    if not isinstance(result, dict):
        return None
    failed = (bool(result.get("error"))
              or result.get("found") is False
              or result.get("success") is False)
    if not failed:
        return None
    message = result.get("error") or "The request could not be completed"
    return err(code, str(message), details=details, status=status)


def _tag_from_path(path):
    """Pick an OpenAPI tag from the URL: /api/v1/<tag>/... → <Tag>."""
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3:
        return parts[2].capitalize().replace("-", " ")
    return "Other"


def _standard_responses(success_status=200, data_schema=None):
    """Standard set of responses for any endpoint. `success_status` tells
    Swagger which 2xx code to expect on success (200 vs 201).

    `data_schema`, when given, narrows the success envelope's `data` member
    to a specific schema instead of the free-form object. It is composed with
    allOf so the envelope's `meta`/`pagination` contract stays in one place.
    """
    success_schema = {"$ref": "#/components/schemas/Envelope"}
    if data_schema:
        success_schema = {"allOf": [
            {"$ref": "#/components/schemas/Envelope"},
            {"type": "object", "properties": {"data": data_schema}},
        ]}
    responses = {
        str(success_status): {
            "description": "OK" if success_status == 200 else "Created",
            "content": {"application/json": {"schema": success_schema}},
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
