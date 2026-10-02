"""The person, and the door — `POST /users`, `/users/<id>/invite`,
`/deactivate`, `/reactivate`. Handoff 43 §1, over HTTP.

Driven against whichever tenant `CADRA_API_BASE` names, as the suite's own
`admin` credential. What is proved here is the CONTRACT: a person created
with roles, the body gate, the four refusals in words, the replay under an
idempotency key, deactivation and reactivation on the row, and the access
record naming the actor. The in-registry suite
(`myservice_api/tests/test_user_lifecycle.py`) holds what needs the inside
— the letter's contents, a live token refused after deactivation, the
label on the partner.

**Whether a letter can be SENT is a fact about the tenant, not the code.**
A tenant with no outgoing mail answers `500 server_misconfigured` to a
create that asks for the invitation, and creates nothing. So every account
this suite creates is created with `send_invitation: false`, and the one
test that sends asserts BOTH honest outcomes: a letter went (row moved to
`outstanding`), or the refusal came and the row did not move. Which one a
run took is in its assertion message.

**Nothing created here can be deleted** (`res.users.unlink` is refused over
the API by design, handoff 42). Every account is created under a
`pytest-` name and address, carries `is_test_fixture` on its partner
because the suite's credential is a test credential (handoff 26), and is
DEACTIVATED in a `finally`, so a re-run does not leave active fixtures.
"""
import datetime
import uuid

import pytest

from .conftest import assert_envelope_ok, assert_envelope_err, assert_fields_refused

USERS = "/api/v1/users"
USER = "/api/v1/users/{id}"
INVITE = "/api/v1/users/{id}/invite"
DEACTIVATE = "/api/v1/users/{id}/deactivate"
REACTIVATE = "/api/v1/users/{id}/reactivate"
ACCESS = "/api/v1/reports/access-changes"

ONLY_THESE = "Over the API only these roles can be granted or removed"
OWN_ACCOUNT = "You cannot deactivate your own account"

INVITATION_STATES = {"never", "outstanding", "expired", "redeemed", "cancelled"}


def _marker():
    return "pytest-person-%s" % uuid.uuid4().hex[:10]


def _person(marker):
    return {"name": marker, "email": "%s@example.invalid" % marker}


def _row(client, user_id):
    return assert_envelope_ok(client.get(USER.format(id=user_id)))["data"]


def _keys(roles):
    return [r["key"] for r in roles]


def _by_login(client, login):
    body = assert_envelope_ok(client.get(USERS, params={"q": login, "limit": 100}))
    return [r for r in body["data"] if r["login"] == login]


@pytest.fixture
def created(client, admin_scope):
    """Create a person with no letter; deactivate them afterwards whatever
    the test did."""
    made = []

    def make(roles=(), **extra):
        body = dict(_person(_marker()), roles=list(roles), send_invitation=False)
        body.update(extra)
        r = client.post(USERS, json=body)
        row = assert_envelope_ok(r, 201)["data"]
        made.append(row["id"])
        return row

    yield make
    for uid in made:
        row = client.get(USER.format(id=uid)).json().get("data") or {}
        if row.get("active"):
            client.post(DEACTIVATE.format(id=uid))


# ─── the create ──────────────────────────────────────────────────────

def test_a_person_is_created_with_the_roles_asked_and_nothing_else(client, created):
    row = created(roles=["asset_user", "tag_issuing_unit"])
    assert row["kind"] == "person"
    assert row["api_client"] is None
    assert row["active"] is True
    assert row["login"] == row["email"]
    assert _keys(row["roles_direct"]) == ["asset_user", "tag_issuing_unit"]
    assert set(_keys(row["roles_effective"])) >= {"asset_user", "tag_issuing_unit"}
    assert row["scopes_source"] == "roles"
    assert "tagging:write" in row["scopes"]
    assert row["last_login_at"] is None
    inv = row["invitation"]
    assert set(inv) == {"state", "sent_at", "sent_by", "sends", "expires_at"}
    assert inv["state"] == "never" and inv["sends"] == 0 and inv["sent_at"] is None
    # and the list sees them
    assert [r["id"] for r in _by_login(client, row["login"])] == [row["id"]]


def test_the_email_is_the_login_lowercased_and_the_name_is_kept(client, created):
    marker = _marker()
    row = created(name="  %s  " % marker, email="%s@Example.INVALID" % marker.upper())
    assert row["name"] == marker
    assert row["login"] == "%s@example.invalid" % marker
    assert row["email"] == "%s@Example.INVALID" % marker.upper()


def test_a_create_with_no_roles_holds_no_cadra_role(client, created):
    row = created()
    assert row["roles_direct"] == []
    assert row["scopes"] == []


