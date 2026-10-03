"""The first five minutes, over HTTP — handoff 45 §2.1.

A person is invited, the letter is READ OUT OF THE INBOX (Mailpit, which
`test19` sends to), its link is the app's page and not Odoo's, the token is
inspected, a bad password is refused in words, a good one is set and the
person is signed in, and the same link then reads `redeemed`. The reset
journey the same way from *Forgot password?*. A letter sent before handoff 45
carries `/web/signup?…token=…`; that link now lands on the app's page with the
same token.

**Mail is a fact about the tenant.** The tests that need a received letter
skip, saying so, when the inbox cannot be read (`CADRA_MAILPIT`, default
`http://localhost:8025`) or when the tenant refuses to send. The expired
state cannot be reached over HTTP without waiting days; the in-registry suite
mints an expired token (`myservice_api/tests/test_password_tokens.py`).

Every account is a `pytest-` fixture and is deactivated in a `finally`.
"""
import base64
import os
import re
import time
import uuid

import pytest
import requests

from .conftest import assert_envelope_ok, assert_envelope_err

INSPECT = "/api/v1/auth/password-token/inspect"
REDEEM = "/api/v1/auth/password-token/redeem"
RESET = "/api/v1/auth/password-reset"
USERS = "/api/v1/users"
USER = "/api/v1/users/{id}"
DEACTIVATE = "/api/v1/users/{id}/deactivate"
LOGIN = "/api/v1/auth/login"

MAILPIT = os.environ.get("CADRA_MAILPIT", "http://localhost:8025").rstrip("/")
STATES = {"outstanding", "expired", "redeemed", "cancelled", "invalid"}
LINK = re.compile(r"(https?://[^\s\"'<>]+/app/(accept-invite|reset-password)\?token=([A-Za-z0-9_\-]+))")


def _anon(api_base):
    s = requests.Session()
    s.headers["Accept"] = "application/json"
    return s


def _inbox_link(address, kind, timeout=20):
    """The link in the newest letter to `address`, read from Mailpit."""
    try:
        requests.get(MAILPIT + "/api/v1/messages", params={"limit": 1}, timeout=5).raise_for_status()
    except requests.RequestException as e:
        pytest.skip("the inbox at %s cannot be read (%s); the letter cannot be "
                    "proved from here" % (MAILPIT, type(e).__name__))
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = requests.get(MAILPIT + "/api/v1/search",
                             params={"query": "to:%s" % address}, timeout=5).json()
        for m in found.get("messages") or []:
            msg = requests.get(MAILPIT + "/api/v1/message/%s" % m["ID"], timeout=5).json()
            text = (msg.get("Text") or "") + " " + (msg.get("HTML") or "")
            for url, page, token in LINK.findall(text):
                if page == kind:
                    return url, token, msg
        time.sleep(1)
    pytest.fail("0 letters to %s with an /app/%s link arrived in %ds (inbox "
                "%s)" % (address, kind, timeout, MAILPIT))


@pytest.fixture
def person(client, admin_scope):
    made = []

    def make(send=True):
        marker = "pytest-h45-%s" % uuid.uuid4().hex[:10]
        email = "%s@example.invalid" % marker
        r = client.post(USERS, json={"name": marker, "email": email,
                                     "roles": ["asset_user"],
                                     "send_invitation": send})
        if send and r.status_code == 500:
            pytest.skip("this tenant refuses to send the invitation (%s); the "
                        "letter cannot be proved here" % r.text[:200])
        row = assert_envelope_ok(r, 201)["data"]
        made.append(row["id"])
        return row, email

    yield make
    for uid in made:
        row = client.get(USER.format(id=uid)).json().get("data") or {}
        if row.get("active"):
            client.post(DEACTIVATE.format(id=uid))


# ─── the token, without a letter ────────────────────────────────────

def test_a_token_that_was_never_one_of_ours_is_invalid_in_words(api_base):
    s = _anon(api_base)
    forged = base64.urlsafe_b64encode(
        b"\x01" + (2 ** 40).to_bytes(8, "little") + b"\x00" * 32
        + b'[1, [2], null, "signup"]').decode().rstrip("=")
    for token in ("", "not-a-token", "%%%", forged):
        body = assert_envelope_ok(s.post(api_base + INSPECT, json={"token": token}))
        data = body["data"]
        assert data["state"] == "invalid", (token, data)
        assert data["message"] and data["next"], data
        assert "name" not in data and "login" not in data, (
            "a dead link said whose it was: %r" % data)
    assert "token" not in str(data).lower().replace("this link", ""), data


