"""All 8 JSON asset endpoints. CSV export is in test_assets_csv.py."""
import time
import uuid


def _uniq():
    """A token unique across concurrent runs, not just within one.

    `int(time.time())` alone collides whenever two runs start in the same
    second — two suites against one instance, or a re-run during a review.
    The provenance filters below assert an EXACT set of ids, so a collision
    makes them fail spuriously and, worse, makes them look flaky rather than
    wrong. The uuid suffix is what actually guarantees the reference is ours.
    """
    return f"{int(time.time())}-{uuid.uuid4().hex[:8]}"

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


# ─── acquisition provenance (INT-03) ─────────────────────────────────
#
# Vendra creates one Cadra asset per asset-classified goods-receipt line and
# then has to be able to get back from a GRN to the assets it produced. These
# tests are the contract for that, so they assert the round-trip AND the
# reverse lookup — the fields alone are only half of a traceable link.


def test_create_with_provenance(client, test_location, capture):
    """POST /api/v1/assets — GRN/PO/vendor and import_* round-trip on create."""
    ts = _uniq()
    payload = {
        "name": f"pytest-provenance-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "grn_reference": f"GRN-PYTEST-{ts}",
        "purchase_order_reference": f"PO-PYTEST-{ts}",
        "purchase_vendor": "Pytest Supplies Ltd",
        "import_source": "other",
        "import_date": "2026-05-12",
        "import_ref": f"VENDRA-RCPT-{ts}",
    }
    r = client.post("/api/v1/assets", json=payload)
    capture("assets/create_with_provenance", r)
    body = assert_envelope_ok(r, expected_status=201)
    data = body["data"]

    prov = data["provenance"]
    assert prov["grn_reference"] == payload["grn_reference"]
    assert prov["purchase_order_reference"] == payload["purchase_order_reference"]
    assert prov["purchase_vendor"] == payload["purchase_vendor"]
    assert prov["import_source"] == "other"
    assert prov["import_date"] == "2026-05-12"
    assert prov["import_ref"] == payload["import_ref"]

    # Vendra treats any rejected field as a failed hand-off, so an empty
    # warnings block is part of the contract, not a nicety.
    assert "_warnings" not in data, (
        f"provenance fields were rejected: {data.get('_warnings')}"
    )


def test_filter_by_grn_reference(client, test_location, capture):
    """GET /api/v1/assets?grn_reference=… returns exactly that receipt's assets."""
    ts = _uniq()
    grn = f"GRN-PYTEST-FILTER-{ts}"
    wanted = set()
    for n in (1, 2):
        r = client.post("/api/v1/assets", json={
            "name": f"pytest-grn-{ts}-{n}",
            "category_id": 1,
            "location_id": test_location["id"],
            "grn_reference": grn,
        })
        wanted.add(assert_envelope_ok(r, expected_status=201)["data"]["id"])
    # A decoy on a different GRN — the filter has to exclude it, or an
    # auditor's GRN lookup over-reports what the receipt delivered.
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-grn-decoy-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "grn_reference": f"GRN-PYTEST-DECOY-{ts}",
    })
    decoy_id = assert_envelope_ok(r, expected_status=201)["data"]["id"]

    r = client.get("/api/v1/assets", params={"grn_reference": grn, "limit": 100})
    capture("assets/filter_by_grn", r)
    body = assert_envelope_ok(r)
    got = {a["id"] for a in body["data"]}
    assert got == wanted, f"expected exactly {wanted}, got {got}"
    assert decoy_id not in got


def test_filter_by_purchase_order_reference(client, test_location):
    """GET /api/v1/assets?purchase_order_reference=… — exact match, no bleed."""
    ts = _uniq()
    po = f"PO-PYTEST-FILTER-{ts}"
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-po-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "purchase_order_reference": po,
    })
    asset_id = assert_envelope_ok(r, expected_status=201)["data"]["id"]

    r = client.get("/api/v1/assets", params={"purchase_order_reference": po, "limit": 100})
    body = assert_envelope_ok(r)
    assert [a["id"] for a in body["data"]] == [asset_id]


def test_patch_provenance_correction(client, test_location):
    """PATCH can correct a mis-keyed GRN — write-once in practice, not enforced."""
    ts = _uniq()
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-prov-patch-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "grn_reference": f"GRN-TYPO-{ts}",
    })
    asset_id = assert_envelope_ok(r, expected_status=201)["data"]["id"]

    corrected = f"GRN-CORRECT-{ts}"
    r = client.patch(f"/api/v1/assets/{asset_id}", json={"grn_reference": corrected})
    body = assert_envelope_ok(r)
    assert body["data"]["provenance"]["grn_reference"] == corrected
    assert "_warnings" not in body["data"]


def test_provenance_in_serializer_for_plain_asset(client, test_asset):
    """Every asset carries the provenance block, populated or not."""
    r = client.get(f"/api/v1/assets/{test_asset['id']}")
    body = assert_envelope_ok(r)
    prov = body["data"]["provenance"]
    for field in ("grn_reference", "purchase_order_reference", "purchase_vendor",
                  "import_source", "import_date", "import_ref"):
        assert field in prov, f"`{field}` missing from the provenance block"


