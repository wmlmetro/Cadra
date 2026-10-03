"""The approval queue over HTTP. Handoff 35.

WHAT THIS PUBLISHES
-------------------
One list and four actions on `nrs.asset.change.request` — the model that
records a person asking a second person to agree before an asset is moved or
handed to somebody else. The reasoning for the model's shape is in
`myservice_asset_register/models/asset_change_request.py`; this file is the
contract.

The REQUESTS themselves are not raised here. They are raised by the two
routes that used to make the change — `POST /assets/<id>/move` and `POST
/assets/<id>/transfer-custody` — which, on a tenant that requires approval,
now create a request instead of moving the asset. **That is the BREAKING
change**: a call that has moved an asset for the life of this API now leaves
it exactly where it was.

**The status stays 200 and the BODY carries it**: `pending_approval` is
`true`, `request` is the record with its reference number, and `asset` is the
asset UNCHANGED, read back in the same response — so a consumer that trusts
the asset rather than the verb sees the truth. `movement_id`, `transfer` and
`custody_change`, the keys the old contract published, are explicitly `null`.

200 rather than 202 is a judgement, and the reason is worth stating because
202 is the better-looking answer. This API has no per-call success status —
it comes from the `cadra_route` decorator — and adding one would have to be
carried through the idempotency cache as well, or replaying the same key
would answer 202 once and 200 afterwards. An idempotent replay that is not
byte-exact is the property handoff 18 built and handoff 31 protected, and
changing that machinery for one route's status code was not worth it.
Announced in `openapi.json` and in `docs/api/CHANGELOG.md`.

TWO FIELDS THAT ARE NEVER THE SAME FIELD
----------------------------------------
* `approver` — WHO IS BEING ASKED. Sent by the requester in the body of
  `/move` or `/transfer-custody`. A nomination: it is what puts the request
  in somebody's queue and what the notification is addressed to.
* `decided_by` — WHO CLICKED. Never read from a body, on any route here.
  Derived from the bearer token exactly as `POST /assets/<id>/approve-disposal`
  derives its approver (handoff 23), and for the reason that route gives: a
  client able to name the approver could raise a request and appoint any user
  in the tenant as the authority for it in the same breath.

A body naming `decided_by`, `approved_by` or an approval date is REFUSED 400
rather than ignored, which is the contract every write route in this API has
published since handoff 31.
"""
from odoo.exceptions import UserError
from odoo.http import request

from odoo import http

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
)
from .query_params import BadFilter, parse_bool, parse_enum, parse_int
from .v1 import PAGINATION_QUERY_PARAMS, cadra_route

MODEL = "nrs.asset.change.request"

#: States, published. Read from the model by `GET /meta/enums`, as every other
#: enum in this API is since handoff 22 — this tuple is here only so the
#: OpenAPI annotations below have something to name, and
#: `tests/test_cursor_and_enums.py` proves it agrees with the model.
STATES = ("pending", "approved", "rejected", "withdrawn")
CHANGE_TYPES = ("location", "custody")

#: Keys a caller might send believing they set the decider. Refused, never
#: ignored — the same list-and-refuse shape as `_APPROVER_CLAIM_FIELDS` on
#: `approve-disposal`.
_DECIDER_CLAIM_FIELDS = frozenset({
    "decided_by", "decided_by_id", "approved_by", "approved_by_id",
    "decided_at", "approved_date", "approved_at", "requested_by",
    "requested_by_id", "state",
})

#: What each action route accepts. A key outside it is a 400 carrying
#: `details.rejected_fields` and `details.writable`.
_REASON_ONLY = ("reason",)

#: What `POST /approvals/<id>/renominate` accepts (handoff 45). WHO re-pointed
#: it and WHEN are taken from the bearer token and the clock, never the body.
_RENOMINATE_KEYS = ("approver_id", "reason")


def _ref(rec, name_field="name"):
    """{id, name} or None. The same shape `v1_assets` publishes."""
    if not rec:
        return None
    return {"id": rec.id, "name": rec[name_field] or rec.display_name}


