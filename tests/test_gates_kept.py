"""The gates, kept — handoff 58, over HTTP.

Every finding report 57 left open, driven through the published surface, and
Section 12 and the role-exclusion table, as the people who use them. The
walks go through `tests/gates.py` — the seven demo personas — because the
no-two-gates rule refuses one credential at the second gate.

Every test that turns the receipt switch, changes a class or an exclusion,
or grants a role puts it back in `finally`.
"""
import time
import uuid

import pytest

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok

SETTINGS_GATE = "/api/v1/settings/receipt-gate"


def _uniq(prefix):
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def gated(client, admin_scope):
    """The switch ON for the test, the tenant's own value afterwards."""
    was = gates.receipt_gated(client)
    assert_envelope_ok(client.patch(SETTINGS_GATE, json={"enabled": True}))
    try:
        yield
    finally:
        assert_envelope_ok(client.patch(SETTINGS_GATE, json={"enabled": was}))


def _categories(client):
    return assert_envelope_ok(client.get("/api/v1/asset-categories"))["data"]


@pytest.fixture
def furniture(client):
    """A `tag_id` class — the seeded furniture one — restored afterwards."""
    rows = [c for c in _categories(client)
            if c["identification_mode"] == "tag_id"]
    assert rows, ("no tag_id class on this tenant: the 19.0.1.27.0 migration "
                  "seeds furniture as tag_id")
    row = rows[0]
    try:
        yield row
    finally:
        # `null` puts the class back on its mode's DEFAULT schema rather than
        # pinning the default as a stored one (verification pass): the
        # seeded classes carry none.
        assert_envelope_ok(client.patch(
            f"/api/v1/asset-categories/{row['id']}",
            json={"identification_mode": row["identification_mode"],
                  "class_attributes_schema": None}))


def _chair(client, category_id, **over):
    body = {"name": _uniq("pytest-58-chair"), "category_id": category_id,
            "make": "Ergo", "model_name": "EC-200", "colour": "Black",
            "material": "Leather", "dimensions": "60x60x120 cm"}
    body.update(over)
    return body


# ── the published surface ────────────────────────────────────────────

def test_every_class_publishes_its_identification(client):
    rows = _categories(client)
    assert rows
    for row in rows:
        # `record_only` since handoff 59 (additive): a test category of it
        # exists on any tenant the handoff-59 suite has run on.
        assert row["identification_mode"] in ("serial", "tag_id", "pool",
                                              "record_only")
        assert isinstance(row["class_attributes_schema"]["mandatory"], list)


def test_readiness_answers_without_a_token(unauthed_client):
    r = unauthed_client.get("/api/v1/meta/readiness")
    assert r.status_code == 200, r.text[:300]
    assert r.json()["data"]["ready"] is True


# ── Section 12 at the receipt ─────────────────────────────────────────

def test_a_tag_id_unit_without_a_serial_walks_all_seven_gates(
        client, gated, furniture):
    a = gates.receive(client, **_chair(client, furniture["id"]))
    assert a["register_state"] == "captured"
    assert a["identification_mode"] == "tag_id"
    assert a["serial_number"] is None
    a = gates.ready_to_affix(client, a)
    # The label, and no tick: refused — there is no serial to scan, so the
    # attributes are the second check.
    body = assert_envelope_err(client.post(
        f"/api/v1/assets/{a['id']}/tag-affixed",
        json={"tag_number": a["tagging"]["tag_number"]}),
        400, "validation_failed")
    assert body["error"]["details"]["field"] == "attributes_confirmed"
    done = gates.on_the_register(client, a)  # the tagger ticks it
    assert done["register_state"] == "registered"
    assert done["tagging"]["is_tagged"] is True
    history = assert_envelope_ok(client.get(
        f"/api/v1/assets/{done['id']}/history"))["data"]
    affix = [e for e in history["events"] if e.get("type") == "gate_fired"
             and "label_and_attributes" in str(e)]
    assert affix, "the affix event records which check was used"


def test_a_tag_id_unit_missing_its_colour_is_refused_naming_it(
        client, gated, furniture):
    body = _chair(client, furniture["id"])
    del body["colour"]
    err = assert_envelope_err(client.post("/api/v1/assets", json=body),
                              400, "validation_failed")["error"]
    assert err["details"]["missing_fields"] == ["colour"]
    assert "colour" in err["message"]


def test_a_serial_unit_without_a_serial_is_refused(client, gated):
    err = assert_envelope_err(client.post("/api/v1/assets", json={
        "name": _uniq("pytest-58-noserial"), "category_id": 1,
        "make": "Perkins", "model_name": "P500"}),
        400, "validation_failed")["error"]
    assert err["message"].endswith(
        ": 0 of 1 serial numbers captured. Capture one serial number per "
        "accepted unit.")


