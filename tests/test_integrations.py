"""External-system integration endpoints: SAP employee sync + workflow callback."""
import pytest

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


def _callback(client, reference, outcome="queried", comment=None, ref=None):
    return client.post("/api/v1/integrations/workflow/callback", json={
        "reference": reference,
        "workspace_ref": ref or "PYTEST-WORKSPACE-REF-001",
        "outcome": outcome,
        "comment": comment or "Queried by tests/test_integrations",
    })


def test_workflow_callback(client, test_request, capture):
    """POST /api/v1/integrations/workflow/callback — apply a workflow decision.

    Uses outcome=queried which is non-destructive (just logs a comment).

    Two answers are correct and which one you get depends on the TENANT, not
    on the payload: a tenant wired to a WorkSpace applies the outcome, and one
    that never was refuses. No local tenant has an active `workflow.config`
    today (measured: 0 of 8), so the refusal is what this suite sees here.

    What the assertions pin down is handoff 18 item B2 — that the refusal is
    not the one this route used to give. `_workflow_callback_approved` calls
    `get_active_config()`, which raises `UserError` on an unconfigured tenant,
    and `cadra_route` renders `str(e)` — so the DOCUMENTED route answered
    `400 validation_failed` carrying "Please configure one under Settings →
    WorkSpace Integration". An internal navigation path in a published
    envelope, under a code that tells an integrator to fix a payload that is
    perfectly good.
    """
    r = _callback(client, test_request["reference"])
    capture("integrations/workflow_callback", r)

    if r.status_code == 200:
        body = assert_envelope_ok(r)
        assert body["data"]["applied_outcome"] == "queried"
        assert body["data"]["request_reference"] == test_request["reference"]
        assert body["data"]["replayed"] is False
        return

    error = r.json()["error"]
    assert r.status_code == 503, f"unexpected status {r.status_code}: {r.text[:300]}"
    assert error["code"] == "server_misconfigured", (
        "a tenant with no WorkSpace configuration is a tenant-configuration "
        "state, not a caller validation failure")
    assert "Settings" not in error["message"] and "→" not in error["message"], (
        "the envelope names our internal menu structure: " + error["message"])


def test_workflow_callback_replay_is_not_a_second_application(client,
                                                              test_request,
                                                              capture):
    """Handoff 18 item A, at the envelope.

    A second byte-identical POST used to answer `200` and do it all again —
    another dispatch-log row, another chatter post, and another write of the
    configured approved stage, which dragged a request a human had since moved
    onward back to where the approval put it. It now fires on the TRANSITION:
    an outcome already applied is a no-op that answers success.

    "Writes nothing" is proved in the registry, where rows can be counted, by
    `myservice_workflow/tests/test_callback_replay.py`. What is proved here is
    the published contract: same status, and `replayed` says which happened.
    """
    first = _callback(client, test_request["reference"], comment="first")
    second = _callback(client, test_request["reference"], comment="first")
    capture("integrations/workflow_callback_replay", second)

    assert second.status_code == first.status_code, (
        "a replay must answer the same way the original did, not fail")
    if first.status_code != 200:
        # SKIP, not `return`. No local tenant has an active workflow.config
        # (0 of 8) and CI's bootstrap database has none either, so this
        # branch is the one taken on every run today — and a bare `return`
        # made the test PASS having asserted nothing, counting toward the
        # suite's green total. A skip says so out loud. The real "writes
        # nothing" proof is in the registry, where rows can be counted:
        # myservice_workflow/tests/test_callback_replay.py.
        pytest.skip("this tenant has no active workflow.config, so the v1 "
                    "callback refuses 503 and the replay path is unreachable "
                    "from here")

    assert assert_envelope_ok(second)["data"]["replayed"] is True, (
        "the second identical callback was applied a second time")


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
