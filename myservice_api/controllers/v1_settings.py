"""
Cadra API v1 — Configuration (asset categories + depreciation settings).

Reads are on `assets:read` so any client can see how a tenant is configured.
WRITES ARE ON `admin`, deliberately: changing a category's useful life restates
book value on every asset in that class, and the calculation conventions restate
the entire register. That is not the same risk as editing one asset, so it does
not share the `assets:write` scope.
"""
import re

from odoo import http
from odoo.http import request

from .utils import (
    ERR_INVALID_REQUEST,
    ERR_CONFLICT,
    ERR_NOT_FOUND,
    SCOPE_ASSETS_READ,
    SCOPE_SETTINGS_WRITE,
    err,
    get_params,
    ok,
)
from .v1 import cadra_route

#: Depreciation policy — what the Depreciation settings screen edits.
_CATEGORY_POLICY_FIELDS = {
    "depreciation_method", "useful_life_months", "declining_rate", "salvage_rate",
}

#: Identity and classification — what the Asset Categories screen edits.
#
# `name` and `code` were deliberately excluded when this controller only served
# the depreciation screen: renaming a category is a taxonomy change, not a
# depreciation setting. Now that there is a categories admin screen that is
# precisely its job, so they are writable here. The split above keeps the two
# screens from editing the same field in two places.
_CATEGORY_IDENTITY_FIELDS = {
    "name", "code", "domain", "description", "sequence", "pm_interval_days",
}

_CATEGORY_WRITABLE = _CATEGORY_POLICY_FIELDS | _CATEGORY_IDENTITY_FIELDS

#: Mirrors the Selection on nrs.asset.category.
_FM_DOMAINS = [
    "building", "plant", "plumbing", "fleet",
    "security", "it", "furniture", "other",
]

_SETTINGS_WRITABLE = {"mode", "proration", "declining_switches_to_straight_line"}


def _serialize_category(c):
    return {
        "id": c.id,
        "name": c.name,
        "code": c.code or None,
        "domain": c.domain or None,
        "description": c.description or None,
        "sequence": c.sequence,
        "asset_count": c.asset_count,
        "depreciating_count": c.asset_depreciating_count,
        "pm_interval_days": c.pm_interval_days or None,
        "depreciation": {
            "method": c.depreciation_method,
            "useful_life_months": c.useful_life_months or None,
            "declining_rate": c.declining_rate or None,
            "salvage_rate": c.salvage_rate or None,
        },
    }