def test_a_pool_unit_is_refused_with_the_phase_e_sentence(
        client, gated, furniture):
    assert_envelope_ok(client.patch(
        f"/api/v1/asset-categories/{furniture['id']}",
        json={"identification_mode": "pool"}))
    err = assert_envelope_err(client.post(
        "/api/v1/assets", json=_chair(client, furniture["id"])),
        400, "validation_failed")["error"]
    assert err["message"] == ("Pool identification is not built yet "
                              "(Addendum A Phase E).")


def test_a_change_of_mode_leaves_units_already_received_alone(
        client, gated, furniture):
    chair = gates.receive(client, **_chair(client, furniture["id"]))
    assert_envelope_ok(client.patch(
        f"/api/v1/asset-categories/{furniture['id']}",
        json={"identification_mode": "serial",
              "class_attributes_schema": {"mandatory": ["make",
                                                        "model_name"]}}))
    again = assert_envelope_ok(client.get(
        f"/api/v1/assets/{chair['id']}"))["data"]
    assert again["identification_mode"] == "tag_id", "AD-31"
    # A NEW one of the class is now serial-mode.
    assert_envelope_err(client.post(
        "/api/v1/assets", json=_chair(client, furniture["id"])),
        400, "validation_failed")
    # And the old one still affixes on the label and the tick.
    done = gates.on_the_register(client, again)
    assert done["register_state"] == "registered"


def test_empty_serials_never_collide_and_a_real_one_does(
        client, gated, furniture):
    gates.receive(client, **_chair(client, furniture["id"]))
    gates.receive(client, **_chair(client, furniture["id"]))
    serial = _uniq("SN58DUP")
    gates.receive(client, name=_uniq("pytest-58-dup"), serial_number=serial)
    err = assert_envelope_err(client.post("/api/v1/assets", json={
        "name": _uniq("pytest-58-dup"), "category_id": 1,
        "serial_number": f"  {serial.lower()} ", "make": "x",
        "model_name": "y"}), 400, "validation_failed")["error"]
    assert "is already registered as an asset in Cadra" in err["message"]


def test_with_the_switch_off_nothing_is_asked_of_a_receipt(client, admin_scope):
    was = gates.receipt_gated(client)
    assert_envelope_ok(client.patch(SETTINGS_GATE, json={"enabled": False}))
    try:
        a = assert_envelope_ok(client.post("/api/v1/assets", json={
            "name": _uniq("pytest-58-off"), "category_id": 1}), 201)["data"]
        assert a["register_state"] == "registered"
        assert a["identification_mode"] is None
    finally:
        assert_envelope_ok(client.patch(SETTINGS_GATE, json={"enabled": was}))


# ── D3: the affix refusal has the gates' shape ────────────────────────

def test_a_two_gates_refusal_at_affix_is_a_409(client, gated):
    a = gates.receive(client, name=_uniq("pytest-58-d3"))
    # The SUITE submits: it has now fired the receipt gate on this unit.
    assert_envelope_ok(client.post(f"/api/v1/assets/{a['id']}/gates/submit",
                                   json={}))
    a = assert_envelope_ok(client.get(f"/api/v1/assets/{a['id']}"))["data"]
    a = gates.ready_to_affix(client, a)
    body = assert_envelope_err(client.post(
        f"/api/v1/assets/{a['id']}/tag-affixed",
        json={"tag_number": a["tagging"]["tag_number"],
              "serial_number": a["serial_number"]}), 409, "conflict")
    err = body["error"]
    assert err["details"]["reason"] == "segregation_of_duties"
    assert err["details"]["earlier"]["gate"] == "receipt"
    assert err["message"].startswith("You received this unit on ")
    assert err["message"].endswith("; a different person must tag it.")


# ── P5: a candidate is not on the register ───────────────────────────

def _employee_id(client):
    rows = assert_envelope_ok(client.get("/api/v1/identity/employees",
                                         params={"limit": 1}))["data"]
    assert rows, "no employee on this tenant to name as a custodian"
    return rows[0]["id"]


def _p5(response, tail):
    err = assert_envelope_err(response, 409, "conflict")["error"]
    assert err["details"]["reason"] == "not_on_the_register"
    assert err["message"].startswith("This unit is not on the register yet "
                                     "(waiting on Store); "), err["message"]
    assert err["message"].endswith(tail), err["message"]


