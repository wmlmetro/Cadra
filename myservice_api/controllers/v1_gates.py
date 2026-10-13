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
from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.myservice_asset_register.models.asset_gates import (
    GateRefused,
    REGISTER_STATES as _MODEL_STATES,
    REGISTERED,
    WAITING_ON,
    WAITING_ON_VALUES,
)

from .utils import (
    ERR_INVALID_REQUEST,
    ERR_VALIDATION_FAILED,
    SCOPE_ASSETS_WRITE,
    SCOPE_CANDIDATES_READ,
    SCOPE_REGISTER_CHECK,
    SCOPE_REGISTER_MAKE,
    SCOPE_TAGGING_REQUEST,
    SCOPE_VFM_APPROVE,
    SCOPE_VFM_VERIFY,
    err,
    gate_refusal,
    get_params,
    ok,
    paginate,
    parse_limit,
    refuse_unwritable,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route
from .v1_assets import (
    REGISTER_STATES,
    _browse_or_404,
    _list_domain,
    serialize_asset,
)
from .query_params import BadFilter

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


def _refusal(e):
    """A `GateRefused` as the envelope — `utils.gate_refusal`, the one
    mapping every route shares since handoff 58 (D3)."""
    return gate_refusal(e)


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
    claims = getattr(request, "jwt_claims", None) or {}
    scopes = claims.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
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
                         "register, newest first",
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
                      "description": "Free text, as on `GET /assets`."},
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
        page, next_cursor, total = paginate(
            Asset, domain, limit=parse_limit(qs), cursor=qs.get("cursor"),
            descending=True)
        return ok(
            data=[serialize_asset(a) for a in page],
            pagination={"next_cursor": next_cursor, "previous_cursor": None,
                        "total_estimate": total})
