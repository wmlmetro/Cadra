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

from .query_params import (
    BadFilter,
    int_filter_terms,
    parse_bool,
    parse_enum,
    parse_int,
)
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
    refuse_unwritable,
    selection_values,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route


# ─── published enums ─────────────────────────────────────────────────

# The floor under the `priority` filter, not its definition: the accepted
# values are read off `request.request.priority` at request time so a value
# the model gains is accepted by the filter that publishes it on the same
# day, and this tuple is only what the check falls back to if the model
# cannot be read.
#
# It has FIVE values, and the route used to publish four. The model declares
# `('0','Low'),('1','Normal'),('2','High'),('3','Critical'),('4','Very
# Urgent')`; the OpenAPI annotation said `["0","1","2","3"]` and described 3
# as "urgent". Per CLAUDE.md architecture rule 4 the model is the published
# surface and the document was wrong on both counts — `4` was always
# accepted by the ORM, and `3` never meant "urgent". Correcting the
# annotation is additive; validating against four values would have been the
# breaking change, because it would start refusing a `priority=4` the
# register already stores.
_PRIORITY_VALUES = ("0", "1", "2", "3", "4")

# Same floor for `kanban_state`, whose three values the PATCH schema already
# published and the list route did not publish at all.
_KANBAN_STATES = ("normal", "done", "blocked")

# The sections `?include=` may name. An unknown one used to be dropped in
# silence — `?include=route`, singular, returned a 200 whose body simply had
# no `available_routes` key — and a client that asks for optional sections
# cannot tell that from a request that has no outbound routes. A dropped
# field is a defect even when it returns 200 (CLAUDE.md architecture rule 3).
_INCLUDE_SECTIONS = ("routes", "events", "messages")