def test_the_body_gate(client, admin_scope):
    marker = _marker()
    r = client.post(USERS, json=dict(_person(marker), password="hunter2", send_invitation=False))
    details = assert_fields_refused(r, "password")
    assert details["writable"] == ["email", "name", "roles", "send_invitation"]
    assert _by_login(client, "%s@example.invalid" % marker) == [], "a refused create created"

    r = client.post(USERS, json={"name": marker, "email": "no-at-sign", "send_invitation": False})
    err = assert_envelope_err(r, 400, "invalid_request")["error"]
    assert err["details"]["field"] == "email"

    r = client.post(USERS, json={"email": "%s@example.invalid" % marker, "send_invitation": False})
    err = assert_envelope_err(r, 400, "invalid_request")["error"]
    assert err["details"]["field"] == "name"

    r = client.post(USERS, json=dict(_person(marker), roles=["not_a_role"], send_invitation=False))
    err = assert_envelope_err(r, 400, "invalid_request")["error"]
    assert err["details"]["rejected_values"] == ["not_a_role"]
    assert "asset_user" in err["details"]["allowed_values"]

    r = client.post(USERS, json=dict(_person(marker), send_invitation="yes"))
    err = assert_envelope_err(r, 400, "invalid_request")["error"]
    assert err["details"]["field"] == "send_invitation"
    assert _by_login(client, "%s@example.invalid" % marker) == []


def test_a_role_the_model_refuses_creates_nothing(client, admin_scope):
    marker = _marker()
    r = client.post(USERS, json=dict(_person(marker), roles=["asset_user", "system"],
                                     send_invitation=False))
    err = assert_envelope_err(r, 403, "forbidden")["error"]
    assert ONLY_THESE in err["message"]
    assert _by_login(client, "%s@example.invalid" % marker) == [], \
        "the model refused the role and the account was created anyway"


def test_an_address_already_held_is_a_conflict_naming_the_account(client, created):
    first = created()
    r = client.post(USERS, json={"name": "Somebody Else", "email": first["email"].upper(),
                                 "send_invitation": False})
    err = assert_envelope_err(r, 409, "conflict")["error"]
    assert err["details"]["user_id"] == first["id"]
    assert err["details"]["active"] is True
    assert "It is active." in err["message"]
    # deactivated: the sentence changes, the conflict stays
    assert_envelope_ok(client.post(DEACTIVATE.format(id=first["id"])))
    r = client.post(USERS, json={"name": "Somebody Else", "email": first["email"],
                                 "send_invitation": False})
    err = assert_envelope_err(r, 409, "conflict")["error"]
    assert err["details"]["active"] is False
    assert "reactivate it" in err["message"]


def test_a_replay_under_the_same_key_answers_the_same_account(client, created):
    marker = _marker()
    key = "pytest-43-%s" % uuid.uuid4().hex
    body = dict(_person(marker), roles=["asset_user"], send_invitation=False)
    r1 = client.post(USERS, json=body, headers={"X-Idempotency-Key": key})
    row = assert_envelope_ok(r1, 201)["data"]
    try:
        r2 = client.post(USERS, json=body, headers={"X-Idempotency-Key": key})
        assert r2.status_code == 201, r2.text
        assert r2.json()["data"]["id"] == row["id"]
        assert r2.json()["meta"]["request_id"] == r1.json()["meta"]["request_id"]
        assert len(_by_login(client, row["login"])) == 1, "the replay created a second account"
    finally:
        client.post(DEACTIVATE.format(id=row["id"]))


