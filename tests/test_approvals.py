"""Nobody moves an asset alone — handoff 35, over HTTP.

WHAT THIS FILE IS FOR
---------------------
A move and a custody change are the two acts in this register that a person
performs on somebody else's behalf, and NRS asked at a demonstration whether
one person should be able to do either alone. The answer built is a request
and a second person: `POST /assets/<id>/move` and
`POST /assets/<id>/transfer-custody` no longer change anything on a tenant
where `cadra.approval.required` is on — **and absent means on**, so a tenant
nobody has configured is one of those.

The properties asserted here are the ones that stop this being theatre:

* **A request writes NOTHING.** Handoff 35 §B's first non-negotiable. The
  append-only records — `nrs.asset.movement`, `nrs.asset.custody` — are
  written on approval and never on the request, because a movement row
  written when somebody ASKED would be a permanent, unalterable record of a
  move that had not happened and might never happen. Every raising test below
  reads the asset back rather than trusting the response.
* **Two fields that are never the same field.** `approver` is WHO IS BEING
  ASKED and comes from the requester's body; `decided_by` is WHO CLICKED and
  comes from the bearer token. A requester who can name the approver can
  forge one — which is only true if naming them is what makes them the
  approver, so the test that matters is the one asserting the two differ and
  that a body naming a decider is REFUSED rather than ignored.
* **Self-approval is refused in the MODEL.** Not hidden in the app. Report 30
  found a disposed asset could be un-disposed through a route nobody had
  looked at; a rule enforced only where the button is has a back way in.
* **A request whose premise no longer holds cannot be approved in silence.**
  §D. The world moves between the asking and the agreeing, and an approver
  clicking Approve on a stale request must be told what changed.
* **The queue filters actually filter.** `?waiting_on_me=true` answering with
  every request in the register is the family of defect handoff 21 closed —
  a full list reads as an answer, and an approver has no way to tell it from
  theirs. So each filter test asserts that a row which should NOT match is
  ABSENT, never merely that the matching ones are present.

WHO IS WHO IN THIS FILE
-----------------------
The suite's own credential RAISES here, and the second person (`admin`, or
whatever `CADRA_SECOND_PERSON_LOGIN` names) APPROVES. That is the opposite
way round from `tests/conftest.py::second_person`, whose job is to make an
asset actually move and which therefore has the suite approve so the
permanent row self-labels as a fixture. Here the requester's identity is the
subject — withdrawal, `raised_by_me`, the self-approval refusal — so the
suite has to be the one asking.
"""
import time
import uuid

import pytest

from . import gates
from .conftest import (assert_envelope_err, assert_envelope_ok,
                       assert_fields_refused)

#: The states and change types the API publishes. Read from the model by
#: `GET /meta/enums` and asserted there (`tests/test_cursor_and_enums.py`);
#: repeated here only so the assertions below read as sentences.
_STATES = ("pending", "approved", "rejected", "withdrawn")


def _uniq(prefix):
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


# ─── the cast ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def approvals_on(second_person):
    """This module's subject, or a loud skip.

    A tenant that has deliberately set `cadra.approval.required = off` has no
    approval queue to test — `/move` moves the asset and no request is ever
    created — so almost everything below has nothing to act on. The two tests
    that ARE about the switch itself do not take this fixture.
    """
    if not second_person.required:
        pytest.skip(
            "this tenant has `cadra.approval.required` off, so a move takes "
            "one person and there are no approval requests to decide")
    return second_person


@pytest.fixture(scope="module")
def approver(approvals_on):
    """The second person: their client, their id, their name."""
    return approvals_on.other


@pytest.fixture(scope="module")
def two_locations(client):
    """Two locations of this module's own.

    Not `any_location`: a premise test moves an asset between them and then
    asserts where it is, and a location another module is also moving assets
    into would make that assertion about somebody else's work.
    """
    made = []
    for n in ("a", "b"):
        made.append(assert_envelope_ok(client.post("/api/v1/locations", json={
            "name": _uniq(f"pytest-approvals-loc-{n}")}), 201)["data"])
    return made


@pytest.fixture(scope="module")
def two_employees(client):
    r = client.get("/api/v1/identity/employees", params={"limit": 2})
    rows = (r.json().get("data") or []) if r.status_code == 200 else []
    if len(rows) < 2:
        pytest.skip("tenant has fewer than two employees to hand an asset "
                    "between")
    return rows[0]["id"], rows[1]["id"]


def _asset(client, location_id, name, **extra):
    """A new asset of this test's own, at `location_id` (or nowhere)."""
    body = {"name": _uniq(name), "category_id": 1, **extra}
    if location_id:
        body["location_id"] = location_id
    # On the register whichever way the receipt switch is set (handoff 58
    # §2): with the gates on a candidate cannot be moved or handed over,
    # so `tests/gates.py` walks it onto the register first.
    return gates.new_registered_asset(client, **body)


def _read(client, asset_id):
    return assert_envelope_ok(client.get(f"/api/v1/assets/{asset_id}"))["data"]


def _raise_move(client, asset_id, to_location_id, approver_id, reason=None):
    body = {"to_location_id": to_location_id, "approver_id": approver_id}
    if reason is not None:
        body["reason"] = reason
    return client.post(f"/api/v1/assets/{asset_id}/move", json=body)


def _raise_custody(client, asset_id, to_custodian_id, approver_id,
                   reason=None):
    body = {"to_custodian_id": to_custodian_id, "approver_id": approver_id}
    if reason is not None:
        body["reason"] = reason
    return client.post(f"/api/v1/assets/{asset_id}/transfer-custody",
                       json=body)


# ─── the switch ──────────────────────────────────────────────────────