def test_unknown_condition_is_400_not_500(client, test_location, capture):
    """A value outside the `condition` enum is the caller's error, not ours.

    `damaged` is the value the published schema used to advertise. The ORM
    raises a bare ValueError for it, which used to reach the catch-all and
    answer 500 — a status an integration retries forever.
    """
    ts = int(time.time())
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-bad-condition-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "condition": "damaged",
    })
    capture("assets/create_invalid_condition", r)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    error = r.json()["error"]
    assert error["code"] == "validation_failed"
    details = error.get("details") or {}
    assert details.get("field") == "condition"
    # The accepted set is handed back so an integrator never has to guess.
    assert set(details.get("allowed_values") or []) == {
        "new", "good", "fair", "poor", "decommissioned"
    }


def test_filter_by_vendor_and_import_fields(client, test_location):
    """The remaining provenance filters are exact and independent."""
    ts = _uniq()
    vendor = f"Pytest Vendor {ts}"
    ref = f"VENDRA-FILTER-{ts}"
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-vendor-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "purchase_vendor": vendor,
        "import_source": "other",
        "import_ref": ref,
    })
    asset_id = assert_envelope_ok(r, expected_status=201)["data"]["id"]

    for params in ({"purchase_vendor": vendor}, {"import_ref": ref}):
        body = assert_envelope_ok(
            client.get("/api/v1/assets", params={**params, "limit": 100}))
        assert [a["id"] for a in body["data"]] == [asset_id], (
            f"filter {params} returned {[a['id'] for a in body['data']]}"
        )

    # import_source alone is low-cardinality — assert it narrows rather than
    # returning an exact set, since other tests write `other` too.
    body = assert_envelope_ok(
        client.get("/api/v1/assets", params={"import_source": "other", "limit": 200}))
    assert asset_id in {a["id"] for a in body["data"]}


def test_q_matches_grn_reference(client, test_location):
    """Free-text search reaches the GRN — an auditor pastes it into the box."""
    ts = _uniq()
    grn = f"GRN-PYTEST-Q-{ts}"
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-q-grn-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "grn_reference": grn,
    })
    asset_id = assert_envelope_ok(r, expected_status=201)["data"]["id"]

    body = assert_envelope_ok(client.get("/api/v1/assets", params={"q": grn, "limit": 50}))
    assert asset_id in {a["id"] for a in body["data"]}


def test_grn_filter_is_exact_not_prefix(client, test_location):
    """`?grn_reference=` must not match a longer GRN that starts with it.

    Under `ilike` an audit lookup for GRN-…-001 would silently also report the
    assets from GRN-…-0011, over-stating what the receipt delivered.
    """
    ts = _uniq()
    grn = f"GRN-PYTEST-EXACT-{ts}"
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-exact-{ts}", "category_id": 1,
        "location_id": test_location["id"], "grn_reference": grn})
    wanted = assert_envelope_ok(r, expected_status=201)["data"]["id"]
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-exact-longer-{ts}", "category_id": 1,
        "location_id": test_location["id"], "grn_reference": grn + "9"})
    longer = assert_envelope_ok(r, expected_status=201)["data"]["id"]

    body = assert_envelope_ok(
        client.get("/api/v1/assets", params={"grn_reference": grn, "limit": 100}))
    got = {a["id"] for a in body["data"]}
    assert got == {wanted}, f"expected exactly {{{wanted}}}, got {got}"
    assert longer not in got


def test_unparseable_date_is_400_not_500(client, test_location, capture):
    """A malformed date is the caller's error too, not an internal error.

    `import_date` is one of the fields an integration now writes, so this is
    the shape a bad INT-03 payload takes.
    """
    ts = int(time.time())
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-bad-date-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "import_date": "not-a-date",
    })
    capture("assets/create_invalid_date", r)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    error = r.json()["error"]
    assert error["code"] == "validation_failed"
    assert (error.get("details") or {}).get("expected_type") == "date"


def test_non_numeric_cost_is_400_not_500(client, test_location):
    """Same for a non-numeric monetary value."""
    ts = int(time.time())
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-bad-cost-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "acquisition_cost": "abc",
    })
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    assert r.json()["error"]["code"] == "validation_failed"


def test_non_integer_relation_id_is_400_not_500(client, test_location):
    """A non-integer many2one id is rejected by Postgres, not by the ORM.

    It surfaces as psycopg2.DataError rather than ValueError, which is a
    separate path from the two above.
    """
    ts = int(time.time())
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-bad-m2o-{ts}",
        "category_id": 1,
        "location_id": "abc",
    })
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    assert r.json()["error"]["code"] == "validation_failed"


def test_import_source_accepts_vendra(client, test_location):
    """`vendra` is a published value of import_source, not a fallback to `other`.

    The enum names the systems Cadra receives from; the goods-receipt system
    is one of them, and `other` + a ref throws away the signal the field
    exists to carry.
    """
    ts = _uniq()
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-vendra-src-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "import_source": "vendra",
        "import_ref": f"VENDRA-RCPT-{ts}",
    })
    body = assert_envelope_ok(r, expected_status=201)
    assert body["data"]["provenance"]["import_source"] == "vendra"
    assert "_warnings" not in body["data"]


def test_import_source_rejects_an_invented_value(client, test_location):
    """Adding `vendra` must not have loosened the enum."""
    ts = int(time.time())
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-bad-src-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "import_source": "not-a-system",
    })
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    details = r.json()["error"].get("details") or {}
    assert details.get("field") == "import_source"
    assert "vendra" in (details.get("allowed_values") or [])
