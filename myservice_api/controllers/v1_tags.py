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

WHY THE NUMBER STAYS (handoff 61, ruling R3)
--------------------------------------------
Until handoff 61 an approval scrapped the label and minted a NEW number
through `nrs.asset._generate_tag` — and on a unit that came through the
receipt gates, whose label is its asset code, the gated generator minted a
location-prefix number instead, so the replacement broke ruling 4.3 (findings
§5.6). Since 61 *the number on the asset doesn't change because a sticker
faded*: the approval VOIDS the print and REPRINTS the label under the same
number. One record is one physical print, so the voided print keeps its
record (`scrapped`, with `voided_at` and `void_reason`) and the reprint is a
new record with the same `tag_number`, `reprint_count` one higher and
`replaces` naming the print it replaces. A number resolves on the lookup
routes to its ACTIVE print only, so after an approval the number finds the
reprint. `tests/test_reprint_same_code.py` proves it gates off and gates on.
This is a BEHAVIOUR CHANGE, announced in the CHANGELOG: a consumer that
expected `new_tag.tag_number` to differ from the old one reads the same
number and a `reprint_count`.

WHAT A SCANNER CANNOT TELL
--------------------------
The voided print and its reprint encode the same value; nothing on the paper
says which is which. `POST /assets/<id>/tag-affixed` therefore refuses a
reprint only while it has not been printed (`label_state` `issued`) — the one
window in which the label in hand can only be the voided one — naming the
void, its date and its reason. `POST /api/v1/tags/printed` is how the app's
station records that it printed a label, because the app renders labels in
the browser and never reaches the PDF funnel that records Odoo's own prints
(handoff 10): without it no reprint printed from the app could be confirmed.
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
    SCOPE_TAGGING_WRITE,
    err,
    get_params,
    ok,
    paginate,
    parse_limit,
    refuse_unwritable,
    selection_values,
)
from .query_params import BadFilter, parse_bool, parse_enum
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
    # Handoff 61: which print this is and when and why a print was voided
    # are stamped by the approval.
    "reprint_count", "voided_at", "voided_date", "void_reason",
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
                            "tag_number": {"type": "string"},
                            "reprint_count": {
                                "type": "integer",
                                "description": "Which print of its number "
                                               "the linked record is — the "
                                               "only thing telling two "
                                               "prints of one number apart "
                                               "(handoff 61)."}}}
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
                   "enum": ["auto", "manual", "sap", "other"],
                   "description": "Where the NUMBER came from. A reprint "
                                  "keeps its number's source."},
        "reprint_count": {"type": "integer",
                          "description": "Which print of this number this "
                                         "record is: 0 for the first print, "
                                         "one more for each approved "
                                         "replacement, which reprints the "
                                         "label under the SAME number "
                                         "(handoff 61)."},
        "voided_at": {"type": "string", "format": "date-time",
                      "nullable": True,
                      "description": "When this print was voided by an "
                                     "approved replacement. Null for a print "
                                     "in service, and for a print scrapped "
                                     "before handoff 61 (read "
                                     "`scrapped_date` there)."},
        "void_reason": {"type": "string", "nullable": True,
                        "enum": list(REPLACEMENT_REASONS),
                        "description": "Why this print was voided — the "
                                       "replacement reason, stamped at the "
                                       "approval and not editable after "
                                       "it."},
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
        "replaces": dict(_TAG_LINK, description="The print this one "
                                                "replaces — since handoff "
                                                "61 the same number, one "
                                                "`reprint_count` lower; a "
                                                "replacement made before 61 "
                                                "names a different "
                                                "number."),
        "replaced_by": dict(_TAG_LINK, description="The reprint issued "
                                                   "when this print was "
                                                   "voided."),
        "can_decide": {"type": "boolean",
                       "description": "Whether the CALLER may approve or "
                                      "reject this one: pending, not their "
                                      "own request, and eligible. Computed "
                                      "per caller so a screen can grey out "
                                      "a button the model would refuse."},
    },
}


