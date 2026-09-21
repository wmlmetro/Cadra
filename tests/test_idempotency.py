"""X-Idempotency-Key behaviour — two writes with the same key on the same
endpoint within 24h must return the cached response (identical request_id,
identical body)."""
import time
import uuid

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


# ─── key validation and concurrency ──────────────────────────────────


def test_overlong_key_is_rejected(client, test_location, capture):
    """A key over 128 chars must 400, not silently degrade to a plain create.

    Dropping it and processing the request as new leaves the caller believing
    it is protected against a retry storm when it is not, and gives it no way
    to find out.
    """
    r = client.post("/api/v1/assets",
                    json={"name": f"idem-longkey-{int(time.time())}",
                          "category_id": 1,
                          "location_id": test_location["id"]},
                    headers={"X-Idempotency-Key": "k" * 200})
    capture("idempotency/overlong_key", r)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    error = r.json()["error"]
    assert error["code"] == "invalid_request"
    details = error.get("details") or {}
    assert details.get("header") == "X-Idempotency-Key"
    assert details.get("max_length") == 128
    assert details.get("received_length") == 200


def test_key_at_max_length_is_accepted(client, test_location):
    """128 characters is the limit, not one past it."""
    key = "b" * 128
    r = client.post("/api/v1/assets",
                    json={"name": f"idem-maxkey-{int(time.time())}",
                          "category_id": 1,
                          "location_id": test_location["id"]},
                    headers={"X-Idempotency-Key": key})
    assert_envelope_ok(r, expected_status=201)


def test_concurrent_same_key_creates_exactly_one(client, test_location, capture):
    """Four simultaneous creates under one key must yield one asset.

    This is the case the key exists for: a client retrying a request whose
    response it never saw. The requests genuinely race — the losers do create
    an asset before failing to claim the key, and the handler has to discard
    that work rather than keep it and answer with the winner's body.

    Whether the race is actually hit depends on worker scheduling, so the
    assertions are on the invariant (one asset, one id, always an envelope)
    rather than on the race occurring.
    """
    import concurrent.futures

    key = f"pytest-idem-race-{int(time.time() * 1000)}"
    name = f"idem-race-{key}"
    payload = {"name": name, "category_id": 1, "location_id": test_location["id"]}

    def fire(_):
        return client.post("/api/v1/assets", json=payload,
                           headers={"X-Idempotency-Key": key})

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(fire, range(4)))
    capture("idempotency/concurrent_same_key", responses[0])

    created_ids = set()
    for r in responses:
        # A raw 500 with an HTML or empty body is the failure mode this
        # guards: every outcome has to be the PRD envelope.
        body = r.json()
        assert "data" in body or "error" in body, f"non-enveloped response: {r.text[:300]}"
        assert r.status_code in (200, 201, 409), (
            f"unexpected status {r.status_code}: {r.text[:300]}"
        )
        if r.status_code in (200, 201):
            created_ids.add(body["data"]["id"])

    assert len(created_ids) == 1, (
        f"idempotency broken: same key produced ids {sorted(created_ids)}"
    )

    # And the losers' assets must not have survived the rollback.
    listing = client.get("/api/v1/assets", params={"q": name, "limit": 50})
    matches = [a for a in assert_envelope_ok(listing)["data"] if a["name"] == name]
    assert len(matches) == 1, (
        f"expected 1 asset named {name}, found {len(matches)}: "
        f"{[a['id'] for a in matches]}"
    )


def test_overlong_key_rejected_on_a_non_idempotent_route(client):
    """The length check runs everywhere, not only where the key is honoured.

    A caller with a key-generation bug should find out on whichever endpoint
    it hits first, rather than only on the subset that caches.
    """
    r = client.get("/api/v1/assets", params={"limit": 1},
                   headers={"X-Idempotency-Key": "k" * 200})
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    assert r.json()["error"]["code"] == "invalid_request"


def test_key_is_accepted_and_ignored_where_it_is_not_honoured(client):
    """A well-formed key on a read route is accepted AND genuinely ignored.

    Two assertions, because "accepted" alone proves nothing — a GET never
    reached the key handling before this change either, so asserting a 200
    would pass just as well against reverted code. What is worth pinning is
    the second half of the contract: the response is recomputed, not replayed
    from the cache, so a caller spraying the header cannot accidentally opt
    into caching on an endpoint the docs list as ignoring it.
    """
    key = f"pytest-spray-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    first = assert_envelope_ok(
        client.get("/api/v1/assets", params={"limit": 1},
                   headers={"X-Idempotency-Key": key}))
    second = assert_envelope_ok(
        client.get("/api/v1/assets", params={"limit": 1},
                   headers={"X-Idempotency-Key": key}))
    assert first["meta"]["request_id"] != second["meta"]["request_id"], (
        "the key was honoured on a route documented as ignoring it — "
        "the second response was replayed from the idempotency cache"
    )
