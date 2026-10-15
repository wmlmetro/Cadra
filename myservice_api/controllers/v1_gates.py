"""The receipt gates over HTTP — handoff 57, kept by handoff 58.

The gate machine lives on `nrs.asset` (`register_state`); handoff 58 kept it
there rather than move it to a separate candidate model
(`docs/ADDENDUM-A-EVALUATION.md` §8). See
`myservice_asset_register/models/asset_gates.py` for the design, and why its
register filter is load-bearing.

WHAT THIS PUBLISHES
-------------------
A unit of a `record_only` class (handoff 59 §2) never sees
`request-tagging` or an affix: IAD's approval moves it to `reg_ready`.

Ten actions, one POST each under `/api/v1/assets/<id>/gates/`, every one a
thin call into `nrs.asset._fire_gate` — the ONE method that moves
`register_state` — and one list, `GET /api/v1/candidates`. The table of
which state each action moves from, to, and who may fire it is
`asset_gates.TRANSITIONS`; nothing here restates it.

Every answer to a gate is the asset as it now stands (`serialize_asset`,
with its `register_state` and `gates` block), so the app redraws from the
server rather than trusting the verb.

BATCHES (handoff 60 §2; six since handoff 61) — routes under
`/api/v1/candidates/gates/`,
for the gates a person fires on many units at once: `verify`, `approve`,
`register` (a pasted list of asset code → SAP code) and
`approve-registration`. **A batch is N single-unit fires**, each through
`_fire_gate`, each in its own savepoint, each checked by every rule a single
fire meets (state, scope, the no-two-gates rule, the placeholder and SAP
class checks) and each writing its own append-only event: a batch never
writes one event for many units, and one refused unit never rolls back the
others. The answer lists every unit, fired or refused with the status,
code and sentence it would have had alone. A refusal of the BATCH itself —
a body that cannot be read, a verify mixing receipts, evidence that fails
the verify checks — is the envelope's 400, before anything is written.
`dry_run: true` runs the whole batch in a savepoint and rolls it back: the
preview is the real answer, a SAP code duplicated inside the paste
included, and nothing remains.

The evidence of a verification is published for the IAD approver, who
until handoff 60 approved without seeing it: `GET /assets/<id>/evidence`
and the file itself at `GET /assets/<id>/evidence/<attachment id>`.
Since handoff 61 (ruling 1 on report 60) both are behind `evidence:read`
— IAD, the Register Maker and Checker, the Auditor — through ONE guard,
`utils.evidence_readable()`; the list answers a caller without it with the
count and nothing else, and the file route refuses it.

`submit` and `request-tagging` have batches too since handoff 61 (ruling 5
on report 60), by the same rules; a selection may mix receipts for these
two, because neither attests to a delivery the way `verify` does.

THE REFUSALS, in the order they are checked — every one BEFORE anything is
written:

* **409 `conflict`, `details.reason = "invalid_state"`** — the action cannot
  be done from the record's state.
* **403 `forbidden`** — the caller lacks the gate's scope; the message names
  it.
* **400 `validation_failed`** — a reason, a response, the four-item
  checklist, an attachment, the SAP code, the cost… missing, in words; a
  category with no SAP asset class at `register` and `approve-registration`
  (handoff 59 §1).
* **409 `conflict`, `details.reason = "segregation_of_duties"`** — the
  no-two-gates rule: *"You received this unit on 7 Oct; a different person
  must verify it."* `details.earlier` names the act, the gate, the date and
  the person. Never "permission denied".
"""
import base64

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.myservice_asset_register.models.asset_gates import (
    CANDIDATES_CTX,
    GateRefused,
    REGISTER_STATES as _MODEL_STATES,
    REGISTERED,
    WAITING_ON,
    WAITING_ON_VALUES,
)