class CadraConfigV1(http.Controller):

    # ── Categories ─────────────────────────────────────────────────

    @cadra_route("/api/v1/asset-categories", method="GET",
                 summary="List asset categories with their depreciation policy",
                 scopes=[SCOPE_ASSETS_READ])
    def list_categories(self, **kwargs):
        """Every category, with the policy its assets inherit.

        Not paginated: the taxonomy is ~20 rows and the settings screen wants
        all of it at once to render a single editable table.
        """
        cats = request.env["nrs.asset.category"].sudo().search([], order="name")
        return [_serialize_category(c) for c in cats]

    @cadra_route("/api/v1/asset-categories/<int:id>", method="PATCH",
                 summary="Update a category's depreciation policy",
                 scopes=[SCOPE_SETTINGS_WRITE],
                 request_schema={
                     "type": "object",
                     "properties": {
                         "depreciation_method": {
                             "type": "string",
                             "enum": ["none", "straight_line",
                                      "declining_balance", "erp_managed"]},
                         "useful_life_months": {"type": "integer"},
                         "declining_rate": {"type": "number"},
                         "salvage_rate": {"type": "number"},
                         "pm_interval_days": {"type": "integer"},
                     },
                 },
                 request_example={
                     "depreciation_method": "straight_line",
                     "useful_life_months": 60,
                     "salvage_rate": 10.0,
                 })
    def patch_category(self, id, **kwargs):
        """Change a category's policy and push it down to the assets that
        follow it. Assets with a per-asset override are left alone."""
        cat = request.env["nrs.asset.category"].sudo().browse(int(id))
        if not cat.exists():
            return err(ERR_NOT_FOUND, f"Category {id} not found", status=404)

        body = get_params()
        vals = {k: v for k, v in body.items() if k in _CATEGORY_WRITABLE}
        rejected = [k for k in body if k not in _CATEGORY_WRITABLE]
        if not vals:
            return err(ERR_INVALID_REQUEST, "No writable fields supplied",
                       details={"rejected_fields": rejected,
                                "writable": sorted(_CATEGORY_WRITABLE)})

        if vals.get("domain") and vals["domain"] not in _FM_DOMAINS:
            return err(ERR_INVALID_REQUEST,
                       f"Unknown FM domain '{vals['domain']}'",
                       details={"allowed": _FM_DOMAINS})

        cat.write(vals)

        # Policy is inherited, so the assets need re-deriving — otherwise the
        # register would keep reporting the old useful life until the next cron.
        assets = request.env["nrs.asset"].sudo().search([
            ("category_id", "=", cat.id), ("use_category_policy", "=", True),
        ])
        assets._sync_policy_from_category()
        assets._apply_depreciation()

        data = _serialize_category(cat)
        data["assets_recomputed"] = len(assets)
        if rejected:
            data["_warnings"] = {"rejected_fields": rejected}
        return data

    @cadra_route("/api/v1/asset-categories", method="POST",
                 summary="Create an asset category",
                 scopes=[SCOPE_SETTINGS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "required": ["name"],
                     "properties": {
                         "name": {"type": "string"},
                         "code": {"type": "string", "nullable": True},
                         "domain": {"type": "string", "enum": _FM_DOMAINS,
                                    "nullable": True},
                         "description": {"type": "string", "nullable": True},
                         "sequence": {"type": "integer"},
                         "pm_interval_days": {"type": "integer"},
                     },
                 },
                 request_example={"name": "Medical Equipment", "code": "MED",
                                  "domain": "other", "pm_interval_days": 180})
    def create_category(self, **kwargs):
        body = get_params()
        name = (body.get("name") or "").strip()
        if not name:
            return err(ERR_INVALID_REQUEST, "`name` is required")

        vals = {k: v for k, v in body.items() if k in _CATEGORY_WRITABLE}
        vals["name"] = name
        if vals.get("domain") and vals["domain"] not in _FM_DOMAINS:
            return err(ERR_INVALID_REQUEST,
                       f"Unknown FM domain '{vals['domain']}'",
                       details={"allowed": _FM_DOMAINS})

        cat = request.env["nrs.asset.category"].sudo().create(vals)
        return _serialize_category(cat)

    @cadra_route("/api/v1/asset-categories/<int:id>", method="DELETE",
                 summary="Delete an asset category (only when it holds no assets)",
                 scopes=[SCOPE_SETTINGS_WRITE])
    def delete_category(self, id, **kwargs):
        """Refuses while assets still reference the category.

        category_id is required on nrs.asset, so deleting one that is in use
        would either orphan those rows or fail at the database. Better to say
        so plainly, with the count, than surface a foreign-key error.
        """
        cat = request.env["nrs.asset.category"].sudo().browse(int(id))
        if not cat.exists():
            return err(ERR_NOT_FOUND, f"Category {id} not found", status=404)

        count = request.env["nrs.asset"].sudo().search_count(
            [("category_id", "=", cat.id)])
        if count:
            return err(ERR_CONFLICT,
                       f"'{cat.name}' still holds {count} asset(s)",
                       status=409,
                       details={"asset_count": count,
                                "hint": "Reassign those assets first."})

        name = cat.name
        cat.unlink()
        return {"deleted": True, "id": int(id), "name": name}

    # ── Branding ───────────────────────────────────────────────────

    #: ir.config_parameter keys the brand endpoint reads. The per-tenant
    #: cadra_brand_* modules seed these with noupdate="1", so writing them here
    #: via set_param is the supported way to change a live tenant — editing the
    #: data file would not touch an existing database.
    _BRAND_PARAMS = {
        "short_name": "cadra.brand_short_name",
        "primary": "cadra.brand_primary",
        "primary_dark": "cadra.brand_primary_dark",
        "logo": "cadra.brand_logo",
    }

    #: A logo rides in every page load as a data URI, so keep it small. Jaiz's
    #: official SVG is ~10KB; this leaves generous headroom without allowing
    #: someone to paste a multi-megabyte PNG into every request.
    _LOGO_MAX_CHARS = 262_144

    _ALLOWED_LOGO_PREFIXES = ("data:image/svg+xml", "data:image/png",
                              "data:image/jpeg", "data:image/webp")

    def _branding_payload(self):
        """Plain dict — NOT the route handler.

        `get_branding` is wrapped by cadra_route/cadra_endpoint, so calling it
        from another handler returns the wrapped response rather than the data.
        Both handlers go through this instead.
        """
        env = request.env
        icp = env["ir.config_parameter"].sudo()
        company = env["res.company"].sudo().search([], limit=1)
        return {
            "name": company.name if company else "Cadra",
            "short_name": icp.get_param(self._BRAND_PARAMS["short_name"], ""),
            "primary": icp.get_param(self._BRAND_PARAMS["primary"], ""),
            "primary_dark": icp.get_param(self._BRAND_PARAMS["primary_dark"], ""),
            "logo": icp.get_param(self._BRAND_PARAMS["logo"], ""),
        }

    @cadra_route("/api/v1/settings/branding", method="GET",
                 summary="Tenant branding (name, colours, logo)",
                 scopes=[SCOPE_ASSETS_READ])
    def get_branding(self, **kwargs):
        return self._branding_payload()

    @cadra_route("/api/v1/settings/branding", method="PATCH",
                 summary="Update tenant branding",
                 scopes=[SCOPE_SETTINGS_WRITE],
                 request_schema={
                     "type": "object",
                     "properties": {
                         "name": {"type": "string"},
                         "short_name": {"type": "string"},
                         "primary": {"type": "string",
                                     "description": "Hex colour, e.g. #004080"},
                         "primary_dark": {"type": "string"},
                         "logo": {"type": "string",
                                  "description": "data: URI, or empty to clear"},
                     },
                 },
                 request_example={"short_name": "Jaiz", "primary": "#004080",
                                  "primary_dark": "#00305F"})
    def patch_branding(self, **kwargs):
        """Writes the brand a tenant is served at runtime.

        One static SPA bundle serves every tenant and fetches GET /api/v1/brand
        at startup, so this takes effect without a rebuild or a deploy — which
        is the whole point of not shipping a module per customer.
        """
        body = get_params()
        allowed = {"name"} | set(self._BRAND_PARAMS)
        vals = {k: v for k, v in body.items() if k in allowed}
        rejected = [k for k in body if k not in allowed]
        if not vals:
            return err(ERR_INVALID_REQUEST, "No writable branding fields supplied",
                       details={"rejected_fields": rejected,
                                "writable": sorted(allowed)})

        for key in ("primary", "primary_dark"):
            colour = (vals.get(key) or "").strip()
            if colour and not re.fullmatch(r"#[0-9A-Fa-f]{6}", colour):
                return err(ERR_INVALID_REQUEST,
                           f"`{key}` must be a 6-digit hex colour like #004080",
                           details={key: colour})
            if colour:
                vals[key] = colour.upper()

        logo = vals.get("logo")
        if logo:
            if len(logo) > self._LOGO_MAX_CHARS:
                return err(ERR_INVALID_REQUEST,
                           "Logo is too large — it is sent with every page load",
                           details={"chars": len(logo),
                                    "max_chars": self._LOGO_MAX_CHARS})
            if not logo.startswith(self._ALLOWED_LOGO_PREFIXES):
                return err(ERR_INVALID_REQUEST,
                           "Logo must be an image data: URI",
                           details={"allowed": list(self._ALLOWED_LOGO_PREFIXES)})

        env = request.env
        icp = env["ir.config_parameter"].sudo()
        for field, key in self._BRAND_PARAMS.items():
            if field in vals:
                icp.set_param(key, vals[field] or "")

        if "name" in vals:
            name = (vals["name"] or "").strip()
            if not name:
                return err(ERR_INVALID_REQUEST, "`name` cannot be blank")
            # This renames the company record, which is what /api/v1/brand
            # reports as the tenant name.
            company = env["res.company"].sudo().search([], limit=1)
            if company:
                company.name = name

        data = self._branding_payload()
        if rejected:
            data["_warnings"] = {"rejected_fields": rejected}
        return data

    # ── Depreciation settings ──────────────────────────────────────

    @cadra_route("/api/v1/settings/depreciation", method="GET",
                 summary="Tenant depreciation settings and data-quality counts",
                 scopes=[SCOPE_ASSETS_READ])
    def get_depreciation_settings(self, **kwargs):
        return request.env["cadra.depreciation.settings"].sudo().get_settings()

    @cadra_route("/api/v1/settings/depreciation", method="PATCH",
                 summary="Update tenant depreciation settings",
                 scopes=[SCOPE_SETTINGS_WRITE],
                 request_schema={
                     "type": "object",
                     "properties": {
                         "mode": {"type": "string",
                                  "enum": ["computed", "erp_managed"]},
                         "proration": {"type": "string",
                                       "enum": ["whole_month", "daily"]},
                         "declining_switches_to_straight_line": {"type": "boolean"},
                     },
                 },
                 request_example={"declining_switches_to_straight_line": True})
    def patch_depreciation_settings(self, **kwargs):
        """Every one of these restates book values across the register, so the
        model recomputes before returning."""
        body = get_params()
        vals = {k: v for k, v in body.items() if k in _SETTINGS_WRITABLE}
        rejected = [k for k in body if k not in _SETTINGS_WRITABLE]
        if not vals:
            return err(ERR_INVALID_REQUEST, "No writable settings supplied",
                       details={"rejected_fields": rejected,
                                "writable": sorted(_SETTINGS_WRITABLE)})

        data = request.env["cadra.depreciation.settings"].sudo().set_settings(vals)
        if rejected:
            data["_warnings"] = {"rejected_fields": rejected}
        return data

    @cadra_route("/api/v1/settings/depreciation/recompute", method="POST",
                 summary="Recompute book values across the register",
                 scopes=[SCOPE_SETTINGS_WRITE],
                 # An action, not a creation — the house default of 201 for
                 # POST-on-a-collection would be wrong here.
                 success_status=200,
                 request_schema={"type": "object", "properties": {}},
                 request_example={})
    def recompute_depreciation(self, **kwargs):
        """On-demand equivalent of the monthly cron — for after a bulk cost
        import, or when someone wants today's figures without waiting."""
        return request.env["cadra.depreciation.settings"].sudo().action_recompute()