def test_the_three_routes_refuse_a_key_they_do_not_read(api_base):
    s = _anon(api_base)
    for path, body in ((INSPECT, {"token": "x", "login": "y"}),
                       (REDEEM, {"token": "x", "password": "p", "user_id": 2}),
                       (RESET, {"login": "x", "password": "y"})):
        r = s.post(api_base + path, json=body)
        assert_envelope_err(r, 400, "invalid_request")
        assert r.json()["error"]["details"]["rejected_fields"], r.text


def test_redeeming_a_dead_token_is_a_conflict_naming_its_state(api_base):
    r = _anon(api_base).post(api_base + REDEEM, json={
        "token": "not-a-token", "password": "x" * 12, "confirm_password": "x" * 12})
    assert_envelope_err(r, 409, "conflict")
    assert r.json()["error"]["details"]["state"] == "invalid", r.text


def test_the_published_rules_are_the_ones_redeem_enforces(api_base):
    data = assert_envelope_ok(_anon(api_base).post(
        api_base + INSPECT, json={"token": "x"}))["data"]
    rules = data["password_rules"]
    assert rules["required"] is True and rules["must_match_confirmation"] is True
    assert isinstance(rules["min_length"], int) and rules["min_length"] >= 1
    assert rules["source"] in ("auth_password_policy", "odoo_core_refuses_only_empty")


def test_forgot_password_answers_the_same_whether_or_not_an_account_matches(
        api_base, person):
    s = _anon(api_base)
    nobody = assert_envelope_ok(s.post(api_base + RESET, json={
        "login": "pytest-nobody-%s@example.invalid" % uuid.uuid4().hex[:8]}))
    assert "If an account matches" in nobody["data"]["message"]
    # The positive half (verification pass: only the miss was tested).
    row, _email = person(send=False)
    somebody = assert_envelope_ok(s.post(api_base + RESET, json={"login": row["login"]}))
    assert somebody["data"] == nobody["data"], (somebody, nobody)
    # A pattern is not a login: `%` matches nothing, and says the same thing.
    pattern = assert_envelope_ok(s.post(api_base + RESET, json={"login": "%@example.invalid"}))
    assert pattern["data"] == nobody["data"]
    r = s.post(api_base + RESET, json={"login": "   "})
    assert_envelope_err(r, 400, "invalid_request")


def test_the_old_letter_link_lands_on_the_app_with_the_same_token(api_base):
    """Every letter sent before handoff 45 carries Odoo's link."""
    s = _anon(api_base)
    for old, new in (("/web/signup", "/app/accept-invite"),
                     ("/web/reset_password", "/app/reset-password")):
        r = s.get(api_base + old, params={"db": "x", "token": "abc_DEF-123",
                                          "redirect": "/app/"},
                  allow_redirects=False)
        assert r.status_code in (301, 302, 303), (old, r.status_code, r.text[:200])
        assert r.headers["Location"].endswith(new + "?token=abc_DEF-123"), r.headers
    r = s.get(api_base + "/web/reset_password", allow_redirects=False)
    assert r.headers.get("Location", "").endswith("/app/forgot-password"), r.headers


# ─── the journey, with a real letter ────────────────────────────────

