"""9 dashboard endpoints. They aggregate data via Odoo controllers — mostly
return empty payloads in our dev DB (no fleet vehicles seeded). Tests verify
the envelope is correct; data shape is not strictly asserted."""
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
    ("/api/v1/fm/dashboard",            "fm_dashboard"),
])
def test_dashboard_endpoint(client, capture, path, name):
    r = client.get(path)
    capture(f"dashboards/{name}", r)
    assert_envelope_ok(r)
