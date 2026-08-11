"""Depreciation endpoints and the `financial.depreciation` block (PRD §8.6).

Pure-arithmetic coverage of the engine lives in test_depreciation_engine.py,
which needs no server. These tests exercise the HTTP surface.
"""
import time

import pytest

from .conftest import assert_envelope_ok


COST = 2_400_000.0
LIFE_MONTHS = 60
SALVAGE_RATE = 10.0
#: (2,400,000 - 10%) / 60 months
EXPECTED_MONTHLY_CHARGE = 36_000.0


@pytest.fixture(scope="module")
def any_category_id(client):
    """A category id that actually exists in this tenant.

    Category ids are not stable across tenant databases (cadra19 starts at 50,
    not 1), so discover one from the register rather than hardcoding.
    """
    r = client.get("/api/v1/assets", params={"limit": 1})
    body = assert_envelope_ok(r)
    if not body["data"]:
        pytest.skip("register is empty — no category to attach a test asset to")
    category = body["data"][0].get("category")
    if not category:
        pytest.skip("first asset has no category")
    return category["id"]


@pytest.fixture(scope="module")
def depreciating_asset(client, test_location, any_category_id):
    """An asset with an explicit straight-line policy.

    Uses a per-asset override rather than a category default so the test does
    not depend on how the tenant's categories happen to be configured.
    """
    ts = int(time.time())
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-depreciation-{ts}",
        "asset_tag": f"PYTEST-DEPR-{ts}",
        "category_id": any_category_id,
        "condition": "new",
        "state": "active",
        "location_id": test_location["id"],
        "acquisition_cost": COST,
        "acquisition_date": "2022-06-15",
        "use_category_policy": False,
        "depreciation_method": "straight_line",
        "useful_life_months": LIFE_MONTHS,
        "salvage_rate": SALVAGE_RATE,
    })
    if r.status_code != 201:
        pytest.fail(f"fixture failed: HTTP {r.status_code} {r.text[:300]}")
    return r.json()["data"]


# ── The serialized block ─────────────────────────────────────────────────────

def test_asset_payload_carries_a_depreciation_block(client, depreciating_asset, capture):
    """GET /api/v1/assets/<id> — financial.depreciation is present and populated."""
    r = client.get(f"/api/v1/assets/{depreciating_asset['id']}")
    capture("depreciation/asset_with_depreciation", r)
    body = assert_envelope_ok(r)
    d = body["data"]["financial"]["depreciation"]

    assert d["method"] == "straight_line"
    assert d["useful_life_months"] == LIFE_MONTHS
    assert d["depreciable_cost"] == COST
    assert d["salvage_value"] == COST * SALVAGE_RATE / 100
    assert d["start_date"] == "2022-06-15"
    assert d["start_date_source"] == "acquisition"
    assert d["start_date_is_estimated"] is False
    assert d["state"] == "depreciating"
    assert d["uses_category_policy"] is False
    # Book value must be cost less accumulated, to the kobo.
    assert round(d["current_book_value"] + d["accumulated_depreciation"], 2) == COST


def test_writable_policy_fields_are_not_rejected(client, test_location, any_category_id):
    """The _WRITABLE_FIELDS allow-list drops unknown keys *silently*, so an
    omission would surface as an unchanged value rather than an error.

    Uses its own asset: mutating the shared module fixture would leak policy
    changes into the schedule tests.
    """
    ts = int(time.time())
    created = client.post("/api/v1/assets", json={
        "name": f"pytest-depr-writable-{ts}",
        "asset_tag": f"PYTEST-WRIT-{ts}",
        "category_id": any_category_id,
        "location_id": test_location["id"],
    })
    assert created.status_code == 201, created.text[:300]
    asset_id = created.json()["data"]["id"]

    policy = {
        "use_category_policy": False,
        "depreciation_method": "declining_balance",
        "useful_life_months": 36,
        "declining_rate": 20.0,
        "salvage_rate": 5.0,
        "depreciation_start_date": "2020-01-31",
    }
    r = client.patch(f"/api/v1/assets/{asset_id}", json=policy)
    body = assert_envelope_ok(r)

    rejected = (body["data"].get("_warnings") or {}).get("rejected_fields") or []
    assert not [f for f in policy if f in rejected], (
        f"policy fields missing from _WRITABLE_FIELDS: {rejected}")

    d = body["data"]["financial"]["depreciation"]
    assert d["method"] == "declining_balance"
    assert d["useful_life_months"] == 36
    assert d["declining_rate"] == 20.0
    assert d["start_date"] == "2020-01-31"
    # An explicitly supplied start date is recorded as such, not inferred.
    assert d["start_date_source"] == "manual"
    assert d["start_date_is_estimated"] is False


# ── The schedule endpoint ────────────────────────────────────────────────────

def test_schedule_returns_one_period_per_month_of_life(client, depreciating_asset, capture):
    """GET /api/v1/assets/<id>/depreciation — the full board."""
    r = client.get(f"/api/v1/assets/{depreciating_asset['id']}/depreciation")
    capture("depreciation/schedule", r)
    body = assert_envelope_ok(r)
    d = body["data"]

    assert d["asset"]["id"] == depreciating_asset["id"]
    assert d["period_count"] == LIFE_MONTHS
    assert len(d["periods"]) == LIFE_MONTHS
    assert d["as_of"] is None
    assert d["currency"]["name"]

    first = d["periods"][0]
    assert first["sequence"] == 1
    # Whole-month convention: first period ends the month after the start date.
    assert first["period_end"] == "2022-07-31"
    assert first["charge"] == EXPECTED_MONTHLY_CHARGE