def test_every_writer_refuses_a_candidate(client, gated, any_location):
    a = gates.receive(client, name=_uniq("pytest-58-p5"))
    emp = _employee_id(client)
    base = f"/api/v1/assets/{a['id']}"
    _p5(client.patch(base, json={"custodian_id": emp}),
        "a custodian can be assigned once it is registered.")
    _p5(client.patch(base, json={"location_id": any_location}),
        "it can be moved once it is registered.")
    _p5(client.patch(base, json={"state": "disposed"}),
        "it can be disposed of once it is registered.")
    _p5(client.post(f"{base}/move", json={
        "to_location_id": any_location, "reason": "probe",
        "approver_id": 2}), "it can be moved once it is registered.")
    _p5(client.post(f"{base}/transfer-custody", json={
        "to_custodian_id": emp, "reason": "probe", "approver_id": 2}),
        "a custodian can be assigned once it is registered.")
    _p5(client.post(f"{base}/condemn", json={"reason": "probe"}),
        "it can be disposed of once it is registered.")
    still = assert_envelope_ok(client.get(base))["data"]
    assert still["current_custodian"] is None
    assert still["state"] != "disposed"


def test_a_receipt_cannot_arrive_disposed(client, gated):
    """P5 at the door too (verification pass): a unit that was never on the
    register cannot leave it — and a disposed candidate walked to
    `approve-registration` would have sent SAP a master for a write-off."""
    r = client.post("/api/v1/assets", json=gates.receipt_body(
        client, name=_uniq("pytest-58-p5d"), state="disposed"))
    _p5(r, "it can be disposed of once it is registered.")


def test_a_receipt_with_a_custodian_is_refused(client, gated):
    r = client.post("/api/v1/assets", json={
        "name": _uniq("pytest-58-p5r"), "category_id": 1,
        "serial_number": _uniq("SN58"), "make": "x", "model_name": "y",
        "custodian_id": _employee_id(client)})
    _p5(r, "a custodian can be assigned once it is registered.")


# ── the switch turned off with a unit in flight (report 58 §9) ────────

def test_turning_the_switch_off_leaves_an_in_flight_unit_in_the_chain(
        client, admin_scope):
    was = gates.receipt_gated(client)
    assert_envelope_ok(client.patch(SETTINGS_GATE, json={"enabled": True}))
    try:
        a = gates.receive(client, name=_uniq("pytest-58-inflight"))
        a = gates._walk(client, a, "vfm_pending")
        assert_envelope_ok(client.patch(SETTINGS_GATE,
                                        json={"enabled": False}))
        listed = assert_envelope_ok(client.get(
            "/api/v1/assets", params={"q": a["name"]}))["data"]
        assert a["id"] not in {r["id"] for r in listed}, (
            "turning the switch off does not put a candidate on the register")
        done = gates.on_the_register(client, a)
        assert done["register_state"] == "registered"
        listed = assert_envelope_ok(client.get(
            "/api/v1/assets", params={"q": a["name"]}))["data"]
        assert a["id"] in {r["id"] for r in listed}
    finally:
        assert_envelope_ok(client.patch(SETTINGS_GATE, json={"enabled": was}))


# ── settings:classes ─────────────────────────────────────────────────

def test_the_asset_controller_changes_a_mode_and_nothing_else(
        client, furniture):
    path = f"/api/v1/asset-categories/{furniture['id']}"
    r = gates._as(client, "asset_controller", "PATCH",
                  path.replace("/api/v1", ""),
                  {"identification_mode": "serial"})
    assert r.status_code == 200, r.text[:300]
    assert r.json()["data"]["identification_mode"] == "serial"
    r = gates._as(client, "asset_controller", "PATCH",
                  path.replace("/api/v1", ""), {"name": "renamed"})
    assert r.status_code == 403, r.text[:300]
    assert "settings:write" in r.json()["error"]["message"]
    r = gates._as(client, "storekeeper", "PATCH",
                  path.replace("/api/v1", ""),
                  {"identification_mode": "tag_id"})
    assert r.status_code == 403, r.text[:300]
    report = assert_envelope_ok(client.get(
        "/api/v1/reports/configuration-changes",
        params={"from": time.strftime("%Y-%m-%d"),
                "to": time.strftime("%Y-%m-%d"), "limit": 500}))["data"]
    key = f"cadra.class_identification.{furniture['id']}"
    rows = [x for x in report["parameters"] if x["key"] == key]
    assert rows, f"{key} is on the configuration record"
    assert rows[0]["current_value"].startswith("serial; ")


def test_the_category_patch_asks_for_its_scope_first(client):
    """Before existence and before the body: a caller holding neither
    `settings:write` nor `settings:classes` is refused 403 and learns
    nothing about which categories exist; a holder of either reaches the
    404 (verification pass — it answered 404/400 to anybody)."""
    r = gates._as(client, "storekeeper", "PATCH", "/asset-categories/0", {})
    assert r.status_code == 403, r.text[:300]
    r = gates._as(client, "asset_controller", "PATCH", "/asset-categories/0",
                  {"identification_mode": "serial"})
    assert r.status_code == 404, r.text[:300]
    spec = client.get("/api/v1/openapi.json").json()
    op = spec["paths"]["/api/v1/asset-categories/{id}"]["patch"]
    assert op["security"] == [{"bearerAuth": []}], (
        "the route requires a token; the published spec must say so")
    assert op["x-cadra-scopes-any-of"] == ["settings:write",
                                          "settings:classes"]