def _approver_ref(user):
    """`{id, name, active}` — the person a request is waiting on.

    `active` is handoff 45 ruling G.1(a), and ADDITIVE: the two keys every
    consumer already reads are unchanged. Handoff 43 measured a request
    waiting on a deactivated account with nothing on the row saying so, and
    an approver who cannot sign in is a request nobody will ever decide. The
    queue screen reads this to say *"X cannot sign in"* beside *"waiting on
    X"*, and to offer *Ask someone else*.
    """
    if not user:
        return None
    return {"id": user.id, "name": user.name or user.display_name,
            "active": bool(user.active)}


def _renomination_row(n):
    """One re-pointing of a request: from whom, to whom, by whom, when, why.

    The names are the row's own Char copies, taken when it was written, so a
    renamed account does not rewrite who was asked. Not called
    `serialize_*`: `myservice_api/tests/test_published_names_resolve.py`
    requires every function so named to be classified against a model, and
    this is a row of `nrs.asset.change.request.renomination` read through
    the request's `renomination_ids`.
    """
    return {
        "id": n.id,
        "from": {"id": n.from_approver_id.id or None,
                 "name": n.from_approver_name or None},
        "to": {"id": n.to_approver_id.id or None,
               "name": n.to_approver_name or None},
        "by": {"id": n.renominated_by_id.id or None,
               "name": n.renominated_by_name or None},
        "at": _dt(n.renominated_at),
        "reason": n.reason or None,
    }


def _dt(value):
    return value.isoformat() if value else None


def serialize_request(r):
    """One approval request, in full.

    **Every published key here resolves to a real field**, which
    `myservice_api/tests/test_published_names_resolve.py` proves by parsing
    this file — the guard handoff 32 built after a published name and the
    thing underneath it stopped agreeing twice without anything failing.

    `premise_holds` and `premise_broken_reason` are computed fresh on read,
    not stored. §D of the handoff: *a request whose premise no longer holds
    must not be approvable in silence.* A queue that showed a stale `true`
    would be the silent half of exactly that.
    """
    return {
        "id": r.id,
        "reference": r.name,
        "state": r.state,
        "change_type": r.change_type,
        "asset": _ref(r.asset_id),
        "asset_code": r.asset_code or None,
        # What is asked for.
        "to_location": _ref(r.to_location_id),
        "to_custodian": _ref(r.to_custodian_id),
        "reason": r.reason or None,
        # WHAT IT WAS WHEN ASKED. The `_name` copies are what the record
        # keeps when a location is renamed or an employee is deleted, so the
        # published premise cannot be emptied from outside.
        "from_location": _ref(r.from_location_id),
        "from_custodian": _ref(r.from_custodian_id),
        "from_location_name": r.from_location_name or None,
        "from_custodian_name": r.from_custodian_name or None,
        "to_location_name": r.to_location_name or None,
        "to_custodian_name": r.to_custodian_name or None,
        "from_state": r.from_state or None,
        # WHO ASKED, and WHO IS BEING ASKED.
        "requested_by": _ref(r.requested_by_id),
        "requested_by_name": r.requested_by_name or None,
        "requested_at": _dt(r.requested_at),
        # `{id, name, active}` — `active` added by handoff 45 (G.1(a)), so a
        # request waiting on somebody who can no longer sign in says so.
        "approver": _approver_ref(r.approver_id),
        # Every time the request was re-pointed at somebody else, OLDEST
        # FIRST — `approver` is only who is asked NOW. Handoff 45 (G.1(b)).
        "renominations": [_renomination_row(n)
                          for n in r.renomination_ids.sorted(
                              lambda n: (n.renominated_at, n.id))],
        # WHO CLICKED. A different key, always, for the reason in the module
        # docstring.
        "decided_by": _ref(r.approved_by_id),
        "decided_by_name": r.approved_by_name or None,
        "decided_at": _dt(r.decided_at),
        "decision_reason": r.decision_reason or None,
        # Whether it can still be approved, and what changed if not.
        "premise_holds": bool(r.premise_holds),
        "premise_broken_reason": r.premise_broken_reason or None,
        # What it produced. Null until approved; the two append-only ids are
        # the durable record and the transfer is the paperwork beside them.
        "movement_id": r.movement_id.id or None,
        "custody_id": r.custody_id.id or None,
        "transfer": {
            "id": r.transfer_id.id,
            "reference": r.transfer_id.name,
        } if r.transfer_id else None,
        "transfer_reference": r.transfer_reference or None,
        # Whether the CALLER may decide this one. Computed per caller, so a
        # queue screen can grey out a row rather than offer a button the
        # model will refuse. The model is still the authority — this is the
        # interface not offering a refused action, exactly as `use-scopes`
        # in the app is.
        "can_decide": r._may_decide(request.env.user),
        "can_withdraw": (r.state == "pending"
                         and r.requested_by_id.id == request.env.uid),
        # Whether the CALLER may re-point it at somebody else — the
        # requester or an administrator, while pending. The model's own
        # answer (`_may_renominate`), so the button and the 403 agree.
        "can_renominate": r._may_renominate(request.env.user),
    }


