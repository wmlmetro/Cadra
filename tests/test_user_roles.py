"""`POST /users/<id>/roles` — the grant, and the refusal. Handoff 42 §4.

The one writer of membership on the API, driven against whichever tenant
`CADRA_API_BASE` names, as the suite's own `admin` credential. What is
proved here is the CONTRACT: the preview, the applied change, the record it
leaves, the two refusals in the model's own sentences, the 400s for a body
the route does not accept, and the replay under an idempotency key. The
in-registry suite (`myservice_api/tests/test_access_guard.py`) drives the
doors this route never opens.

**Every test restores what it changed**, in a `finally`, and every test that
needs a particular account SKIPS naming the denominator it counted when the
tenant has none — `h41_manager` (direct `[asset_manager]`) is the probe
handoff 41 part A provisioned on `test19`.

Two things to know before reading a failure:

* `roles` is the FULL set of DIRECT roles, not a delta. `["asset_manager",
  "tag_issuing_unit"]` on a manager grants one role; `["asset_manager"]`
  afterwards revokes it.
* The refusals are the model's. A `system` key is VALID at the route and
  reaches the write on purpose, so the 403 the caller reads is the sentence
  `models/access_guard.py` raises, verbatim.
"""
import datetime
import uuid

import pytest

from .conftest import (assert_envelope_ok, assert_envelope_err,
                       assert_fields_refused, lagos_today)

ROLES = "/api/v1/roles"
USERS = "/api/v1/users"
USER = "/api/v1/users/{id}"
SET_ROLES = "/api/v1/users/{id}/roles"
SET_ROLES_SPEC_PATH = "/api/v1/users/{user_id}/roles"
ACCESS = "/api/v1/reports/access-changes"

#: The role the grant/record/revert tests add to the manager, and the scope
#: only it brings. It was the Tag-Issuing Unit (`tagging:write`) until
#: handoff 58 §5 seeded the role exclusions: the Asset Manager implies the
#: Asset Officer, and *Asset Officer + Tag-Issuing Unit* is now a forbidden
#: pair, so that grant is refused 403 — correctly. The Auditor is excluded
#: with nothing and is the one source of `export:read` (handoff 50), so the
#: change is still visible in the scopes and on the access record.
SECOND_ROLE = "auditor"
SECOND_ROLE_SCOPE = "export:read"
SECOND_ROLE_GROUP_WORD = "Audit"

MANAGER_LOGIN = "h41_manager"

ONLY_THESE = "Over the API only these roles can be granted or removed"
NOBODY_THEMSELVES = "Nobody grants themselves a role"

#: The five, by key. Pinned here rather than read off `/roles`, for the
#: reason `EXPECTED_AUDITOR_SCOPES` is pinned: a new grantable role is a
#: decision with a name on it (handoff 42 §2) and must FAIL a test. The
#: fifth is exactly such a decision: handoff 47 ruling 3 created the Asset
#: Officer — the role between reading the register and running it.
GRANTABLE = frozenset({"asset_user", "asset_officer", "asset_manager",
                       "tag_issuing_unit", "auditor",
                       # Handoff 57 §2e: the five receipt-gate roles, named
                       # by the handoff (kept by 58).
                       "iad_vfm_officer", "iad_vfm_approver",
                       "asset_controller", "register_maker",
                       "register_checker"})


# ─── helpers ─────────────────────────────────────────────────────────

def _keys(roles):
    return [r["key"] for r in roles]


def _by_login(client, login):
    """The account row whose login is exactly `login`, or None — with the
    count of what `?q=` matched, for the skip message."""
    body = assert_envelope_ok(client.get(USERS, params={"q": login, "limit": 100}))
    rows = body["data"]
    for row in rows:
        if row["login"] == login:
            return row, len(rows)
    return None, len(rows)


def _row(client, user_id):
    return assert_envelope_ok(client.get(USER.format(id=user_id)))["data"]


def _set(client, user_id, roles, dry_run=None, headers=None):
    body = {"roles": roles}
    if dry_run is not None:
        body["dry_run"] = dry_run
    return client.post(SET_ROLES.format(id=user_id), json=body,
                       headers=headers or {})


def _restore(client, user_id, keys):
    body = assert_envelope_ok(_set(client, user_id, keys))
    assert _keys(body["data"]["after"]["roles_direct"]) == keys, (
        "restore did not restore: %s" % body["data"]["after"])


def _access_events(client, login):
    """Every membership event for `login` from yesterday to today, walking
    the report's cursor — it pages by ACCOUNT, so the row can be on any
    page. LAGOS days, as the report bounds them since handoff 65: on CI's
    UTC clock `date.today()` is yesterday in Lagos from 23:00 to 24:00, and
    a grant made a moment ago would fall after `to`."""
    today = lagos_today()
    params = {"from": (today - datetime.timedelta(days=1)).isoformat(),
              "to": today.isoformat(), "limit": 100}
    events, cursor = [], None
    while True:
        q = dict(params)
        if cursor:
            q["cursor"] = cursor
        body = assert_envelope_ok(client.get(ACCESS, params=q))
        events += [e for e in body["data"]["events"] if e["login"] == login]
        cursor = body["pagination"]["next_cursor"]
        if not cursor:
            return events


