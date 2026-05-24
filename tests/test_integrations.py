"""External-system integration endpoints: SAP employee sync + workflow callback."""
from .conftest import assert_envelope_ok


def test_sap_employee_sync(client, capture):
    """POST /api/v1/integrations/sap/employee-sync — minimal SAP-shaped payload.

    The handler delegates to nrs.sap.sync.log.process_sap_payload(...) which
    has its own validation. We send a deliberately minimal payload; either
    a success envelope OR a model-side validation error is acceptable, as
    long as the API envelope shape is right.
    """
    r = client.post("/api/v1/integrations/sap/employee-sync", json={
        "ir_number": "PYTEST-IRTEST-001",
        "userId": "pytest.user@example.com",
        "firstName": "Py",
        "lastName": "Test",
        "department": "Pytest",
        "jobTitle": "Smoke Tester",
        "status": "active",
    })
    capture("integrations/sap_employee_sync", r)
    # PRD envelope, success or error
    assert r.status_code in (200, 201, 400, 500), f"unexpected status {r.status_code}"
    body = r.json()
    assert ("data" in body and "meta" in body) or "error" in body


def test_workflow_callback(client, test_request, capture):
    """POST /api/v1/integrations/workflow/callback — apply a workflow decision.

    Uses outcome=queried which is non-destructive (just logs a comment).
    """
    r = client.post("/api/v1/integrations/workflow/callback", json={
        "reference": test_request["reference"],
        "workspace_ref": "PYTEST-WORKSPACE-REF-001",
        "outcome": "queried",
        "comment": "Queried by tests/test_integrations.test_workflow_callback",
    })
    capture("integrations/workflow_callback", r)
    body = assert_envelope_ok(r)
    assert body["data"]["applied_outcome"] == "queried"
    assert body["data"]["request_reference"] == test_request["reference"]


def test_workflow_callback_unknown_reference(client, capture):
    """Callback with a nonexistent reference → 404."""
    r = client.post("/api/v1/integrations/workflow/callback", json={
        "reference": "NO-SUCH-REQUEST-12345",
        "outcome": "approved",
    })
    capture("integrations/workflow_callback_404", r)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_workflow_callback_invalid_outcome(client, test_request, capture):
    """Callback with an invalid outcome → 400."""
    r = client.post("/api/v1/integrations/workflow/callback", json={
        "reference": test_request["reference"],
        "outcome": "definitely-not-a-real-outcome",
    })
    capture("integrations/workflow_callback_bad_outcome", r)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_request"
