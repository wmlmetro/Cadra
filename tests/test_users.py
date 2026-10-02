"""Who has what — `GET /roles`, `GET /users`, `GET /users/<id>`. Handoff 41 §4B.

All three are `admin`-scoped and all three are READS. This suite runs against
whichever tenant `CADRA_API_BASE` names; the assertions that need a particular
account to exist (an Asset Manager who holds Asset User only by implication,
an inactive account, a user named `h41_*`) SKIP naming the denominator they
counted when the tenant has none, rather than passing on an empty answer.

Four things this suite is built around:

**The drift check needs no import.** `/roles` is derived from
`utils.GROUP_SCOPES`, and so is the token `/auth/login` mints. Rather than
import the table and compare, every person's `scopes` is asserted equal to
the sorted union over `/roles` of the scopes of their `roles_effective`. If
either side stops being derived from the same table, that fails.

**Direct and effective are two questions.** On Odoo 19 implication writes no
membership row, so an Asset Manager is a MEMBER of one role and HOLDS two.
`roles_direct ⊆ roles_effective` is asserted on every row, and the
difference on the rows where there is one must be explained by `implies`
from `/roles`.

**No credential travels.** Every key of every response is matched against
`_CREDENTIALISH`, the same key-name rule the audit reports are held to —
with exactly ONE waiver, `api_client.is_test_credential`, which is a
boolean FLAG about a credential and not a credential (its value is asserted
to be a bool). The waiver is by exact key so a second match fails.

**The boundary is proved with a second person.** A token minted as a user
holding only the Tag-Issuing Unit is refused with a 403 that names `admin`,
so the scope is shown to be enforced and not merely declared.

Nothing here writes. There is no fixture to clean up.
"""
import os
import re

import pytest
import requests

from .conftest import ApiClient, assert_envelope_ok, assert_envelope_err

ROLES = "/api/v1/roles"
USERS = "/api/v1/users"
USER = "/api/v1/users/{id}"
USER_SPEC_PATH = "/api/v1/users/{user_id}"

#: Every key a user row promises. A row missing one is a consumer reading
#: `undefined`.
_USER_KEYS = frozenset({
    "id", "name", "login", "email", "active", "kind", "api_client",
    "roles_direct", "roles_effective", "scopes", "scopes_source",
    "last_login_at", "created_at",
    # Handoff 43: whether a link to set a password is outstanding, and since when.
    "invitation",
})
_ROLE_KEYS = frozenset({
    "key", "name", "xmlid", "scopes", "description", "installed", "implies",
    # Handoff 42: whether `POST /users/<id>/roles` may grant or remove it.
    # Exactly which four are true is `tests/test_user_roles.py`'s to assert.
    "grantable",
})
_API_CLIENT_KEYS = frozenset({
    "id", "name", "client_id", "active", "is_test_credential",
})

# The same rule `tests/test_audit_logs.py` applies to the access report's
# roster: a KEY whose name reads as a credential is a credential travelling,
# whatever its value.
_CREDENTIALISH = re.compile(
    r"secret|password|passwd|pwd|token|api_?key|private_?key|credential"
    r"|salt|signature|totp|hash|cookie|session", re.IGNORECASE)

#: The one key the pattern matches that is not a credential: a boolean flag
#: saying whether the client is a test fixture (`is_test_credential` on
#: `myservice.api.client`, handoff 26). Waived by its EXACT path, and its
#: value is asserted to be a bool, so a string arriving under this name
#: would still fail.
_CREDENTIALISH_WAIVED = {("api_client", "is_test_credential")}

#: A person who holds ONLY the Tag-Issuing Unit, for the 403. Provisioned
#: on `test19` by handoff 41 part A; the test skips if the login is refused.
_TAGGER_LOGIN = os.environ.get("CADRA_H41_TAGGER_LOGIN", "h41_tagger")
_TAGGER_PASSWORD = os.environ.get("CADRA_H41_TAGGER_PASSWORD",
                                  "h41-tagger-pass")


