"""Ask someone else — handoff 45 §1, rulings G.1(a) and G.1(b), over HTTP.

WHAT THIS FILE IS FOR
---------------------
Handoff 43 measured a request left waiting on an approver whose account had
been deactivated, with nothing on the row saying so. Two rulings:

* **G.1(a)** — the queue row publishes `approver.active`, so the screen can
  say *"the approver cannot sign in"*.
* **G.1(b)** — deactivation is NEVER blocked; a stranded request is fixed
  forward by re-pointing it at somebody else, as an act with a name and a
  time on it: `POST /api/v1/approvals/<id>/renominate`, and an append-only
  row published in the request's `renominations`.

The rule is on the model (`myservice_asset_register/tests/test_renomination.py`
holds it there, including under `sudo()`). What is proved here is the DOOR:
the contract, the statuses, the body gate, and that every refusal leaves the
request exactly as it was — read back, not trusted from the status code.

WHO IS WHO
----------
The suite's own credential RAISES every request here, because who may
re-point a request is a question about the REQUESTER. The people it asks are
created for this module over `POST /api/v1/users` (handoff 43) with
`send_invitation: false`: two Asset Managers, one Asset User who cannot
approve, and — per test that needs one — a manager whose account is then
deactivated. **None of them can be deleted** (`res.users.unlink` is refused
over the API by design); each is named `pytest-renominate-*`, carries
`is_test_fixture` on its partner because the suite's credential is a test
credential, and is deactivated when the module finishes.

The 403 — a caller who is neither the requester nor an administrator — needs
a request raised by somebody else. The only other person this suite can sign
in as is `CADRA_SECOND_PERSON_LOGIN` (default `admin`); the suite asks it to
raise one and then asks the suite's own `can_renominate`. **If the suite's
user is itself an administrator on the tenant, the 403 cannot be proved**,
and the test skips saying so — the model test proves the refusal in-registry
either way.
"""
import time
import uuid

import pytest

from .conftest import (assert_envelope_err, assert_envelope_ok,
                       assert_fields_refused)

USERS = "/api/v1/users"
DEACTIVATE = "/api/v1/users/{id}/deactivate"
APPROVAL = "/api/v1/approvals/{id}"
RENOMINATE = "/api/v1/approvals/{id}/renominate"
WITHDRAW = "/api/v1/approvals/{id}/withdraw"

#: The sentence the model refuses a caller with who may not re-point.
NOT_YOURS = "who raised this request, or an administrator"


def _uniq(prefix):
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


# ─── the cast ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def approvals_on(approval_settings):
    if not approval_settings["required"]:
        pytest.skip(
            "this tenant has `cadra.approval.required` off, so a move takes "
            "one person and no approval request is ever raised to re-point")
    return True


@pytest.fixture(scope="module")
def people(client, admin_scope, approvals_on):
    """Create people for this module, and deactivate them afterwards.

    `make(roles)` → the user row. Every account is deactivated at teardown
    whatever the tests did, so a re-run leaves no active fixtures behind.
    """
    made = []

    def make(roles):
        marker = _uniq("pytest-renominate")
        r = client.post(USERS, json={
            "name": marker, "email": "%s@example.invalid" % marker,
            "roles": list(roles), "send_invitation": False})
        row = assert_envelope_ok(r, 201)["data"]
        made.append(row["id"])
        return row

    yield make
    for uid in made:
        row = client.get(f"{USERS}/{uid}").json().get("data") or {}
        if row.get("active"):
            client.post(DEACTIVATE.format(id=uid))


@pytest.fixture(scope="module")
def managers(people):
    """Two people who could have made the change themselves."""
    return people(["asset_manager"]), people(["asset_manager"])


@pytest.fixture(scope="module")
def cannot_approve(people):
    """An Asset User: may see the register, may not approve a move."""
    return people(["asset_user"])


@pytest.fixture(scope="module")
def two_locations(client):
    made = []
    for n in ("a", "b"):
        made.append(assert_envelope_ok(client.post("/api/v1/locations", json={
            "name": _uniq(f"pytest-renominate-loc-{n}")}), 201)["data"])
    return made