def _browse_or_404(request_id):
    rec = request.env[MODEL].sudo().browse(request_id).exists()
    if not rec:
        return None, err(ERR_NOT_FOUND,
                         f"Approval request {request_id} not found", status=404)
    return rec, None


def _refuse_claimed_decider(body):
    """400 if the body tries to name who decided. See the module docstring."""
    if not isinstance(body, dict):
        return None
    claimed = sorted(k for k in body if k in _DECIDER_CLAIM_FIELDS)
    if not claimed:
        return None
    return err(
        ERR_INVALID_REQUEST,
        "Who decided this is taken from the credential that made the call "
        "and cannot be supplied: remove %s and call again as the deciding "
        "user." % ", ".join("`%s`" % k for k in claimed),
        details={"rejected_fields": claimed, "writable": list(_REASON_ONLY)})


class CadraApprovalsAPI(http.Controller):

    # ── The queue: GET /api/v1/approvals ─────────────────────────────

    @cadra_route("/api/v1/approvals", method="GET",
                 summary="Approval requests — what is waiting, and on whom",
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={
                     "type": "array",
                     "items": {"$ref": "#/components/schemas/ApprovalRequest"},
                 },
                 query_params=[
                     {"name": "state",
                      "schema": {"type": "string", "enum": list(STATES)},
                      "description": "Filter by lifecycle state. Omitted "
                                     "returns every state."},
                     {"name": "change_type",
                      "schema": {"type": "string", "enum": list(CHANGE_TYPES)}},
                     {"name": "asset_id", "schema": {"type": "integer"},
                      "description": "Requests against one asset."},
                     {"name": "waiting_on_me",
                      "schema": {"type": "boolean"},
                      "description": "Only requests NAMING the caller as the "
                                     "approver. This is the queue — *what is "
                                     "waiting on me*. Anyone eligible may "
                                     "approve any pending request, so this is "
                                     "a convenience and not a boundary."},
                     {"name": "raised_by_me",
                      "schema": {"type": "boolean"},
                      "description": "Only requests the caller raised — how a "
                                     "requester finds out what happened to "
                                     "theirs."},
                     *PAGINATION_QUERY_PARAMS])
    def list_approvals(self, **kwargs):
        """Every approval request the caller can see, newest first.

        `assets:read`, not `approvals:write`: an Auditor must be able to read
        who authorised what without being able to authorise anything, and
        `group_auditor` holds exactly the read scopes (handoff 23). Deciding
        needs `approvals:write`, on the four routes below.
        """
        env = request.env
        domain = []
        # `parse_*` take (name, raw) and RAISE `BadFilter` — they never fall
        # through and return everything, which is the defect that module
        # exists to end. The first draft of this method called them as
        # `parse_enum(kwargs, "state", …)`, which is (name=kwargs,
        # raw="state"), and every list request 400ed naming a parameter the
        # caller had not sent. Found by calling the endpoint, not by reading
        # it — and the over-broad `except (TypeError, ValueError)` that used
        # to sit here is why the message named `asset_id` for a fault in
        # `state`. A catch-all that reports one parameter's error for another
        # parameter's fault is worse than no catch at all.
        try:
            state = parse_enum("state", kwargs.get("state"), STATES)
            change_type = parse_enum("change_type", kwargs.get("change_type"),
                                     CHANGE_TYPES)
            waiting_on_me = parse_bool("waiting_on_me",
                                       kwargs.get("waiting_on_me"))
            raised_by_me = parse_bool("raised_by_me",
                                      kwargs.get("raised_by_me"))
            asset_id = parse_int("asset_id", kwargs.get("asset_id"))
        except BadFilter as e:
            return err(ERR_INVALID_REQUEST, str(e), details=e.details)
        if state:
            domain.append(("state", "=", state))
        if change_type:
            domain.append(("change_type", "=", change_type))
        if asset_id is not None:
            domain.append(("asset_id", "=", asset_id))
        # `is True`, not truthiness: `parse_bool` answers None for absent and
        # False for an explicit `false`, and `?waiting_on_me=false` must mean
        # "do not filter", not "filter on nothing". `?has_coordinates=false`
        # answering zero was handoff 22's version of this.
        if waiting_on_me is True:
            domain.append(("approver_id", "=", env.uid))
        if raised_by_me is True:
            domain.append(("requested_by_id", "=", env.uid))

        limit = parse_limit(kwargs)
        # `paginate` owns the cursor, the cap and the total — including the
        # rule that `total_estimate` is a count of the CALLER's own domain
        # and not of the capped window, which is the property handoff 13
        # built after a capped caller was told the register held exactly as
        # many rows as it had just been shown. Newest first: a queue is read
        # from the top.
        page, next_cursor, total = paginate(
            env[MODEL].sudo(), domain, limit=limit,
            cursor=kwargs.get("cursor"), descending=True)
        return ok(
            data=[serialize_request(r) for r in page],
            pagination={
                "next_cursor": next_cursor,
                "previous_cursor": None,
                "total_estimate": total,
            },
        )

    # ── One request: GET /api/v1/approvals/<id> ──────────────────────

    @cadra_route("/api/v1/approvals/<int:id>", method="GET",
                 summary="One approval request",
                 scopes=[SCOPE_ASSETS_READ],
                 response_schema={
                     "$ref": "#/components/schemas/ApprovalRequest"})
    def get_approval(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        return serialize_request(rec)

    # ── Who may be asked: GET /api/v1/approvals/approvers ────────────

    @cadra_route("/api/v1/approvals/approvers", method="GET",
                 summary="Who this caller may ask to approve a change",
                 scopes=[SCOPE_ASSETS_WRITE],
                 response_schema={
                     "type": "array",
                     "items": {
                         "type": "object",
                         "properties": {
                             "id": {"type": "integer"},
                             "name": {"type": "string"},
                         },
                     },
                 },
                 query_params=[
                     {"name": "q", "schema": {"type": "string"},
                      "description": "Free-text search on the person's name."},
                     {"name": "limit", "schema": {"type": "integer"}},
                 ])
    def list_approvers(self, **kwargs):
        """The approver picker's list — everyone who could have made the
        change themselves, MINUS the caller.

        The caller's own exclusion is done here and not only in the dialog,
        for the reason the rest of this codebase gives for not hiding things
        in the interface: a picker that offers a choice the model refuses is
        an answer that looks like an answer. `_check_approver_is_not_the_requester`
        refuses the nomination anyway.
        """
        env = request.env
        query = (kwargs.get("q") or "").strip() or None
        limit = parse_limit(kwargs)
        users = env[MODEL].sudo().eligible_approvers(
            exclude_user=env.user, query=query, limit=limit)
        return [{"id": u.id, "name": u.display_name} for u in users]

    # ── Approve: POST /api/v1/approvals/<id>/approve ─────────────────

    @cadra_route("/api/v1/approvals/<int:id>/approve", method="POST",
                 summary="Agree to the change, as whoever holds the credential",
                 scopes=[SCOPE_APPROVALS_WRITE],
                 idempotent=True,
                 error_statuses=(403, 409),
                 response_schema={
                     "type": "object",
                     "properties": {
                         "request": {
                             "$ref": "#/components/schemas/ApprovalRequest"},
                         "asset": {"$ref": "#/components/schemas/Asset"},
                     },
                 },
                 request_schema={
                     "type": "object",
                     "description": (
                         "Optionally a `reason`. WHO decided is taken from "
                         "the bearer token and is never read from the body — "
                         "a body naming a decider or a decision date is "
                         "REFUSED 400 rather than ignored."),
                     "properties": {
                         "reason": {"type": "string", "nullable": True,
                                    "description": "Optional note recorded "
                                                   "with the decision."},
                     },
                 },
                 request_example={"reason": "Checked with the store — fine."})
    def approve(self, id, **kwargs):
        """Approve, and make the change happen.

        Everything of substance is on the model: the self-approval refusal,
        the eligibility check, the premise check and the write itself are
        `action_approve`, so the Odoo button, the shell and this route all
        get the same answer. What is here is the HTTP shape of the three ways
        it says no:

        * **403** — the caller may not decide this one, either because they
          raised it or because they could not have made the change
          themselves.
        * **409** — already decided, or the premise no longer holds. Both are
          *the world is not as you believe*, which is what 409 means, and
          both name what is true instead.
        * **400** — the body tries to say who decided.
        """
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        claimed = _refuse_claimed_decider(body)
        if claimed:
            return claimed
        rejected = sorted(k for k in (body or {}) if k not in _REASON_ONLY)
        if rejected:
            return refuse_unwritable(rejected, _REASON_ONLY)
        reason = (body or {}).get("reason") or ""
        if reason and not isinstance(reason, str):
            return err(ERR_INVALID_REQUEST, "`reason` must be a string")

        # ASKED BEFORE ANYTHING IS WRITTEN. `action_approve` raises on each
        # of these too — that is where the rule lives — but an exception
        # surfaces as a 400 carrying the model's words, and these three
        # deserve their own statuses and their own details so a queue screen
        # can tell "not yours to approve" from "somebody got there first".
        if rec.state != "pending":
            return err(
                ERR_CONFLICT,
                "This request was already %s%s. A decision is taken once."
                % (rec.state,
                   " by %s" % rec.approved_by_name if rec.approved_by_name
                   else ""),
                status=409,
                details={"request_id": rec.id, "state": rec.state,
                         "decided_by": _ref(rec.approved_by_id),
                         "decided_at": _dt(rec.decided_at)})
        if not rec._may_decide(request.env.user):
            own = rec.requested_by_id.id == request.env.uid
            return err(
                ERR_FORBIDDEN,
                "You raised this request and cannot approve it. The point of "
                "an approval is that a second person agrees."
                if own else
                "An approver must be somebody who could have made the change "
                "themselves.",
                status=403,
                details={"request_id": rec.id,
                         "is_own_request": own,
                         "requested_by": _ref(rec.requested_by_id)})
        if not rec.premise_holds:
            return err(
                ERR_CONFLICT,
                "This request can no longer be approved. %s Raise a new "
                "request if the change is still wanted."
                % rec.premise_broken_reason,
                status=409,
                details={"request_id": rec.id,
                         "premise_broken_reason": rec.premise_broken_reason,
                         "asset": _ref(rec.asset_id)})
        # A SAVEPOINT, and it is load-bearing rather than defensive.
        #
        # `action_approve` stamps the decision and creates the transfer
        # document BEFORE it writes the asset — it has to, because the
        # clearance the write needs can only be an approved request (see
        # `_approval_clears`). Its docstring says that is safe because a
        # raise rolls the stamp back, and that is true only while the
        # exception PROPAGATES. This `except` catches it, and `err()` returns
        # a response without rolling anything back — `CLAUDE.md` says so in
        # as many words, and handoff 28 left a `done` transfer behind on a
        # refused move by exactly this mistake.
        #
        # Without the savepoint, any `UserError` raised under `asset.write`
        # — a constraint, an ACL, `_assert_disposed_is_terminal`, anything a
        # downstream module raises — committed a request saying *approved by
        # somebody at some time*, a `done` transfer document for a move that
        # never happened, and an asset that never moved. Found by the
        # verification pass, which also noticed that `AccessError` and
        # `ValidationError` are both `UserError` subclasses and so all of it
        # came through this one clause.
        try:
            with request.env.cr.savepoint():
                rec.action_approve(decision_reason=reason or None)
        except UserError as e:
            # Everything the attempt wrote is gone. The model's words are the
            # accurate ones; 409 because it is still *the world is not as you
            # believe*.
            rec.invalidate_recordset()
            return err(ERR_CONFLICT, str(e), status=409,
                       details={"request_id": rec.id})
        return self._decided_payload(rec)

    # ── Reject: POST /api/v1/approvals/<id>/reject ───────────────────

    @cadra_route("/api/v1/approvals/<int:id>/reject", method="POST",
                 summary="Refuse the change, with a reason",
                 scopes=[SCOPE_APPROVALS_WRITE],
                 idempotent=True,
                 error_statuses=(403, 409),
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
                     "reason": "That room is being repurposed next month — "
                               "hold the asset where it is."})
    def reject(self, id, **kwargs):
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        claimed = _refuse_claimed_decider(body)
        if claimed:
            return claimed
        rejected = sorted(k for k in (body or {}) if k not in _REASON_ONLY)
        if rejected:
            return refuse_unwritable(rejected, _REASON_ONLY)
        reason = ((body or {}).get("reason") or "")
        if not isinstance(reason, str):
            return err(ERR_INVALID_REQUEST, "`reason` must be a string")
        if not reason.strip():
            return err(ERR_INVALID_REQUEST,
                       "`reason` is required — say why this is being "
                       "rejected. The person who asked sees it.")
        if rec.state != "pending":
            return err(ERR_CONFLICT,
                       "This request was already %s." % rec.state, status=409,
                       details={"request_id": rec.id, "state": rec.state})
        if not rec._may_decide(request.env.user):
            own = rec.requested_by_id.id == request.env.uid
            return err(
                ERR_FORBIDDEN,
                "You raised this request. Withdraw it instead of rejecting it."
                if own else
                "Only somebody who could have made the change themselves can "
                "decide on it.",
                status=403,
                details={"request_id": rec.id, "is_own_request": own})
        # Savepointed for the reason `approve` is: `err()` does not roll
        # back. These two write less, but a half-stamped decision is still a
        # decision the record would carry.
        try:
            with request.env.cr.savepoint():
                rec.action_reject(decision_reason=reason)
        except UserError as e:
            rec.invalidate_recordset()
            return err(ERR_CONFLICT, str(e), status=409,
                       details={"request_id": rec.id})
        return self._decided_payload(rec)

    # ── Withdraw: POST /api/v1/approvals/<id>/withdraw ───────────────

    @cadra_route("/api/v1/approvals/<int:id>/withdraw", method="POST",
                 summary="The requester takes their own request back",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 error_statuses=(403, 409),
                 request_schema={
                     "type": "object",
                     "properties": {
                         "reason": {"type": "string", "nullable": True,
                                    "description": "Optional. A requester "
                                                   "withdrawing their own "
                                                   "request owes nobody an "
                                                   "explanation; an approver "
                                                   "rejecting one does, which "
                                                   "is why these are two "
                                                   "routes and not one."},
                     },
                 },
                 request_example={"reason": "Asked the wrong person."})
    def withdraw(self, id, **kwargs):
        """`assets:write`, not `approvals:write`.

        Withdrawing is not a decision about somebody else's request; it is
        taking back your own, and the people who raise requests are exactly
        the people holding `assets:write`. Requiring `approvals:write` would
        mean a requester who cannot approve could not cancel their own
        request either, leaving a dead row in an approver's queue for ever.
        """
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params()
        claimed = _refuse_claimed_decider(body)
        if claimed:
            return claimed
        rejected = sorted(k for k in (body or {}) if k not in _REASON_ONLY)
        if rejected:
            return refuse_unwritable(rejected, _REASON_ONLY)
        reason = (body or {}).get("reason") or ""
        if reason and not isinstance(reason, str):
            return err(ERR_INVALID_REQUEST, "`reason` must be a string")
        if rec.state != "pending":
            return err(ERR_CONFLICT,
                       "This request was already %s." % rec.state, status=409,
                       details={"request_id": rec.id, "state": rec.state})
        if rec.requested_by_id.id != request.env.uid \
                and not request.env.user._is_admin():
            return err(
                ERR_FORBIDDEN,
                "Only %s, who raised this request, can withdraw it. Reject "
                "it instead if you are deciding on it."
                % rec.requested_by_id.display_name,
                status=403,
                details={"request_id": rec.id,
                         "requested_by": _ref(rec.requested_by_id)})
        # Savepointed for the reason `approve` is: `err()` does not roll
        # back. These two write less, but a half-stamped decision is still a
        # decision the record would carry.
        try:
            with request.env.cr.savepoint():
                rec.action_withdraw(decision_reason=reason or None)
        except UserError as e:
            rec.invalidate_recordset()
            return err(ERR_CONFLICT, str(e), status=409,
                       details={"request_id": rec.id})
        return self._decided_payload(rec)

    # ── Ask someone else: POST /api/v1/approvals/<id>/renominate ─────

    @cadra_route("/api/v1/approvals/<int:id>/renominate", method="POST",
                 summary="Re-point a pending request at a different approver",
                 scopes=[SCOPE_ASSETS_WRITE],
                 idempotent=True,
                 error_statuses=(403, 404, 409),
                 response_schema={
                     "type": "object",
                     "properties": {
                         "request": {
                             "$ref": "#/components/schemas/ApprovalRequest"},
                         "renomination": {
                             "type": "object",
                             "description": (
                                 "The append-only row this call wrote: "
                                 "`from` (who it was waiting on), `to` (who "
                                 "it waits on now), `by` (the caller, from "
                                 "the bearer token), `at`, `reason`. It "
                                 "cannot be edited or deleted afterwards, and "
                                 "it appears again, oldest first, in the "
                                 "request's `renominations`."),
                             "properties": {
                                 "id": {"type": "integer"},
                                 "from": {"type": "object"},
                                 "to": {"type": "object"},
                                 "by": {"type": "object"},
                                 "at": {"type": "string"},
                                 "reason": {"type": "string"},
                             },
                         },
                     },
                 },
                 request_schema={
                     "type": "object",
                     "required": ["approver_id", "reason"],
                     "description": (
                         "Handoff 45. A pending request names ONE person as "
                         "the approver it is waiting on; when that person "
                         "cannot act — their account deactivated, most "
                         "often, which is never blocked — the request is "
                         "re-pointed rather than left stranded. Allowed to "
                         "the person who RAISED the request and to an "
                         "administrator (403 otherwise; `can_renominate` on "
                         "the request says which in advance). The new "
                         "approver must be active, eligible to approve (the "
                         "same rule as `approver_id` on `/move`), not the "
                         "requester and not the person already asked — 400 "
                         "otherwise, in words. WHO re-pointed it and WHEN "
                         "come from the bearer token and the clock; any "
                         "other body key is refused 400. Nothing about the "
                         "asset changes."),
                     "properties": {
                         "approver_id": {
                             "type": "integer",
                             "description": "The `res.users` id to ask "
                                            "instead. `GET /api/v1/approvals"
                                            "/approvers` lists candidates."},
                         "reason": {
                             "type": "string",
                             "description": "REQUIRED. Recorded on the "
                                            "append-only row and read by "
                                            "whoever audits the request."},
                     },
                 },
                 request_example={
                     "approver_id": 7,
                     "reason": "Adaeze has left the service; her account is "
                               "deactivated."})
    def renominate(self, id, **kwargs):
        """Ask somebody else. Handoff 45, ruling G.1(b).

        Everything of substance is on the model —
        `nrs.asset.change.request.action_renominate`, the ONE path by which a
        pending request's `approver_id` changes; its `write` still refuses
        every other way. What is here is the HTTP shape of the ways it says
        no, each asked BEFORE anything is written:

        * **400** — a body key other than `approver_id`/`reason`, no reason,
          or an approver who cannot be asked (deactivated, not eligible, the
          requester, or already the one asked). The model's sentence.
        * **403** — the caller is neither the requester nor an
          administrator. The model's sentence, verbatim.
        * **404** — no such request, or no such user.
        * **409** — the request is no longer pending.
        """
        rec, error = _browse_or_404(id)
        if error:
            return error
        body = get_params() or {}
        if not isinstance(body, dict):
            return err(ERR_INVALID_REQUEST, "The body must be a JSON object")
        rejected = sorted(k for k in body if k not in _RENOMINATE_KEYS)
        if rejected:
            return refuse_unwritable(
                rejected, _RENOMINATE_KEYS,
                hint="Who re-pointed the request and when are taken from "
                     "the credential that made the call and the clock; "
                     "only `approver_id` and `reason` are read.")
        reason = body.get("reason")
        if reason is not None and not isinstance(reason, str):
            return err(ERR_INVALID_REQUEST, "`reason` must be a string")
        if not (reason or "").strip():
            return err(ERR_INVALID_REQUEST,
                       "`reason` is required — say why you are asking "
                       "somebody else. It is recorded and cannot be "
                       "changed afterwards.")

        if rec.state != "pending":
            return err(
                ERR_CONFLICT,
                "This request was already %s%s, so there is nobody to "
                "re-point it at." % (
                    rec.state,
                    " by %s" % rec.approved_by_name
                    if rec.approved_by_name else ""),
                status=409,
                details={"request_id": rec.id, "state": rec.state})
        refusal = rec._renomination_refusal(request.env.user)
        if refusal:
            return err(ERR_FORBIDDEN, refusal, status=403,
                       details={"request_id": rec.id,
                                "requested_by": _ref(rec.requested_by_id)})

        raw = body.get("approver_id")
        if raw in (None, "", 0, "0") or isinstance(raw, bool):
            candidates = rec.eligible_approvers(
                exclude_user=rec.requested_by_id, limit=10).filtered(
                    lambda u: u.id != rec.approver_id.id)
            return err(
                ERR_INVALID_REQUEST,
                "`approver_id` is required: name who you are asking instead. "
                "GET /api/v1/approvals/approvers lists who may be asked.",
                details={"request_id": rec.id,
                         "approvers": [{"id": u.id, "name": u.display_name}
                                       for u in candidates]})
        try:
            approver_id = int(raw)
        except (TypeError, ValueError):
            return err(ERR_INVALID_REQUEST,
                       "`approver_id` must be an integer")
        new = request.env["res.users"].sudo().browse(approver_id).exists()
        if not new:
            return err(ERR_NOT_FOUND, f"User {approver_id} not found",
                       status=404)
        problem = rec._renomination_target_problem(new)
        if problem:
            return err(ERR_INVALID_REQUEST, problem,
                       details={"request_id": rec.id,
                                "approver_id": new.id})

        # SAVEPOINTED, for the reason `approve` is: `err()` does not roll
        # back, and `action_renominate` writes the append-only row BEFORE it
        # moves `approver_id`. A `UserError` from underneath would otherwise
        # leave a row recording a re-pointing that did not happen — in a
        # table nobody can delete from.
        try:
            with request.env.cr.savepoint():
                row = rec.with_context(
                    cadra_renomination_source="api_renominate",
                ).action_renominate(new, reason)
        except UserError as e:
            rec.invalidate_recordset()
            return err(ERR_CONFLICT, str(e), status=409,
                       details={"request_id": rec.id})
        rec.invalidate_recordset()
        return {
            "request": serialize_request(rec),
            "renomination": _renomination_row(row),
        }

    # ── shared ───────────────────────────────────────────────────────

    def _decided_payload(self, rec):
        """The request as it now stands, and the asset as it now stands.

        The ASSET is included on every decision, including a rejection, and
        that is not padding: the one thing a caller needs to know after any
        of these three calls is whether the asset moved. On an approval it
        did; on a rejection and a withdrawal it did not, and the asset in the
        response proves it rather than asking the caller to trust the verb.
        """
        from .v1_assets import serialize_asset
        rec.invalidate_recordset()
        return {
            "request": serialize_request(rec),
            "asset": serialize_asset(rec.asset_id),
        }
