"""10 dashboard endpoints. They aggregate data via Odoo controllers — mostly
return empty payloads in our dev DB (no fleet vehicles seeded). Tests verify
the envelope is correct; data shape is not strictly asserted, except where a
key LEAVING a payload is the control (handoff 50 §2.1, below)."""
import pytest

from .conftest import assert_envelope_ok


@pytest.mark.parametrize("path,name", [
    ("/api/v1/dashboard/kpis",          "ops_kpis"),
    ("/api/v1/dashboard/map",           "ops_map"),
    ("/api/v1/dashboard/fleet-command", "ops_fleet_command"),
    ("/api/v1/security/kpis",           "security_kpis"),
    ("/api/v1/security/map-data",       "security_map_data"),
    ("/api/v1/security/trend",          "security_trend"),
    ("/api/v1/security/recent",         "security_recent"),
    ("/api/v1/fleet/dashboard",         "fleet_dashboard"),
    ("/api/v1/fleet/map",               "fleet_map"),
    ("/api/v1/fm/dashboard",            "fm_dashboard"),
])
def test_dashboard_endpoint(client, capture, path, name):
    r = client.get(path)
    capture(f"dashboards/{name}", r)
    assert_envelope_ok(r)


def test_the_map_no_longer_carries_the_fleet(client, capture):
    """Handoff 50 §2.1 — hidden must mean gone.

    The map's `fleet` rows carried plate and driver — identified personal
    data — to every holder of `dashboards:read`, so an Asset User refused
    `/fleet` could still read them through the map. The map now answers
    `locations` alone; the vehicle rows moved to `GET /fleet/map` behind
    `operations:read` (BREAKING, announced). A key coming back here is the
    leak reopening, whatever the diff says it was for.
    """
    r = client.get("/api/v1/dashboard/map")
    capture("dashboards/ops_map_locations_only", r)
    data = assert_envelope_ok(r)["data"]

    assert "locations" in data, (
        f"the map lost its own payload — keys: {sorted(data)}")
    for gone in ("fleet", "recent_requests"):
        assert gone not in data, (
            f"`{gone}` is back on /dashboard/map. Handoff 50 §2.1 took it "
            "off because the register scope must not read the fleet's "
            "plates and drivers through the map."
        )


def test_the_fleet_map_answers_the_fleet(client, capture):
    """The rows that left the map: `GET /fleet/map`, `operations:read`.

    The suite's credential covers the scope (admin wildcard); the per-role
    refusals are driven in test_role_is_a_job.py against the published
    contract and as the personas (e2e/tests/46-…).
    """
    r = client.get("/api/v1/fleet/map")
    capture("dashboards/fleet_map_rows", r)
    data = assert_envelope_ok(r)["data"]

    assert isinstance(data.get("fleet"), list), (
        f"GET /fleet/map must answer a `fleet` list — keys: {sorted(data)}")
