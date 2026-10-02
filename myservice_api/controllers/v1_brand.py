# -*- coding: utf-8 -*-
"""Public per-tenant branding + login-challenge config endpoint.

GET /api/v1/brand — returns the branding for the tenant resolved from the
request host (Odoo's dbfilter binds request.env to the matching database
BEFORE this controller runs, so on gtb.cadra.ng this returns DB `gtb`'s brand
and on staging.app.cadra.ng it returns DB `staging`'s).

Consumed by the React frontend at startup so ONE static build is branded per
host at runtime (name, colour, logo) — no per-client build. It also reports
whether this tenant enforces Turnstile, so the same bundle shows the login
challenge on the tenants that check it and nowhere else. Public + cached;
contains no sensitive data.
"""
import base64
import binascii
import json
from urllib.parse import unquote_to_bytes

from odoo import http
from odoo.http import request

from .utils import turnstile_secret


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
            # Whether THIS tenant enforces Cloudflare Turnstile on login, so
            # the shared bundle renders the challenge only where the API will
            # actually check it. Never exposes the secret itself — just
            # whether one is set. Note the Cache-Control below: flipping a
            # tenant on can take up to 5 minutes to reach a browser.
            "turnstile": bool(turnstile_secret(env)),
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

    @http.route("/api/v1/brand/logo", type="http", auth="none",
                methods=["GET"], csrf=False, save_session=False)
    def brand_logo(self, **kw):
        """The tenant's logo as an IMAGE, for the places a `data:` URI will
        not do — the invitation and password-reset letters (handoff 43 §1b).

        `cadra.brand_logo` is stored as a `data:image/...` URI because the
        app inlines it; Gmail and Outlook strip inline-data images from
        mail, so the letter references this URL instead. A tenant whose
        brand module supplies no logo answers 404 and the letter prints a
        wordmark — never a broken image. Same cache policy as `/brand`.
        """
        icp = request.env["ir.config_parameter"].sudo()
        raw = icp.get_param("cadra.brand_logo", "") or ""
        parsed = _parse_data_uri(raw)
        if not parsed:
            return request.make_response(
                "No logo is set for this tenant.", status=404,
                headers=[("Content-Type", "text/plain; charset=utf-8"),
                         ("Cache-Control", "public, max-age=300")])
        mime, payload = parsed
        return request.make_response(
            payload,
            headers=[("Content-Type", mime),
                     ("Content-Length", str(len(payload))),
                     ("Cache-Control", "public, max-age=300"),
                     # An administrator-set SVG served from the app origin:
                     # it may carry no script and may not be sniffed.
                     ("Content-Security-Policy",
                      "default-src 'none'; style-src 'unsafe-inline'"),
                     ("X-Content-Type-Options", "nosniff"),
                     ("Access-Control-Allow-Origin", "*")])


_LOGO_MIMES = ("image/svg+xml", "image/png", "image/jpeg", "image/webp")


def _parse_data_uri(value):
    """`(mime, bytes)` from a `data:image/...` URI, or None. Accepts the two
    shapes the branding route stores (`v1_settings.py`): base64, and the
    percent-encoded SVG some brand modules ship."""
    if not value.startswith("data:"):
        return None
    head, sep, data = value[5:].partition(",")
    if not sep:
        return None
    parts = head.split(";")
    mime = parts[0].strip().lower()
    if mime not in _LOGO_MIMES:
        return None
    try:
        if "base64" in [p.strip().lower() for p in parts[1:]]:
            payload = base64.b64decode(data, validate=False)
        else:
            payload = unquote_to_bytes(data)
    except (ValueError, binascii.Error):
        return None
    return (mime, payload) if payload else None
