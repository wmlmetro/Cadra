"""All 8 JSON asset endpoints. CSV export is in test_assets_csv.py."""
import time
import uuid

import pytest


def _uniq():
    """A token unique across concurrent runs, not just within one.

    `int(time.time())` alone collides whenever two runs start in the same
    second — two suites against one instance, or a re-run during a review.
    The provenance filters below assert an EXACT set of ids, so a collision
    makes them fail spuriously and, worse, makes them look flaky rather than
    wrong. The uuid suffix is what actually guarantees the reference is ours.
    """
    return f"{int(time.time())}-{uuid.uuid4().hex[:8]}"

from . import gates
from .conftest import assert_envelope_ok


def _registered(client, **body):
    """An asset ON THE REGISTER, whichever way the receipt switch is set —
    for a test about finding, filtering or correcting one (handoff 58 §2:
    with the gates on, a receipt is a candidate the register hides until
    `tests/gates.py` walks it through them)."""
    return gates.new_registered_asset(client, **body)


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


@pytest.mark.parametrize("gated", [True, False],
                         ids=["switch_on", "switch_off"])
def test_create(client, test_location, capture, receipt_switch, gated):
    """POST /api/v1/assets — create with 201.

    The receipt path itself (INT-03), so both switch states (handoff 58 §2):
    on, the 201 is a `captured` candidate; off, a registered asset."""
    receipt_switch(gated)
    ts = int(time.time())
    r = client.post("/api/v1/assets", json=gates.receipt_body(
        client,
        name=f"pytest-asset-create-{ts}",
        category_id=1,
        condition="new",
        state="active",
        location_id=test_location["id"],
    ))
    capture("assets/create", r)
    body = assert_envelope_ok(r, expected_status=201)
    assert body["data"]["id"] > 0
    assert body["data"]["asset_code"]  # auto-generated
    assert body["data"]["register_state"] == (
        "captured" if gated else "registered")


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


def test_move(client, test_asset, second_person, capture):
    """POST /api/v1/assets/<id>/move — the asset ends up at the location.

    Handoff 35 made this two calls rather than one on any tenant that
    requires a second person, which is every tenant that has not
    deliberately switched the rule off. `second_person.move` is the one place
    that knows which kind of tenant this is (`tests/conftest.py`), so what is
    asserted here is the OUTCOME — the asset is there, and there is a
    transfer document saying it went — rather than the shape of whichever
    response carried it.

    The route-specific shapes are asserted where they belong: the pending
    payload in `tests/test_approvals.py`, the approved one in the same file.
    """
    # Find a different location to move to
    list_r = client.get("/api/v1/locations", params={"limit": 5})
    current = test_asset.get("current_location") or {}
    candidate = next(
        (loc for loc in list_r.json()["data"] if loc["id"] != (current.get("id") or 0)),
        None,
    )
    assert candidate, "no other location available to move to"

    moved = second_person.move(test_asset["id"], candidate["id"],
                               reason="test_assets.test_move")
    capture("assets/move", moved["decision"] or moved["raised"])
    assert moved["asset"]["current_location"]["id"] == candidate["id"]
    # The append-only record is the FACT; the transfer is the paperwork. The
    # asset had a location to leave, so there is one of each.
    assert moved["movement_id"]
    assert moved["transfer_reference"]
    # Read back, not trusted: the response is one transaction's opinion and
    # the row is what an auditor sees.
    after = assert_envelope_ok(
        client.get(f"/api/v1/assets/{test_asset['id']}"))["data"]
    assert after["current_location"]["id"] == candidate["id"]


def test_transfer_custody(client, test_asset, second_person, capture):
    """POST /api/v1/assets/<id>/transfer-custody — custodian change.

    `to_custodian_id: 1` used to be hard-coded here with a branch tolerating
    the 400 the route gives when the asset already has that custodian. The
    branch stays — this is a session-scoped asset that other modules also
    hand about — but it now reads the employee off the register rather than
    assuming id 1 exists, which is the same correction `test_custody.
    _two_employees` made for the same reason.
    """
    employees = client.get("/api/v1/identity/employees", params={"limit": 2})
    rows = (employees.json().get("data") or []) if employees.status_code == 200 else []
    if not rows:
        pytest.skip("tenant has no employee to transfer custody to")
    held = (test_asset.get("current_custodian") or {}).get("id")
    target = next((row["id"] for row in rows if row["id"] != held), None)
    if target is None:
        pytest.skip("the asset already holds the only employee on this tenant")

    moved = second_person.transfer_custody(
        test_asset["id"], target, reason="test_assets.test_transfer_custody")
    capture("assets/transfer_custody", moved["decision"] or moved["raised"])
    assert moved["asset"]["current_custodian"]["id"] == target
    # The append-only link. `custody_change` on the direct route and
    # `request.custody_id` on the approved one are the same row.
    assert moved["custody_id"]


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


