"""Depreciation configuration: categories, tenant settings, recompute.

Writes are on the `admin` scope by design — changing a category's useful life
restates book value on every asset in that class, which is a different risk from
editing one asset. These tests use the shared client, which holds a wildcard
scope, so they exercise behaviour rather than scope enforcement.
"""
import time

import pytest

from .conftest import assert_envelope_ok


@pytest.fixture(scope="module")
def a_category(client):
    """A category that actually has assets, so policy changes are observable."""
    r = client.get("/api/v1/asset-categories")
    cats = assert_envelope_ok(r)["data"]
    with_assets = [c for c in cats if c["asset_count"] > 0]
    if not with_assets:
        pytest.skip("no category has assets on this tenant")
    return max(with_assets, key=lambda c: c["asset_count"])


# ── Categories ───────────────────────────────────────────────────────────────

def test_list_categories(client, capture):
    """GET /api/v1/asset-categories — the settings screen's table."""
    r = client.get("/api/v1/asset-categories")
    capture("settings/categories_list", r)
    cats = assert_envelope_ok(r)["data"]

    assert isinstance(cats, list) and cats, "expected at least one category"
    c = cats[0]
    for key in ("id", "name", "asset_count", "depreciating_count", "depreciation"):
        assert key in c, f"missing `{key}`"
    for key in ("method", "useful_life_months", "declining_rate", "salvage_rate"):
        assert key in c["depreciation"]


def test_patch_category_policy_propagates_to_its_assets(client, a_category, capture):
    """The point of the screen: correcting a useful life must restate the assets
    that inherit it, not wait for the monthly cron."""
    original = a_category["depreciation"]["useful_life_months"] or 60
    changed = original + 12
    try:
        r = client.patch(f"/api/v1/asset-categories/{a_category['id']}",
                         json={"useful_life_months": changed})
        capture("settings/category_patch", r)
        d = assert_envelope_ok(r)["data"]

        assert d["depreciation"]["useful_life_months"] == changed
        assert d["assets_recomputed"] >= 1, "inheriting assets should be recomputed"

        # And it is visible on an asset, immediately.
        page = client.get("/api/v1/assets",
                          params={"category_id": a_category["id"], "limit": 1})
        asset = assert_envelope_ok(page)["data"][0]
        assert asset["financial"]["depreciation"]["useful_life_months"] == changed
    finally:
        client.patch(f"/api/v1/asset-categories/{a_category['id']}",
                     json={"useful_life_months": original})


def test_patch_category_rejects_non_policy_fields(client, a_category):
    """`name` is a taxonomy change, not a depreciation setting."""
    r = client.patch(f"/api/v1/asset-categories/{a_category['id']}",
                     json={"name": "renamed-by-test"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_request"

    # And the name is untouched.
    check = client.get("/api/v1/asset-categories")
    names = {c["id"]: c["name"] for c in assert_envelope_ok(check)["data"]}
    assert names[a_category["id"]] == a_category["name"]


def test_patch_unknown_category_404(client, capture):
    r = client.patch("/api/v1/asset-categories/99999999",
                     json={"useful_life_months": 12})
    capture("settings/category_not_found", r)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


# ── Tenant settings ──────────────────────────────────────────────────────────

def test_get_settings_shape(client, capture):
    r = client.get("/api/v1/settings/depreciation")
    capture("settings/depreciation_get", r)
    d = assert_envelope_ok(r)["data"]

    assert d["mode"] in ("computed", "erp_managed")
    assert d["proration"] in ("whole_month", "daily")
    assert isinstance(d["declining_switches_to_straight_line"], bool)
    for key in ("needs_start_date", "missing_cost", "not_configured"):
        assert key in d["data_quality"]


def test_the_straight_line_switch_removes_the_final_period_cliff(
        client, test_location, a_category, capture):
    """The setting exists to fix a real defect: with pure declining balance the
    final charge can be ~50x its predecessor. Toggling it must actually change
    the schedules, not just flip a stored flag.

    Creates its own asset rather than hunting for one: service-account tokens
    are capped at a single 100-row page with no cursor, so an existing
    declining-balance asset further down the register is unreachable here.
    """
    ts = int(time.time())
    created = client.post("/api/v1/assets", json={
        "name": f"pytest-cliff-{ts}",
        "asset_tag": f"PYTEST-CLIFF-{ts}",
        "category_id": a_category["id"],
        "location_id": test_location["id"],
        "acquisition_cost": 66_000.0,
        "acquisition_date": "2020-01-31",
        "use_category_policy": False,
        "depreciation_method": "declining_balance",
        "useful_life_months": 36,
        "declining_rate": 20.0,
        "salvage_rate": 5.0,
    })
    assert created.status_code == 201, created.text[:300]
    asset_id = created.json()["data"]["id"]

    def last_ratio():
        r = client.get(f"/api/v1/assets/{asset_id}/depreciation")
        periods = assert_envelope_ok(r)["data"]["periods"]
        assert len(periods) >= 2 and periods[-2]["charge"]
        return periods[-1]["charge"] / periods[-2]["charge"]

    try:
        client.patch("/api/v1/settings/depreciation",
                     json={"declining_switches_to_straight_line": True})
        smooth = last_ratio()

        r = client.patch("/api/v1/settings/depreciation",
                         json={"declining_switches_to_straight_line": False})
        capture("settings/depreciation_patch", r)
        cliff = last_ratio()

        assert cliff > 10, f"expected a pronounced cliff with the switch off, got {cliff:.1f}x"
        assert smooth < 2, f"switch on should leave no jump, got {smooth:.1f}x"
    finally:
        client.patch("/api/v1/settings/depreciation",
                     json={"declining_switches_to_straight_line": True})


def test_settings_reject_unknown_values(client):
    for body in ({"mode": "nonsense"}, {"proration": "fortnightly"}):
        r = client.patch("/api/v1/settings/depreciation", json=body)
        assert r.status_code == 400, f"{body} should be rejected"


def test_settings_reject_a_body_with_nothing_writable(client):
    r = client.patch("/api/v1/settings/depreciation", json={"not_a_setting": 1})
    assert r.status_code == 400
    assert "writable" in r.json()["error"]["details"]


# ── Recompute ────────────────────────────────────────────────────────────────

def test_recompute_stamps_the_run(client, capture):
    r = client.post("/api/v1/settings/depreciation/recompute", json={})
    capture("settings/recompute", r)
    d = assert_envelope_ok(r)["data"]

    assert isinstance(d["recomputed"], int)
    assert d["last_recompute"], "a completed run must stamp last_recompute"