def _raise(raiser, two_locations, approver_id):
    """A pending move request raised by `raiser`, naming `approver_id`."""
    here, there = two_locations
    asset = assert_envelope_ok(raiser.post("/api/v1/assets", json={
        "name": _uniq("pytest-renominate-asset"), "category_id": 1,
        "location_id": here["id"]}), 201)["data"]
    r = raiser.post(f"/api/v1/assets/{asset['id']}/move", json={
        "to_location_id": there["id"], "approver_id": approver_id,
        "reason": "test_approvals_renomination"})
    data = assert_envelope_ok(r)["data"]
    assert data["pending_approval"] is True, data
    # `/move` answers a SUBSET of the request (no `asset`, no premise); the
    # asset's id is carried alongside for the tests that read it back.
    return dict(data["request"], asset_id=data["asset"]["id"])


def _get(client, request_id):
    return assert_envelope_ok(client.get(APPROVAL.format(id=request_id)))["data"]


@pytest.fixture
def pending(client, two_locations, managers):
    """A pending request raised by the suite naming the first manager —
    withdrawn afterwards if it is still pending, so the asset is free."""
    raised = []

    def make(approver_id=None):
        req = _raise(client, two_locations, approver_id or managers[0]["id"])
        raised.append(req["id"])
        return req

    yield make
    for rid in raised:
        row = client.get(APPROVAL.format(id=rid)).json().get("data") or {}
        if row.get("state") == "pending":
            client.post(WITHDRAW.format(id=rid), json={})


def _unchanged(client, req_id, approver_id):
    """A refusal wrote nothing: same approver, no re-nomination row."""
    row = _get(client, req_id)
    assert row["state"] == "pending"
    assert row["approver"]["id"] == approver_id, (
        "a refused re-nomination moved the approver anyway")
    assert row["renominations"] == [], (
        "a refused re-nomination left a row in a table nobody can delete "
        "from: %s" % row["renominations"])


# ─── G.1(a): the row says whether the approver can sign in ───────────

def test_the_row_publishes_whether_the_approver_can_sign_in(
        client, pending, managers):
    req = pending()
    row = _get(client, req["id"])
    assert row["approver"]["id"] == managers[0]["id"]
    assert row["approver"]["active"] is True
    assert set(row["approver"]) == {"id", "name", "active"}, (
        "the approver ref is `{id, name}` plus `active` — additive, nothing "
        "renamed")
    assert row["renominations"] == []
    assert row["can_renominate"] is True, (
        "the suite raised this request, so it may re-point it")


# ─── G.1(a) + G.1(b): the stranded request, end to end ───────────────

def test_a_stranded_request_is_re_pointed_and_the_record_names_who(
        client, people, pending, managers, suite_user, two_locations,
        capture):
    """The whole ruling in one flow. The approver is deactivated with the
    request pending — and the deactivation is NOT refused, because it is
    never blocked. The row then says the approver cannot sign in; the
    requester re-points it; and the record names who did it, when, from whom,
    to whom and why."""
    leaver = people(["asset_manager"])
    req = pending(leaver["id"])

    off = client.post(DEACTIVATE.format(id=leaver["id"]))
    assert_envelope_ok(off)            # never blocked by the pending request
    row = _get(client, req["id"])
    assert row["state"] == "pending"
    assert row["approver"] == {"id": leaver["id"], "name": leaver["name"],
                               "active": False}, row["approver"]
    assert row["can_renominate"] is True

    reason = "The approver's account is deactivated — %s" % uuid.uuid4().hex[:6]
    r = client.post(RENOMINATE.format(id=req["id"]), json={
        "approver_id": managers[1]["id"], "reason": reason})
    capture("approvals/renominate", r)
    data = assert_envelope_ok(r)["data"]

    after = data["request"]
    assert after["state"] == "pending", "re-pointing is not a decision"
    assert after["approver"]["id"] == managers[1]["id"]
    assert after["approver"]["active"] is True
    assert len(after["renominations"]) == 1
    entry = after["renominations"][0]
    assert entry == data["renomination"]
    assert entry["from"]["id"] == leaver["id"]
    assert entry["from"]["name"], "the row keeps the name it was written with"
    assert entry["to"]["id"] == managers[1]["id"]
    assert entry["by"]["id"] == suite_user["id"], (
        "who re-pointed it is the caller's own user, from the token")
    assert entry["at"], "a re-nomination with no time on it"
    assert entry["reason"] == reason

    # Read back, not trusted from the response.
    assert _get(client, req["id"])["renominations"] == after["renominations"]
    # And the asset did not move.
    asset = assert_envelope_ok(
        client.get(f"/api/v1/assets/{req['asset_id']}"))["data"]
    assert asset["current_location"]["id"] == two_locations[0]["id"]


