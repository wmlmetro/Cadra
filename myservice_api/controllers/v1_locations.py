"""
Cadra API v1 — Locations resource (REST shape per PRD §7.4).

Implements the subset of PRD §7.4 that maps cleanly onto the existing
`generic.location` model (from dist/generic_location). The model is
field-rich but missing a few PRD-specified attributes:

  - `code` (PRD §7.2 required, unique per tenant)  -> not present;
    the `/by-code/{code}` endpoint is omitted from MVP.
  - `lifecycle_state` (planned/active/under_renovation/decommissioned/
    archived, PRD §7.3) -> not present; closest analog is the boolean
    `active`. The `/transition` endpoint is omitted from MVP.
  - `characteristics` (per-tenant JSON) -> not present.
  - `external_references` (per-tenant JSON) -> not present.

These gaps land in a future schema-extension module
(`myservice_locations_cadra`) once the platform-vs-extension lines are
ratified.
"""
from odoo import http
from odoo.http import request

from .utils import (
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    SCOPE_LOCATIONS_READ,
    SCOPE_LOCATIONS_WRITE,
    err,
    get_params,
    ok,
    paginate,
    parse_limit,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route


# ─── serializer ──────────────────────────────────────────────────────

def serialize_location(loc, *, include=(), include_counts=False):
    """Map a generic.location record to the Cadra-shaped dict.

    `include` is a set/sequence of optional expansions:
      - "children"  : embeds direct children as a list of {id, name}
      - "ancestors" : embeds ancestor chain (root → parent) as a list

    `include_counts` toggles on relatively expensive per-location aggregate
    counters (currently just `asset_count`). The list endpoint serializes
    many records per request, so we keep this off by default and only
    enable it on single-record GETs.

    Address fields surface the *effective* values (computed from parents
    when use_parent flags are set). The internal "_*" cache fields are
    not exposed.
    """
    include = set(include or ())
    data = {
        "id": loc.id,
        "name": loc.name,
        "type": {
            "id": loc.type_id.id,
            "name": loc.type_id.name,
        } if loc.type_id else None,
        "location_type": loc.location_type or None,  # NRS-specific Selection
        "description": loc.description or None,
        "parent_id": loc.parent_id.id if loc.parent_id else None,
        "parent_path": loc.parent_path or None,  # materialized path "1/4/12/"
        "active": loc.active,
        "address": {
            "street": loc.street or None,
            "street2": loc.street2 or None,
            "zip": loc.zip or None,
            "city": loc.city or None,
            "state": {"id": loc.state_id.id, "name": loc.state_id.name} if loc.state_id else None,
            "country": {"id": loc.country_id.id, "name": loc.country_id.name} if loc.country_id else None,
        },
        "coordinates": {
            "latitude": loc.latitude or None,
            "longitude": loc.longitude or None,
        } if (loc.latitude or loc.longitude) else None,
        # NRS-specific extras
        "extras": {
            "zone_code": loc.zone_code or None,
            "floor_number": loc.floor_number if loc.floor_number else None,
            "building_id": loc.building_id.id if loc.building_id else None,
        },
        "partner_id": loc.partner_id.id if loc.partner_id else None,
        "child_count": loc.child_count,
        "child_all_count": loc.child_all_count,
        # Audit (Odoo built-ins — map to PRD names)
        "created_at": loc.create_date.isoformat() if loc.create_date else None,
        "updated_at": loc.write_date.isoformat() if loc.write_date else None,
        "created_by": {"id": loc.create_uid.id, "name": loc.create_uid.name} if loc.create_uid else None,
        "updated_by": {"id": loc.write_uid.id, "name": loc.write_uid.name} if loc.write_uid else None,
    }
    if include_counts:
        # Asset rollup across this location and every descendant.
        # `parent_path` on generic.location is a slash-separated id chain
        # (e.g. "1/4/12/") — descendants share this prefix, so a single
        # =like clause picks up self + all descendants.
        # Gated behind `include_counts` because list endpoints fan this
        # out across hundreds of rows; only single-record GETs pay it.
        asset_count = 0
        try:
            Asset = loc.env.get('nrs.asset')
            if Asset is not None and loc.parent_path:
                descendant_locs = loc.search(
                    [('parent_path', '=like', loc.parent_path + '%')]
                )
                asset_count = Asset.search_count(
                    [('location_id', 'in', descendant_locs.ids)]
                )
        except Exception:
            # nrs.asset not installed, or transient query error — fall back
            # to 0 rather than 500-ing the whole serialization.
            asset_count = 0
        data['asset_count'] = asset_count
    if "children" in include:
        data["children"] = [{"id": c.id, "name": c.name} for c in loc.child_ids]
    if "ancestors" in include:
        data["ancestors"] = [
            {"id": a.id, "name": a.name}
            for a in _ancestors(loc)
        ]
    return data


def _ancestors(loc):
    """Root-down ancestor chain (excluding self)."""
    if not loc.parent_path:
        return loc.browse([])
    ids = [int(x) for x in loc.parent_path.strip("/").split("/")]
    ids = ids[:-1]  # drop self
    return loc.browse(ids).sorted(lambda r: loc.parent_path.find(f"/{r.id}/"))


# ─── domain builder ──────────────────────────────────────────────────

def _list_domain(qs):
    """Translate query-string filters into an Odoo domain.

    Query string params (all optional):
      - q              : substring match on `name` (case-insensitive)
      - type_id        : exact location-type FK
      - location_type  : exact Selection match (NRS Zone/State/City/etc.)
      - parent_id      : direct-children filter (use /descendants for deep)
      - country_id     : country (matches stored `_country_id`, not inherited)
      - state_id       : state (matches stored `_state_id`, not inherited)
      - active         : 'true' | 'false' (default true)
      - has_coordinates: 'true' to require lat AND lng

    Note on address-field filtering: `street`, `city`, `state_id`, `country_id`
    are compute=l_parent_compute (store=False) — they inherit from the parent
    chain at read time. Searching them silently fails in OR clauses (Odoo
    treats unsearchable terms as always-true, blowing the filter). We search
    the stored backing fields `_state_id`/`_country_id` instead.
    """
    domain = []
    q = (qs.get("q") or "").strip()
    if q:
        domain.append(("name", "ilike", q))
    if qs.get("location_type"):
        domain.append(("location_type", "=", qs["location_type"]))
    for fld in ("type_id", "parent_id"):
        val = qs.get(fld)
        if val not in (None, "", "null"):
            try:
                domain.append((fld, "=", int(val)))
            except (TypeError, ValueError):
                pass
    for client_fld, stored_fld in (("country_id", "_country_id"), ("state_id", "_state_id")):
        val = qs.get(client_fld)
        if val not in (None, "", "null"):
            try:
                domain.append((stored_fld, "=", int(val)))
            except (TypeError, ValueError):
                pass
    active_filter = qs.get("active")
    if active_filter in ("false", "False", False):
        domain.append(("active", "=", False))
    elif active_filter in ("true", "True", True):
        domain.append(("active", "=", True))
    else:
        domain.append(("active", "=", True))
    if qs.get("has_coordinates") in ("true", "True", True):
        domain += [("latitude", "!=", 0.0), ("longitude", "!=", 0.0)]
    return domain


# ─── writable allow-list for POST/PATCH ──────────────────────────────

_WRITABLE_FIELDS = {
    "name", "description", "active", "parent_id", "type_id", "location_type",
    "street", "street2", "zip", "city", "state_id", "country_id",
    "latitude", "longitude", "zone_code", "floor_number", "building_id",
    "partner_id",
}


def _filter_writable(body):
    if not isinstance(body, dict):
        return {}, []
    vals = {k: v for k, v in body.items() if k in _WRITABLE_FIELDS}
    rejected = [k for k in body if k not in _WRITABLE_FIELDS]
    return vals, rejected


def _browse_or_404(loc_id):
    rec = request.env["generic.location"].sudo().browse(int(loc_id))
    if not rec.exists():
        return None, err(ERR_NOT_FOUND, f"Location {loc_id} not found", status=404)
    return rec, None


# ─── controller ──────────────────────────────────────────────────────

class CadraLocationsV1(http.Controller):

    # ── List: GET /api/v1/locations ────────────────────────────────

    @cadra_route("/api/v1/locations", method="GET",
                 summary="List locations with filters and cursor pagination",
                 scopes=[SCOPE_LOCATIONS_READ],
                 query_params=[
                     {"name": "q", "schema": {"type": "string"},
                      "description": "Free-text search across name and code"},
                     {"name": "type_id", "schema": {"type": "integer"}},
                     {"name": "parent_id", "schema": {"type": "integer"}},
                     {"name": "country_id", "schema": {"type": "integer"}},
                     {"name": "state_id", "schema": {"type": "integer"}},
                     {"name": "location_type", "schema": {"type": "string"}},
                     {"name": "active", "schema": {"type": "boolean"}},
                     {"name": "has_coordinates", "schema": {"type": "boolean"}},
                     *PAGINATION_QUERY_PARAMS,
                 ])
    def list_locations(self, **kwargs):
        qs = get_params()
        Location = request.env["generic.location"].sudo()
        domain = _list_domain(qs)
        limit = parse_limit(qs)
        page, next_cursor, total = paginate(
            Location, domain,
            limit=limit, cursor=qs.get("cursor"),
        )
        return ok(
            data=[serialize_location(l) for l in page],
            pagination={
                "next_cursor": next_cursor,
                "previous_cursor": None,
                "total_estimate": total,
            },
        )

    # ── Get single: GET /api/v1/locations/<id> ─────────────────────

    @cadra_route("/api/v1/locations/<int:id>", method="GET",
                 summary="Get a single location by id",
                 scopes=[SCOPE_LOCATIONS_READ],
                 query_params=[
                     {"name": "include", "schema": {"type": "string"},
                      "description": "Comma-separated optional sections: children, ancestors"},
                 ])
    def get_location(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        include = [s.strip() for s in (kwargs.get("include") or "").split(",") if s.strip()]
        return serialize_location(rec, include=include, include_counts=True)

    # ── Create: POST /api/v1/locations ─────────────────────────────

    @cadra_route("/api/v1/locations", method="POST",
                 summary="Create a new location",
                 scopes=[SCOPE_LOCATIONS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "required": ["name"],
                     "properties": {
                         "name": {"type": "string"},
                         "description": {"type": "string", "nullable": True},
                         "active": {"type": "boolean", "default": True},
                         "parent_id": {"type": "integer", "nullable": True,
                                       "description": "Parent generic.location id"},
                         "type_id": {"type": "integer", "nullable": True,
                                     "description": "generic.location.type id"},
                         "location_type": {"type": "string", "nullable": True,
                                           "description": "NRS Selection (zone/state/city/etc.)"},
                         "street": {"type": "string", "nullable": True},
                         "street2": {"type": "string", "nullable": True},
                         "zip": {"type": "string", "nullable": True},
                         "city": {"type": "string", "nullable": True},
                         "state_id": {"type": "integer", "nullable": True,
                                      "description": "res.country.state id"},
                         "country_id": {"type": "integer", "nullable": True,
                                        "description": "res.country id"},
                         "latitude": {"type": "number", "format": "float", "nullable": True},
                         "longitude": {"type": "number", "format": "float", "nullable": True},
                         "zone_code": {"type": "string", "nullable": True},
                         "floor_number": {"type": "integer", "nullable": True},
                         "building_id": {"type": "integer", "nullable": True},
                         "partner_id": {"type": "integer", "nullable": True},
                     },
                 },
                 request_example={
                     "name": "Block C - 3rd Floor",
                     "description": "Engineering wing",
                     "parent_id": 12,
                     "type_id": 4,
                     "location_type": "floor",
                     "street": "10 Cadra Way",
                     "city": "Abuja",
                     "country_id": 156,
                     "latitude": 9.0765,
                     "longitude": 7.3986,
                     "floor_number": 3,
                 })
    def create_location(self, **kwargs):
        body = get_params()
        vals, rejected = _filter_writable(body)
        if not vals.get("name"):
            return err(ERR_INVALID_REQUEST, "`name` is required",
                       details={"rejected_fields": rejected} if rejected else None)
        rec = request.env["generic.location"].sudo().create(vals)
        out = serialize_location(rec)
        if rejected:
            out["_warnings"] = {"rejected_fields": rejected}
        return out

    # ── Patch: PATCH /api/v1/locations/<id> ────────────────────────

    @cadra_route("/api/v1/locations/<int:id>", method="PATCH",
                 summary="Partial update of a location",
                 scopes=[SCOPE_LOCATIONS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "description": ("Any subset of the writable fields from POST "
                                     "/api/v1/locations. Unknown fields are "
                                     "rejected and reported under `_warnings`."),
                     "properties": {
                         "name": {"type": "string"},
                         "description": {"type": "string", "nullable": True},
                         "active": {"type": "boolean"},
                         "parent_id": {"type": "integer", "nullable": True},
                         "street": {"type": "string"},
                         "city": {"type": "string"},
                         "latitude": {"type": "number", "format": "float"},
                         "longitude": {"type": "number", "format": "float"},
                     },
                 },
                 request_example={
                     "description": "Engineering wing — renamed after 2026 reorg",
                     "active": True,
                 })
    def patch_location(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        vals, rejected = _filter_writable(body)
        if not vals and not rejected:
            return err(ERR_INVALID_REQUEST, "Empty patch — no writable fields supplied")
        if vals:
            rec.write(vals)
        out = serialize_location(rec)
        if rejected:
            out["_warnings"] = {"rejected_fields": rejected}
        return out

    # ── Hierarchy: GET /api/v1/locations/<id>/{children,ancestors,descendants} ─

    @cadra_route("/api/v1/locations/<int:id>/children", method="GET",
                 summary="Direct children of a location",
                 scopes=[SCOPE_LOCATIONS_READ])
    def children(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        return [serialize_location(c) for c in rec.child_ids]

    @cadra_route("/api/v1/locations/<int:id>/ancestors", method="GET",
                 summary="Ancestor chain (root → parent) of a location",
                 scopes=[SCOPE_LOCATIONS_READ])
    def ancestors(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        return [serialize_location(a) for a in _ancestors(rec)]

    @cadra_route("/api/v1/locations/<int:id>/descendants", method="GET",
                 summary="All descendants of a location, paginated (?limit, ?cursor)",
                 scopes=[SCOPE_LOCATIONS_READ])
    def descendants(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        qs = get_params()
        Location = request.env["generic.location"].sudo()
        domain = [("parent_path", "=like", f"{rec.parent_path}%"), ("id", "!=", rec.id)]
        limit = parse_limit(qs)
        page, next_cursor, total = paginate(
            Location, domain,
            limit=limit, cursor=qs.get("cursor"),
        )
        return ok(
            data=[serialize_location(d) for d in page],
            pagination={
                "next_cursor": next_cursor,
                "previous_cursor": None,
                "total_estimate": total,
            },
        )