# ─── fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def manager(client, admin_scope):
    row, matched = _by_login(client, MANAGER_LOGIN)
    if row is None:
        pytest.skip("0 of %d accounts matching %r on this tenant have that "
                    "exact login; handoff 41 part A provisions it on test19"
                    % (matched, MANAGER_LOGIN))
    if _keys(row["roles_direct"]) != ["asset_manager"]:
        pytest.skip("%r holds %s directly, not [asset_manager]; the suite "
                    "will not reshape a probe it did not set up"
                    % (MANAGER_LOGIN, _keys(row["roles_direct"])))
    if not row["active"]:
        pytest.skip("%r is inactive" % MANAGER_LOGIN)
    return row


@pytest.fixture(scope="module")
def me(client, admin_scope, suite_user):
    """The suite's own credential's user row."""
    return _row(client, suite_user["id"])


# ─── the preview ─────────────────────────────────────────────────────

def test_a_dry_run_previews_the_implication_and_writes_nothing(client, manager):
    r = _set(client, manager["id"], ["asset_manager", SECOND_ROLE],
             dry_run=True)
    data = assert_envelope_ok(r)["data"]
    assert data["applied"] is False
    assert data["granted"] == [SECOND_ROLE]
    assert data["revoked"] == []
    assert _keys(data["before"]["roles_direct"]) == ["asset_manager"]
    assert _keys(data["after"]["roles_direct"]) == sorted(
        ["asset_manager", SECOND_ROLE])
    effective = _keys(data["after"]["roles_effective"])
    assert "asset_user" in effective, (
        "the preview did not apply implication: %s" % effective)
    assert SECOND_ROLE in effective
    assert data["user"]["id"] == manager["id"]
    assert set(data["user"]) == set(manager), "the `user` row is not a User row"
    # Nothing written.
    assert _keys(_row(client, manager["id"])["roles_direct"]) == ["asset_manager"]


# ─── the change, the record, the revert ──────────────────────────────

def test_a_real_change_is_applied_recorded_and_reverted(client, manager,
                                                        suite_user):
    try:
        data = assert_envelope_ok(_set(
            client, manager["id"], ["asset_manager", SECOND_ROLE]))["data"]
        assert data["applied"] is True
        assert data["granted"] == [SECOND_ROLE]
        after = _row(client, manager["id"])
        assert _keys(after["roles_direct"]) == sorted(
            ["asset_manager", SECOND_ROLE])
        assert after == data["user"], "the response row and GET disagree"
        assert SECOND_ROLE_SCOPE in after["scopes"]

        events = _access_events(client, MANAGER_LOGIN)
        granted = [e for e in events if e["event"] == "granted"
                   and SECOND_ROLE_GROUP_WORD in (e["group"] or "")]
        assert granted, (
            "the access record shows no `granted` event for %r today "
            "(%d events for that login); the recorder did not see the "
            "route's write" % (MANAGER_LOGIN, len(events)))
        row = granted[-1]
        assert row["attributable"] is True
        assert row["actor"]["name"] == suite_user["name"], (
            "the actor is %r, not the credential's user %r — the route ran "
            "as somebody else" % (row["actor"], suite_user["name"]))
        assert row["precision"] == "exact"
    finally:
        _restore(client, manager["id"], ["asset_manager"])

    reverted = _row(client, manager["id"])
    assert _keys(reverted["roles_direct"]) == ["asset_manager"]
    assert SECOND_ROLE_SCOPE not in reverted["scopes"]


# ─── the two refusals ────────────────────────────────────────────────

def test_the_credential_cannot_make_its_own_user_an_administrator(client, me):
    """Report 41 §G's exposure: an `admin`-scoped credential whose user is
    not a system administrator, asking to become one."""
    if "system" in _keys(me["roles_direct"]):
        pytest.skip("the suite's credential user %r already holds `system` "
                    "directly (1 of 1); nothing to escalate to" % me["login"])
    body = assert_envelope_err(_set(client, me["id"], ["system"]), 403,
                               "forbidden")
    assert ONLY_THESE in body["error"]["message"], body["error"]["message"]
    assert "data" not in body
    assert _row(client, me["id"])["roles_direct"] == me["roles_direct"]


def test_system_cannot_be_granted_to_anybody(client, manager):
    body = assert_envelope_err(_set(client, manager["id"], ["system"]), 403,
                               "forbidden")
    assert ONLY_THESE in body["error"]["message"]
    assert _keys(_row(client, manager["id"])["roles_direct"]) == ["asset_manager"]


def test_a_dry_run_of_a_refused_change_is_refused(client, manager):
    body = assert_envelope_err(
        _set(client, manager["id"], ["system"], dry_run=True), 403, "forbidden")
    assert ONLY_THESE in body["error"]["message"]
    assert _keys(_row(client, manager["id"])["roles_direct"]) == ["asset_manager"]