def _tag_link(tag):
    """`{id, tag_number, reprint_count}` or None — the chain between two
    prints. `reprint_count` since handoff 61, because two prints of one
    number have the same `tag_number` and differ only in it."""
    if not tag:
        return None
    return {"id": tag.id, "tag_number": tag.name,
            "reprint_count": tag.reprint_count}


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
        # Handoff 61: which print of the number this is, and — on a voided
        # print — when and why it was voided.
        "reprint_count": t.reprint_count,
        "voided_at": _dt(t.voided_date),
        "void_reason": t.void_reason or None,
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
            "Only an approver — somebody holding the Asset Manager "
            "role — can decide on it.")
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

        PENDING ONLY, by its published name, and deliberately without a
        `state` filter: a route published as *pending* that can be made to
        return decided rows is one published name carrying two meanings.
        A requester asking *what happened to mine* — which a pending-only
        list answers with *"nothing"* the moment their request is decided —
        reads `GET /api/v1/tags/replacements` below, which takes `state`,
        `waiting_on_me` and `raised_by_me`. This route stays what it says:
        the whole pending queue. (Handoff 51.)
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

    # ── The record: GET /api/v1/tags/replacements ────────────────────

    @cadra_route("/api/v1/tags/replacements", method="GET",
                 summary="Tag replacement requests — waiting and decided, "
                         "filterable by state and by the caller's part in "
                         "them",
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={"type": "array", "items": _TAG_SCHEMA},
                 query_params=[
                     {"name": "state",
                      "schema": {"type": "string", "enum": list(STATES)},
                      "description": "The LABEL's own lifecycle state — "
                                     "`pending` is waiting for a decision, "
                                     "`scrapped` was approved and replaced, "
                                     "`active` was rejected (who refused and "
                                     "why are on the row). Omitted returns "
                                     "every state."},
                     {"name": "waiting_on_me",
                      "schema": {"type": "boolean"},
                      "description": "Only requests NAMING the caller as the "
                                     "approver — *what is waiting on me*. "
                                     "Anyone eligible may decide any pending "
                                     "request, so this is a convenience and "
                                     "not a boundary."},
                     {"name": "raised_by_me",
                      "schema": {"type": "boolean"},
                      "description": "Only requests the caller raised — how "
                                     "a requester finds out what happened to "
                                     "theirs, decided ones included."},
                     *PAGINATION_QUERY_PARAMS])
    def list_replacements(self, **kwargs):
        """Every REPLACEMENT REQUEST the caller can see, newest first.

        The sibling of `pending-replacements`, not a widening of it
        (handoff 51): that route stays pending-only by its published name;
        this one answers the requester's question, which is not *"what is
        pending"* but *"what happened to mine"* — a question a pending-only
        list answers with *"nothing"* an hour after the decision.

        A label that has never had a replacement asked about it is not a
        replacement request, so the base domain is `requested_by` set —
        which an approval (label `scrapped`) and a rejection (label back to
        `active`) both preserve, and which the next request on the same
        label overwrites. The rows are labels, serialized exactly as the
        pending queue serializes them, `can_decide` computed per caller.

        `assets:read`, for `pending-replacements`'s reason: an Auditor must
        be able to read what is waiting and on whom without being able to
        decide any of it. One consequence worth a sentence (handoff 51 §1c):
        the Tag-Issuing Unit's own credential holds `tagging:write` and
        nothing else, so a TAGGING-ONLY caller cannot read this route or the
        pending queue — a human tagger reads them through the Asset User
        pairing (`docs/DECISIONS.md`, 2026-10-01), which is the ruled answer
        and not a bug.
        """
        try:
            state = parse_enum("state", kwargs.get("state"), STATES)
            waiting_on_me = parse_bool("waiting_on_me",
                                       kwargs.get("waiting_on_me"))
            raised_by_me = parse_bool("raised_by_me",
                                      kwargs.get("raised_by_me"))
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        domain = [("requested_by", "!=", False)]
        if state:
            domain.append(("state", "=", state))
        # `is True`, not truthiness: `parse_bool` answers None for absent and
        # False for an explicit `false`, and `?waiting_on_me=false` must mean
        # "do not filter", not "filter on nothing" (handoff 22's lesson, the
        # same line `list_approvals` carries).
        if waiting_on_me is True:
            domain.append(("approver_id", "=", request.env.uid))
        if raised_by_me is True:
            domain.append(("requested_by", "=", request.env.uid))

        limit = parse_limit(kwargs)
        page, next_cursor, total = paginate(
            request.env[MODEL].sudo(), domain,
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

    # ── Printed: POST /api/v1/tags/printed ───────────────────────────

    @cadra_route("/api/v1/tags/printed", method="POST",
                 summary="Record that the app printed these labels",
                 # Records an act on existing labels; creates nothing.
                 success_status=200,
                 # `tagging:write`, not `assets:read`: this WRITES the print
                 # stamp, and the Auditor — who holds `assets:read` — writes
                 # nothing (`test_auditor_access.py`). Producing the label
                 # that goes onto an asset is the Tag-Issuing Unit's job, as
                 # minting and replacing one are (handoff 47). A person
                 # without the scope may still print from the station; the
                 # print is simply not recorded, which is what happened to
                 # every app print before this route.
                 scopes=[SCOPE_TAGGING_WRITE],
                 idempotent=True,
                 error_statuses=(404,),
                 response_schema={
                     "type": "object",
                     "properties": {
                         "recorded": {"type": "array", "items": _TAG_SCHEMA,
                                      "description": "Labels now `printed`, "
                                                     "with who and when."},
                         "not_recorded": {
                             "type": "array",
                             "items": {
                                 "type": "object",
                                 "properties": {
                                     "id": {"type": "integer"},
                                     "tag_number": {"type": "string"},
                                     "reason": {"type": "string"}}},
                             "description": "Labels named and left as they "
                                            "were, each with the sentence "
                                            "saying why: not the label in "
                                            "service, or already confirmed "
                                            "on the asset."},
                     },
                 },
                 request_schema={
                     "type": "object",
                     "required": ["tag_ids"],
                     "description": (
                         "The app renders labels in the browser and so never "
                         "reaches the PDF funnel that records a print made "
                         "from Odoo (handoff 10). The station calls this "
                         "after it opens the print dialog — the same moment "
                         "the funnel records, when the print instruction "
                         "exists; whether paper came out is not something "
                         "Cadra can see. It is what lets a REPRINT be "
                         "confirmed on the asset (handoff 61)."),
                     "properties": {
                         "tag_ids": {
                             "type": "array", "minItems": 1, "maxItems": 500,
                             "items": {"type": "integer"},
                             "description": "`nrs.asset.tag.label` ids — "
                                            "NOT asset ids."},
                     },
                 },
                 request_example={"tag_ids": [4211, 4212]})
    def record_printed(self, **kwargs):
        """Stamp the labels the station just printed, as the funnel would.

        Every refusal happens before anything is written: a key the route
        does not take, a `tag_ids` that is not a non-empty list of integers
        (at most 500), or an id that names no label (404, all of them
        named) — and then nothing is stamped, the valid ids included.

        The stamp is `nrs.asset.tag.label._mark_printed`, the same method
        the PDF funnel calls, so the rules are the funnel's: only the label
        in SERVICE is recorded (the funnel stamps `active_tag_id`; a label
        awaiting replacement or a voided print is not the one coming off the
        printer), and a label already affixed is not walked back.
        """
        body = get_params()
        rejected = sorted(k for k in (body or {}) if k != "tag_ids")
        if rejected:
            return refuse_unwritable(rejected, ("tag_ids",))
        ids = (body or {}).get("tag_ids")
        if (not isinstance(ids, list) or not ids
                or any(isinstance(i, bool) or not isinstance(i, int)
                       for i in ids)):
            return err(ERR_INVALID_REQUEST,
                       "`tag_ids` must be a non-empty list of label ids",
                       details={"field": "tag_ids"})
        ids = list(dict.fromkeys(ids))
        if len(ids) > 500:
            return err(ERR_INVALID_REQUEST,
                       "`tag_ids` names %d labels; at most 500 in one call"
                       % len(ids),
                       details={"field": "tag_ids", "count": len(ids),
                                "maximum": 500})
        labels = request.env[MODEL].sudo().browse(ids).exists()
        missing = sorted(set(ids) - set(labels.ids))
        if missing:
            return err(ERR_NOT_FOUND,
                       "No label with id %s — nothing was recorded"
                       % ", ".join(str(i) for i in missing),
                       status=404, details={"missing": missing})

        by_id = {t.id: t for t in labels}
        recorded = request.env[MODEL].sudo()
        not_recorded = []
        for tag_id in ids:
            t = by_id[tag_id]
            if t.state != "active":
                not_recorded.append({
                    "id": t.id, "tag_number": t.name,
                    "reason": "%s is %s, not the label in service, so its "
                              "print is not recorded" % (
                                  t._print_name().capitalize(), t.state)})
            elif t.label_state == "affixed":
                not_recorded.append({
                    "id": t.id, "tag_number": t.name,
                    "reason": "Already confirmed on the asset; printing it "
                              "again does not make the asset less tagged"})
            else:
                recorded |= t
        # `_mark_printed` stamps `printed_by` from the environment's uid,
        # which under `sudo()` is still the caller's.
        recorded._mark_printed()
        recorded.invalidate_recordset()
        return {
            "recorded": [serialize_tag(t) for t in recorded],
            "not_recorded": not_recorded,
        }

    # ── Ask: POST /api/v1/tags/<id>/request-replacement ──────────────

    @cadra_route("/api/v1/tags/<int:id>/request-replacement", method="POST",
                 summary="Ask a second person to agree that this label be "
                         "replaced",
                 # `tagging:write` since handoff 47 (BREAKING; it was
                 # `assets:write`): replacing a faded label is the
                 # Tag-Issuing Unit's job, the same act as minting one.
                 # Deciding the replacement stays `approvals:write` below —
                 # the second person, from `APPROVER_GROUP`, as on a move.
                 scopes=[SCOPE_TAGGING_WRITE],
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
                         "changes: nothing is voided or reprinted, the label "
                         "stays on the asset, and — by design — its number "
                         "stops resolving on the lookup routes until the "
                         "decision. Look the asset up by its code meanwhile. "
                         "On approval the label is reprinted under the SAME "
                         "number (handoff 61)."),
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
                ("%s (%s) is %s and cannot be replaced again%s."
                 % (tag.name, tag._print_name(), tag.state,
                    (" — the label in service is %s under the same number; "
                     "ask about that one" % tag.replaced_by_id._print_name())
                    if tag.replaced_by_id
                    and tag.replaced_by_id.name == tag.name else
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
                 summary="Agree to the replacement: void this print and "
                         "reprint the label under the same number, as "
                         "whoever holds the credential",
                 scopes=[SCOPE_APPROVALS_WRITE],
                 idempotent=True,
                 error_statuses=(403, 404, 409),
                 response_schema={
                     "type": "object",
                     "properties": {
                         "tag": dict(_TAG_SCHEMA,
                                     description="The print that was asked "
                                                 "about, now `scrapped`, "
                                                 "with `voided_at` and "
                                                 "`void_reason`."),
                         "new_tag": dict(_TAG_SCHEMA,
                                         description="The REPRINT: a new "
                                                     "record under the SAME "
                                                     "`tag_number`, "
                                                     "`active`, "
                                                     "`reprint_count` one "
                                                     "higher, `replaces` "
                                                     "naming the voided "
                                                     "print. Not printed "
                                                     "yet: it cannot be "
                                                     "confirmed on the asset "
                                                     "until it is (handoff "
                                                     "61)."),
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

        `action_approve_replacement` voids this print and reprints the label
        under the SAME number (handoff 61, ruling R3) — whatever the number
        is: an asset code on a gated unit, a location prefix, an import —
        and links the two prints. The self-approval refusal and the
        eligibility check are on the model, unchanged since handoff 38; what
        is here is the HTTP shape:

        * **403** — the caller may not decide this one, either because they
          asked for it (`details.is_own_request`) or because they could not
          have made the change themselves.
        * **409** — not pending: already decided, and the details say by
          whom and when. Also the model's refusal of a number that is
          ALREADY active on a second asset (a pre-61 duplicate): reprinting
          it would print the other asset's label.
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

        # Savepointed: the approval voids the old print BEFORE it creates
        # the reprint, and a `UserError` out of the reprint's create (the
        # one-active-per-number constraint) or the chain write would
        # otherwise leave a voided print with no reprint behind a 409 —
        # `err()` does not roll back.
        try:
            with request.env.cr.savepoint():
                new_tag = tag.action_approve_replacement(
                    decision_reason=reason)
        except UserError as e:
            tag.invalidate_recordset()
            return err(ERR_CONFLICT, str(e), status=409,
                       details={"tag_id": tag.id})
        # One print voided, one reprint issued. A model answering otherwise
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
