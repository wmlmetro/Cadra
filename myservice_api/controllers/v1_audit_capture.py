"""The audit in the room, over HTTP (handoff 66).

The models are `myservice_asset_register/models/audit_capture.py`, which says
what each outcome means and why every one needs two people. This file reads
bodies, checks the caller's scope, and says each refusal in words — the model
raises them, `utils.gate_refusal` maps them, as for the receipt gates.

THE ROUTES
----------
The Asset Controller (`audit:manage`):

* `POST /audit/devices`, `POST /audit/devices/<id>/bind`,
  `POST /audit/devices/<id>/deactivate` — a device, bound to one person;
* `POST /audit/blocks` (N ≤ 500 codes to a device and its person),
  `POST /audit/blocks/<id>/return` (unused codes voided, never reissued);
* `POST /audit/campaigns`, `PATCH /audit/campaigns/<id>`,
  `POST /audit/campaigns/<id>/close` (every capture reviewed first; the two
  lists are kept as they stood);
* `POST /audit/captures/<capture_id>/register-new` and `…/void` — a
  found-not-in-SAP exception registered through the maker and checker, or
  voided with a reason (which voids its code).

The capturer (`audit:capture`), from a device bound to them
(`X-Cadra-Device`): `POST /audit/photos`, then `POST /audit/captures`,
idempotent on the capture's own `capture_id` (a UUID, stored unique — never
the 24-hour cache).

The reviewer (`audit:review`): `POST /audit/captures/<capture_id>/accept`,
`…/return`, and `POST /audit/captures/accept` — a room's batch, 60's rules.

Reads (`audit:read`): campaigns with progress, the two lists (JSON and CSV),
captures, a capture by its id (the phone confirming a sync), photos,
devices, blocks, the ledger, and a room's slice for an offline phone.
`GET /ai/config` is the phone's one read of the AI switch, the model, the
cap left today and the label layout.
"""
import csv
import io
import json
import uuid

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.myservice_asset_register.models.asset_gates import (
    CANDIDATES_CTX,
    GateRefused,
)
from odoo.addons.myservice_asset_register.models.asset_photo import (
    PhotoRefused,
)
from odoo.addons.myservice_asset_register.models.audit_capture import (
    CAPTURE_STATES,
    CODE_STATES,
    CONFIRMED_FIELDS,
    EXCEPTION_STATES,
    LABEL_STATES,
    MAX_BLOCK_SIZE,
    OUTCOMES,
    earliest_capture_day,
)