# ─── helpers ─────────────────────────────────────────────────────────

def _all_rows(client, **params):
    """Every row of `GET /users` for `params`, walking `next_cursor`.

    Returns `(rows, total_estimate, truncated)`. `truncated` is set when a
    page carried `_warnings.truncated`, in which case `rows` is the capped
    window and a test that needed a particular row should say so rather
    than conclude it does not exist.
    """
    rows, truncated, total = [], False, None
    cursor = None
    while True:
        query = dict(params, limit=100)
        if cursor:
            query["cursor"] = cursor
        body = assert_envelope_ok(client.get(USERS, params=query))
        rows.extend(body["data"])
        total = body["pagination"]["total_estimate"]
        if (body.get("_warnings") or {}).get("truncated"):
            truncated = True
        cursor = body["pagination"]["next_cursor"]
        if not cursor:
            break
    return rows, total, truncated


def _keys(roles):
    return [r["key"] for r in roles]


def _walk_keys(value, path=()):
    """Every (path, key) of every dict anywhere in `value`."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield path + (k,), k
            yield from _walk_keys(v, path + (k,))
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item, path)


def _assert_no_credential_key(body, where):
    offenders = []
    for path, key in _walk_keys(body):
        if not _CREDENTIALISH.search(key):
            continue
        # Strip the envelope and list position so the waiver is by the
        # row-relative path: ("api_client", "is_test_credential").
        relative = tuple(p for p in path if p not in ("data",))
        if relative[-2:] in _CREDENTIALISH_WAIVED:
            continue
        offenders.append("/".join(str(p) for p in path))
    assert not offenders, (
        "%s publishes a key whose name reads as a credential: %s"
        % (where, sorted(set(offenders))))


# ─── fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def roles(client, admin_scope):
    body = assert_envelope_ok(client.get(ROLES))
    assert isinstance(body["data"], list) and body["data"], (
        "`/roles` answered an empty vocabulary; GROUP_SCOPES is not empty")
    return body["data"]


@pytest.fixture(scope="module")
def roles_by_key(roles):
    return {r["key"]: r for r in roles}


@pytest.fixture(scope="module")
def everyone(client, admin_scope):
    """Every account on the tenant, as `(rows, total, truncated)`."""
    rows, total, truncated = _all_rows(client)
    assert rows, (
        "`/users` answered no accounts at all; the credential this suite "
        "runs as is an account and must be listed (total_estimate=%s)"
        % total)
    return rows, total, truncated


# ─── the gate ────────────────────────────────────────────────────────

def test_the_three_routes_refuse_a_caller_with_no_token(unauthed_client):
    """Every route runs `sudo()` over the whole user table, so the token is
    the only gate between a caller and every login on the tenant."""
    for path in (ROLES, USERS, USER.format(id=1)):
        assert_envelope_err(unauthed_client.get(path), 401, "unauthorized")


def test_a_token_without_admin_is_refused_naming_the_scope(api_base):
    """A person holding ONLY the Tag-Issuing Unit gets a 403 that names
    `admin` — the scope is ENFORCED, not merely published.

    Minted by the real login route rather than hand-built, so what is
    proved is that `/auth/login` gives a tagger no `admin` AND that the
    three routes refuse without it. Skips, naming why, if the tenant has no
    such person or will not sign them in.
    """
    r = requests.post(f"{api_base}/api/v1/auth/login",
                      json={"login": _TAGGER_LOGIN,
                            "password": _TAGGER_PASSWORD},
                      timeout=30)
    if r.status_code != 200:
        pytest.skip(
            "cannot sign in as %r (HTTP %s): this tenant has no tagger-only "
            "account to prove the 403 with" % (_TAGGER_LOGIN, r.status_code))
    tagger = ApiClient(api_base, r.json()["data"]["access_token"])

    who = assert_envelope_ok(tagger.get("/api/v1/auth/whoami"))["data"]
    scopes = who.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    if "admin" in scopes or "*" in scopes:
        pytest.skip(
            "%r holds `admin` on this tenant, so it cannot prove the "
            "refusal (scopes: %s)" % (_TAGGER_LOGIN, sorted(scopes)))

    for path in (USERS, ROLES, USER.format(id=who["id"])):
        body = assert_envelope_err(tagger.get(path), 403, "forbidden")
        required = body["error"].get("details", {}).get("required_scopes", [])
        assert "admin" in required, (
            "%s refused the tagger without naming `admin` in "
            "`details.required_scopes`: %r" % (path, required))


# ─── the shapes ──────────────────────────────────────────────────────

def test_the_roles_envelope_and_every_role_key(roles):
    for role in roles:
        assert set(role) == _ROLE_KEYS, (
            "role %r carries %s; expected exactly %s"
            % (role.get("key"), sorted(role), sorted(_ROLE_KEYS)))
        assert role["scopes"] == sorted(role["scopes"]), (
            "role %r publishes unsorted scopes" % role["key"])
        assert isinstance(role["installed"], bool)
        assert isinstance(role["implies"], list)
        if not role["installed"]:
            assert role["implies"] == [] and role["description"] is None, (
                "an uninstalled role cannot imply anything or describe "
                "itself: %r" % role)
    keys = _keys(roles)
    assert len(keys) == len(set(keys)), "duplicate role keys: %s" % keys
    assert "asset_user" in keys and "asset_manager" in keys and \
        "system" in keys, keys


def test_system_is_published_as_system_administrator(roles_by_key):
    """Odoo calls `base.group_system` "Settings". NRS does not."""
    assert roles_by_key["system"]["xmlid"] == "base.group_system"
    assert roles_by_key["system"]["name"] == "System Administrator"
    assert roles_by_key["system"]["scopes"] == ["admin"]


def test_every_user_row_carries_every_key(everyone):
    rows, _total, _truncated = everyone
    for row in rows:
        assert set(row) == _USER_KEYS, (
            "row %s carries %s; expected exactly %s"
            % (row.get("id"), sorted(row), sorted(_USER_KEYS)))
        assert row["kind"] in ("person", "api_credential"), row["kind"]
        assert row["scopes_source"] in ("roles", "credential")
        assert row["scopes"] == sorted(row["scopes"]), (
            "row %s publishes unsorted scopes" % row["id"])
        for role in row["roles_direct"]:
            assert set(role) == {"key", "name"}, role
        for role in row["roles_effective"]:
            # `via` is on the effective list only: the direct group(s) that
            # imply the role, empty when it is held directly.
            assert set(role) == {"key", "name", "via"}, role
            assert isinstance(role["via"], list), role
        if row["kind"] == "api_credential":
            assert row["scopes_source"] == "credential"
            assert set(row["api_client"] or {}) == _API_CLIENT_KEYS, (
                "row %s is an api_credential with api_client=%r"
                % (row["id"], row["api_client"]))
        else:
            assert row["scopes_source"] == "roles"
            assert row["api_client"] is None, row["api_client"]
        assert row["created_at"], "created_at is never null"


def test_direct_is_a_subset_of_effective_and_manager_holds_user(everyone):
    """What was granted is always part of what is held, and the one
    implication this register defines — Asset Manager → Asset User — holds
    on every row that has the first."""
    rows, _total, _truncated = everyone
    for row in rows:
        direct, effective = _keys(row["roles_direct"]), _keys(row["roles_effective"])
        assert set(direct) <= set(effective), (
            "row %s (%s) is a MEMBER of %s but does not HOLD them all: %s"
            % (row["id"], row["login"], direct, effective))
        if "asset_manager" in effective:
            assert "asset_user" in effective, (
                "row %s holds asset_manager without asset_user; the "
                "implication in asset_security.xml is not being applied"
                % row["id"])


def test_scopes_are_the_union_over_roles_of_the_effective_roles(
        everyone, roles_by_key):
    """THE drift check. `/roles` and the login token both derive from
    `GROUP_SCOPES`; if either stops, a person's `scopes` and the union of
    their effective roles' `scopes` part company here."""
    rows, _total, _truncated = everyone
    checked = 0
    for row in rows:
        if row["scopes_source"] != "roles":
            continue
        expected = set()
        for role in row["roles_effective"]:
            expected.update(roles_by_key[role["key"]]["scopes"])
        assert row["scopes"] == sorted(expected), (
            "row %s (%s) carries scopes %s but its effective roles %s "
            "produce %s" % (row["id"], row["login"], row["scopes"],
                            _keys(row["roles_effective"]), sorted(expected)))
        checked += 1
    assert checked, "no person on the tenant; the drift check ran on nobody"


