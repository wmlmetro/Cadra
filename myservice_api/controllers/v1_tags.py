"""Tag labels over HTTP — reading one, and replacing a faded one. Handoff 38.

WHAT THIS PUBLISHES
-------------------
Two reads and three actions on `nrs.asset.tag.label`, the record of one
physical label: its number, the asset it is on, and the replacement
lifecycle `active → pending → scrapped` that the model has carried since the
barcode station was built and that, until this file, could be driven only
from the Odoo back office. NRS described the case in the room on 30
September: *an auditor walking around notices an air conditioner's tag is
no longer very clear, and can reprint a tag for that asset.* The model did
it; nothing a person at a scanner could reach did.

A replacement is a REQUEST and a DECISION, by two different people. The
model has had a request step and an approve step for as long as it has
existed, and approvals are the control NRS asked for by name, so making this
one-click would quietly contradict the thing they said they wanted. The
shape is handoff 35's: a nominated `approver_id` at request time, the
decider taken from the bearer token, self-approval refused IN THE MODEL, a
reason required when asking and when refusing, and a decision taken once.

It does NOT reuse `nrs.asset.change.request`. That record is a request to
change an asset's location or custodian and says so in fifteen places —
its premise columns, its approval clearance, its one-pending-per-asset
index — and that last one would make a pending tag replacement block a move
on the same asset, the day before a demonstration. The tag model has its own
state machine and its own stamp fields; this file completes them rather than
copying them somewhere else. Who may decide is exactly
`nrs.asset.change.request._may_decide`'s rule, which the tag model reaches
by naming the same `APPROVER_GROUP`.

TWO FIELDS THAT ARE NEVER THE SAME FIELD
----------------------------------------
* `approver` — WHO IS BEING ASKED. Sent by the requester in the body of
  `/request-replacement`, resolved by the same `_resolve_approver` that
  `/assets/<id>/move` uses. A nomination: it puts the request in somebody's
  queue and confers nothing.
* `approved_by` / `rejected_by` — WHO CLICKED. Written from the bearer token
  by `action_approve_replacement` / `action_reject_replacement` and never
  readable from any payload. A body naming either, or `requested_by`, or
  `state`, is REFUSED 400 rather than ignored — the contract every write
  route in this API has published since handoff 31.

WHY THE OLD NUMBER NEVER COMES BACK
-----------------------------------
`nrs.asset._generate_tag` checks EVERY tag on the tenant for the candidate
number, scrapped ones included, before it mints — so the number a scrapped
label carried is never issued again. `tests/test_tag_replacement.py` proves
it by doing one: the new label's number is not the old one, and the old one
no longer resolves on either lookup route. The chain is `replaces` /
`replaced_by` on the two records, published here.
"""
from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from .utils import (
    ERR_CONFLICT,
    ERR_FORBIDDEN,
    ERR_INVALID_REQUEST,
    ERR_NOT_FOUND,
    SCOPE_APPROVALS_WRITE,
    SCOPE_ASSETS_READ,
    SCOPE_ASSETS_WRITE,
    err,
    get_params,
    ok,
    paginate,
    parse_limit,
    refuse_unwritable,
    selection_values,
)
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route
# `_ref` and `_dt` are IMPORTED rather than copied. `v1_approvals.py` is the
# fourth file carrying a three-line `_ref`, and the published-names guard
# names each copy by hand; a fifth would be one more row for a helper whose
# whole value is being the same everywhere.
from .v1_approvals import _dt, _ref
# `_resolve_approver` is the ONE reading of "who may be asked": the picker's
# list, the nomination's refusals and the self-nomination refusal are all in
# it, and `/move` and `/transfer-custody` go through it. `serialize_asset` is
# in every response so a consumer can see the asset as it now stands rather
# than trust the verb.
from .v1_assets import _resolve_approver, serialize_asset

MODEL = "nrs.asset.tag.label"

#: States and reasons, published. `GET /meta/enums` reads both from the
#: model (`tag_state`, `tag_replacement_reason`); these tuples are the floor
#: under that read and what the OpenAPI annotations below name, and
#: `tests/test_frontend_enums.py` proves they agree with the model.
STATES = ("active", "pending", "scrapped")
REPLACEMENT_REASONS = ("damaged", "lost", "stolen", "reassign", "other")