from .utils import (
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    ERR_VALIDATION_FAILED,
    SCOPE_ASSETS_WRITE,
    SCOPE_CANDIDATES_READ,
    SCOPE_EVIDENCE_READ,
    SCOPE_REGISTER_CHECK,
    SCOPE_REGISTER_MAKE,
    SCOPE_TAGGING_REQUEST,
    SCOPE_VFM_APPROVE,
    SCOPE_VFM_VERIFY,
    _http_response,
    err,
    evidence_count_only,
    evidence_readable,
    gate_refusal,
    gate_refusal_parts,
    get_params,
    ok,
    paginate,
    parse_limit,
    refuse_unwritable,
    require_jwt,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route
from .v1_assets import (
    REGISTER_STATES,
    _browse_or_404,
    _list_domain,
    serialize_asset,
)
from .query_params import BadFilter, parse_bool, parse_enum

_ASSET = {"$ref": "#/components/schemas/Asset"}
_ERRORS = (403, 404, 409)

_NOTES = {"notes": {"type": "string", "nullable": True,
                    "description": "Optional; recorded on the gate's event."}}
_REASON = {"reason": {"type": "string",
                      "description": "Required, in words — why."}}

#: What each action's body may carry. Anything else is refused 400 and
#: nothing is written (rule 3).
_BODY_KEYS = {
    "submit": ("notes",),
    "verify": ("checklist", "attachments", "notes"),
    "approve": ("notes",),
    "query": ("reason",),
    "resubmit": ("response",),
    "reject": ("reason",),
    "request-tagging": ("notes",),
    "register": ("sap_asset_code", "cost", "cost_centre",
                 "capitalisation_date", "asset_class", "notes"),
    "approve-registration": ("notes",),
    "return-registration": ("reason",),
}

#: The batch routes' bodies (handoff 60 §2). Anything else is refused.
_BATCH_KEYS = {
    # Handoff 61, ruling 5 on report 60: the last two gates still at two
    # clicks a unit. Same rules as 60's — N single fires — and a selection
    # may mix receipts: neither act attests to one delivery's papers.
    "submit": ("asset_ids", "notes", "dry_run"),
    "request-tagging": ("asset_ids", "notes", "dry_run"),
    "verify": ("asset_ids", "checklist", "attachments", "notes", "dry_run"),
    "approve": ("asset_ids", "notes", "dry_run"),
    "register": ("lines", "cost_centre", "capitalisation_date", "notes",
                 "dry_run"),
    "approve-registration": ("asset_ids", "notes", "dry_run"),
}
_LINE_KEYS = ("asset_code", "sap_asset_code", "cost")
#: One page of the Candidates list.
BATCH_MAX = 100
#: `GET /candidates?sort=` (handoff 60 §2a).
_SORTS = ("newest", "oldest")


def _refusal(e):
    """A `GateRefused` as the envelope — `utils.gate_refusal`, the one
    mapping every route shares since handoff 58 (D3)."""
    return gate_refusal(e)


def _token_scopes():
    """The caller's scopes, as the token carries them."""
    claims = getattr(request, "jwt_claims", None) or {}
    scopes = claims.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    return scopes


def _fire(asset_id, action, body, *, reason=None, payload=None):
    """The one shape every gate route has."""
    asset, error = _browse_or_404(asset_id)
    if error:
        return error
    allowed = _BODY_KEYS[action]
    rejected = sorted(k for k in (body or {}) if k not in allowed)
    if rejected:
        return refuse_unwritable(rejected, allowed)
    if reason is not None and not isinstance(reason, str):
        return err(ERR_INVALID_REQUEST, "The reason must be a string.")
    scopes = _token_scopes()
    try:
        # A savepoint: `err()` does not roll back, and a refusal raised
        # part-way through a write (the SAP code's uniqueness constraint)
        # must not leave half an act behind.
        with request.env.cr.savepoint():
            asset._fire_gate(action, reason=reason, payload=payload or {},
                             scopes=scopes)
    except GateRefused as e:
        return _refusal(e)
    except (UserError, ValidationError) as e:
        return err(ERR_VALIDATION_FAILED, str(e.args[0]))
    asset.invalidate_recordset()
    data = serialize_asset(asset)
    if action in ("register", "approve-registration"):
        # Handoff 59 §4: an 11-digit SAP number whose first digit is not the
        # class's is said, not refused — the maker may be right and the
        # mapping wrong. The maker reads it on submission, the checker on
        # approval; it is on the `register` event's evidence too.
        warning = asset._sap_number_warning()
        if warning:
            data["_warnings"] = {"sap_asset_number": warning}
    return data


class CadraGatesV1(http.Controller):

    @cadra_route("/api/v1/assets/<int:id>/gates/submit", method="POST",
                 summary="Store submits a captured receipt to Internal Audit",
                 scopes=[SCOPE_ASSETS_WRITE], error_statuses=_ERRORS,
                 request_schema={"type": "object", "properties": dict(_NOTES)},
                 response_schema=_ASSET)
    def gate_submit(self, id, **kwargs):
        """`captured` → `vfm_pending`. The receipt gate."""
        body = get_params() or {}
        return _fire(id, "submit", body, payload={"notes": body.get("notes")})

    @cadra_route("/api/v1/assets/<int:id>/gates/verify", method="POST",
                 summary="IAD sights the unit, attaches evidence and verifies",
                 scopes=[SCOPE_VFM_VERIFY], error_statuses=_ERRORS,
                 request_schema={
                     "type": "object",
                     "required": ["checklist", "attachments"],
                     "properties": {
                         "checklist": {
                             "type": "object",
                             "description": "All four must be `true`.",
                             "properties": {
                                 k: {"type": "boolean"} for k in (
                                     "quantity", "specification",
                                     "condition", "price")}},
                         "attachments": {
                             "type": "array", "minItems": 1,
                             "items": {"type": "object",
                                       "required": ["name", "data"],
                                       "properties": {
                                           "name": {"type": "string"},
                                           "mimetype": {"type": "string"},
                                           "data": {"type": "string",
                                                    "format": "byte"}}}},
                         **_NOTES,
                     }},
                 request_example={
                     "checklist": {"quantity": True, "specification": True,
                                   "condition": True, "price": True},
                     "attachments": [{"name": "sighting.jpg",
                                      "mimetype": "image/jpeg",
                                      "data": "<base64>"}]},
                 response_schema=_ASSET)
    def gate_verify(self, id, **kwargs):
        """`vfm_pending` → `vfm_verified`."""
        body = get_params() or {}
        return _fire(id, "verify", body, payload={
            "checklist": body.get("checklist"),
            "attachments": body.get("attachments"),
            "notes": body.get("notes")})

    @cadra_route("/api/v1/assets/<int:id>/gates/approve", method="POST",
                 summary="IAD approves value for money (not the verifier)",
                 scopes=[SCOPE_VFM_APPROVE], error_statuses=_ERRORS,
                 request_schema={"type": "object", "properties": dict(_NOTES)},
                 response_schema=_ASSET)
    def gate_approve(self, id, **kwargs):
        """`vfm_verified` → `vfm_approved`."""
        body = get_params() or {}
        return _fire(id, "approve", body, payload={"notes": body.get("notes")})

    @cadra_route("/api/v1/assets/<int:id>/gates/query", method="POST",
                 summary="IAD queries the unit back to Store (vfm:verify or "
                         "vfm:approve)",
                 scopes=[SCOPE_CANDIDATES_READ], error_statuses=_ERRORS,
                 request_schema={"type": "object", "required": ["reason"],
                                 "properties": dict(_REASON)},
                 response_schema=_ASSET)
    def gate_query(self, id, **kwargs):
        """`vfm_pending`/`vfm_verified` → `vfm_query`. The route's scope is
        the floor; the model requires `vfm:verify` or `vfm:approve`."""
        body = get_params() or {}
        return _fire(id, "query", body, reason=body.get("reason"))

    @cadra_route("/api/v1/assets/<int:id>/gates/resubmit", method="POST",
                 summary="Store answers IAD's query; the unit returns to "
                         "captured",
                 scopes=[SCOPE_ASSETS_WRITE], error_statuses=_ERRORS,
                 request_schema={"type": "object", "required": ["response"],
                                 "properties": {"response": {
                                     "type": "string",
                                     "description": "Required — Store's "
                                                    "answer to the query."}}},
                 response_schema=_ASSET)
    def gate_resubmit(self, id, **kwargs):
        """`vfm_query` → `captured`."""
        body = get_params() or {}
        return _fire(id, "resubmit", body, reason=body.get("response"))

    @cadra_route("/api/v1/assets/<int:id>/gates/reject", method="POST",
                 summary="IAD rejects the unit (terminal tonight)",
                 scopes=[SCOPE_VFM_APPROVE], error_statuses=_ERRORS,
                 request_schema={"type": "object", "required": ["reason"],
                                 "properties": dict(_REASON)},
                 response_schema=_ASSET)
    def gate_reject(self, id, **kwargs):
        """`vfm_pending`/`vfm_verified` → `vfm_rejected`."""
        body = get_params() or {}
        return _fire(id, "reject", body, reason=body.get("reason"))

    @cadra_route("/api/v1/assets/<int:id>/gates/request-tagging",
                 method="POST",
                 summary="The Asset Controller requests tagging; the label "
                         "is issued",
                 scopes=[SCOPE_TAGGING_REQUEST], error_statuses=_ERRORS,
                 request_schema={"type": "object", "properties": dict(_NOTES)},
                 response_schema=_ASSET)
    def gate_request_tagging(self, id, **kwargs):
        """`vfm_approved` → `tag_requested` → `tag_issued`. The label is
        minted here, its number the asset code."""
        body = get_params() or {}
        return _fire(id, "request-tagging", body,
                     payload={"notes": body.get("notes")})

    @cadra_route("/api/v1/assets/<int:id>/gates/register", method="POST",
                 summary="The Register Maker submits the tagged unit with its "
                         "SAP code and cost",
                 scopes=[SCOPE_REGISTER_MAKE], error_statuses=_ERRORS,
                 request_schema={
                     "type": "object",
                     "required": ["sap_asset_code", "cost", "cost_centre",
                                  "capitalisation_date", "asset_class"],
                     "properties": {
                         "sap_asset_code": {
                             "type": "string",
                             "description": "Typed by the maker; recorded "
                                            "as entered by hand. Both of "
                                            "SAP's shapes — 11 digits, "
                                            "the first the class's — or a "
                                            "legacy code of letters and "
                                            "digits (up to 12) — stored "
                                            "stripped and upper-cased, and "
                                            "unique in that form. An 11-digit "
                                            "number whose first digit is not "
                                            "the class's answers with "
                                            "`data._warnings.sap_asset_number`"
                                            " (handoff 59)."},
                         "cost": {"type": "number", "exclusiveMinimum": 0},
                         "cost_centre": {"type": "string"},
                         "capitalisation_date": {"type": "string",
                                                 "format": "date"},
                         "asset_class": {
                             "type": "integer",
                             "description": "The asset category id — sending "
                                            "it is the confirmation; a "
                                            "different id corrects it. "
                                            "Refused when that category has "
                                            "no `sap_asset_class` (handoff "
                                            "59)."},
                         **_NOTES,
                     }},
                 request_example={"sap_asset_code": "30000214587",
                                  "cost": 1850000, "cost_centre": "NRS-HQ-IT",
                                  "capitalisation_date": "2026-10-08",
                                  "asset_class": 7},
                 response_schema=_ASSET)
    def gate_register(self, id, **kwargs):
        """`tagged` (or `reg_ready`, a unit with no label) →
        `reg_submitted`."""
        body = get_params() or {}
        return _fire(id, "register", body, payload={
            "sap_asset_code": body.get("sap_asset_code"),
            "cost": body.get("cost"),
            "cost_centre": body.get("cost_centre"),
            "capitalisation_date": body.get("capitalisation_date"),
            "asset_class": body.get("asset_class"),
            "notes": body.get("notes")})

    @cadra_route("/api/v1/assets/<int:id>/gates/approve-registration",
                 method="POST",
                 summary="The Register Checker approves (not the maker); the "
                         "unit is registered and SAP gets the master",
                 scopes=[SCOPE_REGISTER_CHECK], error_statuses=_ERRORS,
                 request_schema={"type": "object", "properties": dict(_NOTES)},
                 response_schema=_ASSET)
    def gate_approve_registration(self, id, **kwargs):
        """`reg_submitted` → `registered`."""
        body = get_params() or {}
        return _fire(id, "approve-registration", body,
                     payload={"notes": body.get("notes")})

    @cadra_route("/api/v1/assets/<int:id>/gates/return-registration",
                 method="POST",
                 summary="The Register Checker returns the registration to "
                         "the maker",
                 scopes=[SCOPE_REGISTER_CHECK], error_statuses=_ERRORS,
                 request_schema={"type": "object", "required": ["reason"],
                                 "properties": dict(_REASON)},
                 response_schema=_ASSET)
    def gate_return_registration(self, id, **kwargs):
        """`reg_submitted` → `tagged` (`reg_ready` for a unit with no
        label); the tag and the code are kept."""
        body = get_params() or {}
        return _fire(id, "return-registration", body,
                     reason=body.get("reason"))

    # ── the list ──────────────────────────────────────────────────────

    @cadra_route("/api/v1/candidates", method="GET",
                 summary="Receipt candidates — every unit not yet on the "
                         "register, newest first (or `sort=oldest`)",
                 scopes=[SCOPE_CANDIDATES_READ],
                 response_schema={"type": "array", "items": _ASSET},
                 query_params=[
                     {"name": "waiting_on",
                      "schema": {"type": "string",
                                 "enum": list(WAITING_ON_VALUES)},
                      "description": "Whose move it is, derived from the "
                                     "state: `store` (captured, queried), "
                                     "`iad` (awaiting verification), "
                                     "`iad_approver` (verified), "
                                     "`controller` (VfM approved), "
                                     "`tagging` (tag requested or issued), "
                                     "`maker` (tagged, or ready for "
                                     "registration with no label), "
                                     "`checker` (registration submitted)."},
                     {"name": "register_state",
                      "schema": {"type": "string",
                                 "enum": [s for s in REGISTER_STATES
                                          if s != REGISTERED]}},
                     {"name": "q", "schema": {"type": "string"},
                      "description": "Free text, as on `GET /assets` — "
                                     "the GRN included."},
                     {"name": "waiting_on_me",
                      "schema": {"type": "boolean"},
                      "description": "Handoff 60: only the units waiting "
                                     "on an act the caller may do — they "
                                     "hold its scope and the no-two-gates "
                                     "rule does not bar them. The sidebar "
                                     "badge is this list's "
                                     "`total_estimate`. A barred unit is "
                                     "still under its plain `waiting_on`, "
                                     "with its refusal."},
                     {"name": "sort",
                      "schema": {"type": "string",
                                 "enum": list(_SORTS), "default": "newest"},
                      "description": "Handoff 60: `oldest` lists the unit "
                                     "that has been in its state longest "
                                     "first (`gates.state_since`); `newest` "
                                     "(the default, unchanged) by id, "
                                     "newest first."},
                     *PAGINATION_QUERY_PARAMS,
                 ])
    def list_candidates(self, **kwargs):
        qs = get_params()
        domain = [("register_state", "!=", REGISTERED)]
        waiting_on = (qs.get("waiting_on") or "").strip()
        if waiting_on:
            if waiting_on not in WAITING_ON_VALUES:
                return err(ERR_INVALID_REQUEST,
                           "`waiting_on` must be one of: %s"
                           % ", ".join(WAITING_ON_VALUES),
                           details={"allowed_values": list(WAITING_ON_VALUES)})
            domain.append(("register_state", "in", [
                s for s, who in WAITING_ON.items() if who == waiting_on]))
        state = (qs.get("register_state") or "").strip()
        if state:
            allowed = [s for s, _label in _MODEL_STATES if s != REGISTERED]
            if state not in allowed:
                return err(ERR_INVALID_REQUEST,
                           "`register_state` must be one of: %s"
                           % ", ".join(allowed),
                           details={"allowed_values": allowed})
            domain.append(("register_state", "=", state))
        q = (qs.get("q") or "").strip()
        if q:
            try:
                domain += _list_domain({"q": q})
            except BadFilter as e:
                return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        Asset = request.env["nrs.asset"].sudo()
        try:
            mine = parse_bool("waiting_on_me", qs.get("waiting_on_me"))
            sort = parse_enum("sort", qs.get("sort"), _SORTS) or "newest"
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        if mine:
            # As the PERSON: `_waiting_on_me_domain` judges the no-two-gates
            # rule against `env.user`, which `sudo()` keeps.
            domain = list(Domain(domain) & Asset._waiting_on_me_domain(
                scopes=_token_scopes()))
        if sort == "oldest":
            page, next_cursor, total = paginate(
                Asset, domain, limit=parse_limit(qs), cursor=qs.get("cursor"),
                keyset_field="register_state_since")
        else:
            page, next_cursor, total = paginate(
                Asset, domain, limit=parse_limit(qs), cursor=qs.get("cursor"),
                descending=True)
        return ok(
            data=[serialize_asset(a) for a in page],
            pagination={"next_cursor": next_cursor, "previous_cursor": None,
                        "total_estimate": total})


# ── batches (handoff 60 §2) ───────────────────────────────────────────

class _DryRun(Exception):
    """Raised to roll a dry run's savepoint back."""


def _unit_line(asset):
    """What a batch answer says about one unit — enough for the maker's
    preview (found, class, SAP class, cost) without the whole asset."""
    cat = asset.category_id
    return {
        "asset_id": asset.id,
        "asset_code": asset.asset_code or None,
        "name": asset.name or None,
        "grn_reference": asset.grn_reference or None,
        "category": ({"id": cat.id, "name": cat.name,
                      "sap_asset_class": cat.sap_asset_class or None}
                     if cat else None),
        "cost": asset.acquisition_cost or None,
    }


def _fire_one(asset, action, payload, scopes, *, warn=False):
    """One unit's fire inside a batch: its own savepoint, its own events,
    and the answer a single fire would have given."""
    line = _unit_line(asset)
    try:
        with request.env.cr.savepoint():
            asset._fire_gate(action, payload=payload, scopes=scopes)
    except GateRefused as e:
        status, code, message, details = gate_refusal_parts(e)
        line.update(outcome="refused", status=status, code=code,
                    message=message, details=details,
                    register_state=asset.register_state)
        return line
    except (UserError, ValidationError) as e:
        line.update(outcome="refused", status=400,
                    code=ERR_VALIDATION_FAILED, message=str(e.args[0]),
                    details={}, register_state=asset.register_state)
        return line
    asset.invalidate_recordset()
    line.update(outcome="fired", status=200, code=None, message=None,
                details=None, register_state=asset.register_state)
    if warn:
        line["warning"] = asset._sap_number_warning()
    return line


def _missing_line(asset_id=None, asset_code=None):
    if asset_code:
        message = "There is no unit with asset code %s." % asset_code
    elif asset_id is not None:
        message = "There is no unit with id %s." % asset_id
    else:
        message = "This line names no asset code."
    return {"asset_id": asset_id, "asset_code": asset_code, "name": None,
            "grn_reference": None, "category": None, "cost": None,
            "outcome": "refused", "status": 404, "code": "not_found",
            "message": message,
            "details": {"asset_id": asset_id, "asset_code": asset_code},
            "register_state": None}


def _batch_body(action, body):
    """Refuse a body the batch cannot read, before anything is written.
    Returns (body, error)."""
    allowed = _BATCH_KEYS[action]
    rejected = sorted(k for k in (body or {}) if k not in allowed)
    if rejected:
        return None, refuse_unwritable(rejected, allowed)
    dry_run = body.get("dry_run", False)
    if not isinstance(dry_run, bool):
        return None, err(ERR_INVALID_REQUEST,
                         "`dry_run` must be true or false.",
                         details={"field": "dry_run"})
    notes = body.get("notes")
    if notes is not None and not isinstance(notes, str):
        return None, err(ERR_INVALID_REQUEST, "`notes` must be a string.",
                         details={"field": "notes"})
    return body, None


def _asset_ids(body):
    """The `asset_ids` list, or the 400 saying what is wrong with it."""
    ids = body.get("asset_ids")
    if not isinstance(ids, list) or not ids or not all(
            isinstance(i, int) and not isinstance(i, bool) for i in ids):
        return None, err(ERR_INVALID_REQUEST,
                         "`asset_ids` must be a list of asset ids — at least "
                         "one.", details={"field": "asset_ids"})
    if len(ids) > BATCH_MAX:
        return None, err(ERR_INVALID_REQUEST,
                         "A batch takes at most %d units; this one has %d. "
                         "Send it in parts." % (BATCH_MAX, len(ids)),
                         details={"field": "asset_ids", "max": BATCH_MAX,
                                  "received": len(ids)})
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        return None, err(ERR_INVALID_REQUEST,
                         "Each unit may appear once in a batch; %s appear "
                         "more than once." % ", ".join(map(str, dupes)),
                         details={"field": "asset_ids", "duplicates": dupes})
    return ids, None


def _units(ids):
    """{id: record} for the ids that exist, candidates included."""
    Asset = request.env["nrs.asset"].sudo().with_context(
        **{CANDIDATES_CTX: True})
    return {a.id: a for a in Asset.browse(ids).exists()}


def _run(lines_in, fire, dry_run):
    """Run `fire(item)` for every item, in one savepoint a dry run rolls
    back. Returns the per-unit lines."""
    out = []
    try:
        with request.env.cr.savepoint():
            for item in lines_in:
                out.append(fire(item))
            if dry_run:
                raise _DryRun()
    except _DryRun:
        pass
    return out


def _batch_answer(action, lines, dry_run, **extra):
    if dry_run:
        for line in lines:
            if line["outcome"] == "fired":
                line["outcome"] = "would_fire"
    fired = sum(1 for l in lines if l["outcome"] in ("fired", "would_fire"))
    return dict(action=action, dry_run=dry_run, total=len(lines),
                fired=fired, refused=len(lines) - fired, results=lines,
                **extra)


def _simple_batch(action, body):
    """`approve` and `approve-registration`: the ids and an optional note."""
    body, error = _batch_body(action, get_params() if body is None else body)
    if error:
        return error
    ids, error = _asset_ids(body)
    if error:
        return error
    units = _units(ids)
    scopes = _token_scopes()
    payload = {"notes": body.get("notes")}

    def fire(i):
        if i not in units:
            return _missing_line(asset_id=i)
        return _fire_one(units[i], action, payload, scopes,
                         warn=action == "approve-registration")
    return _batch_answer(action, _run(ids, fire, body.get("dry_run", False)),
                         body.get("dry_run", False))


_RESULT_SCHEMA = {
    "type": "object",
    "description": "One line per unit, in the order sent.",
    "properties": {
        "action": {"type": "string"},
        "dry_run": {"type": "boolean"},
        "total": {"type": "integer"},
        "fired": {"type": "integer",
                  "description": "Units fired — or that would be, on a dry "
                                 "run."},
        "refused": {"type": "integer"},
        "results": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "line": {"type": "integer",
                         "description": "`register` only: the pasted "
                                        "line's number, from 1."},
                "asset_id": {"type": "integer", "nullable": True},
                "asset_code": {"type": "string", "nullable": True},
                "name": {"type": "string", "nullable": True},
                "grn_reference": {"type": "string", "nullable": True},
                "category": {"type": "object", "nullable": True},
                "cost": {"type": "number", "nullable": True},
                "sap_asset_code": {"type": "string", "nullable": True},
                "outcome": {"type": "string",
                            "enum": ["fired", "would_fire", "refused"]},
                "status": {"type": "integer",
                           "description": "The status this unit's fire "
                                          "would have answered alone."},
                "code": {"type": "string", "nullable": True},
                "message": {"type": "string", "nullable": True,
                            "description": "The refusal, in the words a "
                                           "single fire uses."},
                "details": {"type": "object", "nullable": True},
                "register_state": {"type": "string", "nullable": True},
                "warning": {"type": "string", "nullable": True},
            }}},
        "evidence": {"type": "object",
                     "description": "`verify` only: the attachments stored "
                                    "once and linked from each fired unit's "
                                    "event."},
    }}
