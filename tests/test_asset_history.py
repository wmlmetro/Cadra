"""`GET /assets/<id>/history` over the API — handoff 27, INT-10.

The ordering, the join and the honesty rules are asserted against the builder
in `myservice_api/tests/test_asset_history.py`, where time can be frozen and
a reconstructed link can be made. What is asserted HERE is what only a real
request can show: that the route publishes that builder inside the envelope,
that a real custody transfer and a real move made over HTTP come back as
events with the grades the contract promises, and that a bad `sort` is a 400
rather than a default.

`evidence` is asserted for the same reason `test_custody.py` asserts
`source`: it is what tells an append-only link from a line in a message log,
and a reader has to be able to see that without knowing to ask.
"""
import pytest

from .conftest import assert_envelope_err, assert_envelope_ok

_GRADES = ["append_only", "system_stamp", "guarded_record",
           "editable_record", "chatter"]

_EVENT_KEYS = {"id", "type", "title", "summary", "at", "at_precision",
               "actor", "actor_name", "evidence", "reconstructed", "source",
               "record", "detail"}


def _history(client, asset_id, **params):
    r = client.get(f"/api/v1/assets/{asset_id}/history", params=params)
    return r, assert_envelope_ok(r)["data"]


def _new_asset(client, test_location, name):
    """An asset of this test's own, so its history is exactly what we did.

    The session-scoped `test_asset` is moved about by every other module; a
    count asserted against it would be asserting about their order.
    """
    r = client.post("/api/v1/assets", json={
        "name": name,
        "category_id": 1,  # as the session `test_asset` fixture does
        "location_id": test_location["id"]})
    return assert_envelope_ok(r, expected_status=201)["data"]


def _assert_registration_is_oldest(client, asset_id):
    """Nothing may be listed as older than the registration it followed.

    These tests register an asset and act on it within the same second, which
    is exactly the case that sorted wrongly: a whole-second timestamp compared
    raw against `create_date`'s microseconds put the act BEFORE the asset
    existed. Seen on the screen in handoff 27 before any test saw it.
    """
    _, oldest = _history(client, asset_id, sort="oldest")
    assert oldest["events"][0]["type"] == "registered"
    _, newest = _history(client, asset_id)
    assert newest["events"][-1]["type"] == "registered"


def _two_employees(client):
    r = client.get("/api/v1/identity/employees", params={"limit": 2})
    rows = (r.json().get("data") or []) if r.status_code == 200 else []
    return (rows[0]["id"], rows[1]["id"]) if len(rows) >= 2 else None


def test_history_is_published_in_the_envelope(client, test_asset, capture):
    """GET /api/v1/assets/<id>/history — the shape, on a lived-in asset."""
    r, data = _history(client, test_asset["id"])
    capture("assets/history", r)
    assert data["asset"]["id"] == test_asset["id"]
    assert data["order"] == "newest_first"
    assert set(data) == {"asset", "order", "summary", "fidelity", "events"}
    assert data["summary"]["statement"]
    assert data["summary"]["events"] == len(data["events"])
    for event in data["events"]:
        assert set(event) == _EVENT_KEYS
        assert event["evidence"] in _GRADES


def test_the_boundary_arrives_with_the_events(client, test_asset):
    """What it cannot say is on EVERY response, not only an empty one."""
    _, data = _history(client, test_asset["id"])
    fidelity = data["fidelity"]
    assert [g["grade"] for g in fidelity["evidence_grades"]] == _GRADES
    assert all(g["meaning"] for g in fidelity["evidence_grades"])
    named = {n["event"] for n in fidelity["not_recorded"]}
    assert {"financial_change", "sap_change", "provenance_change",
            "deleted_records"} <= named
    assert fidelity["custody"]["statement"]
    assert fidelity["registered_at"]


def test_a_new_asset_says_it_has_no_history_in_words(client, test_location):
    """The defect that produced the handoff was an empty panel."""
    asset = _new_asset(client, test_location, "pytest-history-empty")
    _, data = _history(client, asset["id"])
    assert data["summary"]["events_after_registration"] == 0
    assert data["summary"]["statement"].startswith(
        "There is no recorded history for this asset")
    types = [e["type"] for e in data["events"]]
    assert "registered" in types
    registered = next(e for e in data["events"] if e["type"] == "registered")
    assert registered["evidence"] == "system_stamp"
    # Handoff 08: a client acts as itself, so the registration names it.
    assert registered["actor"] is not None