def test_the_switch_says_what_it_is_and_whether_anybody_set_it(client,
                                                               capture):
    """`GET /settings/approvals` — handoff 35 §C, with the value ABSENT.

    §C asked for the absent case to be PROVED rather than reasoned about,
    because that is how handoff 25's ormcache leak was found: a guard served
    from a per-worker cache said `test` about a database whose parameter row
    had been deleted, and twenty-four writing tests went through it.

    `test19` has never had `cadra.approval.required` set, so this is the
    absent case, live. Two keys carry it and they are not the same fact:
    `required` is the BEHAVIOUR and `configured` is whether anybody ever
    decided. *Nobody has thought about this and it is getting the default*
    and *somebody deliberately turned it on* produce the same behaviour, and
    a settings screen that cannot tell them apart cannot tell an
    administrator whether the control is theirs or an accident.

    Asserted against the tenant rather than pinned to `true`, because a
    tenant that HAS switched it off is a legitimate target for this suite and
    this test must say something true there too. What is pinned in both
    worlds is `default_when_unset`: absent means on, and a build that changed
    that direction would be changing the safety of every unconfigured tenant
    in the estate.
    """
    r = client.get("/api/v1/settings/approvals")
    capture("settings/approvals", r)
    data = assert_envelope_ok(r)["data"]

    assert data["parameter"] == "cadra.approval.required"
    assert data["default_when_unset"] is True, (
        "a value that is neither on nor off must mean ON. A tenant that "
        "skips the second person because a parameter was misspelt has no "
        "symptom at all until an auditor asks who authorised a move.")
    assert isinstance(data["required"], bool)
    assert data["setting"] in (None, "on", "off")
    assert data["configured"] is (data["setting"] is not None)
    if data["setting"] is None:
        assert data["required"] is True, (
            "nobody has set `%s` on this database and it is not requiring "
            "approval — the default has inverted" % data["parameter"])


def test_the_switch_cannot_be_changed_over_the_api(client, approvals_on):
    """There is deliberately no PATCH twin, and that IS the control.

    `assets:write`, `approvals:write` and `settings:write` are all granted by
    the single group `group_asset_manager`, so a PATCH here would let exactly
    the people the rule constrains switch it off, move the asset and switch
    it back on. Every other settings block on that controller has a PATCH;
    this one not having one is a decision, and a decision nothing asserts is
    a decision somebody adds back next quarter for symmetry.
    """
    r = client.patch("/api/v1/settings/approvals", json={"setting": "off"})
    assert r.status_code in (404, 405), (
        "PATCH /api/v1/settings/approvals answered %s — the approval switch "
        "has become settable by the people it constrains"
        % r.status_code)
    # And it really is still on, so the assertion above is not passing
    # because something else broke.
    assert assert_envelope_ok(
        client.get("/api/v1/settings/approvals"))["data"]["required"] is True


# ─── raising a request changes nothing ───────────────────────────────

def test_raising_a_move_request_writes_nothing_to_the_asset(
        client, two_locations, approver, capture):
    """The one property everything else rests on.

    §B: *the append-only records are written on approval, never on request.*
    A movement row written when somebody ASKED would be a permanent record of
    a move that had not happened — and it is permanent in the strongest
    sense, because `nrs.asset.movement.write` and `.unlink` raise
    unconditionally. There is no correcting it afterwards.

    So this reads the asset back whole and compares it, rather than checking
    the one field it expects to be unchanged. `pending_approval` in the
    response is a claim; the record is the evidence.
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-nothing-written")
    before = _read(client, asset["id"])

    r = _raise_move(client, asset["id"], there["id"], approver["id"],
                    reason="test_approvals.nothing_written")
    capture("approvals/move_pending", r)
    data = assert_envelope_ok(r)["data"]

    # The cheapest possible read of this response is the correct one.
    assert data["pending_approval"] is True
    assert data["action"] == "move"
    # The three keys the old contract published, explicitly null: a consumer
    # reading `movement_id` must be able to tell "not yet" from "absent", and
    # both are what this call did not produce.
    assert data["movement_id"] is None
    assert data["transfer"] is None
    assert data["custody_change"] is None
    # The asset, UNCHANGED, read back in the same response — so a consumer
    # that trusts the asset rather than the verb sees the truth.
    assert data["asset"]["current_location"]["id"] == here["id"]

    assert _read(client, asset["id"]) == before, (
        "raising an approval request changed the asset")

    req = data["request"]
    assert req["state"] == "pending"
    assert req["change_type"] == "location"
    assert req["reference"], "a request with no reference number is one a "\
                             "person cannot refer to"
    assert req["approver"]["id"] == approver["id"]
    assert req["requested_by"]["id"] != approver["id"], (
        "the person being asked and the person asking are the same user")
    assert req["to_location"]["id"] == there["id"]

    # And the append-only record really is absent, not merely unreported.
    history = assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset['id']}/history"))["data"]
    moves = [e for e in history["events"]
             if e["type"] == "location_moved" and e["detail"]["from_location"]]
    assert moves == [], (
        "a movement row was written for a move nobody has agreed to yet, in "
        "a model whose write() raises — there is no undoing this one")


def test_raising_a_custody_request_writes_nothing_to_the_asset(
        client, two_locations, two_employees, approver):
    """The same property on the other route, because it is a different code
    path and the model gate is the only thing they share."""
    here, _ = two_locations
    first, second = two_employees
    asset = _asset(client, here["id"], "pytest-approvals-custody-nothing")
    before = _read(client, asset["id"])

    data = assert_envelope_ok(_raise_custody(
        client, asset["id"], first, approver["id"],
        reason="test_approvals.custody_nothing"))["data"]
    assert data["pending_approval"] is True
    assert data["action"] == "transfer-custody"
    assert data["custody_change"] is None
    assert data["asset"]["current_custodian"] == before["current_custodian"]
    assert _read(client, asset["id"]) == before

    chain = assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset['id']}/custody"))["data"]
    assert chain == [], (
        "a custody link was written for a hand-over nobody has agreed to")


# ─── who is being asked ──────────────────────────────────────────────

def test_the_approver_must_be_named_and_the_refusal_names_the_candidates(
        client, two_locations, approvals_on):
    """A 400 that tells the caller who they may ask.

    `details.approvers` is the repair. A client told only *"`approver_id` is
    required"* has to go and find the picker endpoint; one handed the list
    can fill the dialog from the refusal it just received. The same argument
    as `details.writable` on every other refusal in this API since handoff
    31.
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-no-approver")
    before = _read(client, asset["id"])

    r = client.post(f"/api/v1/assets/{asset['id']}/move",
                    json={"to_location_id": there["id"]})
    details = assert_envelope_err(r, 400, "invalid_request")["error"]["details"]
    assert details["approval_required"] is True
    assert details["asset_id"] == asset["id"]
    candidates = details["approvers"]
    assert isinstance(candidates, list) and candidates, (
        "the refusal names nobody to ask, so a caller cannot repair itself "
        "and a dialog has nothing to put in its picker")
    assert all(c["id"] and c["name"] for c in candidates)
    me = assert_envelope_ok(client.get("/api/v1/auth/whoami"))["data"]
    assert me["id"] not in [c["id"] for c in candidates], (
        "the caller is offered as a candidate to approve their own change — "
        "a choice the model then refuses, which is an answer that looks like "
        "an answer")
    assert _read(client, asset["id"]) == before


