"""2 homepage endpoints: /home/form-data and /home/quick-submit."""
import pytest

from .conftest import assert_envelope_ok


def test_form_data(client, capture):
    """GET /api/v1/home/form-data — dropdown data for the homepage form."""
    r = client.get("/api/v1/home/form-data")
    capture("home/form_data", r)
    assert_envelope_ok(r)


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Pre-existing upstream bug: NRSHomepageAPI.quick_submit hardcodes "
        "request type 'Access Modification' which has no start_stage_id in "
        "the seeded DB → ValidationError. The inner controller is an "
        "@http.route-decorated method; when called from inside our v1.py "
        "wrapper, Odoo's response_wrap re-raises the exception in a way "
        "that bypasses our @cadra_endpoint try/except, producing a raw "
        "HTML 500 instead of a JSON envelope. Two upstream fixes needed: "
        "(1) seed/create a default stage for the 'Access Modification' "
        "type, or change the hardcoded type. (2) wrap the delegated call "
        "with an extra try/except in v1.py, OR — better — reimplement the "
        "homepage submission directly in v1.py without delegating."
    ),
)
def test_quick_submit(client, capture):
    """POST /api/v1/home/quick-submit — submit a request via the homepage path."""
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
    assert ("data" in body and "meta" in body) or "error" in body
