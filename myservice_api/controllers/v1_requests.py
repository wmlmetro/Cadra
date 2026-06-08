"""
Cadra API v1 — Service Requests resource (REST shape per PRD §9.10).

Implements the MVP subset of PRD §9 on the vendored `request.request`
model from generic_request. The 13-status workflow PRD describes maps
onto the per-tenant `request.stage` records. Stage transitions go
through `request.stage.route` — the model already exposes
`api_move_request(route_id)` for that.

Deferred from PRD §9.10 endpoints (not in this MVP):
  - /attachments — handled via the mail.thread message_post path for now
  - /approve     — needs approval engine wiring; myservice_workflow
                   has WorkSpace integration but no general approval API
  - /link        — related requests
  - /escalate    — custom workflow concept
  - /reopen      — rare, can patch via /transition for now
  - /search      — basic filters cover this
  - /queue       — UI-specific concept
  - /export      — bulk operation
"""
from odoo import http
from odoo.http import request

from .utils import (
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    SCOPE_REQUESTS_READ,
    SCOPE_REQUESTS_WRITE,
    err,
    get_params,
    ok,
    paginate,
    parse_limit,
)
from .v1 import cadra_route


# ─── small helpers ───────────────────────────────────────────────────

def _ref(rec, name_field="name"):
    if not rec:
        return None
    return {"id": rec.id, "name": getattr(rec, name_field, None) or rec.display_name}


def _dt(v):
    return v.isoformat() if v else None


def _strip_html(v):
    return v or None


# ─── serializer ──────────────────────────────────────────────────────

def serialize_request(r, *, include=()):
    """Map a request.request record to a Cadra-shaped dict.

    `include` accepts:
      - "routes"   : embed available outbound stage transitions
      - "events"   : embed last 20 activity events (request.event rows)
      - "messages" : embed last 20 mail.thread messages
    """
    include = set(include or ())
    data = {
        "id": r.id,
        "reference": r.name,
        "type": _ref(r.type_id),
        "category": _ref(r.category_id),
        "stage": {
            "id": r.stage_id.id,
            "name": r.stage_id.name,
            "code": r.stage_id.code,
            "type_code": r.stage_type_id.code if r.stage_type_id else None,
            "closed": bool(r.closed),
        },
        "kanban_state": r.kanban_state,
        "priority": r.priority,
        "impact": r.impact,
        "urgency": r.urgency,
        "active": r.active,
        "subject": (r.request_text or "")[:255] if r.request_text else None,
        "request_text": _strip_html(r.request_text),
        "response_text": _strip_html(r.response_text),
        "author": _ref(r.author_id),
        "assignee": _ref(r.user_id),
        "partner": _ref(r.partner_id),
        "service": _ref(r.service_id),
        "parent_id": r.parent_id.id if r.parent_id else None,
        "tags": [{"id": t.id, "name": t.name} for t in r.tag_ids],
        "deadline_date": _dt(r.deadline_date),
        "dates": {
            "created": _dt(r.date_created),
            "assigned": _dt(r.date_assigned),
            "moved": _dt(r.date_moved),
            "closed": _dt(r.date_closed),
        },
        "location": _ref(r.location_id) if "location_id" in r._fields else None,
        "vehicle": _ref(r.vehicle_id) if "vehicle_id" in r._fields else None,
        "asset": _ref(r.nrs_asset_id) if "nrs_asset_id" in r._fields else None,
        "created_at": _dt(r.create_date),
        "updated_at": _dt(r.write_date),
        "created_by": _ref(r.create_uid),
        "updated_by": _ref(r.write_uid),
    }

    if "routes" in include:
        routes = r.stage_id.route_out_ids if r.stage_id else r.env["request.stage.route"].browse([])
        data["available_routes"] = [
            {
                "id": rt.id,
                "name": rt.name,
                "from_stage": _ref(rt.stage_from_id),
                "to_stage": _ref(rt.stage_to_id),
            }
            for rt in routes
        ]
    if "events" in include:
        events = r.request_event_ids.sorted("date", reverse=True)[:20]
        data["events"] = [
            {
                "id": e.id,
                "date": _dt(e.date),
                "type_id": e.event_type_id.id if hasattr(e, "event_type_id") and e.event_type_id else None,
                "user": _ref(e.user_id) if hasattr(e, "user_id") else None,
            }
            for e in events
        ]
    if "messages" in include:
        msgs = r.message_ids.sorted("date", reverse=True)[:20]
        data["messages"] = [
            {
                "id": m.id,
                "date": _dt(m.date),
                "author": _ref(m.author_id),
                "subject": m.subject,
                "body_html": m.body,
                "message_type": m.message_type,
            }
            for m in msgs
        ]
    return data


# ─── domain builder ──────────────────────────────────────────────────