@pytest.mark.parametrize("gated", [True, False],
                         ids=["switch_on", "switch_off"])
def test_create_with_provenance(client, test_location, capture,
                                receipt_switch, gated):
    """POST /api/v1/assets — GRN/PO/vendor and import_* round-trip on create.

    INT-03's own call, so both switch states (handoff 58 §2): the
    provenance round-trips on a candidate exactly as on a registered asset.
    """
    receipt_switch(gated)
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
    r = client.post("/api/v1/assets",
                    json=gates.receipt_body(client, **payload))
    capture("assets/create_with_provenance", r)
    body = assert_envelope_ok(r, expected_status=201)
    data = body["data"]
    assert data["register_state"] == ("captured" if gated else "registered")

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
        wanted.add(_registered(
            client, name=f"pytest-grn-{ts}-{n}", category_id=1,
            location_id=test_location["id"], grn_reference=grn)["id"])
    # A decoy on a different GRN — the filter has to exclude it, or an
    # auditor's GRN lookup over-reports what the receipt delivered.
    decoy_id = _registered(
        client, name=f"pytest-grn-decoy-{ts}", category_id=1,
        location_id=test_location["id"],
        grn_reference=f"GRN-PYTEST-DECOY-{ts}")["id"]

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
    asset_id = _registered(
        client, name=f"pytest-po-{ts}", category_id=1,
        location_id=test_location["id"],
        purchase_order_reference=po)["id"]

    r = client.get("/api/v1/assets", params={"purchase_order_reference": po, "limit": 100})
    body = assert_envelope_ok(r)
    assert [a["id"] for a in body["data"]] == [asset_id]


def test_patch_provenance_correction(client, test_location):
    """PATCH can correct a mis-keyed GRN — write-once in practice, not enforced."""
    ts = _uniq()
    asset_id = _registered(
        client, name=f"pytest-prov-patch-{ts}", category_id=1,
        location_id=test_location["id"],
        grn_reference=f"GRN-TYPO-{ts}")["id"]

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
    r = client.post("/api/v1/assets", json=gates.receipt_body(client, **{
        "name": f"pytest-bad-condition-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "condition": "damaged",
    }))
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
    asset_id = _registered(
        client, name=f"pytest-vendor-{ts}", category_id=1,
        location_id=test_location["id"], purchase_vendor=vendor,
        import_source="other", import_ref=ref)["id"]

    for params in ({"purchase_vendor": vendor}, {"import_ref": ref}):
        body = assert_envelope_ok(
            client.get("/api/v1/assets", params={**params, "limit": 100}))
        assert [a["id"] for a in body["data"]] == [asset_id], (
            f"filter {params} returned {[a['id'] for a in body['data']]}"
        )

    # import_source alone is low-cardinality — assert it narrows rather than
    # returning an exact set, since other tests write `other` too.
    #
    # Deliberately NOT "the asset we just made is in the results". The suite
    # authenticates with a client token, which carries no `aud: frontend` and
    # is therefore clamped to EXTERNAL_MAX_PAGE_LIMIT (100) records however
    # large a `limit` it asks for. Every run of this file adds another
    # `import_source: other` asset, so once the corpus passed 100 the newest
    # id stopped fitting in the visible window and this assertion began
    # failing on a filter that was working perfectly. It was a clock, not a
    # test. What the filter actually promises is that everything it returns
    # matches — so assert that, and prove it discriminates by checking a
    # value nothing writes comes back empty.
    body = assert_envelope_ok(
        client.get("/api/v1/assets", params={"import_source": "other", "limit": 200}))
    rows = body["data"]
    assert rows, "no assets at all carry import_source=other — this one should"
    mismatched = [a["id"] for a in rows
                  if a["provenance"]["import_source"] != "other"]
    assert not mismatched, (
        f"?import_source=other returned assets with a different source: {mismatched}"
    )

    body = assert_envelope_ok(
        client.get("/api/v1/assets", params={"import_source": "redhubb", "limit": 5}))
    assert body["data"] == [], (
        "a source nothing in the fixtures writes returned rows — the filter "
        "is not being applied at all"
    )