def test_each_re_pointing_is_kept_oldest_first(client, pending, managers):
    req = pending()
    first, second = managers
    path = RENOMINATE.format(id=req["id"])
    assert_envelope_ok(client.post(path, json={
        "approver_id": second["id"], "reason": "one"}))
    data = assert_envelope_ok(client.post(path, json={
        "approver_id": first["id"], "reason": "two"}))["data"]
    trail = data["request"]["renominations"]
    assert [(e["from"]["id"], e["to"]["id"], e["reason"]) for e in trail] == [
        (first["id"], second["id"], "one"),
        (second["id"], first["id"], "two"),
    ]


# ─── the body gate ───────────────────────────────────────────────────

def test_a_key_the_route_does_not_read_is_refused_and_nothing_is_written(
        client, pending, managers):
    req = pending()
    r = client.post(RENOMINATE.format(id=req["id"]), json={
        "approver_id": managers[1]["id"], "reason": "x",
        "renominated_by": 1})
    details = assert_fields_refused(r, "renominated_by")
    assert details["writable"] == ["approver_id", "reason"]
    _unchanged(client, req["id"], managers[0]["id"])


@pytest.mark.parametrize("body", [
    {}, {"reason": ""}, {"reason": "   "}, {"reason": None},
], ids=["absent", "empty", "blank", "null"])
def test_a_reason_is_required(client, pending, managers, body):
    req = pending()
    payload = dict(body, approver_id=managers[1]["id"])
    r = client.post(RENOMINATE.format(id=req["id"]), json=payload)
    err = assert_envelope_err(r, 400, "invalid_request")["error"]
    assert "`reason` is required" in err["message"]
    _unchanged(client, req["id"], managers[0]["id"])


def test_an_approver_is_required_and_candidates_are_offered(
        client, pending, managers, suite_user):
    req = pending()
    r = client.post(RENOMINATE.format(id=req["id"]), json={"reason": "x"})
    err = assert_envelope_err(r, 400, "invalid_request")["error"]
    assert "`approver_id` is required" in err["message"]
    offered = {u["id"] for u in err["details"]["approvers"]}
    assert suite_user["id"] not in offered, "offered the requester"
    assert managers[0]["id"] not in offered, "offered the person already asked"
    _unchanged(client, req["id"], managers[0]["id"])


# ─── who may be asked ────────────────────────────────────────────────

def test_the_person_already_asked_is_refused(client, pending, managers):
    req = pending()
    r = client.post(RENOMINATE.format(id=req["id"]), json={
        "approver_id": managers[0]["id"], "reason": "x"})
    err = assert_envelope_err(r, 400, "invalid_request")["error"]
    assert "already the person being asked" in err["message"]
    _unchanged(client, req["id"], managers[0]["id"])


def test_the_requester_cannot_be_asked(client, pending, managers, suite_user):
    req = pending()
    r = client.post(RENOMINATE.format(id=req["id"]), json={
        "approver_id": suite_user["id"], "reason": "x"})
    err = assert_envelope_err(r, 400, "invalid_request")["error"]
    assert "person who raised it" in err["message"]
    _unchanged(client, req["id"], managers[0]["id"])


def test_somebody_who_could_not_approve_is_refused(
        client, pending, managers, cannot_approve):
    req = pending()
    r = client.post(RENOMINATE.format(id=req["id"]), json={
        "approver_id": cannot_approve["id"], "reason": "x"})
    err = assert_envelope_err(r, 400, "invalid_request")["error"]
    assert "could have made the change themselves" in err["message"]
    _unchanged(client, req["id"], managers[0]["id"])