_IDS = {"asset_ids": {"type": "array", "items": {"type": "integer"},
                      "minItems": 1, "maxItems": BATCH_MAX}}
_DRY_RUN = {"dry_run": {"type": "boolean",
                        "description": "Run every unit and roll it all "
                                       "back: the preview."}}


class CadraGateBatchesV1(http.Controller):

    @cadra_route("/api/v1/candidates/gates/verify", method="POST",
                 summary="IAD verifies the units of ONE receipt with one "
                         "checklist and one evidence set",
                 scopes=[SCOPE_VFM_VERIFY], success_status=200,
                 request_schema={
                     "type": "object",
                     "required": ["asset_ids", "checklist", "attachments"],
                     "properties": {
                         **_IDS,
                         "checklist": {"type": "object",
                                       "description": "All four `true`, as "
                                                      "for one unit."},
                         "attachments": {
                             "type": "array", "minItems": 1,
                             "description": "Stored ONCE, linked from every "
                                            "fired unit's event.",
                             "items": {"type": "object",
                                       "required": ["name", "data"]}},
                         **_NOTES, **_DRY_RUN}},
                 request_example={
                     "asset_ids": [91201, 91202],
                     "checklist": {"quantity": True, "specification": True,
                                   "condition": True, "price": True},
                     "attachments": [{"name": "delivery-note.pdf",
                                      "mimetype": "application/pdf",
                                      "data": "<base64>"}]},
                 response_schema=_RESULT_SCHEMA)
    def batch_verify(self, **kwargs):
        body, error = _batch_body("verify", get_params() or {})
        if error:
            return error
        ids, error = _asset_ids(body)
        if error:
            return error
        Asset = request.env["nrs.asset"].sudo()
        checklist = body.get("checklist")
        try:
            files = Asset._validate_gate_evidence(checklist,
                                                  body.get("attachments"))
        except GateRefused as e:
            return _refusal(e)
        units = _units(ids)
        # One receipt at a time, so the evidence matches (§2b). A unit with
        # no GRN is a receipt of its own: nothing says it shares a delivery
        # note with anything.
        receipts = {(units[i].grn_reference or "").strip().upper()
                    or "#%d" % i for i in ids if i in units}
        if len(receipts) > 1:
            return err(ERR_VALIDATION_FAILED,
                       "These units come from %d receipts; verify one "
                       "receipt at a time so the evidence matches."
                       % len(receipts),
                       details={"field": "asset_ids",
                                "receipts": len(receipts),
                                "grn_references": sorted(
                                    {(units[i].grn_reference or None)
                                     for i in ids if i in units},
                                    key=lambda g: g or "")})
        dry_run = body.get("dry_run", False)
        scopes = _token_scopes()
        found = Asset.browse([i for i in ids if i in units])
        pending = found.filtered(lambda a: a.register_state == "vfm_pending")
        stored = {"files": Asset.env["ir.attachment"]}

        def fire(i):
            if i not in units:
                return _missing_line(asset_id=i)
            if not stored["files"]:
                stored["files"] = (pending or found)._store_gate_evidence(
                    files)
            return _fire_one(units[i], "verify", {
                "checklist": checklist,
                "_stored_attachment_ids": stored["files"].ids,
                "notes": body.get("notes")}, scopes)

        lines = _run(ids, fire, dry_run)
        fired = [l for l in lines if l["outcome"] == "fired"]
        if not dry_run and not fired and stored["files"]:
            # Nothing was verified, so nothing links the evidence.
            stored["files"].unlink()
            stored["files"] = Asset.env["ir.attachment"]
        elif not dry_run and stored["files"] \
                and stored["files"][:1].res_id != fired[0]["asset_id"]:
            # Filed on a unit that was then refused: move it to the first
            # unit verified, so the back office lists it on a unit it is
            # evidence for (the routes read the events either way).
            stored["files"].write({"res_id": fired[0]["asset_id"]})
        evidence = {"attachment_ids": [] if dry_run else stored["files"].ids,
                    "files": len(files)}
        return _batch_answer("verify", lines, dry_run, evidence=evidence)

    @cadra_route("/api/v1/candidates/gates/submit", method="POST",
                 summary="Store submits many captured receipts to Internal "
                         "Audit, each fired and recorded on its own",
                 scopes=[SCOPE_ASSETS_WRITE], success_status=200,
                 request_schema={"type": "object", "required": ["asset_ids"],
                                 "properties": {**_IDS, **_NOTES,
                                                **_DRY_RUN}},
                 request_example={"asset_ids": [91201, 91202]},
                 response_schema=_RESULT_SCHEMA)
    def batch_submit(self, **kwargs):
        """*Submit selected* (handoff 61, ruling 5 on report 60). A
        selection may span receipts. Each unit is the single route's fire,
        refused alone with the single route's sentence."""
        return _simple_batch("submit", get_params() or {})

    @cadra_route("/api/v1/candidates/gates/request-tagging", method="POST",
                 summary="The Asset Controller requests labels for many "
                         "approved units, each fired and recorded on its own",
                 scopes=[SCOPE_TAGGING_REQUEST], success_status=200,
                 request_schema={"type": "object", "required": ["asset_ids"],
                                 "properties": {**_IDS, **_NOTES,
                                                **_DRY_RUN}},
                 request_example={"asset_ids": [91201, 91202]},
                 response_schema=_RESULT_SCHEMA)
    def batch_request_tagging(self, **kwargs):
        """*Request tagging for selected* (handoff 61, ruling 5 on report
        60). Still a PERSON's act: nothing fires it on IAD's approval — it
        is the Asset Controller's gate (AD-17), and a gate that fires
        itself is not one. Each unit mints its own label in its own fire."""
        return _simple_batch("request-tagging", get_params() or {})

    @cadra_route("/api/v1/candidates/gates/approve", method="POST",
                 summary="IAD approves value for money on many units, each "
                         "fired and recorded on its own",
                 scopes=[SCOPE_VFM_APPROVE], success_status=200,
                 request_schema={"type": "object", "required": ["asset_ids"],
                                 "properties": {**_IDS, **_NOTES,
                                                **_DRY_RUN}},
                 request_example={"asset_ids": [91201, 91202]},
                 response_schema=_RESULT_SCHEMA)
    def batch_approve(self, **kwargs):
        return _simple_batch("approve", get_params() or {})

    @cadra_route("/api/v1/candidates/gates/approve-registration",
                 method="POST",
                 summary="The Register Checker approves many registrations, "
                         "each fired and recorded on its own",
                 scopes=[SCOPE_REGISTER_CHECK], success_status=200,
                 request_schema={"type": "object", "required": ["asset_ids"],
                                 "properties": {**_IDS, **_NOTES,
                                                **_DRY_RUN}},
                 request_example={"asset_ids": [91201, 91202]},
                 response_schema=_RESULT_SCHEMA)
    def batch_approve_registration(self, **kwargs):
        return _simple_batch("approve-registration", get_params() or {})

    @cadra_route("/api/v1/candidates/gates/register", method="POST",
                 summary="The Register Maker submits a pasted list of asset "
                         "code → SAP code, one registration per line",
                 scopes=[SCOPE_REGISTER_MAKE], success_status=200,
                 request_schema={
                     "type": "object",
                     "required": ["lines", "cost_centre",
                                  "capitalisation_date"],
                     "properties": {
                         "lines": {
                             "type": "array", "minItems": 1,
                             "maxItems": BATCH_MAX,
                             "items": {
                                 "type": "object",
                                 "required": ["asset_code", "sap_asset_code"],
                                 "properties": {
                                     "asset_code": {"type": "string"},
                                     "sap_asset_code": {"type": "string"},
                                     "cost": {
                                         "type": "number",
                                         "description": "Optional; the "
                                                        "unit's own cost "
                                                        "when absent."}}}},
                         "cost_centre": {"type": "string",
                                         "description": "For every line."},
                         "capitalisation_date": {"type": "string",
                                                 "format": "date"},
                         **_NOTES, **_DRY_RUN}},
                 request_example={
                     "lines": [{"asset_code": "NRS-AST-055101",
                                "sap_asset_code": "3NNNNNNNNNN"}],
                     "cost_centre": "NRS-HQ-IT",
                     "capitalisation_date": "2026-10-15", "dry_run": True},
                 response_schema=_RESULT_SCHEMA)
    def batch_register(self, **kwargs):
        body, error = _batch_body("register", get_params() or {})
        if error:
            return error
        lines = body.get("lines")
        if not isinstance(lines, list) or not lines or not all(
                isinstance(l, dict) for l in lines):
            return err(ERR_INVALID_REQUEST,
                       "`lines` must be a list of {asset_code, "
                       "sap_asset_code} — at least one.",
                       details={"field": "lines"})
        if len(lines) > BATCH_MAX:
            return err(ERR_INVALID_REQUEST,
                       "A batch takes at most %d units; this one has %d. "
                       "Send it in parts." % (BATCH_MAX, len(lines)),
                       details={"field": "lines", "max": BATCH_MAX,
                                "received": len(lines)})
        stray = sorted({k for l in lines for k in l if k not in _LINE_KEYS})
        if stray:
            return refuse_unwritable(stray, _LINE_KEYS)
        for n, l in enumerate(lines, 1):
            if not isinstance(l.get("asset_code"), str) \
                    or not isinstance(l.get("sap_asset_code"), str) \
                    or ("cost" in l and (isinstance(l["cost"], bool) or
                                         not isinstance(l["cost"],
                                                        (int, float)))):
                return err(ERR_INVALID_REQUEST,
                           "Line %d: `asset_code` and `sap_asset_code` must "
                           "be text, and `cost`, when sent, a number." % n,
                           details={"field": "lines", "line": n})
        # The two values every line shares, refused ONCE in the words a
        # single submission uses — not once per line.
        centre = body.get("cost_centre")
        if not isinstance(centre, str) or not centre.strip():
            return err(ERR_VALIDATION_FAILED, "The cost centre is required.",
                       details={"field": "cost_centre"})
        cap = body.get("capitalisation_date")
        if not isinstance(cap, str) or not cap.strip():
            return err(ERR_VALIDATION_FAILED,
                       "The capitalisation date is required, as YYYY-MM-DD.",
                       details={"field": "capitalisation_date"})
        Asset = request.env["nrs.asset"].sudo().with_context(
            **{CANDIDATES_CTX: True})
        scopes = _token_scopes()
        dry_run = body.get("dry_run", False)

        def fire(numbered):
            n, l = numbered
            code = l["asset_code"].strip()
            sap = l["sap_asset_code"]
            # `=ilike` reads `%` and `_` as wildcards: escaped, so a pasted
            # code matches itself and nothing else, case aside.
            literal = code.replace("\\", "\\\\").replace(
                "%", "\\%").replace("_", "\\_")
            found = Asset.search([("asset_code", "=ilike", literal)],
                                 limit=2) if code else Asset
            # capped-count-ok: `limit=2` asks "one, or more than one?" of a
            # code that should name one unit; it counts nothing published.
            if len(found) != 1:
                line = _missing_line(asset_code=code or None)
                if len(found) > 1:  # capped-count-ok: the same probe
                    line.update(status=409, code="conflict",
                                message="Asset code %s names more than one "
                                        "unit; submit it alone." % code)
            else:
                cost = l.get("cost", found.acquisition_cost)
                line = _fire_one(found, "register", {
                    "sap_asset_code": sap,
                    "cost": cost,
                    "cost_centre": centre,
                    "capitalisation_date": cap,
                    "asset_class": found.category_id.id or None,
                    "notes": body.get("notes")}, scopes, warn=True)
            line.update(line=n, sap_asset_code=sap.strip().upper() or None)
            return line

        return _batch_answer("register",
                             _run(list(enumerate(lines, 1)), fire, dry_run),
                             dry_run)

    # ── the evidence, for the approver ────────────────────────────────

    @cadra_route("/api/v1/assets/<int:id>/evidence", method="GET",
                 summary="What IAD saw: each verification's checklist and "
                         "evidence files",
                 scopes=[SCOPE_CANDIDATES_READ],
                 response_schema={
                     "type": "object",
                     "properties": {
                         "asset_id": {"type": "integer"},
                         "readable": {
                             "type": "boolean",
                             "description": "Whether the caller holds "
                                            "`evidence:read`. False: "
                                            "`verifications` is empty and "
                                            "`count`/`summary` say how many "
                                            "files there are."},
                         "count": {"type": "integer",
                                   "description": "Evidence files across "
                                                  "every verification."},
                         "summary": {"type": "string",
                                     "description": "Non-readers only: "
                                                    "\"IAD evidence: N "
                                                    "items\"."},
                         "requires_scope": {"type": "string"},
                         "verifications": {"type": "array"}}})
    def asset_evidence(self, id, **kwargs):
        """Readers (`evidence:read`) get every verification and its files;
        anybody else holding `candidates:read` gets the count, in words,
        and nothing that opens a file (handoff 61, ruling 1 on report 60).
        `readable` says which answer this is."""
        asset, error = _browse_or_404(id)
        if error:
            return error
        verifications = asset._gate_evidence()
        count = sum(len(v["files"]) for v in verifications)
        if not evidence_readable():
            return dict(evidence_count_only(count), asset_id=asset.id,
                        verifications=[])
        out = []
        for v in verifications:
            ev = v["event"]
            out.append({
                "event_id": ev.id,
                "occurred_at": fields.Datetime.to_string(ev.occurred_at),
                "actor_name": ev.actor_name or None,
                "checklist": v["checklist"],
                "notes": v["notes"],
                "files": [{
                    "id": f.id, "name": f.name,
                    "mimetype": f.mimetype or None,
                    "size": f.file_size or 0,
                    "url": "/api/v1/assets/%d/evidence/%d" % (asset.id, f.id),
                } for f in v["files"]],
            })
        return {"asset_id": asset.id, "readable": True, "count": count,
                "verifications": out}

    @http.route("/api/v1/assets/<int:id>/evidence/<int:attachment_id>",
                type="http", auth="none", methods=["GET"], csrf=False)
    def asset_evidence_file(self, id, attachment_id, **kwargs):
        """One evidence file — the file, not the envelope. Only a file one
        of THIS unit's verifications names; any other id is a 404, so the
        route cannot be walked to read an arbitrary attachment."""
        # The file is the evidence itself: `evidence:read`, the one scope
        # the list's guard reads (handoff 61). `candidates:read` alone — an
        # Asset User, Vendra's credential — is refused here, by name.
        _, envelope, _ = require_jwt(scopes=[SCOPE_CANDIDATES_READ,
                                             SCOPE_EVIDENCE_READ])
        if envelope is not None:
            return _http_response(envelope)
        asset = request.env["nrs.asset"].sudo().browse(id).exists()
        files = asset and {f.id: f for v in asset._gate_evidence()
                           for f in v["files"]}
        f = (files or {}).get(attachment_id)
        if not f:
            return _http_response(err(
                ERR_NOT_FOUND, "Unit %s has no evidence file %s."
                % (id, attachment_id), status=404,
                details={"asset_id": id, "attachment_id": attachment_id}))
        data = base64.b64decode(f.datas or b"")
        return request.make_response(data, headers=[
            ("Content-Type", f.mimetype or "application/octet-stream"),
            # Odoo's own RFC 6266 builder: a name outside Latin-1 (a macOS
            # screenshot carries U+202F) or with a newline would otherwise
            # fail the header rather than download (verification pass).
            ("Content-Disposition", http.content_disposition(
                f.name or "evidence")),
            ("Content-Length", str(len(data))),
        ])
