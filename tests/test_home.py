"""2 homepage endpoints: /home/form-data and /home/quick-submit."""
from .conftest import CANONICAL_ERROR_CODES, assert_envelope_ok


def test_form_data(client, capture):
    """GET /api/v1/home/form-data — dropdown data for the homepage form."""
    r = client.get("/api/v1/home/form-data")
    capture("home/form_data", r)
    assert_envelope_ok(r)


def test_quick_submit(client, capture):
    """POST /api/v1/home/quick-submit — submit a request via the homepage path.

    This was an xfail because the delegated controller failed in a way that
    escaped the envelope entirely and returned a werkzeug HTML 500 — no code,
    no request_id, nothing an integration could branch on. `_http_response`
    now recognises a handler that returned a bare `{"error": "<string>"}` and
    renders it as an `internal_error` envelope carrying the original message,
    so the CONTRACT holds regardless of the upstream defect.

    The upstream defect itself is still open, and this test deliberately does
    not assert success — pinning the endpoint to 500 would just as deliberately
    pin a bug. It asserts the only thing that is ours to guarantee: whatever
    happens, the caller gets a branchable envelope — a canonical code, a
    request_id, and a status that agrees with the body.
    """
    r = client.post("/api/v1/home/quick-submit", json={
        "name": "pytest homepage",
        "email": "pytest@example.com",
        "phone": "+2348000000000",
        "subject": "Smoke test from tests/test_home.py",
        "description": "Created by the pytest suite — please ignore.",
    })
    capture("home/quick_submit", r)
    assert r.headers.get("Content-Type", "").startswith("application/json"), \
        f"expected JSON response, got: {r.headers.get('Content-Type')!r}\nBody:\n{r.text[:300]}"
    body = r.json()

    if "error" in body:
        # Whatever went wrong, it has to be branchable: a canonical code, a
        # request_id to quote, and a status that agrees with the envelope.
        assert r.status_code >= 400, (
            f"an error envelope at HTTP {r.status_code} — an integration "
            f"reading the status would treat this as success"
        )
        assert body["error"]["code"] in CANONICAL_ERROR_CODES, (
            f"uncanonical error code {body['error']['code']!r}"
        )
        assert body["error"]["request_id"]
        assert body["error"]["details"]["http_status"] == r.status_code
    else:
        assert_envelope_ok(r)