def test_naming_yourself_as_the_approver_is_refused(
        client, two_locations, approvals_on):
    """Refused at the door AND in the model.

    `_check_approver_is_not_the_requester` is a Python constraint on the
    record, so the shell and the Odoo form get the same answer; this is the
    route's own version, whose only job is to say what the CALLER did rather
    than what the constraint saw. Both exist on purpose, and a test of only
    the route would let the constraint be deleted.
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-self-nominate")
    before = _read(client, asset["id"])
    me = assert_envelope_ok(client.get("/api/v1/auth/whoami"))["data"]

    r = _raise_move(client, asset["id"], there["id"], me["id"])
    body = assert_envelope_err(r, 400, "invalid_request")
    assert "yourself" in body["error"]["message"].lower()
    assert _read(client, asset["id"]) == before
    assert _pending_on(client, asset["id"]) == [], (
        "a request was created naming its own author as the approver")


def test_the_approver_picker_never_offers_the_caller(client, approvals_on):
    """`GET /approvals/approvers` — everyone who could have made the change
    themselves, MINUS the caller."""
    r = client.get("/api/v1/approvals/approvers")
    rows = assert_envelope_ok(r)["data"]
    assert rows, "nobody on this tenant can approve anything"
    me = assert_envelope_ok(client.get("/api/v1/auth/whoami"))["data"]
    assert me["id"] not in [row["id"] for row in rows]
    assert all(set(row) == {"id", "name"} for row in rows)


# ─── who decided ─────────────────────────────────────────────────────

def _pending_on(client, asset_id):
    body = assert_envelope_ok(client.get(
        "/api/v1/approvals", params={"asset_id": asset_id,
                                     "state": "pending", "limit": 50}))
    return body["data"]


def test_self_approval_is_refused_with_the_reason_named(
        client, two_locations, approver, capture):
    """403, `details.is_own_request`, and the asset does not move.

    The flag matters as much as the status. A queue screen has to tell *"not
    yours to approve"* from *"you raised this one"* — the first is a
    permissions problem and the second is the whole point of the feature —
    and a bare 403 makes them the same message.
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-self-approve")
    req = assert_envelope_ok(_raise_move(
        client, asset["id"], there["id"], approver["id"]))["data"]["request"]

    r = client.post(f"/api/v1/approvals/{req['id']}/approve", json={})
    capture("approvals/self_approval_refused", r)
    details = assert_envelope_err(r, 403, "forbidden")["error"]["details"]
    assert details["is_own_request"] is True
    assert details["request_id"] == req["id"]
    assert details["requested_by"]["id"] != approver["id"]

    assert _read(client, asset["id"])["current_location"]["id"] == here["id"]
    still = assert_envelope_ok(
        client.get(f"/api/v1/approvals/{req['id']}"))["data"]
    assert still["state"] == "pending"
    assert still["decided_by"] is None
    assert still["can_decide"] is False, (
        "the record says this caller may decide it while the route refuses "
        "them — a screen would offer a button the model rejects")


@pytest.mark.parametrize("claim", ["decided_by", "approved_by_id", "state",
                                   "decided_at"])