def test_a_row_where_direct_and_effective_differ_is_explained_by_implies(
        everyone, roles_by_key):
    """The handoff's own proof: on Odoo 19 an Asset Manager is a member of
    one role and holds two, and the row says why.

    Two ways a role is held by implication, and the row explains both:
    through another role in the vocabulary (`/roles` lists it under
    `implies`), or through a group OUTSIDE it — on `test19` the
    administrator holds Security Officer through Security Administrator, which
    grants no scope and is not on `/roles`. The first draft of this test
    allowed only the first and failed on the second; `via` names the group
    either way, so a reader is never shown a role nothing on the row
    accounts for.
    """
    rows, total, truncated = everyone
    differing = [r for r in rows
                 if _keys(r["roles_direct"]) != _keys(r["roles_effective"])]
    if not differing:
        pytest.skip(
            "0 of %d listed accounts (total_estimate %s%s) hold a role only "
            "by implication; nothing to prove the distinction with"
            % (len(rows), total, ", truncated" if truncated else ""))
    explained_by_roles = 0
    for row in differing:
        direct = set(_keys(row["roles_direct"]))
        reachable = set()
        for key in direct:
            reachable.update(roles_by_key[key]["implies"])
        direct_names = {r["name"] for r in row["roles_direct"]}
        for role in row["roles_effective"]:
            if role["key"] in direct:
                assert role["via"] == [], (
                    "row %s (%s): %s is held directly but names `via` %s"
                    % (row["id"], row["login"], role["key"], role["via"]))
                continue
            assert role["via"], (
                "row %s (%s) holds %s by implication and `via` names "
                "nothing" % (row["id"], row["login"], role["key"]))
            if role["key"] in reachable:
                # Implied by a role in the vocabulary: `via` must name it.
                assert direct_names & set(role["via"]), (
                    "row %s (%s): %s is implied by a direct role but `via` "
                    "%s names none of %s"
                    % (row["id"], row["login"], role["key"], role["via"],
                       sorted(direct_names)))
                explained_by_roles += 1
            else:
                # Implied by a group outside the vocabulary: the row can
                # only name it, and it must not be a role the row holds.
                assert not (set(role["via"]) & direct_names), (
                    "row %s (%s): %s is implied by a direct role `/roles` "
                    "does not say implies it" % (row["id"], row["login"],
                                                 role["key"]))
    assert explained_by_roles, (
        "%d of %d listed accounts differ, and none of them holds a role "
        "through another role in the vocabulary (the Asset Manager case)"
        % (len(differing), len(rows)))