def test_the_record_names_the_suite_user_as_the_actor(client, created, suite_user):
    today = datetime.date.today()
    row = created(roles=["asset_user"])
    frm = (today - datetime.timedelta(days=1)).isoformat()
    to = (today + datetime.timedelta(days=1)).isoformat()
    events, cursor = [], None
    for _ in range(50):
        params = {"from": frm, "to": to, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        body = assert_envelope_ok(client.get(ACCESS, params=params))
        events += body["data"]["events"]
        cursor = (body.get("pagination") or {}).get("next_cursor")
        if not cursor:
            break
    mine = [e for e in events if e.get("login") == row["login"] and e["event"] == "granted"]
    assert mine, "no `granted` event for the person this test created (of %d events)" % len(events)
    for e in mine:
        assert e["attributable"] is True
        assert e["actor"]["name"] == suite_user["name"], e


# ─── the letter ──────────────────────────────────────────────────────

def test_an_invitation_either_goes_or_is_refused_with_the_row_unmoved(client, created):
    row = created()
    r = client.post(INVITE.format(id=row["id"]))
    if r.status_code == 200:
        inv = r.json()["data"]["invitation"]
        assert inv["state"] == "outstanding", inv
        assert inv["sends"] == 1
        assert inv["sent_at"] and inv["expires_at"] and inv["expires_at"] > inv["sent_at"]
        assert inv["sent_by"]["id"] != 1
        # a re-send is a fresh send
        again = assert_envelope_ok(client.post(INVITE.format(id=row["id"])))["data"]["invitation"]
        assert again["sends"] == 2 and again["state"] == "outstanding"
    else:
        err = assert_envelope_err(r, 500, "server_misconfigured")["error"]
        assert "could not be sent" in err["message"], err
        after = _row(client, row["id"])["invitation"]
        assert after == row["invitation"], "a refused send moved the row: %r" % (after,)


def test_an_invitation_to_a_deactivated_person_is_refused(client, created):
    row = created()
    assert_envelope_ok(client.post(DEACTIVATE.format(id=row["id"])))
    err = assert_envelope_err(client.post(INVITE.format(id=row["id"])), 409, "conflict")["error"]
    assert "Reactivate" in err["message"]


def test_the_action_routes_accept_no_body_key(client, created):
    row = created()
    for path in (INVITE, DEACTIVATE, REACTIVATE):
        r = client.post(path.format(id=row["id"]), json={"reason": "left the service"})
        details = assert_fields_refused(r, "reason")
        assert details["writable"] == []
    assert _row(client, row["id"])["active"] is True


# ─── deactivate, reactivate ──────────────────────────────────────────

def test_deactivate_then_reactivate_on_the_row(client, created):
    row = created(roles=["asset_user"])
    off = assert_envelope_ok(client.post(DEACTIVATE.format(id=row["id"])))["data"]
    assert off["active"] is False
    assert _keys(off["roles_direct"]) == ["asset_user"], "deactivation touched the roles"
    assert _row(client, row["id"])["active"] is False
    assert [r["active"] for r in _by_login(client, row["login"])] == [False], \
        "the list stopped showing a deactivated account"
    err = assert_envelope_err(client.post(DEACTIVATE.format(id=row["id"])), 409, "conflict")["error"]
    assert "already deactivated" in err["message"]

    on = assert_envelope_ok(client.post(REACTIVATE.format(id=row["id"])))["data"]
    assert on["active"] is True
    err = assert_envelope_err(client.post(REACTIVATE.format(id=row["id"])), 409, "conflict")["error"]
    assert "already active" in err["message"]


def test_you_cannot_deactivate_yourself(client, admin_scope, suite_user):
    err = assert_envelope_err(client.post(DEACTIVATE.format(id=suite_user["id"])), 403, "forbidden")["error"]
    assert OWN_ACCOUNT in err["message"]
    assert _row(client, suite_user["id"])["active"] is True


def test_the_user_behind_another_credential_is_managed_with_the_credential(client, admin_scope, suite_user):
    rows = assert_envelope_ok(client.get(USERS, params={"is_api_client": "true", "limit": 100}))["data"]
    others = [r for r in rows if r["id"] != suite_user["id"]]
    if not others:
        pytest.skip("this tenant has %d API credential(s) and the only one is this suite's"
                    % len(rows))
    target = others[0]
    for path, status in ((DEACTIVATE, 400), (REACTIVATE, 400), (INVITE, 400)):
        err = assert_envelope_err(client.post(path.format(id=target["id"])), status, "invalid_request")["error"]
        assert target["api_client"]["client_id"] in err["message"]
    assert _row(client, target["id"])["active"] == target["active"]


def test_an_unknown_account_is_404_on_all_four(client, admin_scope):
    for path in (INVITE, DEACTIVATE, REACTIVATE):
        assert_envelope_err(client.post(path.format(id=999999999)), 404, "not_found")
    assert_envelope_err(client.get(USER.format(id=999999999)), 404, "not_found")


def test_every_row_publishes_an_invitation_block(client, admin_scope):
    rows = assert_envelope_ok(client.get(USERS, params={"limit": 100}))["data"]
    assert rows
    for r in rows:
        inv = r["invitation"]
        assert inv["state"] in INVITATION_STATES, r["login"]
        assert isinstance(inv["sends"], int)
        if r["kind"] == "api_credential":
            assert inv["state"] == "never", "a credential was invited: %s" % r["login"]
        if inv["state"] == "never":
            assert inv["sent_at"] is None and inv["sends"] == 0
        else:
            assert inv["sent_at"] is not None and inv["sends"] >= 1


# ─── publication ─────────────────────────────────────────────────────

def test_the_four_routes_are_published_admin_scoped_and_idempotent(client):
    spec = client.get("/api/v1/openapi.json").json()
    expected = {
        "/api/v1/users": "post",
        "/api/v1/users/{user_id}/invite": "post",
        "/api/v1/users/{user_id}/deactivate": "post",
        "/api/v1/users/{user_id}/reactivate": "post",
    }
    for path, method in expected.items():
        op = spec["paths"][path][method]
        assert op["x-cadra-scopes"] == ["admin"], (path, op.get("x-cadra-scopes"))
        names = [p["name"] for p in op.get("parameters", [])]
        assert "X-Idempotency-Key" in names, (path, names)
    create = spec["paths"]["/api/v1/users"]["post"]
    props = create["requestBody"]["content"]["application/json"]["schema"]["properties"]
    assert set(props) == {"name", "email", "roles", "send_invitation"}
    assert "409" in create["responses"] and "403" in create["responses"]
    user_schema = spec["components"]["schemas"]["User"]
    assert set(user_schema["properties"]["invitation"]["properties"]) == {
        "state", "sent_at", "sent_by", "sends", "expires_at"}
    assert set(user_schema["properties"]["invitation"]["properties"]["state"]["enum"]) == INVITATION_STATES
