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

JWT auth: clients exchange (client_id, client_secret) for a bearer token at
POST /api/v1/auth/token, then send `Authorization: Bearer <token>` on every
subsequent call. Scopes use the resource:action format from the Cadra API
spec (assets:read, requests:write, etc.) — see utils.SCOPE_* for the list.

Write endpoints (POST/PUT/PATCH/DELETE) support idempotency via the
`X-Idempotency-Key` header. Two requests with the same key on the same
endpoint within 24h return the same cached response.
"""
import csv
import io
import json
import re
import time

from odoo import fields, http
from odoo.http import request

from .utils import (
    API_VERSION,
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    ERR_UNAUTHORIZED,
    SCOPE_ASSETS_READ,
    SCOPE_DASHBOARDS_READ,
    SCOPE_INTEGRATIONS_WRITE,
    SCOPE_REQUESTS_READ,
    SCOPE_REQUESTS_WRITE,
    _http_response,
    cadra_endpoint,
    err,
    get_params,
    jwt_encode,
    jwt_secret,
    ok,
    require_jwt,
)


# ─── route metadata registry (drives the OpenAPI generator) ─────────
#
# Each entry: {path, method, summary, scopes, idempotent, success_status}.
# Populated by the @cadra_route helper at import time; consumed by openapi_json().

_ROUTE_REGISTRY = []


def cadra_route(path, *, method="GET", summary="", scopes=(), idempotent=False, success_status=None):
    """REST route registrar + auth/envelope wrapper.

    method:          "GET" | "POST" | "PATCH" | "PUT" | "DELETE"
    success_status:  HTTP status on success. Defaults:
                       - 201 for POST on resource collections (no path-id)
                       - 200 otherwise
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

    @http.route("/api/v1/auth/token", type="http", auth="none",
                methods=["POST"], csrf=False)
    def token(self, **kwargs):
        """Exchange client credentials for a JWT bearer token.

        Body (flat JSON): {"client_id": "...", "client_secret": "..."}
        Response: PRD envelope with data = {token_type, access_token, expires_in, scope}.
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

        now = int(time.time())
        ttl = int(client.token_ttl_seconds or 3600)
        scopes = (client.scopes or "").split() or ["*"]
        claims = {
            "iss": "myservice_api",
            "sub": client.client_id,
            "uid": client.user_id.id,
            "scopes": scopes,
            "iat": now,
            "exp": now + ttl,
        }
        token = jwt_encode(claims, secret)
        client.sudo().write({
            "last_used_at": fields.Datetime.now(),
            "last_used_ip": request.httprequest.remote_addr,
        })

        return _http_response(ok({
            "token_type": "Bearer",
            "access_token": token,
            "expires_in": ttl,
            "scope": " ".join(scopes),
        }))

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
                    "Cadra REST API \n\n\n"
                    "## Trying it from this page\n\n"
                    "1. Run **POST /api/v1/auth/token** with a flat body "
                    "`{\"client_id\": \"...\", \"client_secret\": \"...\"}`. "
                    "Copy `data.access_token` from the response.\n\n"
                    "2. Click **Authorize** at the top. Paste **only the "
                    "raw token** (do NOT include the word `Bearer `). "
                    "Swagger prepends it for you.\n\n"
                    "3. Use any endpoint's *Try it out*. GET endpoints take "
                    "query-string params; POST/PATCH endpoints take a flat "
                    "JSON body (no `{params: {...}}` wrapper any more).\n\n"
                ),
            },
            "servers": [{"url": "/"}],
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
                },
            },
            "paths": {},
        }

        # Always-on token endpoint (declared manually since it's not in the registry).
        spec["paths"]["/api/v1/auth/token"] = {
            "post": {
                "summary": "Exchange client credentials for a JWT bearer token",
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
                op["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "description": (
                                    "Flat JSON body. See the route summary "
                                    "for the expected fields."
                                ),
                            },
                            "example": {},
                        }
                    },
                }

            spec["paths"].setdefault(spec_path, {})[method_lc] = op

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
                 summary="Lookup asset by tag/barcode (query: ?query=...)",
                 scopes=[SCOPE_ASSETS_READ])
    def barcode_lookup(self, **kwargs):
        from odoo.addons.myservice_barcode_station.controllers.main import BarcodeStationController
        return BarcodeStationController().lookup_tag(query=kwargs.get("query", ""))

    @cadra_route("/api/v1/barcode/kpis", method="GET",
                 summary="Barcode station KPIs", scopes=[SCOPE_ASSETS_READ])
    def barcode_kpis(self, **kwargs):
        from odoo.addons.myservice_barcode_station.controllers.main import BarcodeStationController
        return BarcodeStationController().get_kpis()

    @cadra_route("/api/v1/barcode/recent-tags", method="GET",
                 summary="Recently scanned/printed tags (query: ?domain_filter=&limit=)",
                 scopes=[SCOPE_ASSETS_READ])
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
                 summary="Generate a tag print URL (query: ?tag_id=&size=)",
                 scopes=[SCOPE_ASSETS_READ])
    def barcode_print_url(self, **kwargs):
        from odoo.addons.myservice_barcode_station.controllers.main import BarcodeStationController
        return BarcodeStationController().get_print_url(
            tag_id=kwargs.get("tag_id"),
            size=kwargs.get("size", "medium"),
        )

    @cadra_route("/api/v1/tags/lookup", method="GET",
                 summary="Public-style tag lookup (JWT-protected) — ?query=...",
                 scopes=[SCOPE_ASSETS_READ])
    def tags_lookup(self, **kwargs):
        from odoo.addons.myservice_barcode_station.controllers.main import BarcodeStationController
        return BarcodeStationController().portal_lookup(query=kwargs.get("query", ""))

    # ── Assets bulk export (legacy / CSV) ──────────────────────────

    @cadra_route("/api/v1/assets/export", method="GET",
                 summary="Export all assets as JSON (paginated externally if needed)",
                 scopes=[SCOPE_ASSETS_READ])
    def assets_export(self, **kwargs):
        assets = request.env["nrs.asset"].sudo().search([])
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

        assets = request.env["nrs.asset"].sudo().search([])
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
                 idempotent=True)
    def home_quick_submit(self, **kwargs):
        from odoo.addons.myservice_website_theme.controllers.api import NRSHomepageAPI
        return NRSHomepageAPI().quick_submit(**(get_params() or {}))

    # ── Integrations ───────────────────────────────────────────────

    @cadra_route("/api/v1/integrations/sap/employee-sync", method="POST",
                 summary="Receive SAP SuccessFactors employee sync events",
                 scopes=[SCOPE_INTEGRATIONS_WRITE],
                 idempotent=True,
                 success_status=200)  # action endpoint, not a resource create
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

    @cadra_route("/api/v1/integrations/workflow/callback", method="POST",
                 summary="Apply an external workflow engine's decision to a request",
                 scopes=[SCOPE_INTEGRATIONS_WRITE],
                 idempotent=True,
                 success_status=200)  # action endpoint, not a resource create
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
