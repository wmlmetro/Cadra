"""The receipt gates over HTTP — handoff 57, kept by handoff 58.

The whole chain needs seven different people (the no-two-gates rule), which
one API credential cannot be; it is walked in-registry by
`myservice_api/tests/test_receipt_gates.py` and in the browser by spec 57.
What THIS file proves is what only the published surface can show:

* with the tenant's switch on, `POST /assets` (INT-03) answers a CANDIDATE —
  `captured`, no label — and with it off, exactly what it always answered;
* the register hides it (`GET /assets`), `?register_state=any` and
  `GET /candidates` find it, `GET /assets/<id>` reaches it;
* the refusals have the envelope's shape: the no-two-gates sentence as a
  409 with `details.reason = segregation_of_duties`, a wrong state as a 409
  `invalid_state`, an unaccepted body key as a 400 with nothing written.

The switch is put back as it was found, whatever happens (`receipt_switch`,
tests/conftest.py).
"""
import time
import uuid

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok


def _uniq(prefix):
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


def _receive(client, **body):
    """INT-03's call, as Vendra makes it: a create, answered 201. The body
    is filled in by `tests/gates.py` (a serial-mode class takes a serial,
    make and model when the gates are on — handoff 58, Section 12)."""
    return assert_envelope_ok(
        client.post("/api/v1/assets", json=gates.receipt_body(client, **body)),
        201)["data"]


def _ids(client, path, **params):
    rows = assert_envelope_ok(client.get(path, params=params))["data"]
    return {r["id"] for r in rows}


def test_with_the_switch_on_a_receipt_is_a_candidate_the_register_hides(
        client, receipt_switch):
    receipt_switch(True)
    name = _uniq("pytest-gates-candidate")
    a = _receive(client, name=name, serial_number=_uniq("SN"),
                 grn_reference="GRN-PYTEST-57")
    assert a["register_state"] == "captured"
    assert a["tag"] is None, "the mint moved to request-tagging"
    assert a["gates"]["waiting_on"] == "store"
    assert any(x["action"] == "submit" and x["can_fire"]
               for x in a["gates"]["available"])

    assert a["id"] not in _ids(client, "/api/v1/assets", q=name)
    assert a["id"] in _ids(client, "/api/v1/assets", q=name,
                           register_state="any")
    assert a["id"] in _ids(client, "/api/v1/assets", q=name,
                           register_state="captured")
    assert a["id"] in _ids(client, "/api/v1/candidates", q=name,
                           waiting_on="store")
    assert a["id"] not in _ids(client, "/api/v1/candidates", q=name,
                               waiting_on="iad")
    got = assert_envelope_ok(client.get(f"/api/v1/assets/{a['id']}"))["data"]
    assert got["register_state"] == "captured"


def test_with_the_switch_off_a_receipt_is_registered_and_tagged_at_once(
        client, receipt_switch):
    receipt_switch(False)
    a = _receive(client, name=_uniq("pytest-gates-legacy"))
    assert a["register_state"] == "registered"
    assert a["tag"], "switch off: the label is minted at creation, as before"
    assert a["gates"] == {"waiting_on": None, "state_since": None,
                          "available": [],
                          # handoff 60: the maker's submission, none
                          "registration": None}


def test_the_refusals_have_the_envelope_and_write_nothing(client, receipt_switch):
    receipt_switch(True)
    a = _receive(client, name=_uniq("pytest-gates-refusals"))
    base = f"/api/v1/assets/{a['id']}/gates"

    # A key the action does not accept: 400, nothing moved.
    body = assert_envelope_err(
        client.post(f"{base}/submit", json={"state": "registered"}),
        400, "invalid_request")
    assert body["error"]["details"]["rejected_fields"] == ["state"]

    # From the wrong state.
    body = assert_envelope_err(client.post(f"{base}/approve", json={}),
                               409, "conflict")
    assert body["error"]["details"]["reason"] == "invalid_state"

    moved = assert_envelope_ok(client.post(f"{base}/submit", json={}))["data"]
    assert moved["register_state"] == "vfm_pending"
    assert moved["gates"]["waiting_on"] == "iad"

    # The same credential — the person who received it — may not verify it.
    body = assert_envelope_err(client.post(f"{base}/verify", json={
        "checklist": {"quantity": True, "specification": True,
                      "condition": True, "price": True},
        "attachments": [{"name": "e.txt", "data": "ZXZpZGVuY2U="}]}),
        409, "conflict")
    err = body["error"]
    assert err["details"]["reason"] == "segregation_of_duties"
    assert err["message"].startswith("You received this unit on ")
    assert err["message"].endswith("; a different person must verify it.")
    assert "permission" not in err["message"].lower()

    # A query needs words — refused before the rule is even reached.
    body = assert_envelope_err(client.post(f"{base}/query", json={
        "reason": "  "}), 400, "validation_failed")

    after = assert_envelope_ok(client.get(f"/api/v1/assets/{a['id']}"))["data"]
    assert after["register_state"] == "vfm_pending"
    verify = [x for x in after["gates"]["available"]
              if x["action"] == "verify"]
    assert verify and verify[0]["can_fire"] is False
    assert verify[0]["refusal"].endswith("a different person must verify it.")


def test_register_state_any_needs_candidates_read(client):
    """Holding it (the suite's credential holds `admin`) answers; an unknown
    value is a 400 naming the allowed values."""
    assert_envelope_ok(client.get("/api/v1/assets",
                                  params={"register_state": "any",
                                          "limit": 1}))
    body = assert_envelope_err(
        client.get("/api/v1/assets", params={"register_state": "nearly"}),
        400, "invalid_request")
    assert "any" in body["error"]["details"]["allowed_values"]
    body = assert_envelope_err(
        client.get("/api/v1/candidates", params={"waiting_on": "nobody"}),
        400, "invalid_request")