def test_a_body_that_names_who_decided_is_refused(
        client, two_locations, approver, claim):
    """Refused, not ignored — handoff 23's ruling, applied here.

    A client able to name the decider could raise a request and appoint any
    user in the tenant as its authority in the same breath. Dropping the key
    with a 200 is worse than refusing it: the caller's own logs then say it
    appointed somebody the register never recorded.

    `state` is in the list for a different reason and belongs there: a body
    that sets the state directly would skip the decision entirely.
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-claim-decider")
    req = assert_envelope_ok(_raise_move(
        client, asset["id"], there["id"], approver["id"]))["data"]["request"]
    path = f"/api/v1/approvals/{req['id']}"
    before = assert_envelope_ok(client.get(path))["data"]

    details = assert_fields_refused(
        approver["client"].post(f"{path}/approve", json={claim: 2}), claim)
    assert details["writable"] == ["reason"]
    assert assert_envelope_ok(client.get(path))["data"] == before, (
        "the decision was refused and the request changed anyway")
    assert _read(client, asset["id"])["current_location"]["id"] == here["id"]


def test_approving_moves_the_asset_and_records_two_different_people(
        client, two_locations, approver, capture):
    """The happy path, and the field pair that must never collapse into one.

    `requested_by` is who asked. `decided_by` is who clicked, taken from the
    bearer token and never from a body. They are two columns because an
    approval whose approver the requester supplied is not an approval — and
    the cheapest way for that to regress is for somebody to notice they are
    "the same person in practice" on a one-user demo tenant and merge them.
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-approve")
    raised = assert_envelope_ok(_raise_move(
        client, asset["id"], there["id"], approver["id"],
        reason="test_approvals.approve"))["data"]["request"]

    r = approver["client"].post(f"/api/v1/approvals/{raised['id']}/approve",
                                json={"reason": "checked with the store"})
    capture("approvals/approve", r)
    data = assert_envelope_ok(r)["data"]
    req = data["request"]

    assert req["state"] == "approved"
    assert req["decided_by"]["id"] == approver["id"]
    assert req["requested_by"]["id"] == raised["requested_by"]["id"]
    assert req["decided_by"]["id"] != req["requested_by"]["id"], (
        "the same user is recorded as having asked and as having agreed")
    assert req["approver"]["id"] == approver["id"]
    assert req["decision_reason"] == "checked with the store"
    assert req["decided_at"]

    # What it produced. The movement is the FACT and the transfer is the
    # paperwork; the asset had a location to leave, so there is one of each.
    assert req["movement_id"], (
        "an approved move left no append-only record, which is the whole "
        "thing this control exists to produce")
    assert req["custody_id"] is None
    assert req["transfer"]["id"] and req["transfer_reference"]

    # The asset, in the same response AND read back.
    assert data["asset"]["current_location"]["id"] == there["id"]
    assert _read(client, asset["id"])["current_location"]["id"] == there["id"]

    history = assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset['id']}/history"))["data"]
    move = next(e for e in history["events"]
                if e["type"] == "location_moved"
                and e["record"]["id"] == req["movement_id"])
    assert move["evidence"] == "append_only"
    assert move["detail"]["reason"] == "test_approvals.approve"


def test_approving_a_custody_request_hands_the_asset_over(
        client, two_locations, two_employees, approver):
    """The other change type, end to end — and its own append-only link."""
    here, _ = two_locations
    first, second = two_employees
    asset = _asset(client, here["id"], "pytest-approvals-approve-custody")
    raised = assert_envelope_ok(_raise_custody(
        client, asset["id"], first, approver["id"],
        reason="test_approvals.custody"))["data"]["request"]

    req = assert_envelope_ok(approver["client"].post(
        f"/api/v1/approvals/{raised['id']}/approve",
        json={}))["data"]["request"]
    assert req["state"] == "approved"
    assert req["custody_id"]
    assert req["movement_id"] is None, (
        "a custody change wrote a movement row — the asset did not go "
        "anywhere")
    assert _read(client, asset["id"])["current_custodian"]["id"] == first

    chain = assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset['id']}/custody"))["data"]
    assert [link["id"] for link in chain] == [req["custody_id"]]
    assert chain[0]["reason"] == "test_approvals.custody"


# ─── one at a time ───────────────────────────────────────────────────

def test_a_second_request_on_the_same_asset_is_refused_naming_the_first(
        client, two_locations, two_employees, approver, capture):
    """§D's first question, answered `no`, and the answer names the blocker.

    Two pending requests on one asset are incoherent rather than untidy: each
    records the world it was raised in, so approving the first breaks the
    second's premise by definition and the second can then only ever be
    refused. Letting it be raised invites somebody to queue up work that
    cannot happen.

    A partial unique index is the authority. This is about the ROUTE's
    answer: an index gives a `psycopg2.IntegrityError` that takes the whole
    transaction with it, and a person who pressed Move deserves the reference
    number of the thing in their way.

    Asserted ACROSS change types, which is the case a per-type index would
    have missed: a custody request must be blocked by a pending move.
    """
    here, there = two_locations
    first, _ = two_employees
    asset = _asset(client, here["id"], "pytest-approvals-one-at-a-time")
    blocker = assert_envelope_ok(_raise_move(
        client, asset["id"], there["id"], approver["id"]))["data"]["request"]

    r = _raise_custody(client, asset["id"], first, approver["id"])
    capture("approvals/second_request_conflict", r)
    details = assert_envelope_err(r, 409, "conflict")["error"]["details"]
    assert details["pending_request"]["id"] == blocker["id"]
    assert details["pending_request"]["reference"] == blocker["reference"]
    assert details["pending_request"]["change_type"] == "location"
    assert details["pending_request"]["approver"]["id"] == approver["id"]
    assert [row["id"] for row in _pending_on(client, asset["id"])] == \
        [blocker["id"]]


