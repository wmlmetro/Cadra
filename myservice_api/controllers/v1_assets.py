"""
Cadra API v1 — Assets resource (REST shape per PRD §8.10).

Implements the subset of PRD §8 that maps onto `nrs.asset`. The in-house
model has a simpler 5-state lifecycle (active/in_repair/disposed/
transferred/missing) versus PRD §8.4's 10-state machine
(procured/received/tagged/deployed/in_maintenance/in_transit/idle/lost/
retired/disposed). The full state machine, the immutable custodianship
chain (PRD §8.5), and the disposal-approval workflow (PRD §8.9) are
deferred to a future schema-extension pass.

The move endpoint persists its side-effect by creating an
`nrs.asset.transfer` row. Transfer-custody uses `mail.thread` instead
because `nrs.asset.transfer._check_locations` forbids same-location
transfers.
"""
from odoo import fields as odoo_fields, http
from odoo.http import request

from .utils import (
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    SCOPE_ASSETS_READ,
    SCOPE_ASSETS_WRITE,
    SCOPE_DASHBOARDS_READ,
    err,
    get_params,
    ok,
    paginate,
    parse_limit,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route


# ─── small helpers ───────────────────────────────────────────────────

def _ref(rec, name_field="name"):
    if not rec:
        return None
    return {"id": rec.id, "name": getattr(rec, name_field, None) or rec.display_name}


def _date(v):
    return v.isoformat() if v else None


def _serialize_depreciation(a):
    """The depreciation block of an asset's `financial` object (PRD §8.6).

    Method names match the published enum: straight_line | declining_balance |
    none | erp_managed. For erp_managed the figures are supplied by the
    tenant's ERP and Cadra does not compute them (NRS spec §6.2).
    """
    return {
        "method": a.depreciation_method,
        "useful_life_months": a.useful_life_months or None,
        "declining_rate": a.declining_rate or None,
        "salvage_value": a.salvage_value or None,
        "depreciable_cost": a.depreciable_cost or None,
        "start_date": _date(a.depreciation_start_date),
        "start_date_source": a.depreciation_start_source or None,
        "start_date_is_estimated": a.depreciation_start_is_estimated,
        "accumulated_depreciation": a.accumulated_depreciation or None,
        "current_book_value": a.current_book_value or None,
        "state": a.depreciation_state,
        "end_date": _date(a.depreciation_end_date),
        "uses_category_policy": a.use_category_policy,
    }


# ─── serializer ──────────────────────────────────────────────────────

def serialize_asset(a, *, include=()):
    """Map an nrs.asset record to a Cadra-shaped dict.

    `include` accepts:
      - "transfers"   : embed nrs.asset.transfer history (last 20)
      - "pm"          : embed PM schedule summaries
      - "children"    : embed direct sub-assets (id+name)
    """
    include = set(include or ())
    data = {
        "id": a.id,
        "asset_code": a.asset_code,
        "tag": a.asset_tag or None,
        "legacy_asset_code": a.legacy_asset_code or None,
        "name": a.name,
        "serial_number": a.serial_number or None,
        "make": a.make or None,
        "model": a.model_name or None,
        "manufacturer": a.manufacturer or None,
        "category": _ref(a.category_id),
        "subcategory": _ref(a.subcategory_id),
        "asset_type": _ref(a.asset_type_id),
        "asset_level": a.asset_level or None,
        "domain": a.domain or None,
        "parent_asset": _ref(a.parent_id),
        "child_count": len(a.child_ids),
        "current_location": _ref(a.location_id),
        "location_hierarchy": {
            "building": _ref(a.building_id),
            "floor": _ref(a.floor_id),
            "room": _ref(a.room_id),
        },
        "floor_room": a.floor_room or None,
        "address_display": a.address_display or None,
        "coordinates": {
            "latitude_display": a.latitude_display or None,
            "longitude_display": a.longitude_display or None,
        } if (a.latitude_display or a.longitude_display) else None,
        "current_custodian": _ref(a.custodian_id),
        "department": a.department or None,
        "condition": a.condition,
        "state": a.state,
        "financial": {
            "currency": _ref(a.currency_id),
            "purchase_value": a.purchase_value or None,
            "replacement_cost": a.replacement_cost or None,
            "acquisition_cost": a.acquisition_cost or None,
            # Legacy hand-entered figure. Superseded by
            # financial.depreciation.current_book_value, which is derived.
            "current_value": a.current_value or None,
            "depreciation": _serialize_depreciation(a),
        },
        "dates": {
            "purchase_date": _date(a.purchase_date),
            "warranty_expiry": _date(a.warranty_expiry),
            "acquisition_date": _date(a.acquisition_date),
            "disposal_date": _date(a.disposal_date),
            "last_verified_date": _date(a.last_verified_date),
            "next_service_date": _date(a.next_service_date),
        },
        "disposal_reason": a.disposal_reason or None,
        "maintenance_vendor": _ref(a.maintenance_vendor_id),
        "is_verified": a.is_verified,
        "pm_count": a.pm_count,
        "request_count": a.request_count,
        "notes": a.notes or None,
        "created_at": _date(a.create_date),
        "updated_at": _date(a.write_date),
        "created_by": _ref(a.create_uid),
        "updated_by": _ref(a.write_uid),
    }
    if "transfers" in include:
        data["transfers"] = [
            {
                "id": t.id,
                "reference": t.name,
                "from_location": _ref(t.from_location_id),
                "to_location": _ref(t.to_location_id),
                "from_custodian": _ref(t.from_custodian_id),
                "to_custodian": _ref(t.to_custodian_id),
                "transfer_date": _date(t.transfer_date),
                "state": t.state,
                "reason": t.reason or None,
            }
            for t in a.transfer_ids.sorted(lambda r: r.transfer_date or odoo_fields.Date.today(), reverse=True)[:20]
        ]
    if "children" in include:
        data["children"] = [{"id": c.id, "name": c.name, "asset_code": c.asset_code} for c in a.child_ids]
    if "pm" in include:
        data["pm_schedules"] = [
            {"id": p.id, "name": p.name if hasattr(p, "name") else None,
             "next_due_date": _date(p.next_due_date), "active": p.active}
            for p in a.pm_schedule_ids
        ]
    return data


# ─── domain builder ──────────────────────────────────────────────────

def _list_domain(qs):
    domain = []
    q = (qs.get("q") or "").strip()
    if q:
        domain += ["|", "|", "|",
                   ("name", "ilike", q),
                   ("asset_code", "ilike", q),
                   ("asset_tag", "ilike", q),
                   ("serial_number", "ilike", q)]
    for fld in ("category_id", "subcategory_id", "location_id", "building_id",
                "floor_id", "room_id", "custodian_id", "parent_id"):
        val = qs.get(fld)
        if val not in (None, "", "null"):
            try:
                domain.append((fld, "=", int(val)))
            except (TypeError, ValueError):
                pass
    for fld in ("state", "condition", "domain", "asset_level"):
        val = qs.get(fld)
        if val:
            domain.append((fld, "=", val))
    if qs.get("is_verified") in ("true", "True", True):
        domain.append(("is_verified", "=", True))
    elif qs.get("is_verified") in ("false", "False", False):
        domain.append(("is_verified", "=", False))
    return domain


# ─── writable-fields allow-list ──────────────────────────────────────

_WRITABLE_FIELDS = {
    "name", "asset_tag", "legacy_asset_code", "serial_number",
    "make", "model_name", "manufacturer",
    "category_id", "subcategory_id", "asset_type_id", "asset_level", "domain",
    "parent_id",
    "building_id", "floor_id", "room_id", "location_id",
    "custodian_id", "department",
    "condition", "state",
    "currency_id", "purchase_date", "warranty_expiry",
    "purchase_value", "replacement_cost",
    "acquisition_date", "acquisition_cost", "current_value",
    "disposal_date", "disposal_reason",
    # Depreciation policy (PRD §8.6)
    "use_category_policy", "depreciation_method", "useful_life_months",
    "declining_rate", "salvage_rate", "depreciation_start_date",
    # Writable so an external ERP can feed figures for erp_managed assets.
    # Cadra overwrites these for any computed method.
    "accumulated_depreciation", "current_book_value",
    "maintenance_vendor_id",
    "last_verified_date", "verification_notes",
    "notes",
}


def _filter_writable(body):
    if not isinstance(body, dict):
        return {}, []
    vals = {k: v for k, v in body.items() if k in _WRITABLE_FIELDS}
    rejected = [k for k in body if k not in _WRITABLE_FIELDS]
    return vals, rejected


def _browse_or_404(asset_id):
    rec = request.env["nrs.asset"].sudo().browse(int(asset_id))
    if not rec.exists():
        return None, err(ERR_NOT_FOUND, f"Asset {asset_id} not found", status=404)
    return rec, None


# ─── controller ──────────────────────────────────────────────────────

class CadraAssetsV1(http.Controller):

    # ── List: GET /api/v1/assets ───────────────────────────────────

    @cadra_route("/api/v1/assets", method="GET",
                 summary="List assets with filters and cursor pagination",
                 scopes=[SCOPE_ASSETS_READ],
                 query_params=[
                     {"name": "q", "schema": {"type": "string"},
                      "description": "Free-text search across name, asset_code, asset_tag, serial_number"},
                     {"name": "category_id", "schema": {"type": "integer"}},
                     {"name": "subcategory_id", "schema": {"type": "integer"}},
                     {"name": "location_id", "schema": {"type": "integer"}},
                     {"name": "building_id", "schema": {"type": "integer"}},
                     {"name": "floor_id", "schema": {"type": "integer"}},
                     {"name": "room_id", "schema": {"type": "integer"}},
                     {"name": "custodian_id", "schema": {"type": "integer"}},
                     {"name": "parent_id", "schema": {"type": "integer"}},
                     {"name": "state", "schema": {"type": "string",
                      "enum": ["active", "in_repair", "disposed", "transferred", "missing"]}},
                     {"name": "condition", "schema": {"type": "string",
                      "enum": ["new", "good", "fair", "poor", "damaged"]}},
                     {"name": "domain", "schema": {"type": "string"}},
                     {"name": "asset_level", "schema": {"type": "string"}},
                     {"name": "is_verified", "schema": {"type": "boolean"}},
                     *PAGINATION_QUERY_PARAMS,
                 ])
    def list_assets(self, **kwargs):
        qs = get_params()
        Asset = request.env["nrs.asset"].sudo()
        domain = _list_domain(qs)
        limit = parse_limit(qs)
        page, next_cursor, total = paginate(
            Asset, domain,
            limit=limit, cursor=qs.get("cursor"),
        )
        return ok(
            data=[serialize_asset(a) for a in page],
            pagination={
                "next_cursor": next_cursor,
                "previous_cursor": None,
                "total_estimate": total,
            },
        )

    # ── Get single: GET /api/v1/assets/<id> ────────────────────────

    @cadra_route("/api/v1/assets/<int:id>", method="GET",
                 summary="Get a single asset by id",
                 scopes=[SCOPE_ASSETS_READ],
                 query_params=[
                     {"name": "include", "schema": {"type": "string"},
                      "description": "Comma-separated optional sections: transfers, pm, children"},
                 ])
    def get_asset(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        include = [s.strip() for s in (kwargs.get("include") or "").split(",") if s.strip()]
        return serialize_asset(rec, include=include)

    # ── Get by tag: GET /api/v1/assets/by-tag/<tag> ────────────────

    @cadra_route("/api/v1/assets/by-tag/<string:tag>", method="GET",
                 summary="Get a single asset by asset_tag (or asset_code as fallback)",
                 scopes=[SCOPE_ASSETS_READ],
                 query_params=[
                     {"name": "include", "schema": {"type": "string"},
                      "description": "Comma-separated optional sections: transfers, pm, children"},
                 ])
    def get_asset_by_tag(self, tag, **kwargs):
        Asset = request.env["nrs.asset"].sudo()
        rec = Asset.search([("asset_tag", "=", tag)], limit=1) \
            or Asset.search([("asset_code", "=", tag)], limit=1)
        if not rec:
            return err(ERR_NOT_FOUND, f"No asset with tag or code '{tag}'", status=404)
        include = [s.strip() for s in (kwargs.get("include") or "").split(",") if s.strip()]
        return serialize_asset(rec, include=include)

    # ── Create: POST /api/v1/assets ────────────────────────────────

    @cadra_route("/api/v1/assets", method="POST",
                 summary="Create a new asset (asset_code auto-generated if omitted)",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "required": ["name"],
                     "properties": {
                         "name": {"type": "string"},
                         "asset_tag": {"type": "string", "nullable": True,
                                       "description": "Physical tag/barcode"},
                         "legacy_asset_code": {"type": "string", "nullable": True},
                         "serial_number": {"type": "string", "nullable": True},
                         "make": {"type": "string", "nullable": True},
                         "model_name": {"type": "string", "nullable": True},
                         "manufacturer": {"type": "string", "nullable": True},
                         "category_id": {"type": "integer", "nullable": True},
                         "subcategory_id": {"type": "integer", "nullable": True},
                         "asset_type_id": {"type": "integer", "nullable": True},
                         "asset_level": {"type": "string", "nullable": True},
                         "domain": {"type": "string", "nullable": True},
                         "parent_id": {"type": "integer", "nullable": True},
                         "building_id": {"type": "integer", "nullable": True},
                         "floor_id": {"type": "integer", "nullable": True},
                         "room_id": {"type": "integer", "nullable": True},
                         "location_id": {"type": "integer", "nullable": True},
                         "custodian_id": {"type": "integer", "nullable": True,
                                          "description": "hr.employee id"},
                         "department": {"type": "string", "nullable": True},
                         "condition": {"type": "string",
                                       "enum": ["new", "good", "fair", "poor", "damaged"]},
                         "state": {"type": "string",
                                   "enum": ["active", "in_repair", "disposed",
                                            "transferred", "missing"]},
                         "currency_id": {"type": "integer", "nullable": True},
                         "purchase_date": {"type": "string", "format": "date", "nullable": True},
                         "warranty_expiry": {"type": "string", "format": "date", "nullable": True},
                         "purchase_value": {"type": "number", "nullable": True},
                         "replacement_cost": {"type": "number", "nullable": True},
                         "acquisition_date": {"type": "string", "format": "date", "nullable": True},
                         "acquisition_cost": {"type": "number", "nullable": True},
                         "current_value": {"type": "number", "nullable": True},
                         "maintenance_vendor_id": {"type": "integer", "nullable": True},
                         "notes": {"type": "string", "nullable": True},
                     },
                 },
                 request_example={
                     "name": "Dell Latitude 7430",
                     "asset_tag": "NRS-LT-00421",
                     "serial_number": "5XJZ8T3",
                     "make": "Dell",
                     "model_name": "Latitude 7430",
                     "manufacturer": "Dell Inc.",
                     "category_id": 7,
                     "location_id": 12,
                     "custodian_id": 105,
                     "condition": "new",
                     "state": "active",
                     "purchase_date": "2026-05-10",
                     "purchase_value": 1850.00,
                 })
    def create_asset(self, **kwargs):
        body = get_params()
        vals, rejected = _filter_writable(body)
        if not vals.get("name"):
            return err(ERR_INVALID_REQUEST, "`name` is required",
                       details={"rejected_fields": rejected} if rejected else None)
        rec = request.env["nrs.asset"].sudo().create(vals)
        out = serialize_asset(rec)
        if rejected:
            out["_warnings"] = {"rejected_fields": rejected}
        return out

    # ── Patch: PATCH /api/v1/assets/<id> ───────────────────────────

    @cadra_route("/api/v1/assets/<int:id>", method="PATCH",
                 summary="Partial update of an asset",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "description": ("Any subset of the writable fields from POST "
                                     "/api/v1/assets. Unknown fields are rejected "
                                     "and reported under `_warnings`."),
                     "properties": {
                         "name": {"type": "string"},
                         "condition": {"type": "string",
                                       "enum": ["new", "good", "fair", "poor", "damaged"]},
                         "state": {"type": "string",
                                   "enum": ["active", "in_repair", "disposed",
                                            "transferred", "missing"]},
                         "notes": {"type": "string"},
                         "custodian_id": {"type": "integer"},
                         "location_id": {"type": "integer"},
                     },
                 },
                 request_example={
                     "condition": "fair",
                     "notes": "Hinge cracked — flagged for replacement.",
                 })
    def patch_asset(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        vals, rejected = _filter_writable(body)
        if not vals and not rejected:
            return err(ERR_INVALID_REQUEST, "Empty patch — no writable fields supplied")
        if vals:
            rec.write(vals)
        out = serialize_asset(rec)
        if rejected:
            out["_warnings"] = {"rejected_fields": rejected}
        return out

    # ── Move action: POST /api/v1/assets/<id>/move ─────────────────

    @cadra_route("/api/v1/assets/<int:id>/move", method="POST",
                 summary="Move asset to a new location (creates an nrs.asset.transfer row)",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "required": ["to_location_id"],
                     "properties": {
                         "to_location_id": {"type": "integer",
                                            "description": "Destination generic.location id"},
                         "reason": {"type": "string", "nullable": True},
                     },
                 },
                 request_example={
                     "to_location_id": 47,
                     "reason": "Reassigned to new project room",
                 })
    def move_asset(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        try:
            to_loc_id = int(body.get("to_location_id") or 0)
        except (TypeError, ValueError):
            return err(ERR_INVALID_REQUEST, "`to_location_id` must be an integer")
        if not to_loc_id:
            return err(ERR_INVALID_REQUEST, "`to_location_id` is required")
        to_loc = request.env["generic.location"].sudo().browse(to_loc_id)
        if not to_loc.exists():
            return err(ERR_NOT_FOUND, f"Destination location {to_loc_id} not found", status=404)

        from_loc = rec.location_id
        if from_loc.id == to_loc.id:
            return err(ERR_INVALID_REQUEST, "Asset is already at the requested location",
                       details={"current_location_id": from_loc.id})

        Transfer = request.env["nrs.asset.transfer"].sudo()
        seq = request.env["ir.sequence"].next_by_code("nrs.asset.transfer") or "/"
        transfer = Transfer.create({
            "name": seq,
            "asset_id": rec.id,
            "from_location_id": from_loc.id or False,
            "to_location_id": to_loc.id,
            "from_custodian_id": rec.custodian_id.id or False,
            "to_custodian_id": rec.custodian_id.id or False,
            "transfer_date": odoo_fields.Date.today(),
            "reason": body.get("reason") or "",
            "state": "done",
        })
        rec.write({"location_id": to_loc.id})

        return {
            "asset": serialize_asset(rec),
            "transfer": {
                "id": transfer.id,
                "reference": transfer.name,
                "from_location": _ref(from_loc),
                "to_location": _ref(to_loc),
            },
        }

    # ── Transfer custody: POST /api/v1/assets/<id>/transfer-custody ─

    @cadra_route("/api/v1/assets/<int:id>/transfer-custody", method="POST",
                 summary="Transfer custody to a different hr.employee",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "required": ["to_custodian_id"],
                     "properties": {
                         "to_custodian_id": {"type": "integer",
                                             "description": "New custodian hr.employee id"},
                         "reason": {"type": "string", "nullable": True},
                     },
                 },
                 request_example={
                     "to_custodian_id": 218,
                     "reason": "Previous custodian left the company",
                 })
    def transfer_custody(self, id, **kwargs):
        """Reassign the asset's custodian. The audit trail comes via Odoo's
        mail.thread auto-logging (custodian_id has tracking=True) plus an
        explicit message_post carrying the optional reason. We deliberately
        do NOT use nrs.asset.transfer here — that model has a NOT-NULL
        location-change constraint and is location-move-centric."""
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        try:
            to_cust_id = int(body.get("to_custodian_id") or 0)
        except (TypeError, ValueError):
            return err(ERR_INVALID_REQUEST, "`to_custodian_id` must be an integer")
        if not to_cust_id:
            return err(ERR_INVALID_REQUEST, "`to_custodian_id` is required")
        to_cust = request.env["hr.employee"].sudo().browse(to_cust_id)
        if not to_cust.exists():
            return err(ERR_NOT_FOUND, f"Employee {to_cust_id} not found", status=404)

        from_cust = rec.custodian_id
        if from_cust.id == to_cust.id:
            return err(ERR_INVALID_REQUEST, "Asset is already assigned to that custodian",
                       details={"current_custodian_id": from_cust.id})

        rec.write({"custodian_id": to_cust.id})
        reason = body.get("reason") or ""
        msg_body = (f"Custody transferred via API: "
                    f"<b>{from_cust.name or 'unassigned'}</b> → <b>{to_cust.name}</b>")
        if reason:
            msg_body += f"<br/>Reason: {reason}"
        msg = rec.message_post(body=msg_body, message_type="comment",
                               subtype_xmlid="mail.mt_note")

        return {
            "asset": serialize_asset(rec),
            "custody_change": {
                "from_custodian": _ref(from_cust),
                "to_custodian": _ref(to_cust),
                "reason": reason or None,
                "message_id": msg.id if msg else None,
            },
        }

    # ── Register report: GET /api/v1/reports/depreciation ──────────

    @cadra_route("/api/v1/reports/depreciation", method="GET",
                 summary="Register-wide depreciation totals and breakdowns",
                 scopes=[SCOPE_DASHBOARDS_READ],
                 query_params=[
                     {"name": "category_id", "schema": {"type": "integer"},
                      "description": "Restrict the report to one asset category"},
                 ])
    def depreciation_report(self, **kwargs):
        """Totals, per-category breakdown, and the two data-quality counts that
        matter in practice: assets whose start date was inferred, and assets
        with a depreciation method but no cost to depreciate."""
        domain = []
        raw_cat = kwargs.get("category_id")
        if raw_cat:
            try:
                domain.append(("category_id", "=", int(raw_cat)))
            except (TypeError, ValueError):
                return err(ERR_INVALID_REQUEST, "`category_id` must be an integer",
                           details={"category_id": raw_cat})
        return request.env["nrs.asset"].sudo().get_depreciation_report(domain)

    # ── Depreciation schedule: GET /api/v1/assets/<id>/depreciation ─

    @cadra_route("/api/v1/assets/<int:id>/depreciation", method="GET",
                 summary="Depreciation schedule and summary for one asset",
                 scopes=[SCOPE_ASSETS_READ],
                 query_params=[
                     {"name": "as_of", "schema": {"type": "string", "format": "date"},
                      "description": "Truncate the schedule at this date for a "
                                     "point-in-time view (YYYY-MM-DD)"},
                 ])
    def get_asset_depreciation(self, id, **kwargs):
        """The period-by-period board (PRD §8.6).

        Generated on demand rather than stored: the schedule is a pure function
        of cost, salvage, start date, life and method, so persisting ~12k x ~60
        rows would be derivation with a staleness risk attached. It also makes
        `as_of` a genuine point-in-time view (PRD §13.4) for free.

        Returns an empty `periods` list for methods Cadra does not compute
        (`none`, `erp_managed`) — that is a valid state, not an error.
        """
        rec, error = _browse_or_404(id)
        if error:
            return error

        as_of = None
        raw = (kwargs.get("as_of") or "").strip()
        if raw:
            try:
                as_of = odoo_fields.Date.from_string(raw)
            except (ValueError, TypeError):
                return err(ERR_INVALID_REQUEST,
                           "`as_of` must be a date in YYYY-MM-DD format",
                           details={"as_of": raw})

        periods = rec.get_depreciation_schedule(as_of=as_of)
        return {
            "asset": {"id": rec.id, "asset_code": rec.asset_code, "name": rec.name},
            "summary": _serialize_depreciation(rec),
            "as_of": _date(as_of),
            "currency": _ref(rec.currency_id),
            "period_count": len(periods),
            "periods": [{
                "sequence": p["sequence"],
                "period_end": _date(p["period_end"]),
                "charge": p["charge"],
                "accumulated_depreciation": p["accumulated"],
                "book_value": p["book_value"],
            } for p in periods],
        }
