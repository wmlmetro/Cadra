"""POST /api/v1/auth/token — JWT mint endpoint."""
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