def test_the_caller_cannot_grant_themselves_a_role(client, me):
    """Ruling 2, through the credential's own account: the grantable roles are
    grantable, and still not to yourself."""
    direct = _keys(me["roles_direct"])
    if "auditor" in direct:
        pytest.skip("the suite's credential user already holds `auditor` "
                    "(direct: %s)" % direct)
    body = assert_envelope_err(_set(client, me["id"], direct + ["auditor"]),
                               403, "forbidden")
    assert NOBODY_THEMSELVES in body["error"]["message"], body["error"]["message"]
    assert me["login"] in body["error"]["message"]
    assert _keys(_row(client, me["id"])["roles_direct"]) == direct


# ─── a body the route does not accept ────────────────────────────────

def test_an_unknown_role_key_is_refused_naming_the_vocabulary(client, manager):
    roles = assert_envelope_ok(client.get(ROLES))["data"]
    body = assert_envelope_err(
        _set(client, manager["id"], ["asset_manager", "superuser"]),
        400, "invalid_request")
    details = body["error"]["details"]
    assert details["allowed_values"] == _keys(roles)
    assert details["rejected_values"] == ["superuser"]
    assert _keys(_row(client, manager["id"])["roles_direct"]) == ["asset_manager"]


def test_roles_must_be_a_list_of_strings(client, manager):
    for bad in ("asset_manager", [1], None, {"asset_manager": True}):
        body = assert_envelope_err(
            _set(client, manager["id"], bad), 400, "invalid_request")
        assert "allowed_values" in body["error"]["details"], bad


def test_an_extra_body_key_is_refused_and_nothing_written(client, manager):
    r = client.post(SET_ROLES.format(id=manager["id"]),
                    json={"roles": ["asset_manager", "tag_issuing_unit"],
                          "role": "system"})
    details = assert_fields_refused(r, "role")
    assert details["writable"] == ["dry_run", "roles"]
    assert _keys(_row(client, manager["id"])["roles_direct"]) == ["asset_manager"]


def test_dry_run_must_be_a_boolean(client, manager):
    body = assert_envelope_err(
        _set(client, manager["id"], ["asset_manager"], dry_run="yes"),
        400, "invalid_request")
    assert body["error"]["details"]["field"] == "dry_run"


# ─── who is not an account ───────────────────────────────────────────

def test_a_structural_login_and_a_missing_id_are_404(client, admin_scope):
    for user_id in (1, 999999999):
        assert_envelope_err(_set(client, user_id, ["asset_user"]), 404,
                            "not_found")


def test_unauthenticated_is_401(unauthed_client):
    assert_envelope_err(_set(unauthed_client, 1, ["asset_user"]), 401,
                        "unauthorized")


# ─── idempotency ─────────────────────────────────────────────────────

def test_a_replay_under_the_same_key_returns_the_identical_body(client, manager):
    key = "pytest-h42-%s" % uuid.uuid4().hex[:12]
    headers = {"X-Idempotency-Key": key}
    try:
        r1 = _set(client, manager["id"], ["asset_manager", SECOND_ROLE],
                  headers=headers)
        body1 = assert_envelope_ok(r1)
        assert body1["data"]["applied"] is True
        r2 = _set(client, manager["id"], ["asset_manager", SECOND_ROLE],
                  headers=headers)
        body2 = assert_envelope_ok(r2)
        assert body1 == body2, "the replay is not the original answer"
        assert body1["meta"]["request_id"] == body2["meta"]["request_id"]
        # The replay re-applied nothing: the state is the one change.
        assert _keys(_row(client, manager["id"])["roles_direct"]) == sorted(
            ["asset_manager", SECOND_ROLE])
    finally:
        _restore(client, manager["id"], ["asset_manager"])


# ─── what is published ───────────────────────────────────────────────

def test_the_route_is_published_admin_only_with_its_schema(client):
    spec = client.get("/api/v1/openapi.json").json()
    assert SET_ROLES_SPEC_PATH in spec["paths"], "the route is not published"
    op = spec["paths"][SET_ROLES_SPEC_PATH]["post"]
    assert op["x-cadra-scopes"] == ["admin"], op["x-cadra-scopes"]
    assert op["security"]
    headers = [p["name"] for p in op.get("parameters", []) if p.get("in") == "header"]
    assert "X-Idempotency-Key" in headers, (
        "the route must declare the X-Idempotency-Key header it honours")
    assert "RoleChange" in spec["components"]["schemas"]
    assert "403" in op["responses"] and "404" in op["responses"]
    props = op["requestBody"]["content"]["application/json"]["schema"]["properties"]
    assert set(props) == {"roles", "dry_run"}


def test_roles_marks_exactly_the_four_as_grantable(client, admin_scope):
    roles = assert_envelope_ok(client.get(ROLES))["data"]
    for role in roles:
        assert isinstance(role["grantable"], bool), role
    grantable = {r["key"] for r in roles if r["grantable"]}
    assert grantable == GRANTABLE, (
        "grantable roles are %s; a fifth is a decision with a name on it "
        "(handoff 42 §2)" % sorted(grantable))
    by_key = {r["key"]: r for r in roles}
    assert by_key["system"]["grantable"] is False
