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

from .query_params import BadFilter, int_filter_terms, parse_bool, parse_enum
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
    selection_values,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route


# What `generic.location.location_type` actually declares
# (crnd-19/generic_location/models/generic_location.py, and the identical
# Odoo 15 copy in dist/). This is the floor under `selection_values()`, not a
# second source of truth — the model is the source of truth, and this tuple
# exists so a typo is still refused on a day the registry cannot be read.
#
# The `_list_domain` docstring used to describe this field as "NRS
# Zone/State/City/etc.", which is not a set the model has ever had: there is
# no `state` and no `city` location_type, and a caller who filtered by either
# received `200 []` and read it as "this tenant has no state offices".
_LOCATION_TYPES = ("building", "floor", "wing", "room", "zone")

# The optional sections `GET /api/v1/locations/<id>` knows how to embed.
_INCLUDE_SECTIONS = ("children", "ancestors")


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
        # Derived from the credential that created the record, never
        # declared (`myservice_api/models/test_fixture.py`). Additive and
        # always present; FALSE on every record created before handoff 26,
        # which is NOT the same statement as "this is a real record".
        "is_test_fixture": loc.is_test_fixture,
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
        # `asset_count` used to sit inside a bare `except Exception:` that
        # set it to 0, with a comment claiming the case was "nrs.asset not
        # installed". It was not: `env.get` ALREADY answers None for a model
        # that is not in the registry, so the handler could only ever fire on
        # a real fault — and it answered "this location holds no assets",
        # which is a complete, confident, wrong number published under
        # `asset_count`. Nothing distinguished it from a location that is
        # genuinely empty.
        #
        # So there is no handler. A module that is not installed is a
        # membership test, and its zero is TRUE. A query that fails raises,
        # and `cadra_route` turns it into the envelope's own 500 — which the
        # caller can tell apart from an answer. This is gated behind
        # `include_counts`, so it costs a single-record GET, not a list.
        Asset = loc.env.get('nrs.asset')
        asset_count = 0
        if Asset is not None and loc.parent_path:
            descendant_locs = loc.search(
                [('parent_path', '=like', loc.parent_path + '%')]
            )
            asset_count = Asset.search_count(
                [('location_id', 'in', descendant_locs.ids)]
            )
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
      - type_id        : exact location-type FK (generic.location.type)
      - location_type  : exact Selection match — one of building, floor,
                         wing, room, zone. Nothing else; see
                         `_LOCATION_TYPES` for what this docstring used to
                         claim and why it was wrong.
      - parent_id      : direct-children filter (use /descendants for deep)
      - country_id     : country (matches stored `_country_id`, not inherited)
      - state_id       : state (matches stored `_state_id`, not inherited)
      - active         : `true` | `false`. Absent or empty still means
                         `true` — the published default is unchanged. A
                         value that is present and unreadable is now a 400
                         rather than silently the active list.
      - has_coordinates: `true` requires lat AND lng; `false` requires at
                         least one of them missing. Both branches now exist.

    Every value this cannot read is REFUSED — `BadFilter`, turned into a 400
    by the listing route — never dropped. `query_params.py` carries the
    reasoning.

    Note on address-field filtering: `street`, `city`, `state_id`, `country_id`
    are compute=l_parent_compute (store=False) — they inherit from the parent
    chain at read time. Searching them silently fails in OR clauses (Odoo
    treats unsearchable terms as always-true, blowing the filter). We search
    the stored backing fields `_state_id`/`_country_id` instead.
    """
    domain = []
    q = (qs.get("q") or "").strip()
    if q:
        # Only STORED fields — the address fields (street/city/state/country) are
        # store=False parent-computed (see docstring), so an OR term on them is
        # treated as always-true and would blow the filter. `_city` and
        # `zone_code` are the stored backing fields we can safely match.
        terms = [
            ("name", "ilike", q),
            ("description", "ilike", q),
            ("zone_code", "ilike", q),
            ("_city", "ilike", q),
        ]
        domain += ["|"] * (len(terms) - 1) + terms
    # `location_type` is an enum and used to be appended raw, so
    # `?location_type=Building` — the capitalisation the label uses in every
    # screen and export — matched no row and answered `200 []`. That reads
    # as "this tenant has no buildings", which for a facilities register is
    # the single most misleading empty answer available. The accepted values
    # come from the model's own Selection so this cannot drift from it.
    location_type = parse_enum(
        "location_type", qs.get("location_type"),
        selection_values("generic.location", "location_type", _LOCATION_TYPES))
    if location_type is not None:
        domain.append(("location_type", "=", location_type))
    # `country_id` and `state_id` are the CLIENT-facing names, and the terms
    # deliberately go on the stored backing fields `_country_id`/`_state_id`
    # instead: the public `country_id`/`state_id` are parent-computed
    # store=False (see the docstring above), Odoo treats an unsearchable
    # term as always-true, and a term that is always true does not narrow a
    # list — it silently widens it back to everything.
    #
    # All four sat inside `except (TypeError, ValueError): pass`, so
    # `?parent_id=headquarters` threw the term away and returned every
    # location in the tenant instead of one branch of the tree.
    domain += int_filter_terms(qs, (
        "type_id",
        "parent_id",
        ("country_id", "_country_id"),
        ("state_id", "_state_id"),
    ))
    # `active` keeps its published default exactly: absent or empty means the
    # active locations. Only the third case changes. `?active=1` used to fall
    # past both branches into an `else` that appended `active = True`, so a
    # caller asking for decommissioned sites was handed the live ones — not
    # the unfiltered list, but the wrong filter, and a plausible-looking
    # answer is the kind nobody goes back to check.
    active = parse_bool("active", qs.get("active"))
    domain.append(("active", "=", True if active is None else active))
    # `has_coordinates` had only a `true` branch. `?has_coordinates=false` —
    # the question that finds the sites nobody has surveyed yet — appended no
    # term at all and returned EVERY location, mapped or not, and so did
    # `?has_coordinates=1`. Report 05's inventory of the silent booleans did
    # not have this one.
    #
    # **Unset is NULL here, not 0.0, and that is the whole subtlety.**
    #
    # Handoff 21 wrote this pair as `latitude != 0 AND longitude != 0` against
    # `latitude = 0 OR longitude = 0`, on the stated grounds that the two
    # "partition the register between them with nothing falling through" —
    # De Morgan, which is sound, plus the premise that these are "plain Floats
    # defaulting to zero", which is not. `latitude` and `longitude` are
    # declared with no `default=`, so a record created without them leaves the
    # COLUMN NULL; nothing ever writes a literal 0.0. On `jaizbankplc`, 250 of
    # 380 locations have NULL coordinates and **zero** have 0.0.
    #
    # Odoo renders `('latitude', '!=', 0.0)` as `(latitude != 0 OR latitude IS
    # NULL)`, so the NULLs landed on the HAS-coordinates side:
    #
    #   ?has_coordinates=true  → 380 of 380, every unmapped site included
    #   ?has_coordinates=false → 0, on a tenant where 250 sites are unmapped
    #
    # `?has_coordinates=false` is "which sites has nobody mapped". It answered
    # **none** — an empty list, which reads as reassurance, to the one question
    # the filter was added to make answerable. That is the same defect the
    # handoff closed, surviving inside its own fix, because the negation was
    # checked against the comment rather than against the column.
    #
    # Both branches now name NULL explicitly. `('f', '=', False)` is Odoo's
    # `IS NULL` and `('f', '!=', False)` its `IS NOT NULL`; pairing each with
    # the 0.0 test covers both spellings of unset. (0/0 is a real point in the
    # Gulf of Guinea, so no genuine site sits on it either way.)
    has_coordinates = parse_bool("has_coordinates", qs.get("has_coordinates"))
    if has_coordinates is True:
        domain += [
            ("latitude", "!=", False), ("latitude", "!=", 0.0),
            ("longitude", "!=", False), ("longitude", "!=", 0.0),
        ]
    elif has_coordinates is False:
        domain += [
            "|", "|", "|",
            ("latitude", "=", False), ("latitude", "=", 0.0),
            ("longitude", "=", False), ("longitude", "=", 0.0),
        ]
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
                     {"name": "location_type",
                      "schema": {"type": "string", "enum": list(_LOCATION_TYPES)},
                      "description": "Exact location_type match"},
                     {"name": "active", "schema": {"type": "boolean"},
                      "description": "Defaults to true when absent"},
                     {"name": "has_coordinates", "schema": {"type": "boolean"},
                      "description": ("true: latitude and longitude both set. "
                                      "false: at least one missing.")},
                     *PAGINATION_QUERY_PARAMS,
                 ])
    def list_locations(self, **kwargs):
        qs = get_params()
        Location = request.env["generic.location"].sudo()
        try:
            domain = _list_domain(qs)
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
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
                      "description": ("Comma-separated optional sections: "
                                      "children, ancestors. An unrecognised "
                                      "section is refused with a 400.")},
                 ])
    def get_location(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        # An unrecognised section used to be dropped in silence, so
        # `?include=childs` returned a 200 with no `children` key on it —
        # indistinguishable, to the caller, from a location that has no
        # children. Same family as the filters above and the same rule: a
        # request we cannot carry out is refused, not half-answered.
        #
        # Through the door rather than a hand-written comparison, and the
        # difference is not style: `tests/test_query_param_guard.py` reads
        # the `parse_enum` call to know this parameter is validated at all.
        # A local `if x not in ALLOWED` is invisible to it, which is how a
        # deleted check goes unnoticed.
        #
        # `token.strip()` is applied to the value PASSED to `parse_enum`, not
        # only to the emptiness test. It used to guard the filter and hand the
        # raw token over, so `?include=children, ancestors` — the way a person
        # types a list — was a 400 naming `" ancestors"` on this route while
        # the identical parameter on `/assets` and `/requests` accepted it.
        # One spelling of a published parameter working on two routes out of
        # three is its own small lie.
        try:
            include = [
                parse_enum("include", token.strip(), _INCLUDE_SECTIONS)
                for token in (kwargs.get("include") or "").split(",")
                if token.strip()
            ]
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
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
