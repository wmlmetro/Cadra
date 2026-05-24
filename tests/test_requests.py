"""All 8 Service Request endpoints."""
import time

from .conftest import assert_envelope_ok


def test_list(client, capture):
    """GET /api/v1/requests — paginated list."""
    r = client.get("/api/v1/requests", params={"limit": 5})
    capture("requests/list", r)
    body = assert_envelope_ok(r)
    assert isinstance(body["data"], list)
    assert "pagination" in body


def test_list_filtered(client, capture):
    """GET /api/v1/requests?q=INCIDENT — narrowing filter."""
    r = client.get("/api/v1/requests", params={"q": "INCIDENT", "limit": 10})
    capture("requests/list_filtered", r)
    assert_envelope_ok(r)


def test_get_by_id(client, test_request, capture):
    """GET /api/v1/requests/<id>?include=routes."""
    r = client.get(f"/api/v1/requests/{test_request['id']}",
                   params={"include": "routes"})
    capture("requests/get_by_id", r)
    body = assert_envelope_ok(r)
    assert body["data"]["id"] == test_request["id"]
    assert "available_routes" in body["data"]


def test_get_by_reference(client, test_request, capture):
    """GET /api/v1/requests/by-reference/<ref>."""
    r = client.get(f"/api/v1/requests/by-reference/{test_request['reference']}")
    capture("requests/get_by_reference", r)
    body = assert_envelope_ok(r)
    assert body["data"]["reference"] == test_request["reference"]


def test_get_by_reference_not_found(client, capture):
    """Nonexistent reference → 404."""
    r = client.get("/api/v1/requests/by-reference/NO-SUCH-REF")
    capture("requests/get_by_reference_not_found", r)
    assert r.status_code == 404


def test_create(client, test_location, test_asset, capture):
    """POST /api/v1/requests — create with 201."""
    r = client.post("/api/v1/requests", json={
        "type_id": 1,
        "category_id": 5,
        "priority": "3",
        "request_text": f"<p>test_create at {time.time()}</p>",
        "location_id": test_location["id"],
        "nrs_asset_id": test_asset["id"],
    })
    capture("requests/create", r)
    body = assert_envelope_ok(r, expected_status=201)
    assert body["data"]["id"] > 0
    assert body["data"]["reference"]
    assert body["data"]["stage"]["name"]


def test_patch(client, test_request, capture):
    """PATCH /api/v1/requests/<id> — partial update."""
    r = client.patch(f"/api/v1/requests/{test_request['id']}", json={
        "priority": "4",
        "response_text": "<p>patched by test_requests.test_patch</p>",
    })
    capture("requests/patch", r)
    body = assert_envelope_ok(r)
    assert body["data"]["priority"] == "4"


def test_patch_rejects_stage_id(client, test_request, capture):
    """PATCH with stage_id should be rejected with a warning + hint."""
    r = client.patch(f"/api/v1/requests/{test_request['id']}", json={
        "stage_id": 99,
    })
    capture("requests/patch_stage_rejected", r)
    body = assert_envelope_ok(r)
    assert "_warnings" in body["data"]
    assert "stage_id" in body["data"]["_warnings"]["rejected_fields"]


def test_assign(client, test_request, capture):
    """POST /api/v1/requests/<id>/assign — set the assignee."""
    r = client.post(f"/api/v1/requests/{test_request['id']}/assign", json={
        "user_id": 2,
    })
    capture("requests/assign", r)
    body = assert_envelope_ok(r)
    assert body["data"]["assignee"]["id"] == 2


def test_transition(client, test_location, test_asset, capture):
    """POST /api/v1/requests/<id>/transition — fire the first available route.

    Uses a freshly-created request so this test is independent of others
    that may have already transitioned the shared `test_request` fixture.
    """
    create_r = client.post("/api/v1/requests", json={
        "type_id": 1,
        "category_id": 5,
        "request_text": f"<p>transition test {time.time()}</p>",
        "location_id": test_location["id"],
        "nrs_asset_id": test_asset["id"],
    })
    body = assert_envelope_ok(create_r, expected_status=201)
    req_id = body["data"]["id"]
    routes = body["data"].get("available_routes", [])
    if not routes:
        capture("requests/transition_skipped", create_r)
        return  # nothing to transition to from initial stage

    r = client.post(f"/api/v1/requests/{req_id}/transition", json={
        "route_id": routes[0]["id"],
    })
    capture("requests/transition", r)
    body = assert_envelope_ok(r)
    assert body["data"]["transition"]["from_stage"]["id"] != body["data"]["transition"]["to_stage"]["id"]


def test_comment(client, test_request, capture):
    """POST /api/v1/requests/<id>/comment — post a mail.thread message."""
    r = client.post(f"/api/v1/requests/{test_request['id']}/comment", json={
        "body": "<p>test_requests.test_comment</p>",
        "internal": True,
    })
    capture("requests/comment", r)
    body = assert_envelope_ok(r)
    assert body["data"]["comment"]["id"] > 0
    assert body["data"]["comment"]["internal"] is True
