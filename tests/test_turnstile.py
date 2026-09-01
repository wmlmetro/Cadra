"""Cloudflare Turnstile protection on POST /api/v1/auth/login.

Turnstile is per-tenant and opt-in: it is active only when
`myservice_api.turnstile_secret` is set (bootstrap seeds it from
CADRA_TURNSTILE_SECRET). Both states are correct deployments, so this module
first works out which one it is running against, then asserts the property
that matters for that state:

  - off  → the challenge is a complete no-op, including for clients that
           send a `turnstile_token` anyway
  - on   → a login with no token, or a token Cloudflare rejects, is refused
           before the credentials are ever checked

CI runs with the secret unset (`.env.example` ships it blank), so the "off"
tests are the ones that gate merges — they are the regression guard for every
tenant provisioned before this feature existed.
"""
import pytest
import requests

from .conftest import assert_envelope_err


# Credentials that cannot belong to a real user. Deliberately *present* —
# both probes below need to get past the login/password presence check so
# that what they observe is the Turnstile gate, not field validation.
BOGUS_LOGIN = "cadra-turnstile-probe@example.invalid"
BOGUS_PASSWORD = "not-a-real-password"


def _login(api_base, **body):
    return requests.post(f"{api_base}/api/v1/auth/login", json=body, timeout=30)


@pytest.fixture(scope="session")
def turnstile_enforced(api_base):
    """True when this deployment has a Turnstile secret configured.

    Nothing reports the setting, so probe it: bad credentials with no
    challenge token come back 401 when Turnstile is off (the credentials are
    what failed) and 400 when it is on (the missing token is rejected first).
    """
    r = _login(api_base, login=BOGUS_LOGIN, password=BOGUS_PASSWORD)
    if r.status_code == 401:
        return False
    if r.status_code == 400:
        return True
    pytest.fail(
        f"POST /auth/login with bad credentials returned HTTP {r.status_code}; "
        f"expected 401 (Turnstile off) or 400 (Turnstile on).\n{r.text[:300]}"
    )


# ─── the tenant advertises its own state ─────────────────────────────

def test_brand_reports_turnstile_state(api_base, turnstile_enforced, capture):
    """GET /api/v1/brand agrees with what /auth/login actually enforces.

    One bundle serves every tenant, so the frontend can't decide from the
    build-time sitekey whether to show a challenge — it asks this endpoint.
    If the two ever disagree, a tenant either gets a widget its API ignores
    or a login it can't complete.
    """
    r = requests.get(f"{api_base}/api/v1/brand", timeout=30)
    capture("turnstile/brand_flag", r)
    assert r.status_code == 200, r.text[:300]
    data = r.json()["data"]
    assert data["turnstile"] is turnstile_enforced, (
        f"/api/v1/brand says turnstile={data['turnstile']} but /auth/login "
        f"{'enforces' if turnstile_enforced else 'does not enforce'} it"
    )
    assert "secret" not in r.text.lower(), "brand response mentions a secret"


# ─── field validation runs first, in both states ─────────────────────

def test_missing_credentials_fail_before_turnstile(api_base, capture):
    """A body with no `password` is rejected on the fields, not the challenge.

    Order matters: validating the cheap local fields first means a malformed
    or empty request never costs a round-trip to Cloudflare.
    """
    r = _login(api_base, login=BOGUS_LOGIN)
    capture("turnstile/missing_credentials", r)
    body = assert_envelope_err(r, expected_status=400, expected_code="invalid_request")
    assert "password" in body["error"]["message"], (
        f"expected the login/password validation error, got: {body['error']['message']}"
    )


# ─── Turnstile not configured (the default, and what CI runs) ────────

def test_bad_credentials_still_401_when_unconfigured(api_base, turnstile_enforced, capture):
    """With no secret set, login behaves exactly as it did pre-Turnstile."""
    if turnstile_enforced:
        pytest.skip("Turnstile is configured on this deployment")
    r = _login(api_base, login=BOGUS_LOGIN, password=BOGUS_PASSWORD)
    capture("turnstile/unconfigured_bad_credentials", r)
    assert_envelope_err(r, expected_status=401, expected_code="unauthorized")


def test_unexpected_token_is_ignored_when_unconfigured(api_base, turnstile_enforced, capture):
    """A client that sends a token to an unprotected tenant is not punished.

    The frontend bundle carries a sitekey or it doesn't; a bundle built with
    one must keep working against a tenant that has no secret configured.
    """
    if turnstile_enforced:
        pytest.skip("Turnstile is configured on this deployment")
    r = _login(
        api_base,
        login=BOGUS_LOGIN,
        password=BOGUS_PASSWORD,
        turnstile_token="a-token-nobody-is-going-to-verify",
    )
    capture("turnstile/unconfigured_with_token", r)
    assert_envelope_err(r, expected_status=401, expected_code="unauthorized")


# ─── Turnstile configured ────────────────────────────────────────────

def test_missing_token_rejected_when_configured(api_base, turnstile_enforced, capture):
    """No `turnstile_token` → 400, and the credentials are never checked."""
    if not turnstile_enforced:
        pytest.skip("Turnstile is not configured on this deployment")
    r = _login(api_base, login=BOGUS_LOGIN, password=BOGUS_PASSWORD)
    capture("turnstile/missing_token", r)
    body = assert_envelope_err(r, expected_status=400, expected_code="invalid_request")
    assert "turnstile_token" in body["error"]["message"]


def test_invalid_token_rejected_when_configured(api_base, turnstile_enforced, capture):
    """A token Cloudflare refuses → 400, with no detail handed back.

    The siteverify error-codes distinguish a stale token from a bad secret
    key. That belongs in the server log, not in a response to a caller who
    may be probing for a misconfiguration.
    """
    if not turnstile_enforced:
        pytest.skip("Turnstile is not configured on this deployment")
    r = _login(
        api_base,
        login=BOGUS_LOGIN,
        password=BOGUS_PASSWORD,
        turnstile_token="definitely-not-a-valid-turnstile-response-token",
    )
    capture("turnstile/invalid_token", r)
    if r.status_code == 502:
        pytest.skip("could not reach Cloudflare siteverify from the API host")
    if r.status_code == 401:
        # The challenge passed and the request fell through to credentials,
        # which means this deployment's secret accepts any token — i.e. it is
        # Cloudflare's always-passes test key. Nothing to assert about
        # rejection here; that needs a real key or the always-fails test key.
        pytest.skip("configured secret accepts any token (always-passes test key)")
    body = assert_envelope_err(r, expected_status=400, expected_code="invalid_request")
    assert "error-codes" not in r.text and "invalid-input" not in r.text, (
        f"siteverify diagnostics leaked to the client: {body['error']}"
    )
