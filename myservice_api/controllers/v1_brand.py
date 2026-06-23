# -*- coding: utf-8 -*-
"""Public per-tenant branding endpoint.

GET /api/v1/brand — returns the branding for the tenant resolved from the
request host (Odoo's dbfilter binds request.env to the matching database
BEFORE this controller runs, so on gtb.cadra.ng this returns DB `gtb`'s brand
and on staging.app.cadra.ng it returns DB `staging`'s).

Consumed by the React frontend at startup so ONE static build is branded per
host at runtime (name, colour, logo) — no per-client build. Public + cached;
contains no sensitive data.
"""
import json

from odoo import http
from odoo.http import request


class CadraBrandController(http.Controller):

    @http.route("/api/v1/brand", type="http", auth="none",
                methods=["GET"], csrf=False, save_session=False)
    def brand(self, **kw):
        env = request.env
        icp = env["ir.config_parameter"].sudo()
        company = env["res.company"].sudo().search([], limit=1)

        data = {
            "name": company.name if company else "Cadra",
            "short_name": icp.get_param("cadra.brand_short_name", ""),
            "primary": icp.get_param("cadra.brand_primary", ""),
            "primary_dark": icp.get_param("cadra.brand_primary_dark", ""),
            # data: URI (e.g. SVG); empty → frontend uses its bundled fallback.
            "logo": icp.get_param("cadra.brand_logo", ""),
        }

        return request.make_response(
            json.dumps({"data": data}),
            headers=[
                ("Content-Type", "application/json; charset=utf-8"),
                # Brand rarely changes; let the browser/CDN cache briefly.
                ("Cache-Control", "public, max-age=300"),
                # Same-origin in prod; permissive for the dev server.
                ("Access-Control-Allow-Origin", "*"),
            ],
        )