def test_an_invited_officer_sets_a_password_and_is_signed_in(api_base, client, person):
    row, email = person(send=True)
    url, token, msg = _inbox_link(email, "accept-invite")
    assert "/web/" not in (msg.get("Text") or "") + (msg.get("HTML") or ""), (
        "the letter still links into Odoo")
    s = _anon(api_base)

    data = assert_envelope_ok(s.post(api_base + INSPECT, json={"token": token}))["data"]
    assert data["state"] == "outstanding", data
    assert data["kind"] == "invitation"
    assert data["login"] == row["login"] and data["name"] == row["name"], data

    # Refused in words, nothing spent: the link is still outstanding after.
    r = s.post(api_base + REDEEM, json={"token": token, "password": "",
                                        "confirm_password": ""})
    assert_envelope_err(r, 400, "invalid_request")
    assert "cannot be empty" in r.json()["error"]["message"]
    r = s.post(api_base + REDEEM, json={"token": token, "password": "abc12345XYZ",
                                        "confirm_password": "abc12345XYz"})
    assert_envelope_err(r, 400, "invalid_request")
    assert "do not match" in r.json()["error"]["message"]
    assert assert_envelope_ok(s.post(api_base + INSPECT, json={"token": token}))[
        "data"]["state"] == "outstanding", "a refused attempt spent the link"

    password = "pytest-%s" % uuid.uuid4().hex
    done = assert_envelope_ok(s.post(api_base + REDEEM, json={
        "token": token, "password": password, "confirm_password": password}))["data"]
    assert done["signed_in"] is True and done["access_token"], done
    assert done["login"] == row["login"]

    # The session is the person's own: their roles, not the credential's.
    me = requests.get(api_base + USER.format(id=row["id"]),
                      headers={"Authorization": "Bearer " + done["access_token"]})
    assert me.status_code in (200, 403), me.text   # an asset_user may not read /users
    assert client.get(USER.format(id=row["id"])).json()["data"]["invitation"][
        "state"] == "redeemed"

    # The same link, again: used, said so, and refused.
    data = assert_envelope_ok(s.post(api_base + INSPECT, json={"token": token}))["data"]
    assert data["state"] == "redeemed", data
    r = s.post(api_base + REDEEM, json={"token": token, "password": password,
                                        "confirm_password": password})
    assert_envelope_err(r, 409, "conflict")
    assert r.json()["error"]["details"]["state"] == "redeemed"

    # And the password works on the ordinary sign-in.
    r = s.post(api_base + LOGIN, json={"login": row["login"], "password": password})
    assert r.status_code == 200, r.text

    # And Odoo's own "Security Update: Password Changed" mail did not follow
    # the person's first password into their inbox (handoff 45: it did, on
    # the first run of the browser spec — an Odoo letter with an Odoo link).
    time.sleep(2)
    found = requests.get(MAILPIT + "/api/v1/search", params={
        "query": 'to:%s subject:"Security Update"' % email}, timeout=5).json()
    assert not found.get("messages"), (
        "%d Odoo security notice(s) reached %s after the letter's password "
        "was set" % (len(found["messages"]), email))


def test_a_deactivated_persons_invitation_reads_cancelled(api_base, client, person):
    row, email = person(send=True)
    _url, token, _msg = _inbox_link(email, "accept-invite")
    assert_envelope_ok(client.post(DEACTIVATE.format(id=row["id"])))
    data = assert_envelope_ok(_anon(api_base).post(
        api_base + INSPECT, json={"token": token}))["data"]
    assert data["state"] == "cancelled", data
    assert "no longer valid" in data["message"]


def test_forgot_password_sends_a_reset_link_to_the_app_that_changes_the_password(
        api_base, client, person):
    row, email = person(send=True)
    _url, invite_token, _ = _inbox_link(email, "accept-invite")
    s = _anon(api_base)
    first = "pytest-%s" % uuid.uuid4().hex
    assert_envelope_ok(s.post(api_base + REDEEM, json={
        "token": invite_token, "password": first, "confirm_password": first}))

    assert_envelope_ok(s.post(api_base + RESET, json={"login": row["login"]}))
    _url, token, _ = _inbox_link(email, "reset-password")
    data = assert_envelope_ok(s.post(api_base + INSPECT, json={"token": token}))["data"]
    assert data["state"] == "outstanding" and data["kind"] == "reset", data

    second = "pytest-%s" % uuid.uuid4().hex
    done = assert_envelope_ok(s.post(api_base + REDEEM, json={
        "token": token, "password": second, "confirm_password": second}))["data"]
    assert done["signed_in"] is True
    assert s.post(api_base + LOGIN, json={"login": row["login"],
                                          "password": first}).status_code == 401
    assert s.post(api_base + LOGIN, json={"login": row["login"],
                                          "password": second}).status_code == 200