def _parse_include(raw):
    """The requested `include` sections, or a `BadFilter` naming the set.

    Validated per comma-separated token so the error names the one section
    the caller got wrong rather than the whole string.
    """
    sections = []
    for token in (raw or "").split(","):
        token = token.strip()
        if token:
            sections.append(parse_enum("include", token, _INCLUDE_SECTIONS))
    return sections


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
        # Derived from the credential that created the record, never
        # declared (`myservice_api/models/test_fixture.py`). Additive and
        # always present; FALSE on every record created before handoff 26,
        # which is NOT the same statement as "this is a real record".
        "is_test_fixture": r.is_test_fixture,
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
        "location": (_ref(r[_location_field(r)])
                     if _location_field(r) else None),
        "vehicle": _ref(r.vehicle_id) if "vehicle_id" in r._fields else None,
        "asset": _ref(r.nrs_asset_id) if "nrs_asset_id" in r._fields else None,
        "created_at": _dt(r.create_date),
        "updated_at": _dt(r.write_date),
        "created_by": _ref(r.create_uid),
        "updated_by": _ref(r.write_uid),
        # Handoff 25 C3. Both are on the request form and neither was
        # readable over the API, so a Finance Officer tracing a payment
        # reference could not, and neither could an auditor.
        #
        # They are written by DIFFERENT paths, and saying so matters because
        # a published key is permanent:
        #
        #   payment_ref   `request_request.py:319` and `:386` — the
        #                 WorkSpace/Workflow APPROVAL callback. This is the
        #                 field C3 named, and the measurement is what decided
        #                 it: a column nothing writes is dead and goes; one
        #                 the approval path writes is a financial fact, and an
        #                 invisible financial fact is the defect.
        #
        #   workspace_ref `request_request.py:115` — the OUTBOUND SEND path,
        #                 not the callback. Published alongside because it is
        #                 the same invisibility defect on the same form, but
        #                 it is measured at **0 of 407** requests across all
        #                 eight local tenants (`request_request.py:222`), so
        #                 expect `null` and do not build on it.
        #
        # `_fields` guards because `myservice_workflow` is an optional module
        # and the rest of this serializer already reads that way.
        "workflow": {
            "payment_ref": (r.workflow_payment_ref or None
                            if "workflow_payment_ref" in r._fields else None),
            "workspace_ref": (r.workspace_ref or None
                              if "workspace_ref" in r._fields else None),
        },
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
        # Reference plus the request body (request_text_sample is the stored
        # plain-text subject; request_text catches the full description) and the
        # people on the request (author / contact).
        terms = [
            ("name", "ilike", q),
            ("request_text_sample", "ilike", q),
            ("request_text", "ilike", q),
            ("author_id.name", "ilike", q),
            ("partner_id.name", "ilike", q),
        ]
        domain += ["|"] * (len(terms) - 1) + terms
    # The foreign keys. Every one of these used to sit inside
    # `except (TypeError, ValueError): pass`, so `?stage_id=resolved` dropped
    # the term and handed back EVERY request in the register — every stage,
    # open and closed — to a caller who had asked for one stage. Nothing in
    # the envelope distinguishes that from an answer.
    domain += int_filter_terms(qs, ("type_id", "category_id", "stage_id",
                                    "user_id", "author_id", "partner_id",
                                    "service_id", "parent_id"))
    Req = request.env["request.request"]
    # These two are registry guards, NOT filter decisions, and they stay
    # exactly as they were. `location_id` and `nrs_asset_id` arrive with
    # myservice_request_fields; on a tenant that has not installed it there
    # is no column to filter on, so the parameter is ignored rather than
    # refused. Ignoring a filter the model cannot answer is a different thing
    # from ignoring a value we could not read, and only the second is what
    # this pass is closing.
    # `location_id` is the PUBLISHED name; the model's field is whatever
    # `_location_field` finds. Until handoff 31 this looked for a model field
    # called `location_id`, which the Odoo 19 request model does not have, so
    # the filter was ignored on every deployment and `?location_id=` answered
    # with every request — the defect handoff 21 closed everywhere else,
    # surviving here under a comment that called it a registry guard.
    if _location_field(Req):
        domain += int_filter_terms(qs, (("location_id", _location_field(Req)),))
    if "nrs_asset_id" in Req._fields:
        # `asset_id` is the published name and `nrs_asset_id` the model
        # field; both are accepted as input and both stay accepted. The
        # error names whichever one the caller actually sent, so a client
        # reading `details` sees the parameter it typed rather than our
        # column name.
        param = "asset_id" if qs.get("asset_id") not in (None, "") else "nrs_asset_id"
        asset_id = parse_int(param, qs.get(param))
        if asset_id is not None:
            domain.append(("nrs_asset_id", "=", asset_id))
    # `priority` and `kanban_state` were appended raw, so a typo answered
    # `200 []` — which reads as "there are no critical requests" rather than
    # as "you asked a question I could not parse", and the reassuring reading
    # is the wrong one. The accepted values come from the model's own
    # Selection (see `_PRIORITY_VALUES` for what that corrected in the
    # published annotation); the tuples are only the floor under it.
    priority = parse_enum(
        "priority", qs.get("priority"),
        selection_values("request.request", "priority", _PRIORITY_VALUES))
    if priority is not None:
        domain.append(("priority", "=", priority))
    kanban_state = parse_enum(
        "kanban_state", qs.get("kanban_state"),
        selection_values("request.request", "kanban_state", _KANBAN_STATES))
    if kanban_state is not None:
        domain.append(("kanban_state", "=", kanban_state))
    # `?closed=1` used to fall through both branches, append nothing, and
    # return every request there is — open and closed together — to a caller
    # asking for exactly one of the two. This is the filter an auditor
    # reaches for to ask what is still outstanding, and answering it with the
    # whole register is a false statement rather than an empty one.
    #
    # The literal `"null"` is refused here rather than read as "no filter".
    # That leniency exists on `is_tagged` because `is_tagged` published it
    # before this rule existed; `closed` never published it — `?closed=null`
    # simply fell into the same hole as `?closed=1` and returned everything.
    closed = parse_bool("closed", qs.get("closed"))
    if closed is not None:
        domain.append(("closed", "=", closed))
    # `has_deadline` was worse, because only half of it existed. There was no
    # `false` branch at all, so `?has_deadline=false` — "which requests has
    # nobody put a date on" — returned the entire list, and every request in
    # it appeared to have no deadline. Both answers now filter, and a value
    # that is neither is refused.
    has_deadline = parse_bool("has_deadline", qs.get("has_deadline"))
    if has_deadline is True:
        domain.append(("deadline_date", "!=", False))
    elif has_deadline is False:
        domain.append(("deadline_date", "=", False))
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


