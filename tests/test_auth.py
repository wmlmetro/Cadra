"""POST /api/v1/auth/token — JWT mint endpoint."""
import json

import requests

from .conftest import assert_envelope_err, assert_envelope_ok


def test_mint_token_success(api_base, creds, capture):
    """Happy path: valid client_id + secret returns 200 + access_token."""
    r = requests.post(f"{api_base}/api/v1/auth/token", json={
        "client_id": creds["CLIENT_ID"],
        "client_secret": creds["CLIENT_SECRET"],
    })
    capture("auth/token_success", r)
    body = assert_envelope_ok(r, expected_status=200)
    assert body["data"]["token_type"] == "Bearer"
    assert body["data"]["access_token"].startswith("eyJ")
    assert body["data"]["expires_in"] > 0
    assert "scope" in body["data"]


def test_mint_token_missing_client_id(api_base, capture):
    """Missing client_id returns 400 invalid_request."""
    r = requests.post(f"{api_base}/api/v1/auth/token", json={
        "client_secret": "anything",
    })
    capture("auth/token_missing_client_id", r)
    assert_envelope_err(r, expected_status=400, expected_code="invalid_request")


def test_mint_token_wrong_secret(api_base, creds, capture):
    """Wrong secret returns 401 unauthorized."""
    r = requests.post(f"{api_base}/api/v1/auth/token", json={
        "client_id": creds["CLIENT_ID"],
        "client_secret": "completely-wrong-secret",
    })
    capture("auth/token_wrong_secret", r)
    assert_envelope_err(r, expected_status=401, expected_code="unauthorized")


# ─── one body for every cause (handoff 12 B) ─────────────────────────

def _token_401_body(api_base, client_id, client_secret):
    """POST /auth/token and return the error body with the correlation id
    stripped — that is the ONE field allowed to differ."""
    r = requests.post(f"{api_base}/api/v1/auth/token", json={
        "client_id": client_id, "client_secret": client_secret,
    })
    assert r.status_code == 401, (
        f"expected 401 for client_id={client_id!r}, got {r.status_code}: "
        f"{r.text[:200]}")
    body = r.json()
    body["error"].pop("request_id", None)
    return json.dumps(body, sort_keys=True)


def test_the_401_body_is_identical_for_every_failure_cause(api_base, creds, capture):
    """Wrong secret, unknown client and a wrong-case client id must be
    indistinguishable to the caller.

    Distinguishing them would turn /auth/token into a client-id enumeration
    oracle — one probe per guess, with the answer in the response. The cause
    goes to the `cadra.auth` log against the request_id instead; see
    docs/api/reading-an-auth-failure.md.

    The archived-client case needs a client this suite cannot create, so it
    is covered in myservice_api/tests/test_auth_failure_causes.py.
    """
    real_id = creds["CLIENT_ID"]
    swapped = real_id.upper() if real_id.lower() == real_id else real_id.lower()

    bodies = {
        "bad_secret": _token_401_body(api_base, real_id, "completely-wrong"),
        "no_such_client": _token_401_body(
            api_base, "cadra_no_such_client_exists", "irrelevant"),
        "case_mismatch": _token_401_body(
            api_base, swapped, creds["CLIENT_SECRET"]),
    }

    distinct = set(bodies.values())
    assert len(distinct) == 1, (
        "the failure causes are distinguishable from the response:\n  "
        + "\n  ".join(f"{k} -> {v}" for k, v in sorted(bodies.items())))


def test_a_wrong_case_client_id_is_still_refused(api_base, creds, capture):
    """`=` on a Postgres varchar is case-sensitive, so `Vendra` and `vendra`
    are different clients — deliberately, and the 401 is correct. What is
    new is that the server now says which it was, in the log."""
    real_id = creds["CLIENT_ID"]
    swapped = real_id.upper() if real_id.lower() == real_id else real_id.lower()
    if swapped == real_id:
        import pytest
        pytest.skip("this tenant's client_id has no case to swap")

    r = requests.post(f"{api_base}/api/v1/auth/token", json={
        "client_id": swapped, "client_secret": creds["CLIENT_SECRET"],
    })
    capture("auth/token_case_mismatch", r)
    assert_envelope_err(r, expected_status=401, expected_code="unauthorized")


def test_every_401_carries_a_request_id_to_quote(api_base, capture):
    """The id is the whole mechanism: it is what makes the log line
    findable, and it used to be a token with nothing behind it."""
    r = requests.post(f"{api_base}/api/v1/auth/token", json={
        "client_id": "cadra_no_such_client_exists", "client_secret": "x",
    })
    capture("auth/token_request_id", r)
    body = r.json()
    assert body["error"].get("request_id"), (
        "a 401 with no correlation id cannot be debugged at all")


# A JWT header that is valid JSON but not an OBJECT.
#   base64url("[]") . base64url("{}") . base64url("sig")
# Every segment decodes, and every segment is the wrong shape.
_NON_OBJECT_JWT = "W10.e30.c2ln"


def test_a_token_whose_header_is_not_an_object_gets_a_401_envelope(
        api_base, capture):
    """Not an HTML 500, and not on every route at once.

    `jwt_decode` read `header.get("alg")` straight off whatever the header
    segment decoded to. `[]`, `"x"` and `1` are all valid JSON and none has
    `.get`, so the AttributeError escaped the decoder, escaped `require_jwt`
    (which catches only JwtError) and escaped `cadra_route` — whose try
    starts AFTER the auth call — and Odoo rendered its own HTML error page
    at an unauthenticated caller. One request, no credentials, every
    authenticated route in the API.

    Handoff 15 settled the shape rather than widening the handler: a JWT
    header is required to be an object, and now something says so.
    """
    r = requests.get(f"{api_base}/api/v1/assets",
                     headers={"Authorization": f"Bearer {_NON_OBJECT_JWT}"})
    capture("auth/token_header_not_an_object", r)
    assert r.headers.get("Content-Type", "").startswith("application/json"), (
        "an HTML body here means the exception escaped the envelope "
        "entirely: %r" % r.text[:200])
    assert_envelope_err(r, expected_status=401, expected_code="unauthorized")


def test_a_token_whose_payload_is_not_an_object_gets_a_401_envelope(
        api_base, capture):
    """The same shape one segment along, and reachable before handoff 15
    regardless of what the decoder caught — `exp` is read outside the try."""
    header = "eyJhbGciOiJIUzI1NiJ9"          # {"alg":"HS256"}
    r = requests.get(f"{api_base}/api/v1/assets",
                     headers={"Authorization": f"Bearer {header}.W10.c2ln"})
    capture("auth/token_payload_not_an_object", r)
    assert r.headers.get("Content-Type", "").startswith("application/json"), (
        "an HTML body here means the exception escaped the envelope: %r"
        % r.text[:200])
    assert_envelope_err(r, expected_status=401, expected_code="unauthorized")
