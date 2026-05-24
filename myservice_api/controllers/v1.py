import base64
import hashlib
import hmac
import json
import time

from odoo import fields, http
from odoo.http import request
from odoo.modules.module import get_module_resource


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    raw_bytes = raw.encode("ascii")
    padding = b"=" * (-len(raw_bytes) % 4)
    return base64.urlsafe_b64decode(raw_bytes + padding)


class JwtError(Exception):
    pass


def _jwt_secret(env) -> str:
    return env["ir.config_parameter"].sudo().get_param(
        "myservice_api.jwt_secret",
        "CHANGE_ME__MYservice_API_JWT_SECRET",
    )


def jwt_encode(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}"


def jwt_decode(token: str, secret: str) -> dict:
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


def _json_response(payload: dict, status: int = 200):
    # Kept for HTTP endpoints (docs/spec + download/pdf/csv)
    return request.make_response(
        json.dumps(payload, default=str),
        headers=[("Content-Type", "application/json")],
        status=status,
    )


def _get_bearer_token():
    auth = request.httprequest.headers.get("Authorization", "")
    if not auth:
        return None
    parts = auth.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _set_request_user(uid: int):
    if hasattr(request, "update_env"):
        request.update_env(user=uid)
    else:
        request._env = request.env(user=uid)


def _require_jwt(required_scopes=None):
    required_scopes = required_scopes or []

    token = _get_bearer_token()
    if not token:
        return None, 401, "Unauthorized"

    try:
        claims = jwt_decode(token, _jwt_secret(request.env))
    except Exception:
        return None, 401, "Unauthorized"

    uid = claims.get("uid")
    if not uid:
        return None, 401, "Unauthorized"

    scopes = claims.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()

    for scope in required_scopes:
        if scope not in scopes and "*" not in scopes:
            return None, 403, "Forbidden"

    _set_request_user(int(uid))
    request.jwt_claims = claims
    return claims, None, None


class MyserviceApiV1(http.Controller):
    # ---------------- Auth ----------------
    @http.route("/api/v1/auth/token", type="json", auth="none", methods=["POST"], csrf=False)
    def token(self, **kwargs):
        # Odoo treats application/json as JsonRequest, so keep this as type='json'
        data = kwargs or (request.jsonrequest or {})
        if isinstance(data, dict) and "params" in data and "jsonrpc" in data:
            data = data.get("params") or {}

        client_id = data.get("client_id")
        client_secret = data.get("client_secret")
        if not client_id or not client_secret:
            return {"success": False, "error": "client_id and client_secret required"}

        client = request.env["myservice.api.client"].sudo().search(
            [("client_id", "=", client_id), ("active", "=", True)], limit=1
        )
        if not client or not client.check_client_secret(client_secret):
            return {"success": False, "error": "Invalid client credentials"}

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
        token = jwt_encode(claims, _jwt_secret(request.env))
        client.sudo().write({"last_used_at": fields.Datetime.now(), "last_used_ip": request.httprequest.remote_addr})

        return {
            "success": True,
            "token_type": "Bearer",
            "access_token": token,
            "expires_in": ttl,
            "scope": " ".join(scopes),
        }

    # ---------------- Swagger / OpenAPI ----------------
    @http.route("/api/v1/openapi.yaml", type="http", auth="none", methods=["GET"], csrf=False)
    def openapi_yaml(self, **kwargs):
        spec_path = get_module_resource("myservice_api", "openapi.yaml")
        if not spec_path:
            return request.not_found()
        with open(spec_path, "rb") as f:
            content = f.read()
        return request.make_response(content, headers=[("Content-Type", "text/yaml; charset=utf-8")])

    @http.route("/api/v1/docs", type="http", auth="none", methods=["GET"], csrf=False)
    def swagger_ui(self, **kwargs):
        # CDN-hosted Swagger UI rendering the in-app OpenAPI spec
        spec_url = "/api/v1/openapi.yaml"
        html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Cadra API Docs</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
    <style>
      body {{ margin: 0; background: #fafafa; }}
    </style>
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
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIStandalonePreset
        ],
        layout: "StandaloneLayout"
      }});
    </script>
  </body>
