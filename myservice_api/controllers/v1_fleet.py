"""
Cadra API v1 — Fleet resource.

Exposes `fleet.vehicle` as a searchable, paginated list so the React Fleet page
can run real server-side search instead of the in-browser mock. The serialized
shape stays REST-clean (backend field names); the frontend maps it onto its
richer FleetVehicle view type, filling NRS-specific fields it doesn't have yet.
"""
from odoo import http
from odoo.http import request

from .query_params import BadFilter, parse_bool, parse_enum, parse_int
from .utils import (
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    SCOPE_DASHBOARDS_READ,
    err,
    get_params,
    ok,
    paginate,
    parse_limit,
    selection_values,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route


# The floor under the `fuel_type` filter. `fleet.vehicle.fuel_type` is Odoo
# core's `FUEL_TYPES` and no module in this repository extends it, so the
# accepted values are read off the model at request time and this tuple is
# only what the check falls back to if that read fails. Keeping a copy here
# is what lets the filter refuse a typo even then — a validator that
# disables itself on failure puts `?fuel_type=petrol` straight back to
# answering `200 []`.
_FUEL_TYPES = (
    "diesel", "gasoline", "full_hybrid", "plug_in_hybrid_diesel",
    "plug_in_hybrid_gasoline", "cng", "lpg", "hydrogen", "electric",
)


def _fleet_domain(qs):
    domain = []
    q = (qs.get("q") or "").strip()
    if q:
        # Plate / VIN / vehicle name plus the human relations users search by:
        # driver, model, brand, home location.
        terms = [
            ("name", "ilike", q),
            ("license_plate", "ilike", q),
            ("vin_sn", "ilike", q),
            ("driver_id.name", "ilike", q),
            ("model_id.name", "ilike", q),
            ("model_id.brand_id.name", "ilike", q),
            ("home_location_id.name", "ilike", q),
        ]
        domain += ["|"] * (len(terms) - 1) + terms

    # `?state_id=disposed` used to be swallowed by an
    # `except (TypeError, ValueError): pass` that appended no term, so a
    # caller asking for one fleet state received the whole fleet and had
    # nothing in the response to tell them so.
    state_id = parse_int("state_id", qs.get("state_id"))
    if state_id is not None:
        domain.append(("state_id", "=", state_id))
    # `fuel_type` was appended raw, so `?fuel_type=petrol` — the ordinary
    # British spelling of `gasoline`, and the likeliest thing anybody here
    # types — answered `200 []`, which reads as "the fleet runs nothing on
    # petrol" rather than as "that is not a value I know".
    fuel_type = parse_enum(
        "fuel_type", qs.get("fuel_type"),
        selection_values("fleet.vehicle", "fuel_type", _FUEL_TYPES))
    if fuel_type is not None:
        domain.append(("fuel_type", "=", fuel_type))
    # `?is_staff_bus=1` fell through both branches, appended nothing, and
    # returned every vehicle on the register — staff buses and the rest
    # together — to a caller asking for exactly one of the two. An empty list
    # reads as "no matches"; a full list reads as an answer.
    is_bus = parse_bool("is_staff_bus", qs.get("is_staff_bus"))
    if is_bus is not None:
        domain.append(("is_staff_bus", "=", is_bus))
    return domain


def _ref(rec):
    return {"id": rec.id, "name": rec.name} if rec else None


def serialize_vehicle(v):
    return {
        "id": v.id,
        "name": v.name or "",
        "license_plate": v.license_plate or "",
        "vin_sn": v.vin_sn or "",
        "model": v.model_id.name if v.model_id else "",
        "brand": v.model_id.brand_id.name if (v.model_id and v.model_id.brand_id) else "",
        "model_year": v.model_year or "",
        "color": v.color or "",
        "fuel_type": v.fuel_type or "",
        "odometer": v.odometer or 0.0,
        "seats": v.seats or 0,
        "state": v.state_id.name if v.state_id else "",
        "driver": _ref(v.driver_id) if v.driver_id else None,
        "home_location": _ref(v.home_location_id) if v.home_location_id else None,
        "is_staff_bus": bool(v.is_staff_bus),
        "maintenance_status": v.maintenance_status or "",
        "last_service_date": str(v.last_service_date) if v.last_service_date else "",
        "next_service_date": str(v.next_service_date) if v.next_service_date else "",
        "next_service_odometer": v.next_service_odometer or 0.0,
    }


class CadraFleetV1(http.Controller):

    @cadra_route("/api/v1/fleet", method="GET",
                 summary="List fleet vehicles with search and cursor pagination",
                 scopes=[SCOPE_DASHBOARDS_READ],
                 query_params=[
                     {"name": "q", "schema": {"type": "string"},
                      "description": "Free-text across plate, VIN, name, driver, "
                                     "model, brand, home location"},
                     {"name": "state_id", "schema": {"type": "integer"},
                      "description": "fleet.vehicle.state id"},
                     # Declared as a bare string until now; the enum is the
                     # set the model has always accepted, written down.
                     {"name": "fuel_type", "schema": {"type": "string",
                      "enum": list(_FUEL_TYPES)},
                      "description": "fleet.vehicle fuel type"},
                     {"name": "is_staff_bus", "schema": {"type": "boolean"},
                      "description": "true = only staff buses, "
                                     "false = only other vehicles"},
                     *PAGINATION_QUERY_PARAMS,
                 ])
    def list_fleet(self, **kwargs):
        qs = get_params()
        Vehicle = request.env["fleet.vehicle"].sudo()
        try:
            domain = _fleet_domain(qs)
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        limit = parse_limit(qs)
        page, next_cursor, total = paginate(
            Vehicle, domain, limit=limit, cursor=qs.get("cursor"),
        )
        return ok(
            data=[serialize_vehicle(v) for v in page],
            pagination={
                "next_cursor": next_cursor,
                "previous_cursor": None,
                "total_estimate": total,
            },
        )

    @cadra_route("/api/v1/fleet/<int:id>", method="GET",
                 summary="Get a single fleet vehicle by id",
                 scopes=[SCOPE_DASHBOARDS_READ])
    def get_fleet_vehicle(self, id, **kwargs):
        rec = request.env["fleet.vehicle"].sudo().browse(int(id))
        if not rec.exists():
            return err(ERR_NOT_FOUND, f"Vehicle {id} not found", status=404)
        return serialize_vehicle(rec)