def test_a_decided_request_cannot_be_decided_again(
        client, two_locations, approver):
    """A decision is taken once. 409, and it says who took it.

    All three routes, because they are three methods and only the model's
    state check is shared: approve, reject and withdraw each have their own
    precondition block, and two of the three were written by copying the
    first.
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-decided-once")
    req = assert_envelope_ok(_raise_move(
        client, asset["id"], there["id"], approver["id"]))["data"]["request"]
    path = f"/api/v1/approvals/{req['id']}"

    assert_envelope_ok(approver["client"].post(f"{path}/approve", json={}))
    after = assert_envelope_ok(client.get(path))["data"]

    again = approver["client"].post(f"{path}/approve", json={})
    details = assert_envelope_err(again, 409, "conflict")["error"]["details"]
    assert details["state"] == "approved"
    assert details["decided_by"]["id"] == approver["id"]

    rejected = approver["client"].post(f"{path}/reject",
                                       json={"reason": "too late"})
    assert_envelope_err(rejected, 409, "conflict")
    withdrawn = client.post(f"{path}/withdraw", json={})
    assert_envelope_err(withdrawn, 409, "conflict")

    assert assert_envelope_ok(client.get(path))["data"] == after, (
        "a second decision on a decided request changed the record")


# ─── rejection ───────────────────────────────────────────────────────

def test_rejecting_requires_a_reason_and_leaves_the_asset_alone(
        client, two_locations, approver, capture):
    """The reason is REQUIRED, and the refusal to reject writes nothing.

    A rejection without a reason leaves the requester with a dead request and
    nothing to act on, and they will simply ask again — the shape of control
    that produces noise and no information. `/condemn`, `/mark-missing` and
    `/mark-found` all require one on the same argument.
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-reject")
    req = assert_envelope_ok(_raise_move(
        client, asset["id"], there["id"], approver["id"]))["data"]["request"]
    path = f"/api/v1/approvals/{req['id']}"

    for empty in ({}, {"reason": ""}, {"reason": "   "}):
        assert_envelope_err(approver["client"].post(f"{path}/reject",
                                                    json=empty),
                            400, "invalid_request")
        assert assert_envelope_ok(client.get(path))["data"]["state"] == \
            "pending", "a rejection refused for want of a reason still "\
                       "closed the request"

    r = approver["client"].post(
        f"{path}/reject",
        json={"reason": "that room is being repurposed next month"})
    capture("approvals/reject", r)
    data = assert_envelope_ok(r)["data"]
    assert data["request"]["state"] == "rejected"
    assert data["request"]["decided_by"]["id"] == approver["id"]
    assert data["request"]["decision_reason"] == \
        "that room is being repurposed next month"
    assert data["request"]["movement_id"] is None

    # The asset is in the response BECAUSE a rejection is the case where the
    # caller most needs to see that nothing happened.
    assert data["asset"]["current_location"]["id"] == here["id"]
    assert _read(client, asset["id"])["current_location"]["id"] == here["id"]


# ─── withdrawal ──────────────────────────────────────────────────────

def test_the_requester_can_withdraw_and_nobody_else_can(
        client, two_locations, approver, capture):
    """§D's third question. Withdrawing is not rejecting and is not shared.

    Two routes rather than one, because they mean different things: a
    requester taking their own request back owes nobody an explanation, and
    an approver refusing one does. The interesting half is the refusal — the
    approver, who may DECIDE this request, may not withdraw it, because
    withdrawing would close it with no reason recorded and the person who
    asked would never learn why.
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-withdraw")
    req = assert_envelope_ok(_raise_move(
        client, asset["id"], there["id"], approver["id"]))["data"]["request"]
    path = f"/api/v1/approvals/{req['id']}"

    mine = assert_envelope_ok(client.get(path))["data"]
    assert mine["can_withdraw"] is True
    theirs = assert_envelope_ok(approver["client"].get(path))["data"]
    assert theirs["can_withdraw"] is False, (
        "the record offers withdrawal to somebody who did not raise it")

    r = client.post(f"{path}/withdraw", json={"reason": "asked the wrong "
                                                        "person"})
    capture("approvals/withdraw", r)
    data = assert_envelope_ok(r)["data"]
    assert data["request"]["state"] == "withdrawn"
    assert data["request"]["decision_reason"] == "asked the wrong person"
    assert data["asset"]["current_location"]["id"] == here["id"]
    assert _read(client, asset["id"])["current_location"]["id"] == here["id"]


def test_somebody_elses_request_cannot_be_withdrawn(
        client, two_locations, approver, approvals_on):
    """403 for a user who is neither the requester nor an administrator.

    **And on this tenant that combination does not exist.** An Odoo
    administrator may withdraw anything — omnipotent by construction, and
    withholding it would be theatre, in the same words `GROUP_SCOPES` uses
    about `base.group_system` — and BOTH users available to this suite are
    administrators: the second person is `admin` itself, and
    `scripts/bootstrap.py::ensure_admin_groups` puts the API credential's own
    user into the operational admin groups.

    So the part that IS provable here is the record's own answer,
    `can_withdraw`, which is what a screen offers a button on and which is
    computed from the requester alone with no administrator escape. The
    route's 403 is asserted when the tenant can produce a caller who is
    neither, and the test says loudly when it cannot rather than passing on
    the 200 and calling it a proof.
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-withdraw-theirs")
    req = assert_envelope_ok(_raise_move(
        approver["client"], asset["id"], there["id"],
        approvals_on.approver_id))["data"]["request"]
    path = f"/api/v1/approvals/{req['id']}"

    # The record, read by somebody who did not raise it, does not offer it.
    not_mine = assert_envelope_ok(client.get(path))["data"]
    assert not_mine["can_withdraw"] is False, (
        "the record offers withdrawal to a caller who did not raise it, so a "
        "screen would show them a button meant for somebody else")
    assert not_mine["requested_by"]["id"] == approver["id"]

    r = client.post(f"{path}/withdraw", json={})
    if r.status_code == 200:
        # The administrator exemption, taken. Assert that it did what it says
        # rather than shrugging, then say why the 403 could not be reached.
        assert assert_envelope_ok(r)["data"]["request"]["state"] == "withdrawn"
        pytest.skip(
            "both users this suite can authenticate as are Odoo "
            "administrators, who may withdraw anybody's request by design. "
            "The 403 needs a third user holding "
            "`myservice_asset_register.group_asset_manager` and NOT "
            "`base.group_system`; there is none on this tenant, and the API "
            "publishes no way to make one.")

    details = assert_envelope_err(r, 403, "forbidden")["error"]["details"]
    assert details["requested_by"]["id"] == approver["id"]
    assert assert_envelope_ok(client.get(path))["data"]["state"] == "pending"

    # Left tidy: an abandoned pending request would block every later test
    # that touches this asset, and the asset is this test's own.
    assert_envelope_ok(approver["client"].post(f"{path}/withdraw", json={}))


# ─── the premise ─────────────────────────────────────────────────────

