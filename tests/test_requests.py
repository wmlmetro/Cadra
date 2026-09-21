"""All 8 Service Request endpoints."""
import time

from .conftest import (
    assert_envelope_err, assert_envelope_ok, assert_fields_refused)


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


def test_a_requests_location_is_kept(client, test_location, test_asset):
    """`location_id` is SAVED, published back, and can be changed.

    For the life of this API it was not. The request model's location field
    was renamed in the move to Odoo 19 (`generic_location_id`) and this route
    went on asking the model for `location_id`; the key was dropped and the
    answer was a 201. No test asserted the location came BACK, so nothing
    failed — until handoff 31 made a dropped field a 400 and the suite's own
    fixture broke on it. The published key is the contract; the model's name
    for it is the controller's business.
    """
    r = client.post("/api/v1/requests", json={
        "type_id": 1, "category_id": 5,
        "request_text": "<p>test_a_requests_location_is_kept</p>",
        "location_id": test_location["id"],
    })
    created = assert_envelope_ok(r, expected_status=201)["data"]
    assert created["location"] == {"id": test_location["id"],
                                   "name": test_location["name"]}
    # Read back, not only echoed: a serializer can echo what was never stored.
    read = assert_envelope_ok(
        client.get(f"/api/v1/requests/{created['id']}"))["data"]
    assert read["location"]["id"] == test_location["id"]

    elsewhere = assert_envelope_ok(client.post(
        "/api/v1/locations", json={"name": "pytest-request-elsewhere"}),
        expected_status=201)["data"]
    patched = assert_envelope_ok(client.patch(
        f"/api/v1/requests/{created['id']}",
        json={"location_id": elsewhere["id"]}))["data"]
    assert patched["location"]["id"] == elsewhere["id"]


def test_the_location_filter_filters(client, test_location):
    """`?location_id=` answered with EVERY request until handoff 31.

    The list looked for a model field called `location_id`, did not find one,
    and ignored the parameter — the defect handoff 21 closed on every other
    filter, surviving here under a comment that called it a registry guard.
    A location nobody has raised a request at must return nothing, and a
    bare 200 would prove nothing, so the control is the unfiltered total.
    """
    empty = assert_envelope_ok(client.post(
        "/api/v1/locations", json={"name": "pytest-request-nobody-here"}),
        expected_status=201)["data"]
    everything = assert_envelope_ok(
        client.get("/api/v1/requests", params={"limit": 1}))
    assert everything["pagination"]["total_estimate"] > 0
    nothing = assert_envelope_ok(client.get(
        "/api/v1/requests", params={"location_id": empty["id"], "limit": 1}))
    assert nothing["data"] == []
    here = assert_envelope_ok(client.get(
        "/api/v1/requests", params={"location_id": test_location["id"]}))
    assert here["data"], "the fixture request was raised at this location"
    assert all(row["location"]["id"] == test_location["id"]
               for row in here["data"])


def test_what_a_request_accepts_is_what_this_deployment_can_store(client, test_request):
    """`details.writable` lists `location_id` — and would not, if the
    installed model had nowhere to put it."""
    r = client.patch(f"/api/v1/requests/{test_request['id']}",
                     json={"not_a_request_field": 1})
    details = assert_envelope_err(r, 400, "invalid_request")["error"]["details"]
    assert details["rejected_fields"] == ["not_a_request_field"]
    assert {"location_id", "nrs_asset_id", "vehicle_id"} <= set(details["writable"])


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
    """PATCH with `stage_id` is REFUSED, with a hint naming the right door.

    A stage changes through `POST .../transition`, which runs the route's
    checks; a PATCH that set it would walk round them. Until handoff 31 the
    refusal was a 200 carrying `_warnings` — so a caller reading the status
    believed the request had moved. It is a 400 now, the stage is read back
    to prove it did not move, and the hint is in `details` beside the list
    of what this route does accept.
    """
    before = assert_envelope_ok(
        client.get(f"/api/v1/requests/{test_request['id']}"))["data"]
    r = client.patch(f"/api/v1/requests/{test_request['id']}", json={
        "stage_id": 99,
    })
    capture("requests/patch_stage_rejected", r)
    details = assert_fields_refused(r, "stage_id")
    assert details["rejected_fields"] == ["stage_id"]
    assert "/transition" in details["hint"]
    after = assert_envelope_ok(
        client.get(f"/api/v1/requests/{test_request['id']}"))["data"]
    assert after["stage"] == before["stage"]


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


def test_request_publishes_the_workflow_payment_reference(
        client, test_request, capture):
    """Handoff 25 C3. The approval callback's references are readable.

    `workflow_payment_ref` is written by the WorkSpace/Workflow APPROVAL
    callback and tracked on the request form, and until now the API published
    neither it nor `workspace_ref` — which is written by the OUTBOUND SEND
    path, not the callback, and is measured at 0 of 407 requests. A Finance
    Officer tracing a payment reference over the API could not, and neither
    could an auditor — report 24 §8 listed it as a financial fact invisible to
    every role.

    The measurement decided it rather than a ruling: a column nothing writes
    is dead and goes; a column the approval path writes belongs in the
    serializer. It is additive, so no client breaks.
    """
    detail = client.get("/api/v1/requests/%s" % test_request["id"])
    capture("requests/workflow-refs", detail)
    assert detail.status_code == 200
    data = detail.json()["data"]

    assert "workflow" in data, \
        "the request serializer must publish the workflow reference block"
    block = data["workflow"]
    assert set(block) == {"payment_ref", "workspace_ref"}, \
        "unexpected keys in the workflow block: %s" % sorted(block)
    for key, value in block.items():
        assert value is None or isinstance(value, str), \
            "%s must be a string or null, got %r" % (key, value)
