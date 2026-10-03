"""Handoff 47 — a role is a job: the scope moves, pinned at the contract.

Three rulings moved published routes between scopes, and each is BREAKING
for an API credential provisioned under the old name:

* `identity:read` split — the access record (`/reports/access-changes`) now
  takes `access:read`; the employee picker keeps `identity:read`. Pinned in
  `test_audit_logs.py` beside the report's own suite.
* `dashboards:read` split — the fleet, staff-bus, FM and security routes
  now take `operations:read`; the asset register's own figures
  (`/dashboard/kpis`, `/dashboard/map`, `/reports/depreciation`) keep
  `dashboards:read`. Pinned HERE, both halves.
* tag issuance and replacement moved from `assets:write` to
  `tagging:write` — minting a label is the Tag-Issuing Unit's job, not
  asset-writing. Deciding a replacement stays `approvals:write` (the second
  person). Pinned HERE, all four routes.

And ruling 3 created a role: the Asset Officer, between reading the
register and running it. `/roles` derives from `GROUP_SCOPES`, so what is
asserted here is the published vocabulary — the role exists, is grantable,
carries exactly `assets:write` over Asset User, and the Manager implies it.

Pins read the published contract (`openapi.json`, `/roles`) rather than the
source, because the contract is what Vendra and every credential builds
against. The suite holds one credential and cannot narrow it; refusals per
role are driven in-registry (`myservice_api/tests/test_asset_officer_role.py`)
and as the personas (`e2e/tests/46-…`).
"""
import pytest

from .conftest import assert_envelope_ok


@pytest.fixture(scope="module")
def spec(client):
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200, "openapi.json did not answer"
    return r.json()


def _scopes(spec, path, method):
    assert path in spec["paths"], f"{path} is not published"
    op = spec["paths"][path].get(method)
    assert op, f"{method.upper()} {path} is not published"
    return op.get("x-cadra-scopes")


# ─── ruling 1 · the dashboards:read split ────────────────────────────

#: The operational half — fleet, staff bus, facilities, security.
OPERATIONS_ROUTES = [
    ("/api/v1/dashboard/fleet-command", "get"),
    ("/api/v1/fleet", "get"),
    ("/api/v1/fleet/{id}", "get"),
    ("/api/v1/fleet/dashboard", "get"),
    ("/api/v1/fm/dashboard", "get"),
    ("/api/v1/security/kpis", "get"),
    ("/api/v1/security/map-data", "get"),
    ("/api/v1/security/trend", "get"),
    ("/api/v1/security/recent", "get"),
]

#: The register's own figures — aggregates, nothing identifying an asset.
DASHBOARD_ROUTES = [
    ("/api/v1/dashboard/kpis", "get"),
    ("/api/v1/dashboard/map", "get"),
    ("/api/v1/reports/depreciation", "get"),
]


def test_the_operational_dashboards_take_operations_read(spec):
    """An Asset User reading the register's figures is not also handed the
    fleet, and a Security Officer is not handed the register's figures."""
    wrong = {f"{m.upper()} {p}": _scopes(spec, p, m)
             for p, m in OPERATIONS_ROUTES
             if _scopes(spec, p, m) != ["operations:read"]}
    assert not wrong, (
        "these operational routes do not declare [operations:read]: %s — "
        "the dashboards:read split (handoff 47 ruling 1) is undone" % wrong)


def test_the_registers_own_figures_keep_dashboards_read(spec):
    wrong = {f"{m.upper()} {p}": _scopes(spec, p, m)
             for p, m in DASHBOARD_ROUTES
             if _scopes(spec, p, m) != ["dashboards:read"]}
    assert not wrong, (
        "these register-figure routes do not declare [dashboards:read]: %s "
        "— they are the asset dashboard's backing and stay on the register "
        "side of the split" % wrong)


# ─── ruling 2 · minting and replacing a tag is tagging ───────────────

def test_tag_issuance_and_replacement_take_tagging_write(spec):
    """The unit's own scope covers the unit's own job. Until handoff 47 the
    Tag-Issuing Unit could confirm a label was on and could not print or
    replace one, while every holder of `assets:write` could."""
    for path, method in [("/api/v1/barcode/generate", "post"),
                         ("/api/v1/tags/{id}/request-replacement", "post")]:
        got = _scopes(spec, path, method)
        assert got == ["tagging:write"], (
            f"{method.upper()} {path} declares {got}; issuing and replacing "
            "a tag is tagging, not asset-writing (handoff 47 ruling 2)")


def test_deciding_a_replacement_stays_with_the_second_person(spec):
    """`approvals:write`, unchanged on purpose: the requester and the
    decider are two people, as on a move (handoff 38)."""
    for path in ["/api/v1/tags/{id}/approve-replacement",
                 "/api/v1/tags/{id}/reject-replacement"]:
        got = _scopes(spec, path, "post")
        assert got == ["approvals:write"], (
            f"POST {path} declares {got}; the decision is the second "
            "person's and takes approvals:write")


# ─── ruling 3 · the Asset Officer exists, and is a job ───────────────

@pytest.fixture(scope="module")
def roles(client, admin_scope):
    body = assert_envelope_ok(client.get("/api/v1/roles"))
    return {r["key"]: r for r in body["data"]}


def test_the_asset_officer_is_published_and_grantable(roles):
    officer = roles.get("asset_officer")
    assert officer, (
        "`asset_officer` is not in the /roles vocabulary — GROUP_SCOPES "
        "lost its row, so nobody can hold or grant the role")
    assert officer["grantable"] is True, (
        "the Asset Officer is not grantable over the API — a role "
        "administrators cannot grant from the Users screen does not exist")
    assert officer["scopes"] == ["assets:write"], (
        "the officer's own row grants %s; the delta over Asset User is "
        "exactly [assets:write]" % officer["scopes"])
    assert "asset_user" in officer["implies"], (
        "the Asset Officer no longer implies Asset User")


def test_the_manager_implies_the_officer(roles):
    manager = roles.get("asset_manager")
    assert manager, "`asset_manager` left the /roles vocabulary"
    assert {"asset_officer", "asset_user"} <= set(manager["implies"]), (
        "Asset Manager implies %s; the ladder is User < Officer < Manager "
        "and a manager who cannot register an asset is not a manager"
        % manager["implies"])
