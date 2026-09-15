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


def test_patch_category_policy_propagates_to_its_assets(client, admin_scope, a_category, capture):
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


def test_patch_category_accepts_identity_fields(client, admin_scope, a_category):
    """`name` was rejected while this controller only served the depreciation
    screen. The categories admin screen makes renaming its job, so it is
    writable now — this test records that reversal deliberately."""
    original = a_category["name"]
    try:
        r = client.patch(f"/api/v1/asset-categories/{a_category['id']}",
                         json={"name": f"{original} (renamed by test)"})
        d = assert_envelope_ok(r)["data"]
        assert d["name"] == f"{original} (renamed by test)"
    finally:
        client.patch(f"/api/v1/asset-categories/{a_category['id']}",
                     json={"name": original})


def test_patch_category_rejects_unknown_fields(client, admin_scope, a_category):
    r = client.patch(f"/api/v1/asset-categories/{a_category['id']}",
                     json={"not_a_real_field": 1})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_request"


def test_patch_category_rejects_an_unknown_fm_domain(client, admin_scope, a_category):
    """Handoff 25 C2. The refusal names the accepted set under BOTH keys.

    Every other refusal in this API publishes `allowed_values`; the three
    refusals in `v1_settings.py` published `allowed` alone, so a client keying
    on the standard name got nothing from them and had no way to know these
    were the odd ones out. The handoff named one site; a search found three.

    Both keys carry the same list. `allowed` is DEPRECATED, not removed — a
    published details key is API surface, and renaming it outright would break
    any client reading it today. It goes at the next major version; see
    `docs/api/CHANGELOG.md` for the date.
    """
    r = client.patch(f"/api/v1/asset-categories/{a_category['id']}",
                     json={"domain": "nonsense"})
    assert r.status_code == 400
    details = r.json()["error"]["details"]
    assert details.get("allowed_values"), (
        "the refusal carries no `allowed_values`, which is the key every "
        "other refusal in this API uses")
    assert details.get("allowed") == details["allowed_values"], (
        "`allowed` is deprecated but must keep answering with the same list "
        "until it is removed at the next major version")


# ── Create / delete ──────────────────────────────────────────────────────────

def test_create_then_delete_a_category(client, admin_scope, capture):
    ts = int(time.time())
    r = client.post("/api/v1/asset-categories", json={
        "name": f"pytest-category-{ts}",
        "code": f"PT{ts % 10000}",
        "domain": "other",
        "pm_interval_days": 90,
    })
    capture("settings/category_create", r)
    d = assert_envelope_ok(r, expected_status=201)["data"]
    assert d["name"] == f"pytest-category-{ts}"
    assert d["domain"] == "other"
    assert d["pm_interval_days"] == 90
    assert d["asset_count"] == 0

    gone = client.delete(f"/api/v1/asset-categories/{d['id']}")
    capture("settings/category_delete", gone)
    assert assert_envelope_ok(gone)["data"]["deleted"] is True

    remaining = {c["id"] for c in assert_envelope_ok(
        client.get("/api/v1/asset-categories"))["data"]}
    assert d["id"] not in remaining


def test_a_category_carries_its_own_verification_window(client, admin_scope):
    """`verification_interval_days` is writable, readable and survives a PATCH.

    `is_verified` used to be measured against a hardcoded 365 days that nothing
    ever re-evaluated, so it could only move false -> true: an asset verified
    once was reported verified for ever. It now expires on a per-category
    window, and this is the route a tenant sets that window from — the same
    screen, and the same shape, as `pm_interval_days` beside it.

    0 is not "verified only if verified today". It is the sentinel for "use the
    tenant default", which is why the API reports it as null rather than 0.
    """
    ts = int(time.time())
    r = client.post("/api/v1/asset-categories", json={
        "name": f"pytest-verify-{ts}",
        "code": f"PV{ts % 10000}",
        "domain": "other",
        "verification_interval_days": 90,
    })
    created = assert_envelope_ok(r, expected_status=201)["data"]
    try:
        assert created["verification_interval_days"] == 90

        # It reads back on the list route, not just the create response.
        listed = {c["id"]: c for c in assert_envelope_ok(
            client.get("/api/v1/asset-categories"))["data"]}
        assert listed[created["id"]]["verification_interval_days"] == 90

        patched = assert_envelope_ok(client.patch(
            f"/api/v1/asset-categories/{created['id']}",
            json={"verification_interval_days": 180}))["data"]
        assert patched["verification_interval_days"] == 180

        # Unset is reported as null — the "inherit the tenant default"
        # sentinel, distinguishable from a real 0-day window nobody wants.
        cleared = assert_envelope_ok(client.patch(
            f"/api/v1/asset-categories/{created['id']}",
            json={"verification_interval_days": 0}))["data"]
        assert cleared["verification_interval_days"] is None
    finally:
        client.delete(f"/api/v1/asset-categories/{created['id']}")


def test_create_category_requires_a_name(client, admin_scope):
    r = client.post("/api/v1/asset-categories", json={"code": "NONAME"})
    assert r.status_code == 400


def test_cannot_delete_a_category_that_holds_assets(client, admin_scope, a_category, capture):
    """category_id is required on nrs.asset, so deleting one in use would orphan
    rows or fail at the database. Say so plainly instead."""
    r = client.delete(f"/api/v1/asset-categories/{a_category['id']}")
    capture("settings/category_delete_conflict", r)
    assert r.status_code == 409
    body = r.json()["error"]
    assert body["code"] == "conflict"
    assert body["details"]["asset_count"] == a_category["asset_count"]

    # Still there.
    ids = {c["id"] for c in assert_envelope_ok(
        client.get("/api/v1/asset-categories"))["data"]}
    assert a_category["id"] in ids


def test_patch_unknown_category_404(client, admin_scope, capture):
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
        client, test_location, a_category, admin_scope, capture):
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


def test_settings_reject_unknown_values(client, admin_scope):
    for body in ({"mode": "nonsense"}, {"proration": "fortnightly"}):
        r = client.patch("/api/v1/settings/depreciation", json=body)
        assert r.status_code == 400, f"{body} should be rejected"


def test_settings_reject_a_body_with_nothing_writable(client, admin_scope):
    r = client.patch("/api/v1/settings/depreciation", json={"not_a_setting": 1})
    assert r.status_code == 400
    assert "writable" in r.json()["error"]["details"]


# ── Recompute ────────────────────────────────────────────────────────────────

def test_recompute_stamps_the_run(client, admin_scope, capture):
    r = client.post("/api/v1/settings/depreciation/recompute", json={})
    capture("settings/recompute", r)
    d = assert_envelope_ok(r)["data"]

    assert isinstance(d["recomputed"], int)
    assert d["last_recompute"], "a completed run must stamp last_recompute"