from .query_params import BadFilter, parse_bool, parse_enum, parse_int
from .utils import (
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    ERR_VALIDATION_FAILED,
    SCOPE_ASSETS_WRITE,
    SCOPE_AUDIT_CAPTURE,
    SCOPE_AUDIT_MANAGE,
    SCOPE_AUDIT_READ,
    SCOPE_AUDIT_REVIEW,
    _http_response,
    caller_holds,
    err,
    gate_refusal,
    gate_refusal_parts,
    get_multipart,
    get_params,
    ok,
    paginate,
    parse_limit,
    refuse_unwritable,
    require_jwt,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route
from .v1_ai import ai_settings
from .v1_assets import _parse_updated_since
from .v1_gates import BATCH_MAX, _DryRun

_ISO = "%Y-%m-%dT%H:%M:%SZ"
DEVICE_HEADER = "X-Cadra-Device"
LISTS = ("found_not_in_sap", "in_sap_not_found")
SLICE_KINDS = ("assets", "sap_records")

#: The label as data (handoffs 54 and 61): what the phone prints, so it
#: never guesses. QR first, the code verbatim, no Code 128 below `large`
#: (a camera reads the small and medium Code 128 0 of 24 — handoff 54's
#: corpus, re-measured in 61 §7).
LABEL_LAYOUT = {
    "content": "the asset code, verbatim — nothing added, nothing removed",
    "symbologies": [
        {"format": "qr_code", "sizes": ["small", "medium", "large"],
         "first": True},
        {"format": "code_128", "sizes": ["large"], "first": False,
         "note": "small and medium Code 128 is below any camera's floor "
                 "(0 of 24 decodes each, handoff 54); print it only on "
                 "large"},
    ],
    "text_line": "the code, printed under the symbol, so a person can type "
                 "it when no scanner reads it",
    # Width × height, as Cadra's own label paper formats are
    # (`myservice_asset_register/data/asset_tag_report.xml`).
    "sizes_mm": {"small": [50, 25], "medium": [50, 30], "large": [100, 60]},
}


def _iso(value):
    return value.strftime(_ISO) if value else None


def _user(u):
    return {"id": u.id, "name": u.name} if u else None


def _env(model):
    return request.env[model].sudo()


def _body(allowed):
    body = get_params() or {}
    rejected = sorted(k for k in body if k not in allowed)
    if rejected:
        return None, refuse_unwritable(rejected, sorted(allowed))
    return body, None


def _guard(fn):
    """Run a model act; a refusal becomes its envelope (the decorator's own
    mapping, said here so the route reads as the act it is)."""
    try:
        return fn(), None
    except GateRefused as e:
        request.env.cr.rollback()
        return None, gate_refusal(e)
    except PhotoRefused as e:
        request.env.cr.rollback()
        return None, err(e.code, str(e.args[0]), status=e.status,
                         details=e.details)


def _users(ids, field):
    if not isinstance(ids, list) or not all(
            isinstance(i, int) and not isinstance(i, bool) for i in ids):
        return None, err(ERR_INVALID_REQUEST, "`%s` is a list of user ids."
                         % field, details={"field": field})
    users = _env("res.users").browse(ids).exists()
    if len(users) != len(set(ids)):
        return None, err(ERR_VALIDATION_FAILED, "No user has id %s."
                         % sorted(set(ids) - set(users.ids)),
                         details={"field": field})
    return users, None


def _device_out(d):
    return {"id": d.id, "name": d.name, "device_code": d.device_code,
            "bound_to": _user(d.user_id), "bound_at": _iso(d.bound_at),
            "bound_by": _user(d.bound_by_id), "active": d.active,
            "registered_by": _user(d.registered_by_id),
            "registered_at": _iso(d.registered_at),
            "open_block_id": (d.block_ids.filtered(
                lambda b: b.state == "issued")[:1].id or None)}


def _block_out(b, codes=False):
    out = {"id": b.id, "name": b.name, "device": {"id": b.device_id.id,
                                                   "name": b.device_id.name},
           "issued_to": _user(b.user_id), "size": b.size, "state": b.state,
           "first_code": b.first_code, "last_code": b.last_code,
           "issued_by": _user(b.issued_by_id), "issued_at": _iso(b.issued_at),
           "returned_by": _user(b.returned_by_id),
           "returned_at": _iso(b.returned_at),
           "return_reason": b.return_reason or None,
           "codes_by_state": b._counts()}
    if codes:
        out["codes"] = [_code_out(c) for c in b.code_ids.sorted("code")]
    return out


def _code_out(c):
    return {"code": c.code, "state": c.state, "source": c.source,
            "block_id": c.block_id.id or None,
            "device_id": c.device_id.id or None,
            "reserved_to": _user(c.user_id),
            "reserved_at": _iso(c.reserved_at), "used_at": _iso(c.used_at),
            "activated_at": _iso(c.activated_at),
            "voided_at": _iso(c.voided_at), "voided_by": _user(c.voided_by_id),
            "void_reason": c.void_reason or None,
            "asset_id": c.asset_id.id or None,
            "capture_id": c.capture_id.capture_uuid or None,
            "print_count": c.print_count,
            "first_printed_at": _iso(c.first_printed_at),
            "last_printed_at": _iso(c.last_printed_at),
            "last_printed_by": _user(c.last_printed_by_id)}


def _campaign_out(c, detail=False):
    out = {"id": c.id, "name": c.name, "state": c.state,
           "date_start": fields.Date.to_string(c.date_start) or None,
           "date_end": fields.Date.to_string(c.date_end) or None,
           "scope": [{"location": ({"id": l.location_id.id,
                                    "name": l.location_id.display_name}
                                   if l.location_id else None),
                      "office_code": l.office_code or None}
                     for l in c.scope_ids],
           "capturers": [_user(u) for u in c.capturer_ids],
           "reviewers": [_user(u) for u in c.reviewer_ids],
           "created_by": _user(c.created_by_id),
           "closed_by": _user(c.closed_by_id), "closed_at": _iso(c.closed_at),
           "progress": c._progress()}
    if detail:
        rooms = {}
        for cap in c.capture_ids:
            r = rooms.setdefault(cap.location_id.id, {
                "location": {"id": cap.location_id.id,
                             "name": cap.location_id.display_name},
                "captured": 0, "waiting_for_review": 0})
            r["captured"] += 1
            if cap.state == "pending_review":
                r["waiting_for_review"] += 1
        out["rooms"] = sorted(rooms.values(),
                              key=lambda r: r["location"]["name"] or "")
    return out


def _photo_brief(p):
    return {"id": p.id, "url": "/api/v1/audit/photos/%d" % p.id,
            "mimetype": p.mimetype, "size": p.size, "width": p.width,
            "height": p.height, "sha256": p.sha256}


def _capture_out(cap):
    suggestion = cap.ai_suggestion_id
    sap = cap.sap_record_id
    asset = cap.asset_id
    return {
        "capture_id": cap.capture_uuid, "id": cap.id,
        "campaign": {"id": cap.campaign_id.id, "name": cap.campaign_id.name},
        "location": {"id": cap.location_id.id,
                     "name": cap.location_id.display_name,
                     "location_code": cap.location_id.location_code or None},
        "outcome": cap.outcome, "state": cap.state,
        "asset": ({"id": asset.id, "asset_code": asset.asset_code,
                   "name": asset.name,
                   "location": asset.location_id.display_name or None}
                  if asset else None),
        "sap_record": ({"id": sap.id, "asset_number": sap.asset_number,
                        "sub_number": sap.sub_number or None,
                        "class": sap.asset_class or None,
                        "description": sap.description or None,
                        "old_tag": sap.old_tag or None,
                        "office_code": sap.office_code or None,
                        "capitalized_on": sap.capitalized_on.isoformat()
                        if sap.capitalized_on else None}
                       if sap else None),
        "code": cap.code or None, "scanned_label": cap.scanned_label or None,
        "label": cap.label or None, "name": cap.name or None,
        "category": ({"id": cap.category_id.id,
                      "name": cap.category_id.name}
                     if cap.category_id else None),
        "condition": cap.condition or None,
        "fields": json.loads(cap.confirmed_json or "{}"),
        "photos": [_photo_brief(p) for p in cap.photo_ids.sorted("id")],
        "ai_suggestion": ({"id": suggestion.id, "result": suggestion.result,
                           "suggested": suggestion._suggestion()}
                          if suggestion else None),
        "captured_at": _iso(cap.captured_at),
        "received_at": _iso(cap.received_at),
        # AI-FR-10: only what the capturer chose to send, only here.
        "gps": ({"latitude": cap.gps_latitude,
                 "longitude": cap.gps_longitude,
                 "accuracy_m": cap.gps_accuracy_m or None}
                if cap.gps_recorded else None),
        "captured_by": _user(cap.operator_id),
        "device": {"id": cap.device_id.id, "name": cap.device_id.name},
        "duplicate_of": cap.duplicate_of_id.capture_uuid or None,
        "duplicate_basis": cap.duplicate_basis or None,
        "reviewed_by": _user(cap.reviewed_by_id),
        "reviewed_at": _iso(cap.reviewed_at),
        "return_reason": cap.return_reason or None,
        "result_asset": ({"id": cap.result_asset_id.id,
                          "asset_code": cap.result_asset_id.asset_code,
                          "register_state":
                          cap.result_asset_id.register_state}
                         if cap.result_asset_id else None),
        "reprint_label_id": cap.reprint_label_id.id or None,
        "photos_copied": cap.photos_copied,
        "exception_state": cap.exception_state or None,
        "exception_resolved_by": _user(cap.exception_resolved_by_id),
        "exception_resolved_at": _iso(cap.exception_resolved_at),
        "exception_void_reason": cap.exception_void_reason or None,
    }


def _norm_uuid(value):
    """A capture id as stored: the canonical lower-case UUID. A phone may
    hold it upper-case (iOS `UUID().uuidString`) — the same capture."""
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return value


def _capture_or_404(capture_id):
    capture_id = _norm_uuid(capture_id)
    cap = _env("nrs.audit.capture").search(
        [("capture_uuid", "=", capture_id)], limit=1)
    if not cap:
        return None, err(ERR_NOT_FOUND, "No capture has the id %s."
                         % capture_id, status=404,
                         details={"capture_id": capture_id})
    return cap, None


def _browse_or_404(model, rec_id, what):
    rec = _env(model).with_context(active_test=False).browse(rec_id).exists()
    if not rec:
        return None, err(ERR_NOT_FOUND, "There is no %s with id %s."
                         % (what, rec_id), status=404)
    return rec, None


def _cell(value):
    """A CSV cell a spreadsheet will not run: text a person or SAP typed
    (a description, an old tag) that begins `=`, `+`, `-` or `@` is
    prefixed with a quote, as OWASP's CSV-injection advice says."""
    if value is None:
        return ""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def _csv(rows, columns, filename):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row.get(c)) for c in columns])
    data = buf.getvalue().encode("utf-8")
    return request.make_response(data, headers=[
        ("Content-Type", "text/csv; charset=utf-8"),
        ("Content-Length", str(len(data))),
        ("Content-Disposition", http.content_disposition(filename)),
    ])