def _list_domain(qs):
    """Translate query-string filters into an Odoo domain."""
    domain = []
    q = (qs.get("q") or "").strip()
    if q:
        domain.append(("name", "ilike", q))
    for fld in ("type_id", "category_id", "stage_id", "user_id",
                "author_id", "partner_id", "service_id", "parent_id"):
        val = qs.get(fld)
        if val not in (None, "", "null"):
            try:
                domain.append((fld, "=", int(val)))
            except (TypeError, ValueError):
                pass
    Req = request.env["request.request"]
    if "location_id" in Req._fields:
        val = qs.get("location_id")
        if val not in (None, "", "null"):
            try:
                domain.append(("location_id", "=", int(val)))
            except (TypeError, ValueError):
                pass
    if "nrs_asset_id" in Req._fields:
        val = qs.get("asset_id") or qs.get("nrs_asset_id")
        if val not in (None, "", "null"):
            try:
                domain.append(("nrs_asset_id", "=", int(val)))
            except (TypeError, ValueError):
                pass
    for fld in ("priority", "kanban_state"):
        val = qs.get(fld)
        if val:
            domain.append((fld, "=", val))
    closed = qs.get("closed")
    if closed in ("true", "True", True):
        domain.append(("closed", "=", True))
    elif closed in ("false", "False", False):
        domain.append(("closed", "=", False))
    if qs.get("has_deadline") in ("true", "True", True):
        domain.append(("deadline_date", "!=", False))
    return domain


# ─── writable allow-list (excludes stage_id — use /transition) ──────

_WRITABLE_FIELDS = {
    "type_id", "category_id",
    "priority", "impact", "urgency", "kanban_state",
    "request_text", "response_text",
    "author_id", "user_id", "partner_id", "service_id",
    "parent_id", "deadline_date",
    "tag_ids",
    "location_id", "vehicle_id", "nrs_asset_id",
}


def _filter_writable(body):
    if not isinstance(body, dict):
        return {}, []
    Req = request.env["request.request"]
    vals = {}
    rejected = []
    for k, v in body.items():
        if k in _WRITABLE_FIELDS and k in Req._fields:
            vals[k] = v
        else:
            rejected.append(k)
    return vals, rejected


def _browse_or_404(req_id):
    rec = request.env["request.request"].sudo().browse(int(req_id))
    if not rec.exists():
        return None, err(ERR_NOT_FOUND, f"Request {req_id} not found", status=404)
    return rec, None


# ─── controller ──────────────────────────────────────────────────────