def test_a_deactivated_person_is_refused(client, people, pending, managers):
    """Re-pointing a request AT somebody who cannot sign in would recreate
    the defect the route exists to fix."""
    gone = people(["asset_manager"])
    assert_envelope_ok(client.post(DEACTIVATE.format(id=gone["id"])))
    req = pending()
    r = client.post(RENOMINATE.format(id=req["id"]), json={
        "approver_id": gone["id"], "reason": "x"})
    err = assert_envelope_err(r, 400, "invalid_request")["error"]
    assert "cannot be asked: their account is deactivated" in err["message"]
    _unchanged(client, req["id"], managers[0]["id"])


def test_an_unknown_person_is_404(client, pending, managers):
    req = pending()
    r = client.post(RENOMINATE.format(id=req["id"]), json={
        "approver_id": 2_000_000_000, "reason": "x"})
    assert_envelope_err(r, 404, "not_found")
    _unchanged(client, req["id"], managers[0]["id"])


def test_an_unknown_request_is_404(client, managers):
    r = client.post(RENOMINATE.format(id=2_000_000_000), json={
        "approver_id": managers[1]["id"], "reason": "x"})
    assert_envelope_err(r, 404, "not_found")


# ─── what state, and whose ───────────────────────────────────────────

def test_a_decided_request_is_409(client, pending, managers):
    req = pending()
    assert_envelope_ok(client.post(WITHDRAW.format(id=req["id"]), json={}))
    assert _get(client, req["id"])["can_renominate"] is False
    r = client.post(RENOMINATE.format(id=req["id"]), json={
        "approver_id": managers[1]["id"], "reason": "x"})
    err = assert_envelope_err(r, 409, "conflict")["error"]
    assert "withdrawn" in err["message"]
    row = _get(client, req["id"])
    assert row["approver"]["id"] == managers[0]["id"]
    assert row["renominations"] == []


def test_somebody_elses_request_is_403_unless_you_administer(
        client, second_person, two_locations, managers, suite_user):
    """The requester or an administrator — nobody else.

    The request is raised by the second person, naming the suite's own
    user, which is an Asset Manager. The suite then tries to re-point it.
    Whether that is a 403 depends on whether the suite's user is an Odoo
    administrator on this tenant (handoff 44 stopped bootstrap granting it;
    a tenant bootstrapped before may still carry it) — which the route
    itself publishes as `can_renominate`, so the test reads that first and
    asserts the status that agrees with it.
    """
    if second_person.other is None:
        pytest.skip("this session could not sign a second person in, so no "
                    "request raised by somebody else exists to re-point")
    other = second_person.other
    req = _raise(other["client"], two_locations, suite_user["id"])
    try:
        theirs = _get(other["client"], req["id"])
        assert theirs["can_renominate"] is True, (
            "the person who raised it is not offered re-nomination")
        mine = _get(client, req["id"])
        if mine["can_renominate"]:
            pytest.skip(
                "the suite's own user (%s, id %s) is an administrator on this "
                "tenant, so it MAY re-point anybody's request and the 403 "
                "cannot be proved here; 2 of 2 users this suite can sign in "
                "as are administrators. Proved in-registry by "
                "test_renomination.TestWhoMayRenominate."
                % (suite_user.get("login"), suite_user["id"]))
        r = client.post(RENOMINATE.format(id=req["id"]), json={
            "approver_id": managers[0]["id"], "reason": "not mine"})
        err = assert_envelope_err(r, 403, "forbidden")["error"]
        assert NOT_YOURS in err["message"]
        _unchanged(client, req["id"], suite_user["id"])
    finally:
        other["client"].post(WITHDRAW.format(id=req["id"]), json={})


# ─── published ───────────────────────────────────────────────────────

def test_the_route_is_published_and_scoped_like_raising_a_request(client):
    spec = client.get("/api/v1/openapi.json").json()
    op = spec["paths"]["/api/v1/approvals/{id}/renominate"]["post"]
    assert op["x-cadra-scopes"] == ["assets:write"], op.get("x-cadra-scopes")
    names = [p["name"] for p in op.get("parameters", [])]
    assert "X-Idempotency-Key" in names, names
    schema = op["requestBody"]["content"]["application/json"]["schema"]
    assert set(schema["properties"]) == {"approver_id", "reason"}
    assert set(schema["required"]) == {"approver_id", "reason"}
    for status in ("403", "404", "409"):
        assert status in op["responses"], (status, sorted(op["responses"]))