#: Keys a caller might send believing they set who asked, who decided, or
#: what state the label is in. Refused, never ignored — the same
#: list-and-refuse shape as `v1_approvals._DECIDER_CLAIM_FIELDS`, with the
#: tag model's own stamp fields added.
_CLAIM_FIELDS = frozenset({
    "requested_by", "requested_by_id", "requested_date", "requested_at",
    "approved_by", "approved_by_id", "approved_date", "approved_at",
    "rejected_by", "rejected_by_id", "rejected_date", "rejected_at",
    "decided_by", "decided_by_id", "decided_at", "decision_reason",
    "state", "label_state", "scrapped_date",
    "replaces_id", "replaced_by_id",
})

#: What each route accepts. A key outside the list is a 400 carrying
#: `details.rejected_fields` and `details.writable`.
_REQUEST_KEYS = ("approver_id", "notes", "reason")
_REASON_ONLY = ("reason",)

#: The published shape of one label, for the OpenAPI document. Inline rather
#: than a `components.schemas` entry because the component table lives in
#: `v1.py`'s OpenAPI route, which this handoff does not touch.
_PERSON = {"type": "object", "nullable": True,
           "properties": {"id": {"type": "integer"},
                          "name": {"type": "string"}}}
_TAG_LINK = {"type": "object", "nullable": True,
             "properties": {"id": {"type": "integer"},
                            "tag_number": {"type": "string"}}}
_TAG_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer",
               "description": "`nrs.asset.tag.label` id — NOT an asset id; "
                              "the two id spaces collide numerically."},
        "tag_number": {"type": "string"},
        "state": {"type": "string", "enum": list(STATES),
                  "description": "The REPLACEMENT lifecycle. Only an "
                                 "`active` tag resolves by its number on "
                                 "the lookup routes."},
        "label_state": {"type": "string",
                        "enum": ["issued", "printed", "affixed", "scrapped"],
                        "description": "The PHYSICAL lifecycle, moved only "
                                       "by printing and by a confirmed "
                                       "affix."},
        "source": {"type": "string",
                   "enum": ["auto", "manual", "sap", "other"]},
        "tag_date": {"type": "string", "format": "date", "nullable": True},
        "scrapped_date": {"type": "string", "format": "date",
                          "nullable": True},
        "asset": _PERSON,
        "asset_code": {"type": "string", "nullable": True},
        "serial_number": {"type": "string", "nullable": True},
        "replacement_reason": {"type": "string", "nullable": True,
                               "enum": list(REPLACEMENT_REASONS)},
        "replacement_notes": {"type": "string", "nullable": True},
        "requested_by": _PERSON,
        "requested_at": {"type": "string", "format": "date-time",
                         "nullable": True},
        "approver": dict(_PERSON, description="WHO IS BEING ASKED — the "
                                              "nomination. Never who "
                                              "decided."),
        "approved_by": dict(_PERSON, description="WHO CLICKED approve, from "
                                                 "their own token."),
        "approved_at": {"type": "string", "format": "date-time",
                        "nullable": True},
        "rejected_by": dict(_PERSON, description="WHO CLICKED reject, from "
                                                 "their own token."),
        "rejected_at": {"type": "string", "format": "date-time",
                        "nullable": True},
        "decision_reason": {"type": "string", "nullable": True},
        "replaces": dict(_TAG_LINK, description="The label this one was "
                                                "minted to replace."),
        "replaced_by": dict(_TAG_LINK, description="The label minted when "
                                                   "this one was scrapped."),
        "can_decide": {"type": "boolean",
                       "description": "Whether the CALLER may approve or "
                                      "reject this one: pending, not their "
                                      "own request, and eligible. Computed "
                                      "per caller so a screen can grey out "
                                      "a button the model would refuse."},
    },
}


def _tag_link(tag):
    """`{id, tag_number}` or None — the chain between two labels."""
    if not tag:
        return None
    return {"id": tag.id, "tag_number": tag.name}