_ID_LIST = {"type": "array", "items": {"type": "integer"}}
_SCOPE_LINE = {"type": "object", "properties": {
    "location_id": {"type": "integer"}, "office_code": {"type": "string"}}}


class CadraAuditCaptureV1(http.Controller):

    # ── devices ───────────────────────────────────────────────────────

    @cadra_route("/api/v1/audit/devices", method="GET",
                 summary="Audit capture devices and whom each is bound to",
                 scopes=[SCOPE_AUDIT_READ],
                 query_params=[{"name": "mine", "schema": {"type": "boolean"},
                                "description": "Only the devices bound to "
                                               "the caller"}])
    def devices(self, **kwargs):
        mine = parse_bool("mine", kwargs.get("mine"))
        domain = [("user_id", "=", request.env.uid)] if mine else []
        rows = _env("nrs.audit.device").search(domain)
        return [_device_out(d) for d in rows]

    @cadra_route("/api/v1/audit/devices", method="POST",
                 summary="Register a device, bound to a person",
                 scopes=[SCOPE_AUDIT_MANAGE],
                 request_schema={"type": "object", "required": ["name"],
                                 "properties": {
                                     "name": {"type": "string"},
                                     "user_id": {"type": "integer"}}})
    def device_create(self, **kwargs):
        body, error = _body({"name", "user_id"})
        if error:
            return error
        user = _env("res.users")
        if body.get("user_id") is not None:
            user, error = _users([body["user_id"]], "user_id")
            if error:
                return error
        device, error = _guard(lambda: _env("nrs.audit.device").with_user(
            request.env.user)._register_device(body.get("name"), user))
        return error or _device_out(device)

    @cadra_route("/api/v1/audit/devices/<int:id>/bind", method="POST",
                 summary="Bind a device to a person (or to nobody)",
                 scopes=[SCOPE_AUDIT_MANAGE],
                 request_schema={"type": "object", "required": ["user_id"],
                                 "properties": {
                                     "user_id": {"type": ["integer",
                                                          "null"]}}})
    def device_bind(self, id, **kwargs):
        body, error = _body({"user_id"})
        if error:
            return error
        device, error = _browse_or_404("nrs.audit.device", id, "device")
        if error:
            return error
        if "user_id" not in body:
            return err(ERR_VALIDATION_FAILED, "Say whom the device is bound "
                       "to: `user_id`, or null for nobody.",
                       details={"field": "user_id"})
        user = _env("res.users")
        if body["user_id"] is not None:
            user, error = _users([body["user_id"]], "user_id")
            if error:
                return error
        result, error = _guard(lambda: device.with_user(
            request.env.user).sudo()._bind(user))
        return error or _device_out(result)

    @cadra_route("/api/v1/audit/devices/<int:id>/deactivate", method="POST",
                 summary="Deactivate a device",
                 scopes=[SCOPE_AUDIT_MANAGE])
    def device_deactivate(self, id, **kwargs):
        body, error = _body(set())
        if error:
            return error
        device, error = _browse_or_404("nrs.audit.device", id, "device")
        if error:
            return error
        result, error = _guard(lambda: device._deactivate())
        return error or _device_out(result)

    @cadra_route("/api/v1/audit/people", method="GET",
                 summary="Who may be named on an audit: the active people "
                         "holding the capturer and the reviewer roles",
                 scopes=[SCOPE_AUDIT_MANAGE])
    def people(self, **kwargs):
        """The Asset Controller binds a device to a capturer and names a
        campaign's team; `GET /users` is the administrator's, so this is the
        one list of candidates the controller can read. Two roles, nothing
        else about anybody."""
        out = {}
        for key, xmlid in (
                ("capturers", "myservice_asset_register.group_audit_capturer"),
                ("reviewers", "myservice_asset_register.group_audit_reviewer")):
            group = request.env.ref(xmlid, raise_if_not_found=False)
            members = group.sudo().all_user_ids if group else _env("res.users")
            out[key] = [{"id": u.id, "name": u.name, "login": u.login}
                        for u in members.filtered("active").sorted("name")]
        return out

    # ── code blocks and the ledger ────────────────────────────────────

    @cadra_route("/api/v1/audit/blocks", method="GET",
                 summary="Code blocks issued to devices",
                 scopes=[SCOPE_AUDIT_READ],
                 query_params=[
                     {"name": "device_id", "schema": {"type": "integer"}},
                     {"name": "state", "schema": {
                         "type": "string", "enum": ["issued", "returned"]}}])
    def blocks(self, **kwargs):
        try:
            device_id = parse_int("device_id", kwargs.get("device_id"),
                                  minimum=1)
            state = parse_enum("state", kwargs.get("state"),
                               ("issued", "returned"))
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        domain = []
        if device_id:
            domain.append(("device_id", "=", device_id))
        if state:
            domain.append(("state", "=", state))
        return [_block_out(b) for b in _env("nrs.audit.code.block").search(
            domain)]

    @cadra_route("/api/v1/audit/blocks", method="POST",
                 summary="Issue a block of asset codes to a device and the "
                         "person it is bound to",
                 scopes=[SCOPE_AUDIT_MANAGE],
                 request_schema={"type": "object",
                                 "required": ["device_id", "size"],
                                 "properties": {
                                     "device_id": {"type": "integer"},
                                     "size": {"type": "integer", "minimum": 1,
                                              "maximum": MAX_BLOCK_SIZE}}})
    def block_issue(self, **kwargs):
        body, error = _body({"device_id", "size"})
        if error:
            return error
        device_id = body.get("device_id")
        if not isinstance(device_id, int) or isinstance(device_id, bool):
            return err(ERR_VALIDATION_FAILED, "`device_id` is required.",
                       details={"field": "device_id"})
        device, error = _browse_or_404("nrs.audit.device", device_id,
                                       "device")
        if error:
            return error
        block, error = _guard(lambda: _env("nrs.audit.code.block").with_user(
            request.env.user).sudo()._issue_block(device, body.get("size")))
        return error or _block_out(block, codes=True)

    @cadra_route("/api/v1/audit/blocks/<int:id>", method="GET",
                 summary="A code block and every code in it",
                 scopes=[SCOPE_AUDIT_READ])
    def block_get(self, id, **kwargs):
        block, error = _browse_or_404("nrs.audit.code.block", id, "block")
        return error or _block_out(block, codes=True)

    @cadra_route("/api/v1/audit/blocks/<int:id>/return", method="POST",
                 summary="Return a block: its unused codes are voided (the "
                         "Asset Controller any block, a capturer their own)",
                 # Handoff 67 §2.3: the capturer returns their own block — a
                 # shift ending at a shared station — not only the Asset
                 # Controller.
                 scopes_any=[SCOPE_AUDIT_MANAGE, SCOPE_AUDIT_CAPTURE],
                 request_schema={"type": "object", "properties": {
                     "reason": {"type": "string"}}})
    def block_return(self, id, **kwargs):
        body, error = _body({"reason"})
        if error:
            return error
        block, error = _browse_or_404("nrs.audit.code.block", id, "block")
        if error:
            return error
        holder_only = not caller_holds(SCOPE_AUDIT_MANAGE)
        voided, error = _guard(lambda: block.with_user(
            request.env.user).sudo()._return_block(
                body.get("reason"), holder_only=holder_only))
        if error:
            return error
        out = _block_out(block, codes=True)
        out["voided_now"] = voided
        return out

    @cadra_route("/api/v1/audit/codes/printed", method="POST",
                 summary="Record that codes from your block were printed "
                         "(the station's print, handoff 67)",
                 scopes=[SCOPE_AUDIT_CAPTURE], success_status=200,
                 request_schema={"type": "object", "required": ["codes"],
                                 "properties": {"codes": {
                                     "type": "array", "minItems": 1,
                                     "maxItems": BATCH_MAX,
                                     "items": {"type": "string"}}}})
    def codes_printed(self, **kwargs):
        """Every print of a block code is recorded, as every tag label's is
        (61): who printed it, when, how many times. A code not reserved to
        the caller on the device in `X-Cadra-Device` refuses the whole
        request, before anything is recorded."""
        body, error = _body({"codes"})
        if error:
            return error
        codes = body.get("codes")
        if not isinstance(codes, list) or not codes \
                or len(codes) > BATCH_MAX or not all(
                    isinstance(c, str) and c.strip() for c in codes):
            return err(ERR_VALIDATION_FAILED,
                       "`codes` lists between 1 and %d codes that were "
                       "printed." % BATCH_MAX, details={"field": "codes"})
        wanted = list(dict.fromkeys(c.strip() for c in codes))
        me = request.env.user

        def act():
            device = _env("nrs.audit.device")._from_header(
                request.httprequest.headers.get(DEVICE_HEADER), me)
            rows = _env("nrs.asset.code").search([("code", "in", wanted)])
            found = {r.code: r for r in rows}
            missing = [c for c in wanted if c not in found]
            if missing:
                raise GateRefused(
                    "No code %s exists in the ledger." % ", ".join(missing),
                    "validation_failed", {"field": "codes",
                                          "unknown": missing})
            for c in wanted:
                found[c]._assert_reserved_to(me, device)
            return rows.with_user(me).sudo()._record_print()
        rows, error = _guard(act)
        if error:
            return error
        return {"recorded": [{"code": r.code, "print_count": r.print_count,
                              "last_printed_at": _iso(r.last_printed_at)}
                             for r in rows.sorted("code")]}

    @cadra_route("/api/v1/audit/codes/<string:code>/void", method="POST",
                 summary="Void one spoiled code reserved to you (a label "
                         "torn at print); never reissued",
                 scopes=[SCOPE_AUDIT_CAPTURE],
                 request_schema={"type": "object", "required": ["reason"],
                                 "properties": {
                                     "reason": {"type": "string"}}})
    def code_void(self, code, **kwargs):
        body, error = _body({"reason"})
        if error:
            return error
        row = _env("nrs.asset.code").search([("code", "=", code.strip())],
                                            limit=1)
        if not row:
            return err(ERR_NOT_FOUND, "No code %s exists in the ledger."
                       % code, status=404, details={"code": code})
        me = request.env.user

        def act():
            row._assert_reserved_to(me)
            return row.with_user(me).sudo()._void_spoiled(body.get("reason"))
        result, error = _guard(act)
        return error or _code_out(result)

    @cadra_route("/api/v1/audit/codes", method="GET",
                 summary="The ledger of asset codes — which codes exist",
                 scopes=[SCOPE_AUDIT_READ],
                 query_params=[
                     {"name": "code", "schema": {"type": "string"}},
                     {"name": "state", "schema": {
                         "type": "string", "enum": [s for s, _l in
                                                    CODE_STATES]}},
                     {"name": "block_id", "schema": {"type": "integer"}},
                     *PAGINATION_QUERY_PARAMS])
    def codes(self, **kwargs):
        try:
            state = parse_enum("state", kwargs.get("state"),
                               [s for s, _l in CODE_STATES])
            block_id = parse_int("block_id", kwargs.get("block_id"),
                                 minimum=1)
            limit = parse_limit(kwargs)
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        domain = []
        code = (kwargs.get("code") or "").strip()
        if code:
            domain.append(("code", "=", code))
        if state:
            domain.append(("state", "=", state))
        if block_id:
            domain.append(("block_id", "=", block_id))
        rows, nxt, total = paginate(_env("nrs.asset.code"), domain,
                                    limit=limit, cursor=kwargs.get("cursor"))
        return ok([_code_out(c) for c in rows],
                  pagination={"next_cursor": nxt, "total_estimate": total})

    # ── campaigns ─────────────────────────────────────────────────────

    @cadra_route("/api/v1/audit/campaigns", method="GET",
                 summary="Audit campaigns, with progress",
                 scopes=[SCOPE_AUDIT_READ],
                 query_params=[{"name": "state", "schema": {
                     "type": "string", "enum": ["open", "closed"]}}])
    def campaigns(self, **kwargs):
        try:
            state = parse_enum("state", kwargs.get("state"),
                               ("open", "closed"))
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        domain = [("state", "=", state)] if state else []
        return [_campaign_out(c) for c in _env("nrs.audit.campaign").search(
            domain)]

    @cadra_route("/api/v1/audit/campaigns", method="POST",
                 summary="Open an audit campaign",
                 scopes=[SCOPE_AUDIT_MANAGE],
                 request_schema={"type": "object",
                                 "required": ["name", "scope"],
                                 "properties": {
                                     "name": {"type": "string"},
                                     "scope": {"type": "array",
                                               "items": _SCOPE_LINE},
                                     "capturer_ids": _ID_LIST,
                                     "reviewer_ids": _ID_LIST,
                                     "date_start": {"type": "string",
                                                    "format": "date"},
                                     "date_end": {"type": "string",
                                                  "format": "date"}}})
    def campaign_create(self, **kwargs):
        body, error = _body({"name", "scope", "capturer_ids", "reviewer_ids",
                             "date_start", "date_end"})
        if error:
            return error
        capturers, error = _users(body.get("capturer_ids") or [],
                                  "capturer_ids")
        if error:
            return error
        reviewers, error = _users(body.get("reviewer_ids") or [],
                                  "reviewer_ids")
        if error:
            return error
        campaign, error = _guard(lambda: _env("nrs.audit.campaign").with_user(
            request.env.user).sudo()._open_campaign(
                body.get("name"), body.get("scope"), capturers, reviewers,
                body.get("date_start"), body.get("date_end")))
        return error or _campaign_out(campaign, detail=True)

    @cadra_route("/api/v1/audit/campaigns/<int:id>", method="GET",
                 summary="One campaign: scope, team, progress and rooms",
                 scopes=[SCOPE_AUDIT_READ])
    def campaign_get(self, id, **kwargs):
        campaign, error = _browse_or_404("nrs.audit.campaign", id,
                                         "campaign")
        return error or _campaign_out(campaign, detail=True)

    @cadra_route("/api/v1/audit/campaigns/<int:id>", method="PATCH",
                 summary="Change an open campaign's name, team or end date",
                 scopes=[SCOPE_AUDIT_MANAGE],
                 request_schema={"type": "object", "properties": {
                     "name": {"type": "string"},
                     "capturer_ids": _ID_LIST, "reviewer_ids": _ID_LIST,
                     "date_end": {"type": "string", "format": "date"}}})
    def campaign_patch(self, id, **kwargs):
        body, error = _body({"name", "capturer_ids", "reviewer_ids",
                             "date_end"})
        if error:
            return error
        campaign, error = _browse_or_404("nrs.audit.campaign", id,
                                         "campaign")
        if error:
            return error
        vals = {}
        capturers, reviewers = campaign.capturer_ids, campaign.reviewer_ids
        if "capturer_ids" in body:
            capturers, error = _users(body["capturer_ids"], "capturer_ids")
            if error:
                return error
            vals["capturer_ids"] = [(6, 0, capturers.ids)]
        if "reviewer_ids" in body:
            reviewers, error = _users(body["reviewer_ids"], "reviewer_ids")
            if error:
                return error
            vals["reviewer_ids"] = [(6, 0, reviewers.ids)]
        if "name" in body:
            if not isinstance(body["name"], str) or not body["name"].strip():
                return err(ERR_VALIDATION_FAILED, "Name the campaign.",
                           details={"field": "name"})
            vals["name"] = body["name"].strip()
        if "date_end" in body:
            vals["date_end"] = body["date_end"] or False

        def act():
            campaign._assert_open()
            campaign._assert_team(capturers, reviewers)
            campaign._w(vals)
            return campaign
        result, error = _guard(act)
        return error or _campaign_out(result, detail=True)

    @cadra_route("/api/v1/audit/campaigns/<int:id>/close", method="POST",
                 summary="Close a campaign — every capture reviewed — and "
                         "keep its two lists as they stood",
                 scopes=[SCOPE_AUDIT_MANAGE])
    def campaign_close(self, id, **kwargs):
        body, error = _body(set())
        if error:
            return error
        campaign, error = _browse_or_404("nrs.audit.campaign", id,
                                         "campaign")
        if error:
            return error
        lists, error = _guard(lambda: campaign.with_user(
            request.env.user).sudo()._close_campaign())
        if error:
            return error
        out = _campaign_out(campaign)
        out["lists"] = lists
        return out

    def _lists_of(self, campaign):
        if campaign.state == "closed" and campaign.closing_json:
            lists = json.loads(campaign.closing_json)
            lists["as_of"] = "closing"
        else:
            lists = campaign._lists()
            lists["as_of"] = "now"
        return lists

    @cadra_route("/api/v1/audit/campaigns/<int:id>/lists", method="GET",
                 summary="The audit's two lists, per office: found not in "
                         "SAP, and in SAP not found",
                 scopes=[SCOPE_AUDIT_READ])
    def campaign_lists(self, id, **kwargs):
        campaign, error = _browse_or_404("nrs.audit.campaign", id,
                                         "campaign")
        return error or self._lists_of(campaign)

    @http.route("/api/v1/audit/campaigns/<int:id>/lists.csv", type="http",
                auth="none", methods=["GET"], csrf=False)
    def campaign_lists_csv(self, id, **kwargs):
        """One of the two lists as a file (`?list=`), for the auditors who
        take it away."""
        _, envelope, _ = require_jwt(scopes=[SCOPE_AUDIT_READ])
        if envelope is not None:
            return _http_response(envelope)
        try:
            which = parse_enum("list", kwargs.get("list"), LISTS)
        except BadFilter as e:
            return _http_response(err(ERR_INVALID_REQUEST, str(e),
                                      details=e.details))
        if not which:
            return _http_response(err(
                ERR_VALIDATION_FAILED, "Say which list: `?list=` is one of "
                "%s." % ", ".join(LISTS), details={"allowed_values":
                                                   list(LISTS)}))
        campaign = _env("nrs.audit.campaign").browse(id).exists()
        if not campaign:
            return _http_response(err(ERR_NOT_FOUND, "There is no campaign "
                                      "with id %s." % id, status=404))
        lists = self._lists_of(campaign)
        if which == "found_not_in_sap":
            columns = ["office_code", "code", "name", "category", "location",
                       "captured_by", "captured_at", "exception_state",
                       "capture_id"]
        else:
            columns = ["office_code", "asset_number", "sub_number",
                       "asset_class", "description", "old_tag",
                       "capitalized_on"]
        return _csv(lists[which], columns, "campaign-%d-%s.csv"
                    % (campaign.id, which.replace("_", "-")))

    @cadra_route("/api/v1/audit/campaigns/<int:id>/slice", method="GET",
                 summary="A room's Cadra assets, or its office's SAP "
                         "records, for an offline phone",
                 scopes=[SCOPE_AUDIT_READ],
                 query_params=[
                     {"name": "location_id", "required": True,
                      "schema": {"type": "integer"}},
                     {"name": "kind", "schema": {"type": "string",
                                                 "enum": list(SLICE_KINDS)}},
                     {"name": "updated_since", "schema": {"type": "string"}},
                     *PAGINATION_QUERY_PARAMS])
    def campaign_slice(self, id, **kwargs):
        try:
            location_id = parse_int("location_id", kwargs.get("location_id"),
                                    minimum=1)
            kind = parse_enum("kind", kwargs.get("kind"), SLICE_KINDS) \
                or "assets"
            since = _parse_updated_since(kwargs.get("updated_since"))
            limit = parse_limit(kwargs)
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        if not location_id:
            return err(ERR_VALIDATION_FAILED, "`location_id` is the room — "
                       "from its scanned room code.",
                       details={"field": "location_id"})
        campaign, error = _browse_or_404("nrs.audit.campaign", id,
                                         "campaign")
        if error:
            return error
        room = _env("generic.location").browse(location_id).exists()
        if not room:
            return err(ERR_NOT_FOUND, "There is no room with id %s."
                       % location_id, status=404)
        if not campaign._covers(room):
            return err("conflict", "%s is outside campaign %s."
                       % (room.display_name, campaign.name), status=409,
                       details={"reason": "invalid_state"})
        office = campaign._office_of(room)
        if kind == "assets":
            domain = [("location_id", "child_of", room.id)]
            if since:
                domain.append(("write_date", ">=", since))
            rows, nxt, total = paginate(_env("nrs.asset"), domain,
                                        limit=limit,
                                        cursor=kwargs.get("cursor"))
            data = [{"id": a.id, "asset_code": a.asset_code, "name": a.name,
                     "asset_tag": a.asset_tag or None,
                     "legacy_asset_code": a.legacy_asset_code or None,
                     "serial_number": a.serial_number or None,
                     "category": a.category_id.name or None,
                     "condition": a.condition, "state": a.state,
                     "sap_asset_number": a.sap_asset_number or None,
                     "location_id": a.location_id.id or None,
                     "updated_at": _iso(a.write_date)} for a in rows]
        else:
            if not office:
                return ok({"office_code": None, "records": [],
                           "note": "This room's campaign names no SAP "
                                   "office for it, so no SAP records are "
                                   "sent."}, pagination={
                               "next_cursor": None, "total_estimate": 0})
            domain = [("office_code", "=", office),
                      ("deactivated_on", "=", False),
                      ("in_latest_export", "=", True)]
            if since:
                domain.append(("write_date", ">=", since))
            rows, nxt, total = paginate(_env("nrs.sap.asset"), domain,
                                        limit=limit,
                                        cursor=kwargs.get("cursor"))
            linked = rows._linked_assets()
            data = [{"id": s.id, "asset_number": s.asset_number,
                     "sub_number": s.sub_number or None,
                     "class": s.asset_class or None,
                     "description": s.description or None,
                     "old_tag": s.old_tag or None,
                     "serial_number": s.serial_number or None,
                     "capitalized_on": s.capitalized_on.isoformat()
                     if s.capitalized_on else None,
                     "linked_asset_id": (linked.get(s.id) or {}).get(
                         "asset_id"),
                     "updated_at": _iso(s.write_date)} for s in rows]
        return ok({"kind": kind, "office_code": office,
                   "location": {"id": room.id, "name": room.display_name,
                                "location_code": room.location_code or None},
                   "records": data},
                  pagination={"next_cursor": nxt, "total_estimate": total})

    # ── photos and captures ───────────────────────────────────────────

    @cadra_route("/api/v1/audit/photos", method="POST",
                 summary="Sync one photo for a capture (multipart: `file`, "
                         "`source`)",
                 scopes=[SCOPE_AUDIT_CAPTURE],
                 error_statuses=(413, 415),
                 request_schema={"type": "object",
                                 "x-cadra-content-type": "multipart/form-data",
                                 "properties": {
                                     "file": {"type": "string",
                                              "format": "binary"},
                                     "source": {"type": "string",
                                                "enum": ["web", "mobile"]}}})
    def photo_upload(self, **kwargs):
        values, uploads, error = get_multipart(
            file_fields=("file",), text_fields=("source",),
            required=("file",))
        if error:
            return error
        up = uploads["file"]
        result, error = _guard(lambda: _env("nrs.audit.photo").with_user(
            request.env.user).sudo()._upload(
                up.read(), source=values.get("source") or "mobile",
                filename=up.filename))
        if error:
            return error
        photo, created = result
        out = _photo_brief(photo)
        out["already_synced"] = not created
        return out

    @http.route("/api/v1/audit/photos/<int:id>", type="http", auth="none",
                methods=["GET"], csrf=False)
    def photo_file(self, id, **kwargs):
        """A capture's photo — the file, not the envelope."""
        _, envelope, _ = require_jwt(scopes=[SCOPE_AUDIT_READ])
        if envelope is not None:
            return _http_response(envelope)
        photo = _env("nrs.audit.photo").browse(id).exists()
        if not photo:
            return _http_response(err(ERR_NOT_FOUND, "There is no audit "
                                      "photo with id %s." % id, status=404))
        try:
            data = photo._bytes()
        except UserError as e:
            # Altered underneath the row: not served as the photo.
            return _http_response(err(
                "conflict", str(e.args[0]), status=409,
                details={"reason": "integrity_mismatch",
                         "photo_id": photo.id,
                         "recorded_sha256": photo.sha256}))
        return request.make_response(data, headers=[
            ("Content-Type", photo.mimetype),
            ("Content-Length", str(len(data))),
            ("X-Content-Type-Options", "nosniff"),
            ("Cache-Control", "private, max-age=31536000, immutable"),
            ("ETag", '"%s"' % photo.sha256),
        ])

    @cadra_route("/api/v1/audit/captures", method="POST",
                 summary="Sync one capture from a device (idempotent on "
                         "`capture_id`)",
                 scopes=[SCOPE_AUDIT_CAPTURE], success_status=201,
                 request_schema={
                     "type": "object",
                     "required": ["capture_id", "campaign_id", "location_id",
                                  "outcome", "photo_ids", "captured_at",
                                  "fields"],
                     "properties": {
                         "capture_id": {"type": "string", "format": "uuid"},
                         "campaign_id": {"type": "integer"},
                         "location_id": {"type": "integer"},
                         "outcome": {"type": "string",
                                     "enum": [o for o, _l in OUTCOMES]},
                         "asset_id": {"type": "integer"},
                         "sap_record_id": {"type": "integer"},
                         "code": {"type": "string"},
                         "scanned_label": {"type": "string"},
                         "label": {"type": "string",
                                   "enum": [l for l, _x in LABEL_STATES]},
                         "photo_ids": _ID_LIST,
                         "ai_suggestion_id": {"type": "integer"},
                         "captured_at": {"type": "string",
                                         "format": "date-time"},
                         "gps": {"type": "object", "description":
                                 "AI-FR-10, optional: where the device was. "
                                 "Stored on the capture only — never sent "
                                 "to the AI provider, never on the asset.",
                                 "properties": {
                                     "latitude": {"type": "number",
                                                  "minimum": -90,
                                                  "maximum": 90},
                                     "longitude": {"type": "number",
                                                   "minimum": -180,
                                                   "maximum": 180},
                                     "accuracy_m": {"type": "number",
                                                    "minimum": 0}},
                                 "required": ["latitude", "longitude"]},
                         "fields": {"type": "object", "properties": {
                             k: {} for k in CONFIRMED_FIELDS}}}})
    def capture(self, **kwargs):
        body, error = _body({"capture_id", "campaign_id", "location_id",
                             "outcome", "asset_id", "sap_record_id", "code",
                             "scanned_label", "label", "photo_ids",
                             "ai_suggestion_id", "captured_at", "fields",
                             "gps"})
        if error:
            return error
        me = request.env.user

        def act():
            device = _env("nrs.audit.device")._from_header(
                request.httprequest.headers.get(DEVICE_HEADER), me)
            return _env("nrs.audit.capture").with_user(me).sudo()._receive(
                body, device)
        result, error = _guard(act)
        if error:
            return error
        cap, created = result
        out = _capture_out(cap)
        out["replayed"] = not created
        return out

    @cadra_route("/api/v1/audit/captures", method="GET",
                 summary="Captures — by campaign, room, state and outcome",
                 scopes=[SCOPE_AUDIT_READ],
                 query_params=[
                     {"name": "campaign_id", "schema": {"type": "integer"}},
                     {"name": "location_id", "schema": {"type": "integer"}},
                     {"name": "state", "schema": {
                         "type": "string",
                         "enum": [s for s, _l in CAPTURE_STATES]}},
                     {"name": "outcome", "schema": {
                         "type": "string", "enum": [o for o, _l in OUTCOMES]}},
                     {"name": "exception_state", "schema": {
                         "type": "string",
                         "enum": [s for s, _l in EXCEPTION_STATES]}},
                     {"name": "duplicates", "schema": {"type": "boolean"}},
                     {"name": "mine", "schema": {"type": "boolean"}},
                     *PAGINATION_QUERY_PARAMS])
    def captures(self, **kwargs):
        try:
            campaign_id = parse_int("campaign_id", kwargs.get("campaign_id"),
                                    minimum=1)
            location_id = parse_int("location_id", kwargs.get("location_id"),
                                    minimum=1)
            state = parse_enum("state", kwargs.get("state"),
                               [s for s, _l in CAPTURE_STATES])
            outcome = parse_enum("outcome", kwargs.get("outcome"),
                                 [o for o, _l in OUTCOMES])
            exception_state = parse_enum(
                "exception_state", kwargs.get("exception_state"),
                [s for s, _l in EXCEPTION_STATES])
            duplicates = parse_bool("duplicates", kwargs.get("duplicates"))
            mine = parse_bool("mine", kwargs.get("mine"))
            limit = parse_limit(kwargs)
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        domain = []
        if campaign_id:
            domain.append(("campaign_id", "=", campaign_id))
        if location_id:
            domain.append(("location_id", "=", location_id))
        if state:
            domain.append(("state", "=", state))
        if outcome:
            domain.append(("outcome", "=", outcome))
        if exception_state:
            domain.append(("exception_state", "=", exception_state))
        if duplicates is not None:
            domain.append(("duplicate_of_id", "!=" if duplicates else "=",
                           False))
        if mine:
            domain.append(("operator_id", "=", request.env.uid))
        rows, nxt, total = paginate(_env("nrs.audit.capture"), domain,
                                    limit=limit, cursor=kwargs.get("cursor"))
        return ok([_capture_out(c) for c in rows],
                  pagination={"next_cursor": nxt, "total_estimate": total})

    @cadra_route("/api/v1/audit/captures/<string:capture_id>", method="GET",
                 summary="One capture by its capture_id — the phone "
                         "confirming a sync",
                 scopes=[SCOPE_AUDIT_READ])
    def capture_get(self, capture_id, **kwargs):
        cap, error = _capture_or_404(capture_id)
        return error or _capture_out(cap)

    # ── review ────────────────────────────────────────────────────────

    @cadra_route("/api/v1/audit/captures/<string:capture_id>/accept",
                 method="POST", summary="Accept a capture somebody else made",
                 scopes=[SCOPE_AUDIT_REVIEW])
    def capture_accept(self, capture_id, **kwargs):
        body, error = _body(set())
        if error:
            return error
        cap, error = _capture_or_404(capture_id)
        if error:
            return error
        result, error = _guard(lambda: cap.with_user(request.env.user).sudo()._accept())
        return error or _capture_out(result)

    @cadra_route("/api/v1/audit/captures/<string:capture_id>/return",
                 method="POST",
                 summary="Return a capture to its capturer, with a reason",
                 scopes=[SCOPE_AUDIT_REVIEW],
                 request_schema={"type": "object", "required": ["reason"],
                                 "properties": {"reason": {"type": "string"}}})
    def capture_return(self, capture_id, **kwargs):
        body, error = _body({"reason"})
        if error:
            return error
        cap, error = _capture_or_404(capture_id)
        if error:
            return error
        result, error = _guard(lambda: cap.with_user(request.env.user).sudo()._return_capture(body.get("reason")))
        return error or _capture_out(result)

    @cadra_route("/api/v1/audit/captures/accept", method="POST",
                 summary="Accept a batch of captures — a room's, or a list",
                 scopes=[SCOPE_AUDIT_REVIEW], success_status=200,
                 request_schema={"type": "object", "properties": {
                     "capture_ids": {"type": "array",
                                     "items": {"type": "string"},
                                     "maxItems": BATCH_MAX},
                     "campaign_id": {"type": "integer"},
                     "location_id": {"type": "integer"},
                     "dry_run": {"type": "boolean"}}})
    def capture_accept_batch(self, **kwargs):
        body, error = _body({"capture_ids", "campaign_id", "location_id",
                             "dry_run"})
        if error:
            return error
        dry_run = body.get("dry_run", False)
        if not isinstance(dry_run, bool):
            return err(ERR_INVALID_REQUEST, "`dry_run` must be true or "
                       "false.", details={"field": "dry_run"})
        Capture = _env("nrs.audit.capture")
        if body.get("capture_ids") is not None:
            ids = body["capture_ids"]
            if not isinstance(ids, list) or not ids or not all(
                    isinstance(i, str) for i in ids) \
                    or len(ids) > BATCH_MAX or len(set(ids)) != len(ids):
                return err(ERR_INVALID_REQUEST, "`capture_ids` is a list of "
                           "1 to %d distinct capture ids." % BATCH_MAX,
                           details={"field": "capture_ids"})
        else:
            if not all(isinstance(body.get(k), int)
                       and not isinstance(body.get(k), bool)
                       for k in ("campaign_id", "location_id")):
                return err(ERR_VALIDATION_FAILED, "Name the captures: "
                           "`capture_ids`, or a room — `campaign_id` and "
                           "`location_id` — whose waiting captures are "
                           "accepted. Held duplicates are left for one-by-"
                           "one review.", details={"field": "capture_ids"})
            ids = Capture.search([
                ("campaign_id", "=", body["campaign_id"]),
                ("location_id", "=", body["location_id"]),
                ("state", "=", "pending_review"),
                ("duplicate_of_id", "=", False)], order="id",
                limit=BATCH_MAX).mapped("capture_uuid")
        ids = [_norm_uuid(i) for i in ids]
        found = {c.capture_uuid: c for c in Capture.search(
            [("capture_uuid", "in", ids)])}
        me = request.env.user
        out = []
        try:
            with request.env.cr.savepoint():
                for uid in ids:
                    line = {"capture_id": uid}
                    cap = found.get(uid)
                    if not cap:
                        line.update(outcome="refused", status=404,
                                    code=ERR_NOT_FOUND,
                                    message="No capture has the id %s." % uid,
                                    details={})
                        out.append(line)
                        continue
                    try:
                        with request.env.cr.savepoint():
                            done = cap.with_user(me).sudo()._accept()
                        line.update(outcome="done", status=200, code=None,
                                    message=None, details=None,
                                    asset_id=done.result_asset_id.id or None)
                    except GateRefused as e:
                        status, code, message, details = \
                            gate_refusal_parts(e)
                        line.update(outcome="refused", status=status,
                                    code=code, message=message,
                                    details=details)
                    except (UserError, ValidationError) as e:
                        line.update(outcome="refused", status=400,
                                    code=ERR_VALIDATION_FAILED,
                                    message=str(e.args[0]), details={})
                    out.append(line)
                if dry_run:
                    raise _DryRun()
        except _DryRun:
            pass
        if dry_run:
            for line in out:
                if line["outcome"] == "done":
                    line["outcome"] = "would_do"
                    line["asset_id"] = None
        done = sum(1 for l in out if l["outcome"] in ("done", "would_do"))
        # capped-count-ok: the lines of THIS batch, one per capture named.
        total = len(out)
        return {"action": "accept", "dry_run": dry_run, "total": total,
                "done": done, "refused": total - done, "results": out}

    # ── the exceptions (outcome c) ────────────────────────────────────

    @cadra_route("/api/v1/audit/captures/<string:capture_id>/register-new",
                 method="POST",
                 summary="Register a found-not-in-SAP item as new, through "
                         "the Register Maker and Checker",
                 scopes=[SCOPE_AUDIT_MANAGE],
                 request_schema={"type": "object", "properties": {
                     "fields": {"type": "object", "description":
                                "The item's identity the class asks for and "
                                "the capture lacks: make, model_name, "
                                "serial_number, colour, material, "
                                "dimensions."}}})
    def exception_register(self, capture_id, **kwargs):
        body, error = _body({"fields"})
        if error:
            return error
        completed = body.get("fields") or {}
        if not isinstance(completed, dict):
            return err(ERR_INVALID_REQUEST, "`fields` is an object.",
                       details={"field": "fields"})
        cap, error = _capture_or_404(capture_id)
        if error:
            return error
        _asset, error = _guard(lambda: cap.with_user(
            request.env.user).sudo()._register_new(completed))
        return error or _capture_out(cap)

    @cadra_route("/api/v1/audit/captures/<string:capture_id>/void",
                 method="POST",
                 summary="Void a found-not-in-SAP exception, with a reason "
                         "(its code is voided)",
                 scopes=[SCOPE_AUDIT_MANAGE],
                 request_schema={"type": "object", "required": ["reason"],
                                 "properties": {"reason": {"type": "string"}}})
    def exception_void(self, capture_id, **kwargs):
        body, error = _body({"reason"})
        if error:
            return error
        cap, error = _capture_or_404(capture_id)
        if error:
            return error
        result, error = _guard(lambda: cap.with_user(request.env.user).sudo()._void_exception(body.get("reason")))
        return error or _capture_out(result)

    # ── the phone's one read of the AI and the label ──────────────────

    @cadra_route("/api/v1/ai/config", method="GET",
                 summary="The AI switch, model and today's remaining calls, "
                         "and the label layout — for a phone going offline",
                 scopes_any=[SCOPE_AUDIT_CAPTURE, SCOPE_ASSETS_WRITE])
    def ai_config(self, **kwargs):
        env = request.env
        s = ai_settings(env)
        calls = env["nrs.ai.suggestion"].sudo()._calls_today()
        return {
            "ai_identify": {"enabled": s["enabled"],
                            "provider": s["provider"], "model": s["model"],
                            "daily_cap": s["daily_cap"],
                            "calls_today": calls,
                            "remaining_today": max(0, s["daily_cap"] - calls),
                            "route": "/api/v1/ai/identify"},
            "label": LABEL_LAYOUT,
            "capture": {"earliest_captured_on":
                        earliest_capture_day().isoformat(),
                        "max_working_days_back": 5,
                        "device_header": DEVICE_HEADER,
                        "max_block_size": MAX_BLOCK_SIZE,
                        "confirmed_fields": list(CONFIRMED_FIELDS),
                        "outcomes": [o for o, _l in OUTCOMES]},
        }