def _location_field(Req):
    """The model field behind the published key `location_id`, or None.

    **The published key and the model field stopped agreeing in the move to
    Odoo 19, and nobody noticed for the life of the API.** This controller
    was written when the request model's location was `location_id`. On 19 it
    is `generic_location_id` (`myservice_request_core`). The allow-list kept
    the old name, the filter below refused any allow-listed key the model did
    not define — and so every request raised THROUGH THIS ROUTE with a
    location answered 201 and was saved without it, the serializer published
    `location: null` for every request whatever it held, and `?location_id=`
    filtered nothing. Measured in handoff 31: `jaizbankplc`, 0 of 460
    requests with a location. The endpoint reference's own example, the Cadra
    app's request form, the test suite's fixture and the smoke test all sent
    one.

    **Only this route, though, and the first draft of this docstring said
    "by anyone".** The model's field has been written all along by the doors
    that knew its name: `POST /home/quick-submit`, the PM scheduler's
    auto-tickets, fleet maintenance and the Odoo form — `cadra19` holds 80
    requests and all 80 have a location. Those requests published
    `location: null` until now too, and will start showing the location they
    always had.

    Found because handoff 31 turned the silent drop into a 400 — and then,
    nearly missed a second time: the first reading was "the register cannot
    hold a request's location", and the app's picker was removed on it. The
    model could all along. It is the depreciation-method bug again, one layer
    down: the API publishes one name and the thing underneath answers to
    another. The published key is the contract; translating it is this
    file's job.
    """
    for name in ("location_id", "generic_location_id"):
        if name in Req._fields:
            return name
    return None


def _model_field(Req, key):
    """The model field a published body key writes, or None if this
    deployment's model has nowhere to put it."""
    if key == "location_id":
        return _location_field(Req)
    return key if key in Req._fields else None


def _writable_here():
    """What this route accepts ON THIS DATABASE — a key is refused when the
    installed model has nowhere to put it, so publishing the bare allow-list
    would name keys that are then refused."""
    Req = request.env["request.request"]
    return [k for k in _WRITABLE_FIELDS if _model_field(Req, k)]