def test_a_request_whose_premise_broke_cannot_be_approved_in_silence(
        client, two_locations, approver, capture):
    """§D: *a request whose premise no longer holds must not be approvable in
    silence.*

    The world moves between the asking and the agreeing. Here the asset is
    marked missing while a move request waits — a writer OUTSIDE the approval
    rule, deliberately, because that is the case §D is about: the change the
    approver is being asked to agree to is no longer the change that will
    happen.

    Two halves, and the second is the one that would rot: the QUEUE must say
    so before the approver clicks, not only afterwards. `premise_holds` is
    computed fresh on read for exactly that reason — a stored flag would show
    a stale `true` and the screen would be the silent half of the defect.
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-premise")
    req = assert_envelope_ok(_raise_move(
        client, asset["id"], there["id"], approver["id"]))["data"]["request"]
    path = f"/api/v1/approvals/{req['id']}"
    assert assert_envelope_ok(client.get(path))["data"]["premise_holds"] is True

    # The world changes underneath, through a door that is not this one.
    assert_envelope_ok(client.post(
        f"/api/v1/assets/{asset['id']}/mark-missing",
        json={"reason": "not at the desk it was booked to"}))

    # Read as the APPROVER, because that is who the queue screen belongs to
    # and `can_decide` is computed per caller.
    stale = assert_envelope_ok(approver["client"].get(path))["data"]
    assert stale["premise_holds"] is False, (
        "the queue still shows this request as applicable after the asset "
        "changed underneath it — the approver would be told nothing until "
        "after they had agreed")
    assert stale["premise_broken_reason"], (
        "`premise_holds` went false and said nothing about WHAT changed")
    assert stale["can_decide"] is True, (
        "`can_decide` is about WHO may decide, not about whether the request "
        "is still applicable; conflating them would make a broken premise "
        "look like a permissions problem, and a screen greying the button "
        "out would never show the approver what actually changed")

    r = approver["client"].post(f"{path}/approve", json={})
    capture("approvals/premise_broken", r)
    error = assert_envelope_err(r, 409, "conflict")["error"]
    assert error["details"]["premise_broken_reason"] == \
        stale["premise_broken_reason"], (
        "the queue and the refusal give different accounts of what changed")
    assert "missing" in error["details"]["premise_broken_reason"].lower()

    after = _read(client, asset["id"])
    assert after["current_location"]["id"] == here["id"], (
        "a request whose premise had broken was applied anyway")
    assert after["state"] == "missing"
    assert assert_envelope_ok(client.get(path))["data"]["state"] == "pending", (
        "a refused approval closed the request, so the requester cannot see "
        "what happened to it")


# ─── the queue ───────────────────────────────────────────────────────

def _ids(body):
    return [row["id"] for row in body["data"]]


def test_the_queue_filters_actually_filter(
        client, two_locations, approver, approvals_on):
    """`waiting_on_me`, `raised_by_me` and `state` — proved by ABSENCE.

    Asserting that a matching row is present proves nothing: a filter that
    was dropped on the floor returns every row in the register, and every
    matching row is in it. The family of defect handoff 21 closed was exactly
    this — an unrecognised value appended no domain term, so the caller got
    the unfiltered list and read it as an answer.

    So each assertion below names a row that must NOT be there: a request the
    OTHER person raised on themselves, which shares the asset's tenant and
    nothing else with the caller's own.
    """
    here, there = two_locations
    mine_asset = _asset(client, here["id"], "pytest-approvals-queue-mine")
    theirs_asset = _asset(client, here["id"], "pytest-approvals-queue-theirs")

    # Raised by the suite, waiting on the second person.
    mine = assert_envelope_ok(_raise_move(
        client, mine_asset["id"], there["id"],
        approver["id"]))["data"]["request"]
    # Raised by the second person, waiting on the suite. The mirror image,
    # which is what makes every "is absent" below meaningful.
    theirs = assert_envelope_ok(_raise_move(
        approver["client"], theirs_asset["id"], there["id"],
        approvals_on.approver_id))["data"]["request"]

    try:
        raised_by_me = _ids(assert_envelope_ok(client.get(
            "/api/v1/approvals", params={"raised_by_me": "true",
                                         "state": "pending", "limit": 100})))
        assert mine["id"] in raised_by_me
        assert theirs["id"] not in raised_by_me, (
            "`?raised_by_me=true` returned a request the caller did not "
            "raise")

        waiting_on_me = _ids(assert_envelope_ok(client.get(
            "/api/v1/approvals", params={"waiting_on_me": "true",
                                         "state": "pending", "limit": 100})))
        assert theirs["id"] in waiting_on_me
        assert mine["id"] not in waiting_on_me, (
            "`?waiting_on_me=true` returned a request waiting on somebody "
            "else — an approver reading this list cannot tell it from theirs")

        # `false` must mean "do not filter", not "filter on nothing". That is
        # the `?has_coordinates=false` defect (handoff 22) in this endpoint's
        # own shape.
        unfiltered = _ids(assert_envelope_ok(client.get(
            "/api/v1/approvals", params={"waiting_on_me": "false",
                                         "state": "pending", "limit": 100})))
        assert mine["id"] in unfiltered and theirs["id"] in unfiltered, (
            "`?waiting_on_me=false` filtered on nothing rather than not "
            "filtering")

        by_asset = _ids(assert_envelope_ok(client.get(
            "/api/v1/approvals", params={"asset_id": mine_asset["id"],
                                         "limit": 100})))
        assert by_asset == [mine["id"]]

        for state in _STATES:
            rows = assert_envelope_ok(client.get(
                "/api/v1/approvals", params={"state": state, "limit": 100}))
            assert all(row["state"] == state for row in rows["data"]), (
                "`?state=%s` returned rows in other states" % state)
        decided = _ids(assert_envelope_ok(client.get(
            "/api/v1/approvals", params={"state": "approved", "limit": 100})))
        assert mine["id"] not in decided and theirs["id"] not in decided

        change_type = _ids(assert_envelope_ok(client.get(
            "/api/v1/approvals", params={"change_type": "custody",
                                         "state": "pending", "limit": 100})))
        assert mine["id"] not in change_type, (
            "`?change_type=custody` returned a location request")
    finally:
        client.post(f"/api/v1/approvals/{mine['id']}/withdraw", json={})
        approver["client"].post(f"/api/v1/approvals/{theirs['id']}/withdraw",
                                json={})


@pytest.mark.parametrize("param,value", [
    ("state", "nonsense"),
    ("change_type", "nonsense"),
    ("waiting_on_me", "nonsense"),
    ("asset_id", "nonsense"),
])
def test_a_filter_value_the_queue_cannot_read_is_a_400(
        client, approvals_on, param, value):
    """Not the unfiltered list. Handoff 21's rule, on the newest endpoint.

    The refusal must also name the parameter that was actually wrong: the
    first draft of `list_approvals` caught too broadly and reported
    `asset_id` for a fault in `state`, which is worse than no catch at all
    because it sends the caller to fix the wrong thing.
    """
    r = client.get("/api/v1/approvals", params={param: value})
    body = assert_envelope_err(r, 400, "invalid_request")
    assert param in body["error"]["message"], (
        "a bad `%s` was refused with a message naming something else: %r"
        % (param, body["error"]["message"]))


# ─── PATCH, and the asymmetry the app depends on ─────────────────────

def test_patching_a_location_to_a_new_value_is_refused_whole(
        client, two_locations, approvals_on, capture):
    """PATCH is the ambiguous writer, and it is refused rather than converted.

    A PATCH carries a whole object. Turning the location half into a request
    and writing the rest would leave the caller with a half-applied save and
    no way to tell which half — so the WHOLE body is refused, which is the
    contract every write route in this API has published since handoff 31.

    `details.use_instead` is what makes the refusal actionable: the caller is
    told the route that does the job, by id, rather than being left to find
    it.
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-patch-refused")
    before = _read(client, asset["id"])

    r = client.patch(f"/api/v1/assets/{asset['id']}",
                     json={"location_id": there["id"],
                           "notes": "SHOULD-NOT-BE-WRITTEN"})
    capture("approvals/patch_refused", r)
    details = assert_fields_refused(r, "location_id")
    assert details["approval_required"] is True
    assert details["rejected_fields"] == ["location_id"]
    assert "/move" in details["use_instead"]["location_id"]
    assert "notes" in details["writable"], (
        "the refusal does not tell the caller which of its fields WOULD have "
        "been accepted, so it cannot repair the body it sent")

    after = _read(client, asset["id"])
    assert after == before, (
        "the PATCH was refused whole and the writable half landed anyway: %s"
        % {k: (before[k], after[k]) for k in before if before[k] != after[k]})


