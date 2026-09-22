"""All 7 Location endpoints."""
import time

from .conftest import assert_envelope_ok


def test_list(client, capture):
    """GET /api/v1/locations — list with pagination."""
    r = client.get("/api/v1/locations", params={"limit": 5})
    capture("locations/list", r)
    body = assert_envelope_ok(r)
    assert isinstance(body["data"], list)
    assert len(body["data"]) <= 5
    assert "pagination" in body
    assert body["pagination"]["total_estimate"] >= 0


def test_list_filtered_by_q(client, capture):
    """GET /api/v1/locations?q=Lagos — narrowing filter.

    `?q=` searches FOUR fields — `name`, `description`, `zone_code` and the
    stored city (`v1_locations._list_domain`) — and this test asserted the
    match was always in the name. It passed for the life of the suite because
    no location on the test tenant happened to be in a city called Lagos.
    Handoff 32's sweep created one — *Sweep probe location*, city Lagos — and
    the test failed on a row the filter was right to return.

    A test that only passes because of the data it happens to meet is a test
    of the tenant, not of the route. It now asserts what the route actually
    promises: the term appears in one of the fields the route searches.
    """
    r = client.get("/api/v1/locations", params={"q": "Lagos", "limit": 5})
    capture("locations/list_filtered", r)
    body = assert_envelope_ok(r)
    for item in body["data"]:
        haystack = " ".join(str(v or "") for v in (
            item.get("name"),
            item.get("description"),
            (item.get("extras") or {}).get("zone_code"),
            (item.get("address") or {}).get("city"),
        )).lower()
        assert "lagos" in haystack, (
            f"{item['name']!r} matched ?q=Lagos and carries the term in none "
            f"of the four fields the route searches")


def test_list_pagination_cursor(client, capture):
    """Two pages with cursor — IDs should be disjoint."""
    r1 = client.get("/api/v1/locations", params={"limit": 3})
    capture("locations/list_page1", r1)
    body1 = assert_envelope_ok(r1)
    cursor = body1["pagination"]["next_cursor"]
    if not cursor:
        # If the DB has ≤3 locations, there's nothing to paginate; skip cleanly.
        return
    r2 = client.get("/api/v1/locations", params={"limit": 3, "cursor": cursor})
    capture("locations/list_page2", r2)
    body2 = assert_envelope_ok(r2)
    ids1 = {item["id"] for item in body1["data"]}
    ids2 = {item["id"] for item in body2["data"]}
    assert not (ids1 & ids2), f"page 1 and page 2 overlap: {ids1 & ids2}"


def test_get_by_id(client, any_location, capture):
    """GET /api/v1/locations/<id> — single record."""
    r = client.get(f"/api/v1/locations/{any_location}",
                   params={"include": "children,ancestors"})
    capture("locations/get_by_id", r)
    body = assert_envelope_ok(r)
    assert body["data"]["id"] == any_location
    assert "children" in body["data"]
    assert "ancestors" in body["data"]


def test_get_not_found(client, capture):
    """GET nonexistent id → 404 not_found."""
    r = client.get("/api/v1/locations/99999999")
    capture("locations/get_not_found", r)
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"


def test_create(client, capture):
    """POST /api/v1/locations — create with 201."""
    r = client.post("/api/v1/locations", json={
        "name": f"pytest-create-{int(time.time())}",
        "description": "via test_locations.test_create",
        "latitude": 6.5244,
        "longitude": 3.3792,
    })
    capture("locations/create", r)
    body = assert_envelope_ok(r, expected_status=201)
    assert body["data"]["id"] > 0
    assert body["data"]["name"].startswith("pytest-create-")


def test_create_missing_name(client, capture):
    """POST with missing required field → 400 invalid_request."""
    r = client.post("/api/v1/locations", json={"description": "no name"})
    capture("locations/create_missing_name", r)
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "invalid_request"


def test_patch(client, test_location, capture):
    """PATCH /api/v1/locations/<id> — partial update."""
    r = client.patch(f"/api/v1/locations/{test_location['id']}", json={
        "description": "patched by test_locations.test_patch",
    })
    capture("locations/patch", r)
    body = assert_envelope_ok(r)
    assert body["data"]["description"] == "patched by test_locations.test_patch"


def test_children(client, any_location, capture):
    """GET /api/v1/locations/<id>/children — direct children."""
    r = client.get(f"/api/v1/locations/{any_location}/children")
    capture("locations/children", r)
    body = assert_envelope_ok(r)
    assert isinstance(body["data"], list)


def test_ancestors(client, any_location, capture):
    """GET /api/v1/locations/<id>/ancestors — root → parent chain."""
    # Pick a deep-enough location for ancestors to be non-empty
    list_r = client.get("/api/v1/locations", params={"limit": 100})
    deep = next((it for it in list_r.json()["data"]
                 if it.get("parent_path") and it["parent_path"].count("/") >= 3), None)
    target_id = deep["id"] if deep else any_location
    r = client.get(f"/api/v1/locations/{target_id}/ancestors")
    capture("locations/ancestors", r)
    body = assert_envelope_ok(r)
    assert isinstance(body["data"], list)


def test_descendants(client, any_location, capture):
    """GET /api/v1/locations/<id>/descendants — paginated descendant tree."""
    r = client.get(f"/api/v1/locations/{any_location}/descendants",
                   params={"limit": 5})
    capture("locations/descendants", r)
    body = assert_envelope_ok(r)
    assert isinstance(body["data"], list)
    assert "pagination" in body
