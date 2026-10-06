"""`whoami` names the hat — handoff 56.

`GET /auth/whoami` answers `roles`: the caller's DIRECT roles, as exactly
the `[{key, name}]` rows `/users/<id>` publishes as `roles_direct` — same
`PUBLISHED_ROLE_NAMES` vocabulary, same `role_key`, same `GROUP_SCOPES`
order. Direct and not effective, because the top bar names the hat somebody
was given: the effective closure would caption every Asset Manager
"Asset User · Asset Officer +1".

Three legs:

* **Every demo persona** (`docs/api/.personas.<tenant>`, handoff 46) signs
  in and their `whoami.roles` is byte-equal to their own row's
  `roles_direct` — the administrator (`system`), the manager, the auditor,
  the unit and the paired tagger all at once, so the one-role, two-role and
  system cases are all driven by real sign-ins.
* **The suite's own credential**: same equality, through `/auth/token`
  rather than `/auth/login`, so the credential path answers the same list
  as the person path.
* **An account with no roles answers `[]`** — proved by CREATING one
  (`POST /users` with no `roles`, handoff 43), reading its letter out of
  Mailpit, redeeming a password and signing in, exactly as
  `test_password_tokens.py` does. The handoff asked for "a credential with
  no groups"; on `test19` no such credential can authenticate (the suite's
  own holds five vocabulary groups via `SCOPE_GROUPS`, and the only other
  credential — `cadra_demo_personas` — is archived with no secret, by
  design), so the empty case is proved with a person instead. Skips,
  naming why, when the inbox cannot be read.

The persona leg skips when the tenant has no personas file — the passwords
live there and nowhere else.
"""
import os
import pathlib
import re
import time
import uuid

import pytest
import requests

from .conftest import ApiClient, assert_envelope_ok, tenant_from_base

WHOAMI = "/api/v1/auth/whoami"
LOGIN = "/api/v1/auth/login"
USER = "/api/v1/users/{id}"
USERS = "/api/v1/users"
DEACTIVATE = "/api/v1/users/{id}/deactivate"
REDEEM = "/api/v1/auth/password-token/redeem"

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MAILPIT = os.environ.get("CADRA_MAILPIT", "http://localhost:8025").rstrip("/")
LINK = re.compile(
    r"(https?://[^\s\"'<>]+/app/(accept-invite|reset-password)\?token=([A-Za-z0-9_\-]+))")


def _personas(api_base):
    """`{key: (login, password)}` from `docs/api/.personas.<tenant>`."""
    tenant = tenant_from_base(api_base)
    path = REPO_ROOT / "docs" / "api" / (".personas.%s" % tenant)
    if not tenant or not path.exists():
        pytest.skip("no personas file for %r (%s); seed the demo personas "
                    "first (scripts/demo_personas.sh)" % (tenant, path))
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 3:
            out[parts[0]] = (parts[1], parts[2])
    if not out:
        pytest.skip("%s holds 0 persona lines" % path)
    return out


def _whoami_as(api_base, login, password):
    r = requests.post(api_base + LOGIN,
                      json={"login": login, "password": password}, timeout=30)
    assert r.status_code == 200, (
        "persona %r cannot sign in: HTTP %s %s" % (login, r.status_code,
                                                   r.text[:200]))
    me = ApiClient(api_base, r.json()["data"]["access_token"])
    return assert_envelope_ok(me.get(WHOAMI))["data"]


def _roles_direct(client, user_id):
    return assert_envelope_ok(client.get(USER.format(id=user_id)))["data"]["roles_direct"]


# ─── every persona: whoami and the Users page say the same list ──────

def test_every_personas_whoami_roles_equal_their_users_row(api_base, client,
                                                           admin_scope):
    personas = _personas(api_base)
    assert len(personas) >= 3, (
        "the personas file holds %d account(s) of the 6 the seed writes; "
        "3 are the minimum this proof needs" % len(personas))
    for key, (login, password) in sorted(personas.items()):
        who = _whoami_as(api_base, login, password)
        assert "roles" in who, "whoami answered no `roles` key at all"
        for ref in who["roles"]:
            assert set(ref) == {"key", "name"}, (key, ref)
        expected = _roles_direct(client, who["id"])
        assert who["roles"] == expected, (
            "persona %r: whoami says %r, /users/%s says roles_direct=%r"
            % (key, who["roles"], who["id"], expected))
        assert who["roles"], (
            "persona %r holds no role at all — the seed grants every "
            "persona at least one, so this equality proved nothing" % key)
        if key == "administrator":
            # Holds `system`, published under the vocabulary's one chosen
            # name — `in`, not `==`: what else the tenant's administrator
            # holds is a fact about the tenant (test19's also holds Asset
            # Manager), and the equality above already pins the whole list.
            by_key = {r["key"]: r["name"] for r in who["roles"]}
            assert "system" in by_key, who["roles"]
            assert by_key["system"] == "System Administrator"


# ─── the credential path answers the same list ───────────────────────

def test_the_suites_own_credential_agrees_with_its_users_row(client,
                                                             admin_scope):
    who = assert_envelope_ok(client.get(WHOAMI))["data"]
    assert "roles" in who
    assert who["roles"] == _roles_direct(client, who["id"])


# ─── an account with no roles answers the empty list ─────────────────

def test_an_account_with_no_roles_answers_an_empty_list(api_base, client,
                                                        admin_scope):
    """Created with NO `roles`, so it lands in the default groups and none
    of the published vocabulary; signed in through its own letter."""
    try:
        requests.get(MAILPIT + "/api/v1/messages", params={"limit": 1},
                     timeout=5).raise_for_status()
    except requests.RequestException as e:
        pytest.skip("the inbox at %s cannot be read (%s); the no-role "
                    "account cannot be signed in from here"
                    % (MAILPIT, type(e).__name__))

    marker = "pytest-h56-%s" % uuid.uuid4().hex[:10]
    email = "%s@example.invalid" % marker
    r = client.post(USERS, json={"name": marker, "email": email,
                                 "send_invitation": True})
    if r.status_code == 500:
        pytest.skip("this tenant refuses to send the invitation (%s)"
                    % r.text[:200])
    row = assert_envelope_ok(r, 201)["data"]
    try:
        assert row["roles_direct"] == [], (
            "a create that named no role granted some: %r"
            % row["roles_direct"])

        token = None
        deadline = time.time() + 20
        while time.time() < deadline and token is None:
            found = requests.get(MAILPIT + "/api/v1/search",
                                 params={"query": "to:%s" % email},
                                 timeout=5).json()
            for m in found.get("messages") or []:
                msg = requests.get(MAILPIT + "/api/v1/message/%s" % m["ID"],
                                   timeout=5).json()
                text = (msg.get("Text") or "") + " " + (msg.get("HTML") or "")
                for _url, page, tok in LINK.findall(text):
                    if page == "accept-invite":
                        token = tok
                        break
                if token:
                    break
            if token is None:
                time.sleep(1)
        assert token, ("0 letters to %s with an /app/accept-invite link "
                       "arrived in 20s (inbox %s)" % (email, MAILPIT))

        password = "H56-%s!x" % uuid.uuid4().hex[:12]
        redeemed = requests.post(
            api_base + REDEEM,
            json={"token": token, "password": password,
                  "confirm_password": password},
            timeout=30)
        assert redeemed.status_code == 200, redeemed.text[:300]

        who = _whoami_as(api_base, row["login"], password)
        assert who["roles"] == [], (
            "an account holding no published role answered %r" % who["roles"])
        assert who["roles"] == _roles_direct(client, who["id"])
    finally:
        client.post(DEACTIVATE.format(id=row["id"]))