</html>
"""
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])

    # ---------------- Dashboard ----------------
    @http.route("/api/v1/dashboard/kpis", type="json", auth="none", methods=["POST"], csrf=False)
    def dashboard_kpis(self, **kwargs):
        _, status, msg = _require_jwt(["dashboard"])
        if status:
            return {"success": False, "error": msg}
        return {"success": True, "data": request.env["myservice.dashboard"].get_kpis()}

    @http.route("/api/v1/dashboard/map", type="json", auth="none", methods=["POST"], csrf=False)
    def dashboard_map(self, **kwargs):
        _, status, msg = _require_jwt(["dashboard"])
        if status:
            return {"success": False, "error": msg}
        return {"success": True, "data": request.env["myservice.dashboard"].get_map_data()}

    @http.route("/api/v1/dashboard/fleet-command", type="json", auth="none", methods=["POST"], csrf=False)
    def dashboard_fleet_command(self, **kwargs):
        _, status, msg = _require_jwt(["dashboard"])
        if status:
            return {"success": False, "error": msg}
        return {"success": True, "data": request.env["myservice.dashboard"].get_fleet_command()}

    # ---------------- Security ----------------
    @http.route("/api/v1/security/kpis", type="json", auth="none", methods=["POST"], csrf=False)
    def security_kpis(self, **kwargs):
        _, status, msg = _require_jwt(["security"])
        if status:
            return {"success": False, "error": msg}
        from myservice_security.controllers.main import SecurityDashboardController

        return {"success": True, "data": SecurityDashboardController().get_kpis()}

    @http.route("/api/v1/security/map-data", type="json", auth="none", methods=["POST"], csrf=False)
    def security_map_data(self, **kwargs):
        _, status, msg = _require_jwt(["security"])
        if status:
            return {"success": False, "error": msg}
        from myservice_security.controllers.main import SecurityDashboardController

        return {"success": True, "data": SecurityDashboardController().get_map_data()}

    @http.route("/api/v1/security/trend", type="json", auth="none", methods=["POST"], csrf=False)
    def security_trend(self, **kwargs):
        _, status, msg = _require_jwt(["security"])
        if status:
            return {"success": False, "error": msg}
        from myservice_security.controllers.main import SecurityDashboardController

        return {"success": True, "data": SecurityDashboardController().get_trend()}

    @http.route("/api/v1/security/recent", type="json", auth="none", methods=["POST"], csrf=False)
    def security_recent(self, **kwargs):
        _, status, msg = _require_jwt(["security"])
        if status:
            return {"success": False, "error": msg}
        from myservice_security.controllers.main import SecurityDashboardController

        return {"success": True, "data": SecurityDashboardController().get_recent()}

    # ---------------- Barcode ----------------
    @http.route("/api/v1/barcode/lookup", type="json", auth="none", methods=["POST"], csrf=False)
    def barcode_lookup(self, **kwargs):
        _, status, msg = _require_jwt(["assets"])
        if status:
            return {"success": False, "error": msg}
        from myservice_barcode_station.controllers.main import BarcodeStationController

        query = (kwargs or {}).get("query", "")
        return {"success": True, "data": BarcodeStationController().lookup_tag(query=query)}

    @http.route("/api/v1/barcode/kpis", type="json", auth="none", methods=["POST"], csrf=False)
    def barcode_kpis(self, **kwargs):
        _, status, msg = _require_jwt(["assets"])
        if status:
            return {"success": False, "error": msg}
        from myservice_barcode_station.controllers.main import BarcodeStationController

        return {"success": True, "data": BarcodeStationController().get_kpis()}

    @http.route("/api/v1/barcode/recent-tags", type="json", auth="none", methods=["POST"], csrf=False)
    def barcode_recent_tags(self, **kwargs):
        _, status, msg = _require_jwt(["assets"])
        if status:
            return {"success": False, "error": msg}
        from myservice_barcode_station.controllers.main import BarcodeStationController

        data = kwargs or {}
        return {
            "success": True,
            "data": BarcodeStationController().get_recent_tags(
                domain_filter=data.get("domain_filter", ""),
                limit=int(data.get("limit", 50) or 50),
            ),
        }

    @http.route("/api/v1/barcode/print-url", type="json", auth="none", methods=["POST"], csrf=False)
    def barcode_print_url(self, **kwargs):
        _, status, msg = _require_jwt(["assets"])
        if status:
            return {"success": False, "error": msg}
        from myservice_barcode_station.controllers.main import BarcodeStationController

        data = kwargs or {}
        return {
            "success": True,
            "data": BarcodeStationController().get_print_url(
                tag_id=data.get("tag_id"),
                size=data.get("size", "medium"),
            ),
        }

    @http.route("/api/v1/tags/lookup", type="json", auth="none", methods=["POST"], csrf=False)
    def tags_lookup(self, **kwargs):
        _, status, msg = _require_jwt(["assets"])
        if status:
            return {"success": False, "error": msg}
        from myservice_barcode_station.controllers.main import BarcodeStationController

        query = (kwargs or {}).get("query", "")
        return {"success": True, "data": BarcodeStationController().portal_lookup(query=query)}

    # ---------------- Fleet/FM dashboards ----------------
    @http.route("/api/v1/fleet/dashboard", type="json", auth="none", methods=["POST"], csrf=False)
    def fleet_dashboard(self, **kwargs):
        _, status, msg = _require_jwt(["fleet"])
        if status:
            return {"success": False, "error": msg}
        from myservice_fleet_maintenance.controllers.fleet_dashboard import FleetDashboardController

        return {"success": True, "data": FleetDashboardController().fleet_dashboard_data(**(kwargs or {}))}

    @http.route("/api/v1/fm/dashboard", type="json", auth="none", methods=["POST"], csrf=False)
    def fm_dashboard(self, **kwargs):
        _, status, msg = _require_jwt(["fm"])
        if status:
            return {"success": False, "error": msg}
        from myservice_fm_dashboard.controllers.dashboard import FMDashboardController

        return {"success": True, "data": FMDashboardController().dashboard_data(**(kwargs or {}))}

    # ---------------- Homepage (quick submit) ----------------
    @http.route("/api/v1/home/form-data", type="json", auth="none", methods=["POST"], csrf=False)
    def home_form_data(self, **kwargs):
        _, status, msg = _require_jwt(["requests"])
        if status:
            return {"success": False, "error": msg}
        from myservice_website_theme.controllers.api import NRSHomepageAPI

        return {"success": True, "data": NRSHomepageAPI().get_form_data(**(kwargs or {}))}

    @http.route("/api/v1/home/quick-submit", type="json", auth="none", methods=["POST"], csrf=False)
    def home_quick_submit(self, **kwargs):
        _, status, msg = _require_jwt(["requests"])
        if status:
            return {"success": False, "error": msg}
        from myservice_website_theme.controllers.api import NRSHomepageAPI

        return {"success": True, "data": NRSHomepageAPI().quick_submit(**(kwargs or {}))}

    # ---------------- Integrations ----------------
    @http.route("/api/v1/integrations/sap/employee-sync", type="json", auth="none", methods=["POST"], csrf=False)
    def sap_employee_sync(self, **kwargs):
        _, status, msg = _require_jwt(["integrations"])
        if status:
            return {"success": False, "error": msg}

        payload = kwargs or (request.jsonrequest or {})
        if isinstance(payload, dict) and "params" in payload and "jsonrpc" in payload:
            payload = payload.get("params") or {}
        if not payload:
            return {"success": False, "error": "Empty payload"}

        employees = payload if isinstance(payload, list) else [payload]
        results = []
        SyncLog = request.env["nrs.sap.sync.log"].sudo()
        for emp_data in employees:
            employee, log = SyncLog.process_sap_payload(emp_data, sync_type="api")
            results.append(
                {
                    "ir_number": emp_data.get("ir_number") or emp_data.get("userId", "unknown"),
                    "status": log.status,
                    "employee_id": employee.id if employee else None,
                    "changes": log.changes_applied or "",
                }
            )
        return {"success": True, "processed": len(results), "results": results}

    @http.route("/api/v1/assets/export", type="json", auth="none", methods=["POST"], csrf=False)
    def assets_export(self, **kwargs):
        _, status, msg = _require_jwt(["assets"])
        if status:
            return {"success": False, "error": msg}

        assets = request.env["nrs.asset"].sudo().search([])
        result = []
        for a in assets:
            result.append(
                {
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
                    "last_updated": str(fields.Datetime.now()),
                }
            )
        return {"success": True, "count": len(result), "assets": result, "exported_at": str(fields.Datetime.now())}

    @http.route("/api/v1/assets/export.csv", type="http", auth="none", methods=["GET"], csrf=False)
    def assets_export_csv(self, **kwargs):
        _, status, msg = _require_jwt(["assets"])
        if status:
            return request.make_response(msg, status=status)

        import csv
        import io

        assets = request.env["nrs.asset"].sudo().search([])
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Asset Code",
                "Name",
                "Category",
                "Condition",
                "State",
                "Location",
                "Assigned To",
                "IR Number",
                "Department",
                "Assignment Date",
                "Retrieval Flag",
                "Serial Number",
            ]
        )
        for a in assets:
            writer.writerow(
                [
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
                ]
            )
        return request.make_response(
            output.getvalue(),
            headers=[
                ("Content-Type", "text/csv"),
                ("Content-Disposition", "attachment; filename=nrs_assets.csv"),
            ],
        )

    @http.route("/api/v1/integrations/workflow/callback", type="json", auth="none", methods=["POST"], csrf=False)
    def workflow_callback_v1(self, **kwargs):
        _, status, msg = _require_jwt(["workflow"])
        if status:
            return {"success": False, "error": msg}

        data = kwargs or (request.jsonrequest or {})
        if isinstance(data, dict) and "params" in data and "jsonrpc" in data:
            data = data.get("params") or {}
        if not isinstance(data, dict):
            return {"success": False, "error": "Invalid payload"}

        ref = data.get("reference", "")
        workspace_ref = data.get("workspace_ref", "")
        outcome = (data.get("outcome") or data.get("status") or "").lower().strip()
        payment_ref = data.get("payment_ref", "")
        comment = data.get("comment") or data.get("reason") or data.get("message") or ""

        if not ref:
            return {"success": False, "error": "reference field is required"}
        if outcome not in ("approved", "rejected", "queried"):
            return {"success": False, "error": f"Unknown outcome '{outcome}'"}

        req_rec = request.env["request.request"].sudo().search([("name", "=", ref)], limit=1)
        if not req_rec:
            return {"success": False, "error": f"Request '{ref}' not found"}

        log = request.env["workflow.dispatch.log"].sudo().create(
            {
                "request_id": req_rec.id,
                "direction": "inbound",
                "status": outcome,
                "workspace_ref": workspace_ref,
                "response_received": json.dumps(data, default=str),
            }
        )

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

        return {"success": True, "message": f"Outcome '{outcome}' applied to request '{ref}'"}