def test_q_matches_grn_reference(client, test_location):
    """Free-text search reaches the GRN — an auditor pastes it into the box."""
    ts = _uniq()
    grn = f"GRN-PYTEST-Q-{ts}"
    asset_id = _registered(
        client, name=f"pytest-q-grn-{ts}", category_id=1,
        location_id=test_location["id"], grn_reference=grn)["id"]

    body = assert_envelope_ok(client.get("/api/v1/assets", params={"q": grn, "limit": 50}))
    assert asset_id in {a["id"] for a in body["data"]}


def test_grn_filter_is_exact_not_prefix(client, test_location):
    """`?grn_reference=` must not match a longer GRN that starts with it.

    Under `ilike` an audit lookup for GRN-…-001 would silently also report the
    assets from GRN-…-0011, over-stating what the receipt delivered.
    """
    ts = _uniq()
    grn = f"GRN-PYTEST-EXACT-{ts}"
    wanted = _registered(
        client, name=f"pytest-exact-{ts}", category_id=1,
        location_id=test_location["id"], grn_reference=grn)["id"]
    longer = _registered(
        client, name=f"pytest-exact-longer-{ts}", category_id=1,
        location_id=test_location["id"], grn_reference=grn + "9")["id"]

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
    r = client.post("/api/v1/assets", json=gates.receipt_body(client, **{
        "name": f"pytest-bad-date-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "import_date": "not-a-date",
    }))
    capture("assets/create_invalid_date", r)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    error = r.json()["error"]
    assert error["code"] == "validation_failed"
    assert (error.get("details") or {}).get("expected_type") == "date"


def test_non_numeric_cost_is_400_not_500(client, test_location):
    """Same for a non-numeric monetary value."""
    ts = int(time.time())
    r = client.post("/api/v1/assets", json=gates.receipt_body(client, **{
        "name": f"pytest-bad-cost-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "acquisition_cost": "abc",
    }))
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    assert r.json()["error"]["code"] == "validation_failed"


def test_non_integer_relation_id_is_400_not_500(client, test_location):
    """A non-integer many2one id is rejected by Postgres, not by the ORM.

    It surfaces as psycopg2.DataError rather than ValueError, which is a
    separate path from the two above.
    """
    ts = int(time.time())
    r = client.post("/api/v1/assets", json=gates.receipt_body(client, **{
        "name": f"pytest-bad-m2o-{ts}",
        "category_id": 1,
        "location_id": "abc",
    }))
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    assert r.json()["error"]["code"] == "validation_failed"


def test_import_source_accepts_vendra(client, test_location):
    """`vendra` is a published value of import_source, not a fallback to `other`.

    The enum names the systems Cadra receives from; the goods-receipt system
    is one of them, and `other` + a ref throws away the signal the field
    exists to carry.
    """
    ts = _uniq()
    r = client.post("/api/v1/assets", json=gates.receipt_body(
        client,
        name=f"pytest-vendra-src-{ts}",
        category_id=1,
        location_id=test_location["id"],
        import_source="vendra",
        import_ref=f"VENDRA-RCPT-{ts}",
    ))
    body = assert_envelope_ok(r, expected_status=201)
    assert body["data"]["provenance"]["import_source"] == "vendra"
    assert "_warnings" not in body["data"]


def test_import_source_rejects_an_invented_value(client, test_location):
    """Adding `vendra` must not have loosened the enum."""
    ts = int(time.time())
    r = client.post("/api/v1/assets", json=gates.receipt_body(client, **{
        "name": f"pytest-bad-src-{ts}",
        "category_id": 1,
        "location_id": test_location["id"],
        "import_source": "not-a-system",
    }))
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
    details = r.json()["error"].get("details") or {}
    assert details.get("field") == "import_source"
    assert "vendra" in (details.get("allowed_values") or [])