def test_schedule_sums_to_cost_less_salvage(client, depreciating_asset):
    """The rounding-remainder guarantee, over HTTP."""
    r = client.get(f"/api/v1/assets/{depreciating_asset['id']}/depreciation")
    d = assert_envelope_ok(r)["data"]

    total = round(sum(p["charge"] for p in d["periods"]), 2)
    salvage = d["summary"]["salvage_value"]
    assert total == round(COST - salvage, 2)
    # And the board terminates exactly at salvage, not at zero.
    assert d["periods"][-1]["book_value"] == salvage


def test_schedule_accumulates_monotonically(client, depreciating_asset):
    r = client.get(f"/api/v1/assets/{depreciating_asset['id']}/depreciation")
    periods = assert_envelope_ok(r)["data"]["periods"]
    accs = [p["accumulated_depreciation"] for p in periods]
    books = [p["book_value"] for p in periods]
    assert accs == sorted(accs)
    assert books == sorted(books, reverse=True)


def test_as_of_gives_a_point_in_time_view(client, depreciating_asset, capture):
    """?as_of= truncates the board — PRD §13.4 historical register snapshot."""
    r = client.get(f"/api/v1/assets/{depreciating_asset['id']}/depreciation",
                   params={"as_of": "2023-12-31"})
    capture("depreciation/schedule_as_of", r)
    d = assert_envelope_ok(r)["data"]

    assert d["as_of"] == "2023-12-31"
    # 2022-07-31 through 2023-12-31 inclusive = 18 monthly periods.
    assert d["period_count"] == 18
    assert d["periods"][-1]["period_end"] == "2023-12-31"
    assert d["periods"][-1]["accumulated_depreciation"] == 18 * EXPECTED_MONTHLY_CHARGE


def test_as_of_rejects_a_malformed_date(client, depreciating_asset, capture):
    r = client.get(f"/api/v1/assets/{depreciating_asset['id']}/depreciation",
                   params={"as_of": "notadate"})
    capture("depreciation/schedule_bad_as_of", r)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_request"


def test_schedule_404_for_unknown_asset(client, capture):
    r = client.get("/api/v1/assets/99999999/depreciation")
    capture("depreciation/schedule_not_found", r)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_non_depreciating_asset_returns_an_empty_board(client, test_location,
                                                       any_category_id):
    """An asset with no policy is a valid state, not an error."""
    ts = int(time.time())
    created = client.post("/api/v1/assets", json={
        "name": f"pytest-depr-none-{ts}",
        "asset_tag": f"PYTEST-NONE-{ts}",
        "category_id": any_category_id,
        "location_id": test_location["id"],
        "use_category_policy": False,
        "depreciation_method": "none",
    })
    assert created.status_code == 201, created.text[:300]

    r = client.get(f"/api/v1/assets/{created.json()['data']['id']}/depreciation")
    d = assert_envelope_ok(r)["data"]
    assert d["period_count"] == 0
    assert d["periods"] == []
    assert d["summary"]["method"] == "none"
    assert d["summary"]["state"] == "not_applicable"


# ── ERP-managed ──────────────────────────────────────────────────────────────

def test_erp_managed_figures_are_stored_not_computed(client, test_location,
                                                     any_category_id, capture):
    """NRS spec §6.2 — Cadra reads but does not compute. Figures written from
    outside must survive, and no schedule is generated."""
    ts = int(time.time())
    created = client.post("/api/v1/assets", json={
        "name": f"pytest-depr-erp-{ts}",
        "asset_tag": f"PYTEST-ERP-{ts}",
        "category_id": any_category_id,
        "location_id": test_location["id"],
        "acquisition_cost": 1_000_000.0,
        "use_category_policy": False,
        "depreciation_method": "erp_managed",
    })
    assert created.status_code == 201, created.text[:300]
    asset_id = created.json()["data"]["id"]

    fed = client.patch(f"/api/v1/assets/{asset_id}", json={
        "accumulated_depreciation": 250_000.0,
        "current_book_value": 750_000.0,
    })
    capture("depreciation/erp_managed_feed", fed)
    d = assert_envelope_ok(fed)["data"]["financial"]["depreciation"]

    assert d["method"] == "erp_managed"
    assert d["state"] == "erp_managed"
    assert d["accumulated_depreciation"] == 250_000.0
    assert d["current_book_value"] == 750_000.0

    board = client.get(f"/api/v1/assets/{asset_id}/depreciation")
    assert assert_envelope_ok(board)["data"]["period_count"] == 0


# ── Register report ──────────────────────────────────────────────────────────

def test_register_report_shape(client, capture):
    """GET /api/v1/reports/depreciation — totals and breakdowns."""
    r = client.get("/api/v1/reports/depreciation")
    capture("depreciation/report", r)
    d = assert_envelope_ok(r)["data"]

    for key in ("totals", "by_category", "by_state", "by_method",
                "needs_start_date", "missing_cost"):
        assert key in d, f"missing `{key}` in report payload"
    for key in ("asset_count", "depreciable_cost", "accumulated_depreciation",
                "current_book_value"):
        assert key in d["totals"]

    assert isinstance(d["by_category"], list)
    assert isinstance(d["by_state"], dict)
    assert d["totals"]["asset_count"] >= 1


def test_register_report_rejects_a_bad_category_id(client, capture):
    r = client.get("/api/v1/reports/depreciation", params={"category_id": "abc"})
    capture("depreciation/report_bad_category", r)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_request"


def test_register_report_scoped_to_a_category(client, any_category_id):
    r = client.get("/api/v1/reports/depreciation", params={"category_id": any_category_id})
    d = assert_envelope_ok(r)["data"]
    assert d["totals"]["asset_count"] >= 0