def serialize_tag(t):
    """One label, in full.

    **Every published key here resolves to a real field**, which
    `myservice_api/tests/test_published_names_resolve.py` proves by parsing
    this file — so every read below is a bare attribute on `t`, never a
    `getattr` or an `in _fields`, which that guard reads as *this field may
    have been renamed and we publish null now*.

    `can_decide` is computed for the CALLER, the way `serialize_request`
    in `v1_approvals.py` does it, and only for a pending label: a decided
    or never-requested label has nothing to decide.
    """
    return {
        "id": t.id,
        "tag_number": t.name,
        "state": t.state,
        "label_state": t.label_state,
        "source": t.source,
        "tag_date": _dt(t.tag_date),
        "scrapped_date": _dt(t.scrapped_date),
        "asset": _ref(t.asset_id),
        "asset_code": t.asset_id.asset_code or None,
        "serial_number": t.asset_id.serial_number or None,
        "replacement_reason": t.replacement_reason or None,
        "replacement_notes": t.replacement_notes or None,
        # WHO ASKED, and WHO IS BEING ASKED.
        "requested_by": _ref(t.requested_by),
        "requested_at": _dt(t.requested_date),
        "approver": _ref(t.approver_id),
        # WHO CLICKED. Two keys, because approve and reject stamp two
        # different people and a decision is taken once.
        "approved_by": _ref(t.approved_by),
        "approved_at": _dt(t.approved_date),
        "rejected_by": _ref(t.rejected_by),
        "rejected_at": _dt(t.rejected_date),
        "decision_reason": t.decision_reason or None,
        # The chain. A replacement is two records that name each other.
        "replaces": _tag_link(t.replaces_id),
        "replaced_by": _tag_link(t.replaced_by_id),
        "can_decide": bool(t.state == "pending"
                           and t._may_decide(request.env.user)),
    }


def _browse_or_404(tag_id):
    rec = request.env[MODEL].sudo().browse(tag_id).exists()
    if not rec:
        return None, err(ERR_NOT_FOUND, f"Tag {tag_id} not found",
                         status=404)
    return rec, None


def _refuse_claimed_stamp(body, writable):
    """400 if the body tries to say who asked, who decided, or what state
    the label is in. See the module docstring."""
    if not isinstance(body, dict):
        return None
    claimed = sorted(k for k in body if k in _CLAIM_FIELDS)
    if not claimed:
        return None
    return err(
        ERR_INVALID_REQUEST,
        "Who asked, who decided and what state a label is in are taken from "
        "the credential that made the call and the act it performed, and "
        "cannot be supplied: remove %s and call again."
        % ", ".join("`%s`" % k for k in claimed),
        details={"rejected_fields": claimed, "writable": list(writable)})


def _reason_text(body, *, required):
    """`(reason_or_None, None)` or `(None, error)` for the two decision
    routes, where the reason is free text."""
    reason = (body or {}).get("reason")
    if reason is not None and not isinstance(reason, str):
        return None, err(ERR_INVALID_REQUEST, "`reason` must be a string")
    reason = (reason or "").strip()
    if required and not reason:
        return None, err(ERR_INVALID_REQUEST,
                         "`reason` is required — say why this is being "
                         "rejected. The person who asked sees it.")
    return reason or None, None


def _not_pending(tag):
    """409 for a decision on a label that is not waiting for one."""
    # A scrapped label was approved; an active one was rejected or never
    # asked about. Whichever stamp the state implies is the decision named.
    decided_by = tag.approved_by if tag.state == "scrapped" else tag.rejected_by
    decided_at = (tag.approved_date if tag.state == "scrapped"
                  else tag.rejected_date)
    return err(
        ERR_CONFLICT,
        "This tag is %s, not pending replacement%s. A decision is taken once."
        % (tag.state,
           " — decided by %s" % decided_by.display_name if decided_by else ""),
        status=409,
        details={"tag_id": tag.id, "state": tag.state,
                 "decided_by": _ref(decided_by),
                 "decided_at": _dt(decided_at)})


def _may_not_decide(tag, *, verb):
    """403 for a caller the model will refuse — with WHY, because a screen
    has to tell *you raised this one* from *not yours to decide*."""
    own = tag.requested_by.id == request.env.uid
    if verb == "approve":
        message = (
            "You asked for this replacement and cannot approve it. The point "
            "of an approval is that a second person agrees."
            if own else
            "An approver must be somebody who could have made the change "
            "themselves.")
    else:
        message = (
            "You asked for this replacement. Ask an approver to reject it, "
            "or let it stand."
            if own else
            "Only somebody who could have made the change themselves can "
            "decide on it.")
    return err(ERR_FORBIDDEN, message, status=403,
               details={"tag_id": tag.id, "is_own_request": own,
                        "requested_by": _ref(tag.requested_by)})


