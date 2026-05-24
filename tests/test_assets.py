"""All 8 JSON asset endpoints. CSV export is in test_assets_csv.py."""
import time

from .conftest import assert_envelope_ok


def test_list(client, capture):
    """GET /api/v1/assets — paginated list."""
    r = client.get("/api/v1/assets", params={"limit": 5})
    capture("assets/list", r)
    body = assert_envelope_ok(r)
    assert isinstance(body["data"], list)
    assert "pagination" in body


def test_list_filtered(client, capture):
    """GET /api/v1/assets?q=pytest — narrowing filter."""
    r = client.get("/api/v1/assets", params={"q": "pytest", "limit": 10})
    capture("assets/list_filtered", r)
    assert_envelope_ok(r)


def test_get_by_id(client, test_asset, capture):
    """GET /api/v1/assets/<id> — single record."""
    r = client.get(f"/api/v1/assets/{test_asset['id']}", params={"include": "transfers"})
    capture("assets/get_by_id", r)
    body = assert_envelope_ok(r)
    assert body["data"]["id"] == test_asset["id"]
    assert "transfers" in body["data"]


def test_get_by_tag(client, test_asset, capture):
    """GET /api/v1/assets/by-tag/<tag> — lookup by asset_tag."""
    r = client.get(f"/api/v1/assets/by-tag/{test_asset['tag']}")
    capture("assets/get_by_tag", r)
    body = assert_envelope_ok(r)
    assert body["data"]["id"] == test_asset["id"]
    assert body["data"]["tag"] == test_asset["tag"]


def test_get_by_tag_not_found(client, capture):
    """GET /api/v1/assets/by-tag/<bogus> → 404."""
    r = client.get("/api/v1/assets/by-tag/NO-SUCH-TAG-12345")
    capture("assets/get_by_tag_not_found", r)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_create(client, test_location, capture):
    """POST /api/v1/assets — create with 201."""
    ts = int(time.time())
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-asset-create-{ts}",
        "asset_tag": f"PYTEST-CREATE-{ts}",
        "category_id": 1,
        "condition": "new",
        "state": "active",
        "location_id": test_location["id"],
    })
    capture("assets/create", r)
    body = assert_envelope_ok(r, expected_status=201)
    assert body["data"]["id"] > 0
    assert body["data"]["asset_code"]  # auto-generated


def test_patch(client, test_asset, capture):
    """PATCH /api/v1/assets/<id> — partial update."""
    r = client.patch(f"/api/v1/assets/{test_asset['id']}", json={
        "condition": "good",
        "notes": "patched by test_assets.test_patch",
    })
    capture("assets/patch", r)
    body = assert_envelope_ok(r)
    assert body["data"]["condition"] == "good"
    assert body["data"]["notes"] == "patched by test_assets.test_patch"


def test_move(client, test_asset, capture):
    """POST /api/v1/assets/<id>/move — location change creates transfer row."""
    # Find a different location to move to
    list_r = client.get("/api/v1/locations", params={"limit": 5})
    current = test_asset.get("current_location") or {}
    candidate = next(
        (loc for loc in list_r.json()["data"] if loc["id"] != (current.get("id") or 0)),
        None,
    )
    assert candidate, "no other location available to move to"

    r = client.post(f"/api/v1/assets/{test_asset['id']}/move", json={
        "to_location_id": candidate["id"],
        "reason": "test_assets.test_move",
    })
    capture("assets/move", r)
    body = assert_envelope_ok(r)
    assert body["data"]["transfer"]["to_location"]["id"] == candidate["id"]


def test_transfer_custody(client, test_asset, capture):
    """POST /api/v1/assets/<id>/transfer-custody — custodian change."""
    r = client.post(f"/api/v1/assets/{test_asset['id']}/transfer-custody", json={
        "to_custodian_id": 1,
        "reason": "test_assets.test_transfer_custody",
    })
    capture("assets/transfer_custody", r)
    # If the asset is already assigned to employee 1, expect 400 'invalid_request'
    if r.status_code == 400 and r.json()["error"]["code"] == "invalid_request":
        # Already the same custodian — acceptable outcome.
        return
    body = assert_envelope_ok(r)
    assert body["data"]["custody_change"]["to_custodian"]["id"] == 1


def test_export(client, capture):
    """GET /api/v1/assets/export — bulk JSON export."""
    r = client.get("/api/v1/assets/export")
    capture("assets/export", r)
    body = assert_envelope_ok(r)
    assert "count" in body["data"]
    assert "assets" in body["data"]
    assert isinstance(body["data"]["assets"], list)
