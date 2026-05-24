"""X-Idempotency-Key behaviour — two writes with the same key on the same
endpoint within 24h must return the cached response (identical request_id,
identical body)."""
import time

from .conftest import assert_envelope_ok


def test_idempotent_location_create(client, capture):
    """Two POST /locations with same key → same record + same request_id."""
    key = f"pytest-idem-loc-{int(time.time())}"
    body = {"name": f"idem-test-{key}", "description": "first call"}

    r1 = client.post("/api/v1/locations", json=body,
                     headers={"X-Idempotency-Key": key})
    capture("idempotency/location_first", r1)
    body1 = assert_envelope_ok(r1, expected_status=201)
    id1 = body1["data"]["id"]
    rid1 = body1["meta"]["request_id"]

    # Second call with a deliberately different body — should be ignored
    r2 = client.post("/api/v1/locations",
                     json={"name": "SHOULD-BE-IGNORED", "description": "second call"},
                     headers={"X-Idempotency-Key": key})
    capture("idempotency/location_second", r2)
    body2 = assert_envelope_ok(r2, expected_status=201)
    id2 = body2["data"]["id"]
    rid2 = body2["meta"]["request_id"]

    assert id1 == id2, f"idempotency broken: created two records id={id1} vs id={id2}"
    assert rid1 == rid2, "idempotency cache should return identical envelope (incl. request_id)"


def test_idempotent_asset_create(client, test_location, capture):
    """Two POST /assets with same key → same record."""
    key = f"pytest-idem-asset-{int(time.time())}"
    body = {
        "name": f"idem-asset-{key}",
        "category_id": 1,
        "location_id": test_location["id"],
    }
    r1 = client.post("/api/v1/assets", json=body,
                     headers={"X-Idempotency-Key": key})
    capture("idempotency/asset_first", r1)
    body1 = assert_envelope_ok(r1, expected_status=201)

    r2 = client.post("/api/v1/assets",
                     json={"name": "DIFFERENT", "category_id": 1, "location_id": test_location["id"]},
                     headers={"X-Idempotency-Key": key})
    capture("idempotency/asset_second", r2)
    body2 = assert_envelope_ok(r2, expected_status=201)

    assert body1["data"]["id"] == body2["data"]["id"]
    assert body1["meta"]["request_id"] == body2["meta"]["request_id"]


def test_idempotent_request_create(client, test_location, test_asset, capture):
    """Two POST /requests with same key → same record."""
    key = f"pytest-idem-req-{int(time.time())}"
    body = {
        "type_id": 1,
        "category_id": 5,
        "request_text": f"<p>idem request {key}</p>",
        "location_id": test_location["id"],
        "nrs_asset_id": test_asset["id"],
    }
    r1 = client.post("/api/v1/requests", json=body,
                     headers={"X-Idempotency-Key": key})
    capture("idempotency/request_first", r1)
    body1 = assert_envelope_ok(r1, expected_status=201)

    r2 = client.post("/api/v1/requests",
                     json={**body, "request_text": "<p>DIFFERENT</p>"},
                     headers={"X-Idempotency-Key": key})
    capture("idempotency/request_second", r2)
    body2 = assert_envelope_ok(r2, expected_status=201)

    assert body1["data"]["id"] == body2["data"]["id"]
    assert body1["meta"]["request_id"] == body2["meta"]["request_id"]