def _filter_writable(body):
    if not isinstance(body, dict):
        return {}, []
    Req = request.env["request.request"]
    vals = {}
    rejected = []
    for k, v in body.items():
        field = _model_field(Req, k) if k in _WRITABLE_FIELDS else None
        if field:
            vals[field] = v
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
                 summary="List service requests with filters and cursor pagination",
                 scopes=[SCOPE_REQUESTS_READ],
                 query_params=[
                     {"name": "q", "schema": {"type": "string"},
                      "description": "Free-text search across name, description, request reference"},
                     {"name": "type_id", "schema": {"type": "integer"},
                      "description": "request.type id"},
                     {"name": "category_id", "schema": {"type": "integer"}},
                     {"name": "stage_id", "schema": {"type": "integer"},
                      "description": "request.stage id"},
                     {"name": "user_id", "schema": {"type": "integer"},
                      "description": "Assignee res.users id"},
                     {"name": "author_id", "schema": {"type": "integer"},
                      "description": "Author res.partner id"},
                     {"name": "partner_id", "schema": {"type": "integer"},
                      "description": "Contact res.partner id"},
                     {"name": "service_id", "schema": {"type": "integer"},
                      "description": "generic.service id"},
                     {"name": "parent_id", "schema": {"type": "integer"},
                      "description": "Parent request.request id"},
                     # Corrected, not extended: the model has declared five
                     # priorities all along and this said four, with `3`
                     # labelled "urgent" where the model calls it Critical.
                     # See `_PRIORITY_VALUES`.
                     {"name": "priority", "schema": {"type": "string",
                      "enum": ["0", "1", "2", "3", "4"]},
                      "description": "0=Low, 1=Normal, 2=High, 3=Critical, "
                                     "4=Very Urgent"},
                     {"name": "kanban_state", "schema": {"type": "string",
                      "enum": ["normal", "done", "blocked"]},
                      "description": "normal=In Progress, done=Ready, "
                                     "blocked=Blocked"},
                     {"name": "closed", "schema": {"type": "boolean"},
                      "description": "true = only closed requests, "
                                     "false = only open ones"},
                     {"name": "has_deadline", "schema": {"type": "boolean"},
                      "description": "true = only requests with a deadline "
                                     "set, false = only those without one"},
                     {"name": "location_id", "schema": {"type": "integer"},
                      "description": "Ignored on a tenant without "
                                     "myservice_request_fields installed"},
                     {"name": "asset_id", "schema": {"type": "integer"},
                      "description": "Related nrs.asset id; `nrs_asset_id` "
                                     "is accepted as an alias"},
                     {"name": "nrs_asset_id", "schema": {"type": "integer"},
                      "description": "Alias of `asset_id`"},
                     *PAGINATION_QUERY_PARAMS,
                 ])
    def list_requests(self, **kwargs):
        qs = get_params()
        Req = request.env["request.request"].sudo()
        try:
            domain = _list_domain(qs)
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
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
                 summary="Get a single request by id",
                 scopes=[SCOPE_REQUESTS_READ],
                 query_params=[
                     {"name": "include", "schema": {"type": "string"},
                      "description": "Comma-separated optional sections: "
                                     "routes, events, messages. An "
                                     "unrecognised section is refused with a "
                                     "400 rather than dropped."},
                 ])
    def get_request(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        try:
            include = _parse_include(kwargs.get("include"))
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        return serialize_request(rec, include=include)

    # ── Get by reference: GET /api/v1/requests/by-reference/<ref> ──

    @cadra_route("/api/v1/requests/by-reference/<string:reference>", method="GET",
                 summary="Get a single request by reference (e.g. INCIDENT-052026-0000002)",
                 scopes=[SCOPE_REQUESTS_READ],
                 query_params=[
                     {"name": "include", "schema": {"type": "string"},
                      "description": "Comma-separated optional sections: "
                                     "routes, events, messages. An "
                                     "unrecognised section is refused with a "
                                     "400 rather than dropped."},
                 ])
    def get_request_by_reference(self, reference, **kwargs):
        rec = request.env["request.request"].sudo().search(
            [("name", "=", reference)], limit=1)
        if not rec:
            return err(ERR_NOT_FOUND, f"No request with reference '{reference}'", status=404)
        try:
            include = _parse_include(kwargs.get("include"))
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
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
                         # Five values, from the model. See `_PRIORITY_VALUES`
                         # — the four published here were never what the ORM
                         # accepted, and `3` is Critical, not "urgent".
                         "priority": {"type": "string",
                                      "enum": ["0", "1", "2", "3", "4"],
                                      "description": "0=Low, 1=Normal, 2=High, "
                                                     "3=Critical, 4=Very Urgent"},
                         "impact": {"type": "string", "nullable": True},
                         "urgency": {"type": "string", "nullable": True},
                         # Both are on the allow-list and were missing here,
                         # which did not matter while an unlisted key was
                         # merely dropped. Now that an unaccepted key is a
                         # 400, the published list is what a caller repairs
                         # itself FROM, so it has to be the whole list.
                         "kanban_state": {"type": "string", "nullable": True},
                         "response_text": {"type": "string", "nullable": True},
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
                         "location_id": {
                             "type": "integer", "nullable": True,
                             "description": (
                                 "A `generic.location` id — where the "
                                 "problem is. SAVED since handoff 31 (21 "
                                 "September 2026). Before that it was "
                                 "accepted, dropped and answered 201 by "
                                 "THIS route: the model's field was renamed "
                                 "in the move to Odoo 19 and this route went "
                                 "on asking for the old name. Published back "
                                 "as `data.location` — including on older "
                                 "requests raised by quick-submit, a PM "
                                 "schedule or the Odoo form, which kept "
                                 "theirs and used to read null — and a "
                                 "filter on the list.")},
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
        if rejected:
            return refuse_unwritable(rejected, _writable_here())
        if not vals.get("type_id"):
            return err(ERR_INVALID_REQUEST, "`type_id` is required")
        if not vals.get("request_text"):
            return err(ERR_INVALID_REQUEST, "`request_text` is required (the issue description)")
        rec = request.env["request.request"].sudo().create(vals)
        return serialize_request(rec, include=["routes"])

    # ── Patch: PATCH /api/v1/requests/<id> ─────────────────────────

    @cadra_route("/api/v1/requests/<int:id>", method="PATCH",
                 summary="Partial update of a request (stage changes go through /transition)",
                 scopes=[SCOPE_REQUESTS_WRITE],
                 idempotent=True,
                 request_schema={
                     "type": "object",
                     "description": ("Any subset of the writable fields from POST "
                                     "/api/v1/requests. `stage_id` is intentionally "
                                     "excluded — use POST .../transition. A "
                                     "field this route does not accept is a "
                                     "400 `invalid_request` naming it in "
                                     "`details.rejected_fields`, and nothing "
                                     "is written."),
                     "properties": {
                         "priority": {"type": "string",
                                      "enum": ["0", "1", "2", "3", "4"]},
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
        if rejected:
            # The hint used to ride on EVERY rejection here, whatever was
            # rejected. It is advice about one field.
            return refuse_unwritable(
                rejected, _writable_here(),
                hint=("Use POST /api/v1/requests/<id>/transition to change "
                      "stage_id") if "stage_id" in rejected else None)
        if not vals:
            return err(ERR_INVALID_REQUEST, "Empty patch — no writable fields supplied")
        rec.write(vals)
        return serialize_request(rec)

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