def test_an_api_credential_row_exists_and_says_so(everyone):
    """The suite's own credential is an API client with a `res.users`, so
    the tenant always has at least one. Its row must not look like staff."""
    rows, _total, _truncated = everyone
    credentials = [r for r in rows if r["kind"] == "api_credential"]
    assert credentials, (
        "no api_credential row among %d accounts, yet this suite is "
        "authenticated as one" % len(rows))
    flagged = [r for r in credentials if r["api_client"]["is_test_credential"]]
    assert flagged, (
        "no api_credential row is flagged is_test_credential; the suite's "
        "own credential is (handoff 25) — %s"
        % [r["login"] for r in credentials])
    for row in credentials:
        assert row["scopes_source"] == "credential"
        assert isinstance(row["api_client"]["is_test_credential"], bool)
        assert row["api_client"]["client_id"]


# ─── the filters ─────────────────────────────────────────────────────

def test_active_filters_and_absent_means_both(client, admin_scope, everyone):
    rows, total, truncated = everyone
    inactive, _t, _tr = _all_rows(client, active="false")
    active, _t, _tr = _all_rows(client, active="true")
    assert all(r["active"] is False for r in inactive), (
        "`?active=false` returned an active row: %s"
        % [r["login"] for r in inactive if r["active"]])
    assert all(r["active"] is True for r in active), (
        "`?active=true` returned an inactive row: %s"
        % [r["login"] for r in active if not r["active"]])
    if not inactive:
        pytest.skip(
            "0 of %d listed accounts (total_estimate %s%s) are inactive; "
            "the `?active=false` half cannot be proved to return anything"
            % (len(rows), total, ", truncated" if truncated else ""))
    if not truncated:
        assert len(active) + len(inactive) == len(rows), (
            "absent must mean both: %d active + %d inactive != %d listed"
            % (len(active), len(inactive), len(rows)))


