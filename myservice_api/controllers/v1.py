"""
Cadra API v1 — JWT-protected JSON endpoints.

All endpoints return the PRD envelope (PRD §10.7):
    success: {"data": ..., "meta": {request_id, timestamp, version}}
    error:   {"error": {"code", "message", "details", "request_id"}}

JWT auth: clients exchange (client_id, client_secret) for a bearer token at
/api/v1/auth/token, then send it as `Authorization: Bearer <token>` on every
subsequent call. Scopes use the resource:action format from the Cadra API
spec (assets:read, requests:write, etc.) — see utils.SCOPE_* for the list.

Write endpoints (POST/PUT/PATCH/DELETE) support idempotency via the
`X-Idempotency-Key` header. Two requests with the same key on the same
endpoint within 24h return the same cached response.
"""
import csv
import io
import json
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
    cadra_endpoint,
    err,
    jwt_encode,
    jwt_secret,
    ok,
    require_jwt,
)


# ─── route metadata registry (drives the OpenAPI generator) ─────────
#
# Each entry: {path, method, summary, scopes, idempotent}. Populated by
# the @cadra_route helper at import time; consumed by openapi_json().

_ROUTE_REGISTRY = []


def cadra_route(path, *, method="POST", summary="", scopes=(), idempotent=False, type_="json"):
    """Combined decorator: registers route metadata + wraps with @http.route + @cadra_endpoint.

    Replaces the previous pattern of stacking @http.route + manual _require_jwt
    calls. Keeps everything an endpoint needs declared in one place.
    """
    def decorator(fn):
        _ROUTE_REGISTRY.append({
            "path": path,
            "method": method,
            "summary": summary or fn.__doc__ or fn.__name__,
            "scopes": list(scopes),
            "idempotent": idempotent,
        })
        # Apply decorators bottom-up: cadra_endpoint first, then http.route.
        wrapped = cadra_endpoint(scopes=scopes, idempotent=idempotent)(fn)
        return http.route(
            path,
            type=type_,
            auth="none",
            methods=[method],
            csrf=False,
        )(wrapped)
    return decorator


def _unwrap_json_rpc(payload):
    """Odoo's type=json route already unwraps JSON-RPC params into kwargs,
    but some callers POST raw JSON without the envelope. Handle both."""
    if isinstance(payload, dict) and "params" in payload and "jsonrpc" in payload:
        return payload.get("params") or {}
    return payload or {}


# ─── controller ──────────────────────────────────────────────────────

