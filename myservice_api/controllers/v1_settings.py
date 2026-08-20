"""
Cadra API v1 — Configuration (asset categories + depreciation settings).

Reads are on `assets:read` so any client can see how a tenant is configured.
WRITES ARE ON `admin`, deliberately: changing a category's useful life restates
book value on every asset in that class, and the calculation conventions restate
the entire register. That is not the same risk as editing one asset, so it does
not share the `assets:write` scope.
"""
from odoo import http
from odoo.http import request

from .utils import (
    ERR_INVALID_REQUEST,
    ERR_CONFLICT,
    ERR_NOT_FOUND,
    SCOPE_ADMIN,
    SCOPE_ASSETS_READ,
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
                 scopes=[SCOPE_ADMIN],
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
                 scopes=[SCOPE_ADMIN],
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
                 scopes=[SCOPE_ADMIN])
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

    # ── Depreciation settings ──────────────────────────────────────

    @cadra_route("/api/v1/settings/depreciation", method="GET",
                 summary="Tenant depreciation settings and data-quality counts",
                 scopes=[SCOPE_ASSETS_READ])
    def get_depreciation_settings(self, **kwargs):
        return request.env["cadra.depreciation.settings"].sudo().get_settings()

    @cadra_route("/api/v1/settings/depreciation", method="PATCH",
                 summary="Update tenant depreciation settings",
                 scopes=[SCOPE_ADMIN],
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
                 scopes=[SCOPE_ADMIN],
                 # An action, not a creation — the house default of 201 for
                 # POST-on-a-collection would be wrong here.
                 success_status=200,
                 request_schema={"type": "object", "properties": {}},
                 request_example={})
    def recompute_depreciation(self, **kwargs):
        """On-demand equivalent of the monthly cron — for after a bulk cost
        import, or when someone wants today's figures without waiting."""
        return request.env["cadra.depreciation.settings"].sudo().action_recompute()