def test_role_is_effective_and_role_direct_is_membership(
        client, admin_scope, everyone):
    rows, total, truncated = everyone
    effective, _t, _tr = _all_rows(client, role="asset_user")
    for row in effective:
        assert "asset_user" in _keys(row["roles_effective"]), (
            "`?role=asset_user` returned %s, which does not HOLD it: %s"
            % (row["login"], _keys(row["roles_effective"])))
    direct, _t, _tr = _all_rows(client, role_direct="asset_user")
    for row in direct:
        assert "asset_user" in _keys(row["roles_direct"]), (
            "`?role_direct=asset_user` returned %s, which is not a MEMBER: %s"
            % (row["login"], _keys(row["roles_direct"])))
    assert {r["id"] for r in direct} <= {r["id"] for r in effective}, (
        "a member of asset_user is not among those who hold it")
    by_implication = [r for r in effective
                      if "asset_user" not in _keys(r["roles_direct"])]
    if not by_implication:
        pytest.skip(
            "0 of %d accounts holding asset_user (of %d listed, "
            "total_estimate %s%s) hold it only by implication; the "
            "difference between the two filters cannot be shown"
            % (len(effective), len(rows), total,
               ", truncated" if truncated else ""))
    assert not {r["id"] for r in by_implication} & {r["id"] for r in direct}


def test_is_api_client_splits_people_from_credentials(client, admin_scope):
    credentials, _t, _tr = _all_rows(client, is_api_client="true")
    people, _t, _tr = _all_rows(client, is_api_client="false")
    assert credentials and all(r["kind"] == "api_credential" for r in credentials)
    assert people and all(r["kind"] == "person" for r in people)


def test_an_unknown_role_is_refused_naming_the_vocabulary(
        client, admin_scope, roles):
    for param in ("role", "role_direct"):
        body = assert_envelope_err(
            client.get(USERS, params={param: "nonsense"}),
            400, "invalid_request")
        allowed = body["error"]["details"].get("allowed_values")
        assert allowed == _keys(roles), (
            "`?%s=nonsense` must list the vocabulary in "
            "`details.allowed_values`; got %r" % (param, allowed))


def test_an_unreadable_boolean_is_refused(client, admin_scope):
    for param in ("active", "is_api_client"):
        body = assert_envelope_err(
            client.get(USERS, params={param: "maybe"}), 400, "invalid_request")
        assert body["error"]["details"].get("allowed_values") == ["true", "false"]