class CadraTagsAPI(http.Controller):

    # ── The queue: GET /api/v1/tags/pending-replacements ─────────────

    @cadra_route("/api/v1/tags/pending-replacements", method="GET",
                 summary="Tag replacements waiting for a decision",
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={"type": "array", "items": _TAG_SCHEMA},
                 query_params=[*PAGINATION_QUERY_PARAMS])
    def list_pending_replacements(self, **kwargs):
        """Every label in state `pending`, newest request first.

        `assets:read`, not `approvals:write`, for the reason the approval
        queue gives: an Auditor must be able to read what is waiting and on
        whom without being able to decide any of it. `can_decide` on each
        row says whether THIS caller may.
        """
        limit = parse_limit(kwargs)
        page, next_cursor, total = paginate(
            request.env[MODEL].sudo(), [("state", "=", "pending")],
            limit=limit, cursor=kwargs.get("cursor"), descending=True)
        return ok(
            data=[serialize_tag(t) for t in page],
            pagination={
                "next_cursor": next_cursor,
                "previous_cursor": None,
                "total_estimate": total,
            },
        )

    # ── One label: GET /api/v1/tags/<id> ─────────────────────────────

    @cadra_route("/api/v1/tags/<int:id>", method="GET",
                 summary="One tag label, with its replacement history",
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema=_TAG_SCHEMA)
    def get_tag(self, id, **kwargs):
        """The label by its OWN id — `tagging.label_id` on an asset, or
        `tag_id` from a lookup. Not the asset id; the two collide."""
        rec, error = _browse_or_404(id)
        if error:
            return error
        return serialize_tag(rec)

    # ── Ask: POST /api/v1/tags/<id>/request-replacement ──────────────

    @cadra_route("/api/v1/tags/<int:id>/request-replacement", method="POST",
                 summary="Ask a second person to agree that this label be "
                         "replaced",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 error_statuses=(403, 404, 409),
                 response_schema={
                     "type": "object",
                     "properties": {
                         "pending_approval": {
                             "type": "boolean",
                             "description": "Always `true`: nothing is "
                                            "replaced until an approver "
                                            "agrees."},
                         "tag": _TAG_SCHEMA,
                         "asset": {"$ref": "#/components/schemas/Asset"},
                     },
                 },
                 request_schema={
                     "type": "object",
                     "required": ["reason", "approver_id"],
                     "description": (
                         "The label moves to `pending` and NOTHING else "
                         "changes: no new number is minted, the old label "
                         "stays on the asset, and — by design — its number "
                         "stops resolving on the lookup routes until the "
                         "decision. Look the asset up by its code meanwhile."),
                     "properties": {
                         "reason": {
                             "type": "string",
                             "enum": list(REPLACEMENT_REASONS),
                             "description": "Why. One of the model's own "
                                            "values (`GET /meta/enums` → "
                                            "`tag_replacement_reason`); "
                                            "anything else is a 400 naming "
                                            "`allowed_values`."},
                         "notes": {"type": "string", "nullable": True,
                                   "description": "Free text beside the "
                                                  "reason."},
                         "approver_id": {
                             "type": "integer",
                             "description": "WHO IS BEING ASKED — a "
                                            "res.users id from "
                                            "GET /api/v1/approvals/approvers. "
                                            "Not yourself. A nomination "
                                            "only: who DECIDED is taken from "
                                            "the deciding caller's own token "
                                            "and can never be supplied."},
                     },
                 },
                 request_example={
                     "reason": "damaged",
                     "notes": "Label on the AC unit in room 3F-12 has faded "
                              "past reading.",
                     "approver_id": 12,
                 })
    def request_replacement(self, id, **kwargs):
        """Mark a label as needing replacement, and name who is to agree.

        Everything of substance is on the model —
        `action_request_replacement` refuses a label that is not `active`,
        a reason outside the set, a missing or ineligible approver and a
        self-nomination — so the Odoo button, the shell and this route get
        the same answer. What is here is the HTTP shape of the refusals:

        * **400** — a key the route does not accept, a reason outside the
          set (`details.allowed_values`), no `approver_id`
          (`details.approvers` lists who may be asked), or the caller
          naming themself.
        * **404** — no such label, or no such user.
        * **409** — the label is not `active`: already pending (the
          details name who asked and who is being asked) or scrapped (the
          details name what replaced it).

        **Every refusal happens before anything is written.** `err()`
        returns a response and does not roll back; the model call is the
        last thing this route does, inside a savepoint.
        """
        tag, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        claimed = _refuse_claimed_stamp(body, _REQUEST_KEYS)
        if claimed:
            return claimed
        rejected = sorted(k for k in (body or {}) if k not in _REQUEST_KEYS)
        if rejected:
            return refuse_unwritable(rejected, _REQUEST_KEYS)

        reason = (body or {}).get("reason")
        if reason is not None and not isinstance(reason, str):
            return err(ERR_INVALID_REQUEST, "`reason` must be a string")
        reason = (reason or "").strip()
        allowed = selection_values(MODEL, "replacement_reason",
                                   REPLACEMENT_REASONS)
        if not reason:
            return err(ERR_INVALID_REQUEST,
                       "`reason` is required — why is this label being "
                       "replaced? It is the whole point of the record.",
                       details={"field": "reason",
                                "allowed_values": list(allowed)})
        if reason not in allowed:
            return err(ERR_INVALID_REQUEST,
                       "`reason` must be one of: %s" % ", ".join(allowed),
                       details={"field": "reason", "value": reason,
                                "allowed_values": list(allowed)})
        notes = (body or {}).get("notes")
        if notes is not None and not isinstance(notes, str):
            return err(ERR_INVALID_REQUEST, "`notes` must be a string")
        notes = (notes or "").strip() or None

        if tag.state != "active":
            return err(
                ERR_CONFLICT,
                ("A replacement for %s is already waiting — %s asked %s on "
                 "%s. Decide that one first."
                 % (tag.name,
                    tag.requested_by.display_name or "somebody",
                    tag.approver_id.display_name or "an approver",
                    tag.requested_date and tag.requested_date.date() or "?"))
                if tag.state == "pending" else
                ("%s is %s and cannot be replaced again%s."
                 % (tag.name, tag.state,
                    " — it was replaced by %s" % tag.replaced_by_id.name
                    if tag.replaced_by_id else "")),
                status=409,
                details={"tag_id": tag.id, "state": tag.state,
                         "requested_by": _ref(tag.requested_by),
                         "approver": _ref(tag.approver_id),
                         "replaced_by": _tag_link(tag.replaced_by_id)})

        approver, approver_err = _resolve_approver(body, tag.asset_id)
        if approver_err:
            return approver_err

        # A SAVEPOINT, for the reason `v1_approvals.approve` gives at
        # length: `err()` does not roll back, and a `UserError` the model
        # raises part-way through a write would otherwise leave a
        # half-stamped request behind a 409.
        try:
            with request.env.cr.savepoint():
                tag.action_request_replacement(
                    reason=reason, notes=notes, approver=approver)
        except UserError as e:
            tag.invalidate_recordset()
            return err(ERR_CONFLICT, str(e), status=409,
                       details={"tag_id": tag.id})
        tag.invalidate_recordset()
        return {
            # FIRST KEY, and a boolean, so the cheapest read of this response
            # is the correct one: nothing has been replaced yet.
            "pending_approval": True,
            "tag": serialize_tag(tag),
            "asset": serialize_asset(tag.asset_id),
        }

    # ── Agree: POST /api/v1/tags/<id>/approve-replacement ────────────

    @cadra_route("/api/v1/tags/<int:id>/approve-replacement", method="POST",
                 summary="Agree to the replacement: scrap this label and "
                         "mint the next, as whoever holds the credential",
                 scopes=[SCOPE_APPROVALS_WRITE],
                 idempotent=True,
                 error_statuses=(403, 404, 409),
                 response_schema={
                     "type": "object",
                     "properties": {
                         "tag": dict(_TAG_SCHEMA,
                                     description="The label that was asked "
                                                 "about, now `scrapped`."),
                         "new_tag": dict(_TAG_SCHEMA,
                                         description="The label minted in "
                                                     "its place, `active`, "
                                                     "with a number never "
                                                     "issued before."),
                         "asset": {"$ref": "#/components/schemas/Asset"},
                     },
                 },
                 request_schema={
                     "type": "object",
                     "description": (
                         "Optionally a `reason`. WHO decided is taken from "
                         "the bearer token and is never read from the body — "
                         "a body naming a decider, a requester or a state is "
                         "REFUSED 400 rather than ignored."),
                     "properties": {
                         "reason": {"type": "string", "nullable": True,
                                    "description": "Optional note recorded "
                                                   "with the decision."},
                     },
                 },
                 request_example={"reason": "Sighted the label — unreadable."})
    def approve_replacement(self, id, **kwargs):
        """Approve, and make the replacement happen.

        `action_approve_replacement` scraps the old label, mints the new
        number through `nrs.asset._generate_tag` — which checks every tag
        on the tenant, scrapped ones included, so the old number is never
        reissued — and links the two. The self-approval refusal and the
        eligibility check are on the model; what is here is the HTTP shape:

        * **403** — the caller may not decide this one, either because they
          asked for it (`details.is_own_request`) or because they could not
          have made the change themselves.
        * **409** — not pending: already decided, and the details say by
          whom and when.
        * **400** — the body tries to say who decided.
        """
        tag, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        claimed = _refuse_claimed_stamp(body, _REASON_ONLY)
        if claimed:
            return claimed
        rejected = sorted(k for k in (body or {}) if k not in _REASON_ONLY)
        if rejected:
            return refuse_unwritable(rejected, _REASON_ONLY)
        reason, error = _reason_text(body, required=False)
        if error:
            return error

        # ASKED BEFORE ANYTHING IS WRITTEN. The model raises on both of these
        # too — that is where the rule lives — but an exception surfaces as
        # a 400 carrying the model's words, and these deserve their own
        # statuses so a screen can tell "not yours" from "already done".
        if tag.state != "pending":
            return _not_pending(tag)
        if not tag._may_decide(request.env.user):
            return _may_not_decide(tag, verb="approve")

        # Savepointed: the approval stamps the old label BEFORE it mints the
        # new one, and a `UserError` out of `_generate_tag` or the chain
        # write would otherwise leave a scrapped label with no replacement
        # behind a 409 — `err()` does not roll back.
        try:
            with request.env.cr.savepoint():
                new_tag = tag.action_approve_replacement(
                    decision_reason=reason)
        except UserError as e:
            tag.invalidate_recordset()
            return err(ERR_CONFLICT, str(e), status=409,
                       details={"tag_id": tag.id})
        # One label approved, one label minted. A model answering otherwise
        # is a model fault and surfaces as one rather than as a shaped 200.
        new_tag.ensure_one()
        tag.invalidate_recordset()
        return {
            "tag": serialize_tag(tag),
            "new_tag": serialize_tag(new_tag),
            "asset": serialize_asset(tag.asset_id),
        }

    # ── Refuse: POST /api/v1/tags/<id>/reject-replacement ────────────

    @cadra_route("/api/v1/tags/<int:id>/reject-replacement", method="POST",
                 summary="Refuse the replacement, with a reason; the label "
                         "goes back to active",
                 scopes=[SCOPE_APPROVALS_WRITE],
                 idempotent=True,
                 error_statuses=(403, 404, 409),
                 response_schema={
                     "type": "object",
                     "properties": {
                         "tag": dict(_TAG_SCHEMA,
                                     description="The label, `active` "
                                                 "again, with who refused "
                                                 "and why."),
                         "asset": {"$ref": "#/components/schemas/Asset"},
                     },
                 },
                 request_schema={
                     "type": "object",
                     "required": ["reason"],
                     "properties": {
                         "reason": {"type": "string",
                                    "description": "REQUIRED. The person who "
                                                   "asked sees it. A "
                                                   "rejection without one "
                                                   "tells them nothing they "
                                                   "can act on, and they "
                                                   "will simply ask again."},
                     },
                 },
                 request_example={
                     "reason": "The label is legible — clean it rather than "
                               "replace it."})
    def reject_replacement(self, id, **kwargs):
        """Refuse. The label returns to `active` and its number resolves
        again; who refused and why are stamped on it."""
        tag, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        claimed = _refuse_claimed_stamp(body, _REASON_ONLY)
        if claimed:
            return claimed
        rejected = sorted(k for k in (body or {}) if k not in _REASON_ONLY)
        if rejected:
            return refuse_unwritable(rejected, _REASON_ONLY)
        reason, error = _reason_text(body, required=True)
        if error:
            return error
        if tag.state != "pending":
            return _not_pending(tag)
        if not tag._may_decide(request.env.user):
            return _may_not_decide(tag, verb="reject")
        # Savepointed for the reason `approve_replacement` is: a
        # half-stamped decision is still a decision the record would carry.
        try:
            with request.env.cr.savepoint():
                tag.action_reject_replacement(decision_reason=reason)
        except UserError as e:
            tag.invalidate_recordset()
            return err(ERR_CONFLICT, str(e), status=409,
                       details={"tag_id": tag.id})
        tag.invalidate_recordset()
        return {
            "tag": serialize_tag(tag),
            "asset": serialize_asset(tag.asset_id),
        }