class MyserviceApiV1(http.Controller):

    # ── Auth ────────────────────────────────────────────────────────

    @http.route("/api/v1/auth/token", type="json", auth="none", methods=["POST"], csrf=False)
    def token(self, **kwargs):
        """Exchange client credentials for a JWT bearer token."""
        data = _unwrap_json_rpc(kwargs or (request.jsonrequest or {}))

        client_id = data.get("client_id")
        client_secret = data.get("client_secret")
        if not client_id or not client_secret:
            return err(ERR_INVALID_REQUEST, "client_id and client_secret are required")

        client = request.env["myservice.api.client"].sudo().search(
            [("client_id", "=", client_id), ("active", "=", True)], limit=1
        )
        if not client or not client.check_client_secret(client_secret):
            return err(ERR_UNAUTHORIZED, "Invalid client credentials", status=401)

        try:
            secret = jwt_secret(request.env)
        except Exception as e:
            return err("server_misconfigured", str(e), status=500)

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

        return ok({
            "token_type": "Bearer",
            "access_token": token,
            "expires_in": ttl,
            "scope": " ".join(scopes),
        })

    # ── OpenAPI + Swagger UI ────────────────────────────────────────

    @http.route("/api/v1/openapi.json", type="http", auth="none", methods=["GET"], csrf=False)
    def openapi_json(self, **kwargs):
        """Auto-generated OpenAPI 3.0 spec from the route registry."""
        spec = {
            "openapi": "3.0.3",
            "info": {
                "title": "Cadra API",
                "version": API_VERSION,
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

        # Always-on token endpoint
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
                    }}},
                },
                "responses": _standard_responses(),
            }
        }

        # Routes from the @cadra_route registry
        for entry in _ROUTE_REGISTRY:
            path = entry["path"]
            method = entry["method"].lower()
            spec["paths"].setdefault(path, {})[method] = {
                "summary": entry["summary"],
                "tags": [_tag_from_path(path)],
                "security": [{"bearerAuth": []}] if entry["scopes"] else [],
                "parameters": [
                    {
                        "name": "X-Idempotency-Key",
                        "in": "header",
                        "schema": {"type": "string"},
                        "required": False,
                    }
                ] if entry["idempotent"] else [],
                "x-cadra-scopes": entry["scopes"],
                "responses": _standard_responses(),
            }

        return request.make_response(
            json.dumps(spec, indent=2),
            headers=[("Content-Type", "application/json; charset=utf-8")],
        )

    @http.route("/api/v1/docs", type="http", auth="none", methods=["GET"], csrf=False)
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

    @cadra_route("/api/v1/dashboard/kpis", summary="Operations dashboard KPIs", scopes=[SCOPE_DASHBOARDS_READ])
    def dashboard_kpis(self, **kwargs):
        return request.env["myservice.dashboard"].get_kpis()

    @cadra_route("/api/v1/dashboard/map", summary="Operations dashboard map data", scopes=[SCOPE_DASHBOARDS_READ])
    def dashboard_map(self, **kwargs):
        return request.env["myservice.dashboard"].get_map_data()

    @cadra_route("/api/v1/dashboard/fleet-command", summary="Fleet command payload", scopes=[SCOPE_DASHBOARDS_READ])
    def dashboard_fleet_command(self, **kwargs):
        return request.env["myservice.dashboard"].get_fleet_command()

    @cadra_route("/api/v1/security/kpis", summary="Security KPIs", scopes=[SCOPE_DASHBOARDS_READ])
    def security_kpis(self, **kwargs):
        from myservice_security.controllers.main import SecurityDashboardController
        return SecurityDashboardController().get_kpis()

    @cadra_route("/api/v1/security/map-data", summary="Security map data", scopes=[SCOPE_DASHBOARDS_READ])
    def security_map_data(self, **kwargs):
        from myservice_security.controllers.main import SecurityDashboardController
        return SecurityDashboardController().get_map_data()

    @cadra_route("/api/v1/security/trend", summary="Security incident trend", scopes=[SCOPE_DASHBOARDS_READ])
    def security_trend(self, **kwargs):
        from myservice_security.controllers.main import SecurityDashboardController
        return SecurityDashboardController().get_trend()

    @cadra_route("/api/v1/security/recent", summary="Recent security incidents", scopes=[SCOPE_DASHBOARDS_READ])
    def security_recent(self, **kwargs):
        from myservice_security.controllers.main import SecurityDashboardController
        return SecurityDashboardController().get_recent()

    @cadra_route("/api/v1/fleet/dashboard", summary="Fleet dashboard data", scopes=[SCOPE_DASHBOARDS_READ])
    def fleet_dashboard(self, **kwargs):
        from myservice_fleet_maintenance.controllers.fleet_dashboard import FleetDashboardController
        return FleetDashboardController().fleet_dashboard_data(**(kwargs or {}))

    @cadra_route("/api/v1/fm/dashboard", summary="Facilities management dashboard data", scopes=[SCOPE_DASHBOARDS_READ])
    def fm_dashboard(self, **kwargs):
        from myservice_fm_dashboard.controllers.dashboard import FMDashboardController
        return FMDashboardController().dashboard_data(**(kwargs or {}))

    # ── Asset lookup (barcode + portal) ────────────────────────────

    @cadra_route("/api/v1/barcode/lookup", summary="Lookup asset by tag/barcode", scopes=[SCOPE_ASSETS_READ])
    def barcode_lookup(self, **kwargs):
        from myservice_barcode_station.controllers.main import BarcodeStationController
        query = (kwargs or {}).get("query", "")
        return BarcodeStationController().lookup_tag(query=query)

    @cadra_route("/api/v1/barcode/kpis", summary="Barcode station KPIs", scopes=[SCOPE_ASSETS_READ])
    def barcode_kpis(self, **kwargs):
        from myservice_barcode_station.controllers.main import BarcodeStationController
        return BarcodeStationController().get_kpis()

    @cadra_route("/api/v1/barcode/recent-tags", summary="Recently scanned/printed tags", scopes=[SCOPE_ASSETS_READ])
    def barcode_recent_tags(self, **kwargs):
        from myservice_barcode_station.controllers.main import BarcodeStationController
        data = kwargs or {}
        return BarcodeStationController().get_recent_tags(
            domain_filter=data.get("domain_filter", ""),
            limit=int(data.get("limit", 50) or 50),
        )

    @cadra_route("/api/v1/barcode/print-url", summary="Generate a tag print URL", scopes=[SCOPE_ASSETS_READ])
    def barcode_print_url(self, **kwargs):
        from myservice_barcode_station.controllers.main import BarcodeStationController
        data = kwargs or {}
        return BarcodeStationController().get_print_url(
            tag_id=data.get("tag_id"),
            size=data.get("size", "medium"),
        )

    @cadra_route("/api/v1/tags/lookup", summary="Public-style tag lookup (JWT-protected)", scopes=[SCOPE_ASSETS_READ])
    def tags_lookup(self, **kwargs):
        from myservice_barcode_station.controllers.main import BarcodeStationController
        query = (kwargs or {}).get("query", "")
        return BarcodeStationController().portal_lookup(query=query)

    # ── Assets (full register) ─────────────────────────────────────

    @cadra_route("/api/v1/assets/export", summary="Export all assets as JSON", scopes=[SCOPE_ASSETS_READ])
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
        return {"count": len(items), "assets": items, "exported_at": str(fields.Datetime.now())}

    @http.route("/api/v1/assets/export.csv", type="http", auth="none", methods=["GET"], csrf=False)
    def assets_export_csv(self, **kwargs):
        """CSV export — type=http endpoint, can't use the JSON envelope.
        Auth and error shape are handled inline."""
        _, envelope, _ = require_jwt(scopes=[SCOPE_ASSETS_READ])
        if envelope is not None:
            return request.make_response(
                json.dumps(envelope),
                headers=[("Content-Type", "application/json")],
                status=envelope["error"]["details"].get("http_status", 401),
            )

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

    @cadra_route("/api/v1/home/form-data", summary="Homepage form dropdown data", scopes=[SCOPE_REQUESTS_READ])
    def home_form_data(self, **kwargs):
        from myservice_website_theme.controllers.api import NRSHomepageAPI
        return NRSHomepageAPI().get_form_data(**(kwargs or {}))

    @cadra_route("/api/v1/home/quick-submit",
                 summary="Submit a service request from the homepage",
                 scopes=[SCOPE_REQUESTS_WRITE],
                 idempotent=True)
    def home_quick_submit(self, **kwargs):
        from myservice_website_theme.controllers.api import NRSHomepageAPI
        return NRSHomepageAPI().quick_submit(**(kwargs or {}))

    # ── Integrations ───────────────────────────────────────────────

    @cadra_route("/api/v1/integrations/sap/employee-sync",
                 summary="Receive SAP SuccessFactors employee sync events",
                 scopes=[SCOPE_INTEGRATIONS_WRITE],
                 idempotent=True)
    def sap_employee_sync(self, **kwargs):
        payload = _unwrap_json_rpc(kwargs or (request.jsonrequest or {}))
        if not payload:
            return err(ERR_INVALID_REQUEST, "Empty payload")

        employees = payload if isinstance(payload, list) else [payload]
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

    @cadra_route("/api/v1/integrations/workflow/callback",
                 summary="Apply an external workflow engine's decision to a request",
                 scopes=[SCOPE_INTEGRATIONS_WRITE],
                 idempotent=True)
    def workflow_callback_v1(self, **kwargs):
        data = _unwrap_json_rpc(kwargs or (request.jsonrequest or {}))
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

        req_rec = request.env["request.request"].sudo().search([("name", "=", ref)], limit=1)
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

def _tag_from_path(path):
    """Pick an OpenAPI tag from the URL path: /api/v1/<tag>/... → <Tag>."""
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3:
        return parts[2].capitalize().replace("-", " ")
    return "Other"


def _standard_responses():
    return {
        "200": {
            "description": "OK",
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