def test_q_matches_name_login_or_email(client, admin_scope, everyone):
    rows, total, truncated = everyone
    found, _t, _tr = _all_rows(client, q="h41")
    for row in found:
        haystack = " ".join(filter(None, (row["name"], row["login"],
                                          row["email"]))).lower()
        assert "h41" in haystack, (
            "`?q=h41` returned %s, which matches on none of name, login, "
            "email" % row["login"])
    if not found:
        pytest.skip(
            "0 of %d listed accounts (total_estimate %s%s) match `h41`; "
            "the positive half cannot be shown"
            % (len(rows), total, ", truncated" if truncated else ""))


# ─── the detail route ────────────────────────────────────────────────

def test_the_detail_route_round_trips_a_list_row_exactly(
        client, admin_scope, everyone):
    rows, _total, _truncated = everyone
    for row in rows[:3]:
        body = assert_envelope_ok(client.get(USER.format(id=row["id"])))
        assert body["data"] == row, (
            "GET /users/%s differs from its list row:\n  list:   %r\n  "
            "detail: %r" % (row["id"], row, body["data"]))


def test_a_missing_id_is_404(client, admin_scope):
    assert_envelope_err(client.get(USER.format(id=999999999)), 404, "not_found")


def test_a_structural_login_is_not_an_account(client, admin_scope, everyone):
    """`__system__` (OdooBot, uid 1) is excluded by the same domain the list
    uses, so the two routes cannot disagree about who is an account."""
    rows, _total, _truncated = everyone
    structural = [r["login"] for r in rows
                  if r["login"] in ("__system__", "public", "portaltemplate")]
    assert not structural, "the list carries structural logins: %s" % structural
    assert_envelope_err(client.get(USER.format(id=1)), 404, "not_found")


# ─── nothing leaks ───────────────────────────────────────────────────

def test_no_key_anywhere_reads_as_a_credential(client, admin_scope, everyone):
    rows, _total, _truncated = everyone
    _assert_no_credential_key(
        assert_envelope_ok(client.get(ROLES)), "GET /roles")
    _assert_no_credential_key({"data": rows}, "GET /users")
    credential_rows = [r for r in rows if r["kind"] == "api_credential"]
    if credential_rows:
        _assert_no_credential_key(
            assert_envelope_ok(client.get(USER.format(id=credential_rows[0]["id"]))),
            "GET /users/<api credential>")


# ─── the published contract ──────────────────────────────────────────

def test_the_three_routes_are_published_admin_only_with_their_schemas(client):
    spec = client.get("/api/v1/openapi.json").json()
    for path in (ROLES, USERS, USER_SPEC_PATH):
        assert path in spec["paths"], "%s is not published in openapi" % path
        op = spec["paths"][path]["get"]
        assert op["x-cadra-scopes"] == ["admin"], (
            "%s declares %s; the user list is admin-only"
            % (path, op["x-cadra-scopes"]))
        assert op["security"], "%s publishes no security requirement" % path
    schemas = spec["components"]["schemas"]
    for name in ("User", "Role", "UserRole"):
        assert name in schemas, "component schema %s is not published" % name
    assert "404" in spec["paths"][USER_SPEC_PATH]["get"]["responses"], (
        "the detail route answers 404 and must say so")


def test_pagination_walks_by_cursor(client, admin_scope, everyone):
    rows, _total, _truncated = everyone
    if len(rows) < 2:
        pytest.skip("1 of 1 accounts listed; nothing to page")
    first = assert_envelope_ok(client.get(USERS, params={"limit": 1}))
    assert len(first["data"]) == 1
    assert first["pagination"]["next_cursor"], "limit=1 on 2+ rows must page"
    second = assert_envelope_ok(client.get(
        USERS, params={"limit": 1, "cursor": first["pagination"]["next_cursor"]}))
    assert len(second["data"]) == 1
    assert second["data"][0]["id"] != first["data"][0]["id"]
    assert second["data"][0]["id"] > first["data"][0]["id"], "the walk is by id"