def test_a_repeat_affix_of_a_tag_id_unit_needs_no_tick(
        client, gated, furniture):
    """Handoff 39's idempotent repeat holds for a `tag_id` unit too: the
    tick is asked of the FIRST confirmation, not of a repeat."""
    done = gates.new_registered_asset(client, **_chair(client,
                                                       furniture["id"]))
    r = client.post(f"/api/v1/assets/{done['id']}/tag-affixed",
                    json={"tag_number": done["tagging"]["tag_number"]})
    assert r.status_code == 200, r.text[:300]


# ── rule 2: the role-exclusion table ─────────────────────────────────

@pytest.fixture
def person(client, admin_scope):
    """One invented person for the run, deactivated at the end."""
    r = client.post("/api/v1/users", json={
        "name": _uniq("pytest-58-person"),
        "email": f"{_uniq('p58')}@example.invalid", "roles": ["asset_user"],
        # No letter: a tenant with no outgoing mail (CI) answers 500 to an
        # invitation it cannot send, and this fixture is about roles.
        "send_invitation": False})
    data = assert_envelope_ok(r, 201)["data"]
    try:
        yield data
    finally:
        client.post(f"/api/v1/users/{data['id']}/roles",
                    json={"roles": ["asset_user"]})
        client.post(f"/api/v1/users/{data['id']}/deactivate", json={})


def _exclusions(client):
    return assert_envelope_ok(client.get(
        "/api/v1/settings/role-exclusions"))["data"]


def test_every_seeded_exclusion_refuses_the_grant(client, person):
    rows = [x for x in _exclusions(client) if x["active"]]
    assert len(rows) >= 8, rows
    for x in rows:
        a, b = x["role_a"]["key"], x["role_b"]["key"]
        assert_envelope_ok(client.post(
            f"/api/v1/users/{person['id']}/roles", json={"roles": [a]}))
        for dry in (True, False):
            err = assert_envelope_err(client.post(
                f"/api/v1/users/{person['id']}/roles",
                json={"roles": [a, b], "dry_run": dry}), 403,
                "forbidden")["error"]
            assert "cannot be held by one person" in err["message"]
            assert x["role_a"]["name"] in err["message"]
            assert x["role_b"]["name"] in err["message"]


def test_an_exclusion_switched_off_lets_the_grant_through_and_is_recorded(
        client, person):
    x = next(r for r in _exclusions(client)
             if r["role_a"]["key"] == "register_maker")
    try:
        assert_envelope_ok(client.patch(
            f"/api/v1/settings/role-exclusions/{x['id']}",
            json={"active": False}))
        assert_envelope_ok(client.post(
            f"/api/v1/users/{person['id']}/roles",
            json={"roles": ["register_maker", "register_checker"]}))
        report = assert_envelope_ok(client.get(
            "/api/v1/reports/configuration-changes",
            params={"from": time.strftime("%Y-%m-%d"),
                    "to": time.strftime("%Y-%m-%d"),
                    "limit": 500}))["data"]
        mine = [r for r in report["parameters"]
                if r["key"] == f"cadra.role_exclusion.{x['id']}"]
        assert mine and mine[0]["current_value"].startswith("off; ")
    finally:
        assert_envelope_ok(client.patch(
            f"/api/v1/settings/role-exclusions/{x['id']}",
            json={"active": True}))
    # Switched back on, the holder is listed, not revoked.
    body = assert_envelope_ok(client.get(
        "/api/v1/settings/conflicting-grants"))
    held = [p for p in body["data"] if p["user"]["id"] == person["id"]]
    assert held, "an existing pair is listed, never revoked"
    assert body["meta"]["total"] >= 1


def test_an_exclusion_body_is_checked_before_anything_is_written(client):
    assert_envelope_err(client.post("/api/v1/settings/role-exclusions",
                                    json={"role_a": "register_maker",
                                          "role_b": "nobody",
                                          "reason": "x"}),
                        400, "invalid_request")
    assert_envelope_err(client.post("/api/v1/settings/role-exclusions",
                                    json={"role_a": "register_maker",
                                          "role_b": "register_checker",
                                          "reason": "x", "colour": "red"}),
                        400, "invalid_request")
    # A role key that is not a string is a 400, not a 500 (verification
    # pass: an unhashable list reached a dict lookup).
    assert_envelope_err(client.post("/api/v1/settings/role-exclusions",
                                    json={"role_a": ["register_maker"],
                                          "role_b": "register_checker",
                                          "reason": "x"}),
                        400, "invalid_request")