class CadraRequestsV1(http.Controller):

    # ── List: GET /api/v1/requests ─────────────────────────────────

    @cadra_route("/api/v1/requests", method="GET",
                 summary="List service requests (?q, ?type_id, ?category_id, ?stage_id, ?user_id, ?priority, ?closed, ?location_id, ?asset_id, ?limit, ?cursor)",
                 scopes=[SCOPE_REQUESTS_READ])
    def list_requests(self, **kwargs):
        qs = get_params()
        Req = request.env["request.request"].sudo()
        domain = _list_domain(qs)
        limit = parse_limit(qs)
        page, next_cursor, total = paginate(
            Req, domain,
            limit=limit, cursor=qs.get("cursor"),
        )
        return ok(
            data=[serialize_request(r) for r in page],
            pagination={
                "next_cursor": next_cursor,
                "previous_cursor": None,
                "total_estimate": total,
            },
        )

    # ── Get single: GET /api/v1/requests/<id> ──────────────────────

    @cadra_route("/api/v1/requests/<int:id>", method="GET",
                 summary="Get a single request by id (?include=routes,events,messages)",
                 scopes=[SCOPE_REQUESTS_READ])
    def get_request(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        include = [s.strip() for s in (kwargs.get("include") or "").split(",") if s.strip()]
        return serialize_request(rec, include=include)

    # ── Get by reference: GET /api/v1/requests/by-reference/<ref> ──

    @cadra_route("/api/v1/requests/by-reference/<string:reference>", method="GET",
                 summary="Get a single request by reference (e.g. INCIDENT-052026-0000002)",
                 scopes=[SCOPE_REQUESTS_READ])
    def get_request_by_reference(self, reference, **kwargs):
        rec = request.env["request.request"].sudo().search(
            [("name", "=", reference)], limit=1)
        if not rec:
            return err(ERR_NOT_FOUND, f"No request with reference '{reference}'", status=404)
        include = [s.strip() for s in (kwargs.get("include") or "").split(",") if s.strip()]
        return serialize_request(rec, include=include)

    # ── Create: POST /api/v1/requests ──────────────────────────────

    @cadra_route("/api/v1/requests", method="POST",
                 summary="Create a new request (name + stage auto-assigned from type)",
                 scopes=[SCOPE_REQUESTS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "required": ["type_id", "request_text"],
                     "properties": {
                         "type_id": {"type": "integer", "description": "request.type id"},
                         "category_id": {"type": "integer", "nullable": True},
                         "request_text": {"type": "string",
                                          "description": "Issue description (HTML allowed)"},
                         "priority": {"type": "string",
                                      "enum": ["0", "1", "2", "3"],
                                      "description": "0=low, 1=normal, 2=high, 3=urgent"},
                         "impact": {"type": "string", "nullable": True},
                         "urgency": {"type": "string", "nullable": True},
                         "author_id": {"type": "integer", "nullable": True,
                                       "description": "res.partner id"},
                         "user_id": {"type": "integer", "nullable": True,
                                     "description": "Initial assignee (res.users id)"},
                         "partner_id": {"type": "integer", "nullable": True},
                         "service_id": {"type": "integer", "nullable": True},
                         "parent_id": {"type": "integer", "nullable": True},
                         "deadline_date": {"type": "string", "format": "date-time", "nullable": True},
                         "tag_ids": {"type": "array", "items": {"type": "integer"},
                                     "nullable": True},
                         "location_id": {"type": "integer", "nullable": True},
                         "vehicle_id": {"type": "integer", "nullable": True},
                         "nrs_asset_id": {"type": "integer", "nullable": True,
                                          "description": "Related nrs.asset id"},
                     },
                 },
                 request_example={
                     "type_id": 1,
                     "category_id": 3,
                     "request_text": "Air conditioner in conference room B-2 is leaking water onto the floor.",
                     "priority": "2",
                     "service_id": 4,
                     "location_id": 12,
                     "nrs_asset_id": 87,
                 })
    def create_request(self, **kwargs):
        body = get_params()
        vals, rejected = _filter_writable(body)
        if not vals.get("type_id"):
            return err(ERR_INVALID_REQUEST, "`type_id` is required",
                       details={"rejected_fields": rejected} if rejected else None)
        if not vals.get("request_text"):
            return err(ERR_INVALID_REQUEST, "`request_text` is required (the issue description)",
                       details={"rejected_fields": rejected} if rejected else None)
        rec = request.env["request.request"].sudo().create(vals)
        out = serialize_request(rec, include=["routes"])
        if rejected:
            out["_warnings"] = {"rejected_fields": rejected}
        return out

    # ── Patch: PATCH /api/v1/requests/<id> ─────────────────────────

    @cadra_route("/api/v1/requests/<int:id>", method="PATCH",
                 summary="Partial update of a request (stage changes go through /transition)",
                 scopes=[SCOPE_REQUESTS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "description": ("Any subset of the writable fields from POST "
                                     "/api/v1/requests. `stage_id` is intentionally "
                                     "excluded — use POST .../transition. Unknown "
                                     "fields are reported under `_warnings`."),
                     "properties": {
                         "priority": {"type": "string", "enum": ["0", "1", "2", "3"]},
                         "impact": {"type": "string"},
                         "urgency": {"type": "string"},
                         "kanban_state": {"type": "string",
                                          "enum": ["normal", "done", "blocked"]},
                         "response_text": {"type": "string"},
                         "user_id": {"type": "integer"},
                         "deadline_date": {"type": "string", "format": "date-time"},
                         "tag_ids": {"type": "array", "items": {"type": "integer"}},
                     },
                 },
                 request_example={
                     "priority": "3",
                     "kanban_state": "blocked",
                     "response_text": "Waiting on parts ETA from vendor.",
                 })
    def patch_request(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        vals, rejected = _filter_writable(body)
        if not vals and not rejected:
            return err(ERR_INVALID_REQUEST, "Empty patch — no writable fields supplied")
        if vals:
            rec.write(vals)
        out = serialize_request(rec)
        if rejected:
            out["_warnings"] = {"rejected_fields": rejected,
                                "hint": "Use POST /api/v1/requests/<id>/transition to change stage_id"}
        return out

    # ── Assign: POST /api/v1/requests/<id>/assign ──────────────────

    @cadra_route("/api/v1/requests/<int:id>/assign", method="POST",
                 summary="Assign request to a res.users (body: {user_id: int|null})",
                 scopes=[SCOPE_REQUESTS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "required": ["user_id"],
                     "properties": {
                         "user_id": {"type": "integer", "nullable": True,
                                     "description": "res.users id; null to unassign"},
                     },
                 },
                 request_example={"user_id": 42})
    def assign_request(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        if "user_id" not in body:
            return err(ERR_INVALID_REQUEST, "`user_id` is required (use null to unassign)")
        user_id = body.get("user_id")
        if user_id in (None, False, "null"):
            rec.write({"user_id": False})
            return {"assignee": None, "request": serialize_request(rec)}
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return err(ERR_INVALID_REQUEST, "`user_id` must be an integer or null")
        user = request.env["res.users"].sudo().browse(user_id)
        if not user.exists():
            return err(ERR_NOT_FOUND, f"User {user_id} not found", status=404)
        rec.write({"user_id": user.id})
        return {"assignee": _ref(user), "request": serialize_request(rec)}

    # ── Transition: POST /api/v1/requests/<id>/transition ──────────

    @cadra_route("/api/v1/requests/<int:id>/transition", method="POST",
                 summary="Move the request to the next stage via a stage route (body: {route_id|to_stage_id})",
                 scopes=[SCOPE_REQUESTS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "description": ("Provide either `route_id` (request.stage.route id) "
                                     "or `to_stage_id` (request.stage id). If neither "
                                     "is given, the error response lists the legal "
                                     "outbound routes from the current stage."),
                     "properties": {
                         "route_id": {"type": "integer", "nullable": True},
                         "to_stage_id": {"type": "integer", "nullable": True},
                     },
                 },
                 request_example={"to_stage_id": 5})
    def transition_request(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()

        route_id = body.get("route_id")
        to_stage_id = body.get("to_stage_id")

        if not route_id and not to_stage_id:
            return err(ERR_INVALID_REQUEST,
                       "Either `route_id` or `to_stage_id` must be provided",
                       details={"available_routes": [
                           {"id": r.id, "name": r.name,
                            "to_stage_id": r.stage_to_id.id,
                            "to_stage_name": r.stage_to_id.name}
                           for r in rec.stage_id.route_out_ids
                       ]})

        if route_id:
            try:
                route = request.env["request.stage.route"].sudo().browse(int(route_id))
            except (TypeError, ValueError):
                return err(ERR_INVALID_REQUEST, "`route_id` must be an integer")
            if not route.exists():
                return err(ERR_NOT_FOUND, f"Route {route_id} not found", status=404)
        else:
            try:
                to_stage_id = int(to_stage_id)
            except (TypeError, ValueError):
                return err(ERR_INVALID_REQUEST, "`to_stage_id` must be an integer")
            route = rec.stage_id.route_out_ids.filtered(
                lambda r: r.stage_to_id.id == to_stage_id
            )[:1]
            if not route:
                return err(ERR_INVALID_REQUEST,
                           f"No legal route from stage {rec.stage_id.name!r} "
                           f"to stage {to_stage_id}",
                           details={"current_stage_id": rec.stage_id.id,
                                    "available_to_stages": rec.stage_id.route_out_ids.mapped("stage_to_id.id")})

        if route.stage_from_id.id != rec.stage_id.id:
            return err(ERR_INVALID_REQUEST,
                       f"Route {route.id} starts from stage {route.stage_from_id.name!r}, "
                       f"but request is currently in {rec.stage_id.name!r}")

        from_stage = rec.stage_id
        rec.api_move_request(route.id)
        # Re-browse to get the fresh stage_id (Odoo 15 ORM auto-invalidates,
        # but our serializer reads a number of related fields; safer to refetch).
        rec = rec.browse(rec.id)

        return {
            "request": serialize_request(rec, include=["routes"]),
            "transition": {
                "route_id": route.id,
                "route_name": route.name,
                "from_stage": _ref(from_stage),
                "to_stage": _ref(rec.stage_id),
            },
        }

    # ── Comment: POST /api/v1/requests/<id>/comment ────────────────

    @cadra_route("/api/v1/requests/<int:id>/comment", method="POST",
                 summary="Post a comment on a request via mail.thread (body: {body, internal?:bool})",
                 scopes=[SCOPE_REQUESTS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "required": ["body"],
                     "properties": {
                         "body": {"type": "string",
                                  "description": "HTML or plain text body of the comment"},
                         "internal": {"type": "boolean", "default": True,
                                      "description": ("true = internal note "
                                                      "(mail.mt_note), false = "
                                                      "customer-visible comment "
                                                      "(mail.mt_comment)")},
                     },
                 },
                 request_example={
                     "body": "<p>Customer called — needs ETA before end of day.</p>",
                     "internal": False,
                 })
    def comment_request(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        body_html = body.get("body") or body.get("body_html") or ""
        if not body_html.strip():
            return err(ERR_INVALID_REQUEST, "`body` is required (HTML or plain text)")
        internal = bool(body.get("internal", True))
        subtype = "mail.mt_note" if internal else "mail.mt_comment"
        msg = rec.message_post(
            body=body_html,
            message_type="comment",
            subtype_xmlid=subtype,
        )
        return {
            "comment": {
                "id": msg.id if msg else None,
                "internal": internal,
                "subtype": subtype,
            },
            "request_id": rec.id,
            "request_reference": rec.name,
        }