def test_patching_the_location_it_already_has_still_succeeds(
        client, two_locations, two_employees, approvals_on):
    """NAMING a field is not CHANGING it — and this one is load-bearing.

    The Cadra app's edit form re-sends `location_id` and `custodian_id` on
    every save whether or not anybody touched them. Refusing the mere
    PRESENCE of the key would make saving a note on an asset impossible,
    which is the trap `CLAUDE.md` names in as many words: *a screen that
    PATCHes back the object it GET-ed now fails the day the serializer gains
    a read-only key.*

    So the gate compares values. This is the test that stops somebody
    "tightening" it back to a presence check, which would look like a
    hardening and would break every save in the app.
    """
    here, _ = two_locations
    first, _second = two_employees
    asset = _asset(client, here["id"], "pytest-approvals-patch-unchanged")

    data = assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}",
        json={"location_id": here["id"],
              "notes": "the form re-sent everything"}))["data"]
    assert data["current_location"]["id"] == here["id"]
    assert data["notes"] == "the form re-sent everything"

    # And with the custodian named as well, unchanged and empty — the exact
    # body an edit form sends for an asset nobody holds.
    data = assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}",
        json={"location_id": here["id"], "custodian_id": None,
              "notes": "and again"}))["data"]
    assert data["notes"] == "and again"


def test_clearing_a_custodian_is_not_a_grant_and_is_not_gated(
        client, two_locations, two_employees, approver, approvals_on):
    """**Clearing is not a grant.** Taking an asset off somebody hands it to
    nobody, so it does not need a second person.

    This started as a refusal and was reversed on evidence: the refusal named
    `POST /assets/<id>/transfer-custody`, that route answers *"`to_custodian_id`
    is required"*, and so un-assigning a custodian had become impossible
    through the API after working for the whole life of the register. A
    control whose only effect is to make a legitimate act impossible is not a
    control.

    The asymmetry is the whole point and it is easy to regress in either
    direction, so both halves are here in one test: you may DROP custody, and
    you still may not HAND IT to anybody without approval.
    """
    here, _ = two_locations
    first, _second = two_employees
    asset = _asset(client, here["id"], "pytest-approvals-clearing")

    # Get a custodian onto it the only way there is — through an approval.
    raised = assert_envelope_ok(_raise_custody(
        client, asset["id"], first, approver["id"]))["data"]["request"]
    assert_envelope_ok(approver["client"].post(
        f"/api/v1/approvals/{raised['id']}/approve", json={}))
    assert _read(client, asset["id"])["current_custodian"]["id"] == first

    # CLEARING: allowed, and it really clears.
    cleared = assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}", json={"custodian_id": False}))["data"]
    assert cleared["current_custodian"] is None
    assert _read(client, asset["id"])["current_custodian"] is None, (
        "the API said the custodian was cleared and the record still names "
        "somebody")

    # GRANTING, from empty: still gated. This is the half that makes the
    # clearing allowance safe rather than a bypass.
    details = assert_fields_refused(client.patch(
        f"/api/v1/assets/{asset['id']}", json={"custodian_id": first}),
        "custodian_id")
    assert details["approval_required"] is True
    assert "/transfer-custody" in details["use_instead"]["custodian_id"]
    assert _read(client, asset["id"])["current_custodian"] is None