def test_a_custody_transfer_is_an_append_only_event(client, test_location):
    pair = _two_employees(client)
    if not pair:
        pytest.skip("tenant has no two employees to transfer between")
    asset = _new_asset(client, test_location, "pytest-history-custody")
    r = client.post(f"/api/v1/assets/{asset['id']}/transfer-custody",
                    json={"to_custodian_id": pair[0],
                          "reason": "test_asset_history.custody"})
    link_id = assert_envelope_ok(r)["data"]["custody_change"]["custody_id"]
    _, data = _history(client, asset["id"])
    events = [e for e in data["events"] if e["type"] == "custody_changed"]
    assert len(events) == 1, (
        "`custodian_id` is tracked as well; the chain supersedes that row "
        "and the change must be listed once")
    event = events[0]
    assert event["record"] == {"model": "nrs.asset.custody", "id": link_id}
    assert event["evidence"] == "append_only"
    assert event["reconstructed"] is False
    # See test_custody.py: `test` is `api_transfer` relabelled by the
    # credential. Either is a source; null would mean it stopped travelling.
    assert event["source"] in ("api_transfer", "test")
    assert event["actor"] is not None
    assert event["detail"]["reason"] == "test_asset_history.custody"
    _assert_registration_is_oldest(client, asset["id"])
    assert data["summary"]["events_after_registration"] >= 1
    assert not data["summary"]["statement"].startswith("There is no")


def test_a_move_is_one_event_and_says_what_its_record_is_worth(
        client, test_location, any_location):
    """`POST /move` leaves a transfer row AND a chatter row: one line."""
    if any_location == test_location["id"]:
        pytest.skip("tenant has no second location to move to")
    asset = _new_asset(client, test_location, "pytest-history-move")
    r = client.post(f"/api/v1/assets/{asset['id']}/move",
                    json={"to_location_id": any_location,
                          "reason": "test_asset_history.move"})
    transfer = assert_envelope_ok(r)["data"]["transfer"]
    _, data = _history(client, asset["id"])
    moves = [e for e in data["events"] if e["type"] == "location_moved"]
    assert len(moves) == 1
    move = moves[0]
    # NOT append_only. A transfer row is editable and deletable by any
    # asset manager, and the history must not dress it as more.
    assert move["evidence"] == "editable_record"
    assert move["detail"]["transfer"]["reference"] == transfer["reference"]
    assert move["detail"]["transfer"]["reason"] == "test_asset_history.move"
    assert move["detail"]["records"] == ["nrs.asset.transfer", "mail.message"]
    assert move["actor"] is not None
    _assert_registration_is_oldest(client, asset["id"])


def test_a_patched_location_is_a_move_with_only_a_message_behind_it(
        client, test_location, any_location):
    """`location_id` is PATCH-writable and PATCH writes no transfer row."""
    if any_location == test_location["id"]:
        pytest.skip("tenant has no second location to move to")
    asset = _new_asset(client, test_location, "pytest-history-patch-move")
    r = client.patch(f"/api/v1/assets/{asset['id']}",
                     json={"location_id": any_location})
    assert_envelope_ok(r)
    _, data = _history(client, asset["id"])
    moves = [e for e in data["events"] if e["type"] == "location_moved"]
    assert len(moves) == 1
    assert moves[0]["evidence"] == "chatter"
    assert moves[0]["detail"]["transfer"] is None
    _assert_registration_is_oldest(client, asset["id"])
    assert data["summary"]["by_evidence"]["chatter"] >= 1


def test_sort_oldest_is_the_exact_reverse(client, test_asset):
    _, newest = _history(client, test_asset["id"])
    _, oldest = _history(client, test_asset["id"], sort="oldest")
    assert oldest["order"] == "oldest_first"
    assert ([e["id"] for e in oldest["events"]]
            == [e["id"] for e in reversed(newest["events"])])
    _, explicit = _history(client, test_asset["id"], sort="newest")
    assert ([e["id"] for e in explicit["events"]]
            == [e["id"] for e in newest["events"]])


def test_a_bad_sort_is_a_400_not_a_default(client, test_asset):
    r = client.get(f"/api/v1/assets/{test_asset['id']}/history",
                   params={"sort": "latest"})
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["allowed_values"] == ["newest", "oldest"]


def test_history_of_an_unknown_asset_is_a_404(client):
    r = client.get("/api/v1/assets/999999999/history")
    assert_envelope_err(r, 404, "not_found")


def test_the_history_has_no_write_endpoint(client, test_asset):
    """It is a reading of other records. There is nothing to POST."""
    r = client.post(f"/api/v1/assets/{test_asset['id']}/history", json={})
    assert r.status_code in (404, 405)