def test_clearing_a_location_is_not_a_grant_and_is_not_gated(
        client, two_locations, approvals_on):
    """The same rule on the other field, because they are two code paths.

    An asset taken off a location is not put anywhere; 46% of `jaizbankplc`'s
    register had no location when handoff 28 measured it, so "nowhere" is an
    ordinary state of this model rather than an edge case.
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-clearing-location")

    cleared = assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}", json={"location_id": False}))["data"]
    assert cleared["current_location"] is None
    assert _read(client, asset["id"])["current_location"] is None

    # And putting it somewhere — from nowhere — is a grant and is gated.
    details = assert_fields_refused(client.patch(
        f"/api/v1/assets/{asset['id']}", json={"location_id": there["id"]}),
        "location_id")
    assert details["approval_required"] is True
    assert _read(client, asset["id"])["current_location"] is None


# ─── idempotency ─────────────────────────────────────────────────────

def test_replaying_an_approval_under_the_same_key_returns_the_first_answer(
        client, two_locations, approver):
    """An approval is a decision, and a decision is taken once.

    Without the cache the second call would answer 409 *"already approved"* —
    correct, and useless to a client that never learned the first call
    succeeded. The idempotency contract (handoff 18, protected by handoff 31)
    is that a replay is BYTE-EXACT, `meta.request_id` included, and that is
    what makes a retry after a timeout safe here as everywhere else.

    It also proves the approval did not happen twice: one movement row, not
    two, in a model where a spurious row cannot be deleted.
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-idempotent")
    req = assert_envelope_ok(_raise_move(
        client, asset["id"], there["id"], approver["id"]))["data"]["request"]
    path = f"/api/v1/approvals/{req['id']}/approve"
    key = _uniq("pytest-approvals-idem")
    headers = {"X-Idempotency-Key": key}

    first = assert_envelope_ok(approver["client"].post(
        path, json={"reason": "first"}, headers=headers))
    second = assert_envelope_ok(approver["client"].post(
        path, json={"reason": "SHOULD BE IGNORED"}, headers=headers))

    assert second["meta"]["request_id"] == first["meta"]["request_id"], (
        "the replay was processed rather than served from the cache, so a "
        "client retrying after a timeout is told its own approval conflicts "
        "with itself")
    assert second["data"] == first["data"]
    assert first["data"]["request"]["decision_reason"] == "first"

    history = assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset['id']}/history"))["data"]
    moves = [e for e in history["events"]
             if e["type"] == "location_moved" and e["detail"]["from_location"]]
    assert len(moves) == 1, (
        "the replayed approval wrote a second append-only movement row: %r"
        % [e["record"] for e in moves])


# ─── what the queue publishes ────────────────────────────────────────

def test_one_request_carries_everything_a_queue_screen_needs(
        client, two_locations, approver, capture):
    """`GET /approvals/<id>` — the shape, on a real pending request.

    The `_name` copies are asserted because they are what the record keeps
    when a location is renamed or an employee is deleted. A premise stated
    only as a foreign key is a premise that can be emptied from outside the
    record, in a row nobody can edit — so the published answer would silently
    become "was at (nothing)".
    """
    here, there = two_locations
    asset = _asset(client, here["id"], "pytest-approvals-shape")
    raised = assert_envelope_ok(_raise_move(
        client, asset["id"], there["id"], approver["id"],
        reason="test_approvals.shape"))["data"]["request"]

    r = client.get(f"/api/v1/approvals/{raised['id']}")
    capture("approvals/get_by_id", r)
    req = assert_envelope_ok(r)["data"]

    assert req["id"] == raised["id"]
    assert req["state"] in _STATES
    assert req["change_type"] in ("location", "custody")
    assert req["asset"]["id"] == asset["id"]
    assert req["asset_code"] == asset["asset_code"]
    # WHAT IT WAS WHEN ASKED, in both forms.
    assert req["from_location"]["id"] == here["id"]
    assert req["from_location_name"] == here["name"]
    assert req["to_location_name"] == there["name"]
    assert req["from_state"] == "active"
    # WHO, and WHEN.
    assert req["requested_by"]["id"] and req["requested_by_name"]
    assert req["requested_at"]
    assert req["approver"]["id"] == approver["id"]
    # Nothing decided yet, and it says so rather than omitting the keys.
    assert req["decided_by"] is None and req["decided_at"] is None
    assert req["movement_id"] is None and req["custody_id"] is None
    assert req["transfer"] is None

    client.post(f"/api/v1/approvals/{raised['id']}/withdraw", json={})


def test_the_queue_is_newest_first_and_pages(client, approvals_on):
    """A queue is read from the top, and `paginate()` owns the rest.

    `total_estimate` counting the caller's whole domain rather than the
    capped window is handoff 13's property, inherited here only because this
    route goes through the shared helper — which is worth one assertion,
    because a route that hand-rolled its own paging would look identical
    until somebody crossed the cap.
    """
    body = assert_envelope_ok(client.get("/api/v1/approvals",
                                         params={"limit": 5}))
    ids = _ids(body)
    assert ids == sorted(ids, reverse=True), (
        "the approval queue is not newest-first")
    assert body["pagination"]["total_estimate"] >= len(ids)
    if not body["pagination"]["next_cursor"]:
        return
    second = assert_envelope_ok(client.get(
        "/api/v1/approvals",
        params={"limit": 5, "cursor": body["pagination"]["next_cursor"]}))
    assert not set(ids) & set(_ids(second)), "page two repeats page one"


def test_an_approval_request_that_does_not_exist_is_a_404(client,
                                                          approvals_on):
    for suffix in ("", "/approve", "/reject", "/withdraw"):
        r = (client.get if not suffix else client.post)(
            "/api/v1/approvals/999999999%s" % suffix,
            **({} if not suffix else {"json": {"reason": "x"}}))
        assert_envelope_err(r, 404, "not_found")
