"""Handoff 70 — the administrator can finish it.

With the tenant's switch `cadra.admin_override` on, an ADMINISTRATOR (a
person, signed in, in `base.group_system`) takes a unit through every gate
alone and captures and reviews in any open campaign, their own capture
included; every act that needed the override is flagged and listed on
`GET /reports/admin-overrides`. With the switch off nothing changes, and
nobody else — a non-administrator, a machine credential — ever overrides.

Driven as the demo personas: `administrator` (System + Asset Manager), the
Asset Controller, the audit capturer and reviewer, the Auditor. The machine
credential case is the suite's own `/auth/token` credential here (its user
holds no system group since handoff 44); a machine credential whose user IS
in `base.group_system` cannot be made over the API (handoff 42's guard) and
is proved in-registry (`myservice_asset_register/tests/test_admin_override.py`).

The switch is put back as it was after each test.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok
from .test_the_audit import _as, _png, _uid

ADMIN, CTL, CAP, REV = ("administrator", "asset_controller",
                        "audit_capturer", "audit_reviewer")
SWITCH = "/settings/admin-override"
REPORT = "/reports/admin-overrides"


def _u():
    return uuid.uuid4().hex[:6].upper()


def _settings(client):
    return assert_envelope_ok(client.get("/api/v1/settings"))["data"]


def _set(client, enabled):
    return assert_envelope_ok(_as(client, ADMIN, "PATCH", SWITCH,
                                  json={"enabled": enabled}))["data"]


@pytest.fixture
def switch(client):
    """Set the switch for one test; the tenant's own value after."""
    was = _settings(client)["admin_override"]["enabled"]
    try:
        yield lambda enabled: _set(client, enabled)
    finally:
        _set(client, was)


def _gated(client):
    if not gates.receipt_gated(client):
        pytest.skip("the receipt gates are off on this tenant, so there is "
                    "no gate to fire; CI's gates-on job runs this")


def _fire(client, asset, action):
    """Fire as the administrator; the unit as THEY read it — the gates
    block is the caller's."""
    gates._fire(client, asset, action, ADMIN, "registered")
    return _read(client, asset["id"])


def _read(client, asset_id, key=ADMIN):
    return assert_envelope_ok(_as(client, key, "GET",
                                  f"/assets/{asset_id}"))["data"]


def _report(client, key=ADMIN, **params):
    rows, cursor = [], None
    while True:
        q = dict(params, limit=100)
        if cursor:
            q["cursor"] = cursor
        body = assert_envelope_ok(_as(client, key, "GET", REPORT, params=q))
        rows += body["data"]
        cursor = body["pagination"]["next_cursor"]
        if not cursor:
            return rows


# ── the switch ──────────────────────────────────────────────────────────

def test_only_an_administrator_switches_it(client, switch):
    block = _settings(client)["admin_override"]
    assert block["parameter"] == "cadra.admin_override"
    assert block["default_when_unset"] is False
    assert "Leave it off where two people must sign." in block["statement"]
    # `settings:write` alone is not enough: the Asset Manager holds it.
    assert_envelope_err(_as(client, "asset_manager", "PATCH", SWITCH,
                            json={"enabled": True}), 403, "forbidden")
    # The Auditor reads settings and writes none.
    assert_envelope_err(_as(client, "auditor", "PATCH", SWITCH,
                            json={"enabled": True}), 403, "forbidden")
    on = switch(True)
    assert on["enabled"] is True and on["since"]
    assert on["changed_by"]["id"] == _uid(client, ADMIN)
    off = switch(False)
    assert off["enabled"] is False and off["since"] is None
    assert_envelope_err(_as(client, ADMIN, "PATCH", SWITCH,
                            json={"enabled": "yes"}), 400)
    assert_envelope_err(_as(client, ADMIN, "PATCH", SWITCH,
                            json={"enabled": True, "why": "x"}), 400)


# ── the receipt gates ──────────────────────────────────────────────────

def test_the_administrator_takes_a_unit_to_the_register_alone(client,
                                                              switch):
    _gated(client)
    switch(True)
    asset = gates.receive(client, name=f"pytest-70 alone {_u()}")
    assert asset["register_state"] == "captured"
    acts, labelled = [], []
    for action, _key in gates.CREW:
        row = next((a for a in asset["gates"]["available"]
                    if a["action"] == action), None)
        if acts and row is not None:
            # Before each act after the first, the gates block says the
            # action is open to them as administrator. (`affix` is not in
            # the block: it is fired from the station, by the label.)
            assert row["can_fire"] is True and row["as_admin"] is True, row
            assert row["refusal"] is None
            labelled.append(action)
        asset = _fire(client, asset, action)
        acts.append(action)
    assert asset["register_state"] == "registered"
    assert {"verify", "approve", "register",
            "approve-registration"} <= set(labelled), labelled

    history = assert_envelope_ok(client.get(
        f"/api/v1/assets/{asset['id']}/history"))["data"]
    events = history["events"] if isinstance(history, dict) else history
    gate_rows = [e for e in events if e.get("type") == "gate_fired"
                 or e.get("event_type") == "gate_fired"]
    flagged = [e for e in gate_rows
               if (e.get("detail") or {}).get("admin_override")]
    # The first act broke no rule; every one after it needed the override.
    # (`request-tagging` also moves the unit through `issue-tag`, one act
    # and so one flag.)
    assert sorted(e["detail"]["action"] for e in flagged) \
        == sorted(acts[1:]), [e.get("summary") for e in gate_rows]
    assert not [e for e in gate_rows if e["detail"].get("action") == "submit"
                and e["detail"].get("admin_override")]
    approve = next(e for e in flagged
                   if e["detail"].get("action") == "approve")
    assert "as administrator (they received this unit on " \
        in approve["summary"], approve
    assert approve["detail"]["override_of"].startswith(
        "You received this unit on ")

    rows = [r for r in _report(client, "auditor", kind="gate")
            if (r["asset"] or {}).get("id") == asset["id"]]
    assert sorted(r["act"] for r in rows) == sorted(acts[1:]), rows
    assert all(r["by"]["id"] == _uid(client, ADMIN) for r in rows)
    verify = next(r for r in rows if r["act"] == "verify")
    assert verify["override_of"].startswith("They received this unit on ")
    assert verify["at"].endswith("+01:00")
    # Newest first.
    assert [r["at"] for r in rows] == sorted((r["at"] for r in rows),
                                             reverse=True)


def test_with_the_switch_off_the_second_gate_is_refused(client, switch):
    _gated(client)
    switch(False)
    asset = gates.receive(client, name=f"pytest-70 off {_u()}")
    asset = _fire(client, asset, "submit")
    row = next(a for a in asset["gates"]["available"]
               if a["action"] == "verify")
    assert row["can_fire"] is False and row["as_admin"] is False
    r = _as(client, ADMIN, "POST", f"/assets/{asset['id']}/gates/verify",
            json={"checklist": {k: True for k in (
                "quantity", "specification", "condition", "price")},
                  "attachments": [{"name": "s.txt", "data": "cw=="}]})
    err = assert_envelope_err(r, 409, "conflict")
    assert err["error"]["details"]["reason"] == "segregation_of_duties"
    assert "a different person must verify it" in err["error"]["message"]


# ── the audit ──────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(scope="module")
def room(client):
    """A campaign that names the audit capturer and reviewer — never the
    administrator — and a device and block bound to the administrator."""
    u = _u()
    building = assert_envelope_ok(client.post(
        "/api/v1/locations", json={"name": f"pytest-70 {u}"}), 201)["data"]
    campaign = assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/campaigns",
        json={"name": f"pytest-70 audit {u}",
              "scope": [{"location_id": building["id"]}],
              "capturer_ids": [_uid(client, CAP)],
              "reviewer_ids": [_uid(client, REV)]}), 201)["data"]
    devices = {}
    for key in (ADMIN, CAP):
        device = assert_envelope_ok(_as(
            client, CTL, "POST", "/audit/devices",
            json={"name": f"pytest-70 {key} {u}",
                  "user_id": _uid(client, key)}), 201)["data"]
        block = assert_envelope_ok(_as(
            client, CTL, "POST", "/audit/blocks",
            json={"device_id": device["id"], "size": 8}), 201)["data"]
        devices[key] = {"code": device["device_code"],
                        "codes": [c["code"] for c in block["codes"]]}
    return {"campaign": campaign, "room": building["id"], "devices": devices}


def _capture(client, room, key, seed, expect=201, **instead):
    device = room["devices"][key]
    code = device["codes"].pop(0)
    photo = assert_envelope_ok(_as(
        client, key, "POST", "/audit/photos",
        files={"file": (f"item-70-{seed}.png", _png(700 + seed),
                        "image/png")}, data={"source": "mobile"}),
        201)["data"]["id"]
    r = _as(client, key, "POST", "/audit/captures", device=device["code"],
            json={"capture_id": str(uuid.uuid4()),
                  "campaign_id": room["campaign"]["id"],
                  "location_id": room["room"], "outcome": "in_neither",
                  "code": code, "scanned_label": code,
                  "photo_ids": [photo], "captured_at": _now(),
                  "fields": {"condition": "fair",
                             "category_id": gates.receipt_body(
                                 client)["category_id"],
                             "name": f"pytest-70 item {seed}"},
                  **instead})
    if expect == 201:
        return assert_envelope_ok(r, 201)["data"]
    return r


def test_the_administrator_captures_and_accepts_their_own(client, room,
                                                          switch):
    switch(True)
    cap = _capture(client, room, ADMIN, 1)
    assert cap["captured_as_admin"] is True
    assert cap["override_of"] == ["not_a_capturer"]
    done = assert_envelope_ok(_as(
        client, ADMIN, "POST",
        f"/audit/captures/{cap['capture_id']}/accept", json={}))["data"]
    assert done["state"] == "accepted"
    assert done["reviewed_as_admin"] is True
    assert set(done["override_of"]) == {"not_a_capturer", "own_capture",
                                        "not_a_reviewer"}

    rows = [r for r in _report(client, "auditor", kind="audit")
            if (r["capture"] or {}).get("capture_id") == cap["capture_id"]]
    assert sorted(r["act"] for r in rows) == ["accept", "capture"], rows
    accept = next(r for r in rows if r["act"] == "accept")
    assert set(accept["rules"]) == {"own_capture", "not_a_reviewer"}
    assert accept["override_of"].startswith(
        "They captured the item themselves; they were not named a reviewer "
        "on campaign "), accept
    assert accept["capture"]["campaign"]["id"] == room["campaign"]["id"]
    # Nothing about the capture is a gate.
    assert not [r for r in _report(client, "auditor", kind="gate")
                if (r["capture"] or {}).get("capture_id")
                == cap["capture_id"]]


def test_own_acceptance_reprints_a_missing_label(client, room, switch):
    """Verification pass: an item on the register whose label is missing is
    reprinted on acceptance, the capturer asking and the reviewer approving
    — the same administrator, under the override, flagged on the capture."""
    switch(True)
    asset = gates.new_registered_asset(
        client, name=f"pytest-70 chair {_u()}", location_id=room["room"])
    cap = _capture(client, room, ADMIN, 7, outcome="on_register",
                   asset_id=asset["id"], label="missing", code=None,
                   scanned_label=None)
    done = assert_envelope_ok(_as(
        client, ADMIN, "POST",
        f"/audit/captures/{cap['capture_id']}/accept", json={}))["data"]
    assert done["state"] == "accepted" and done["reprint_label_id"], done
    assert "own_capture" in done["override_of"]


def test_the_controller_can_bind_a_device_to_an_administrator(client,
                                                              switch):
    switch(False)
    people = assert_envelope_ok(_as(client, CTL, "GET",
                                    "/audit/people"))["data"]
    assert people["administrators"] == []
    switch(True)
    people = assert_envelope_ok(_as(client, CTL, "GET",
                                    "/audit/people"))["data"]
    assert _uid(client, ADMIN) in {p["id"] for p in people["administrators"]}


def test_a_named_reviewer_accepting_is_no_override(client, room, switch):
    switch(True)
    cap = _capture(client, room, CAP, 2)
    assert cap["captured_as_admin"] is False and cap["override_of"] == []
    done = assert_envelope_ok(_as(
        client, REV, "POST",
        f"/audit/captures/{cap['capture_id']}/accept", json={}))["data"]
    assert done["reviewed_as_admin"] is False and done["override_of"] == []
    assert not [r for r in _report(client, ADMIN, kind="audit")
                if (r["capture"] or {}).get("capture_id")
                == cap["capture_id"]]


def test_with_the_switch_off_the_administrator_is_refused(client, room,
                                                          switch):
    switch(False)
    r = _capture(client, room, ADMIN, 3, expect=403)
    err = assert_envelope_err(r, 403, "forbidden")
    assert "You are not a capturer on campaign" in err["error"]["message"]
    cap = _capture(client, room, CAP, 4)
    err = assert_envelope_err(_as(
        client, ADMIN, "POST",
        f"/audit/captures/{cap['capture_id']}/accept", json={}), 403,
        "forbidden")
    assert "You are not a reviewer on campaign" in err["error"]["message"]


def test_nobody_else_overrides_with_the_switch_on(client, room, switch):
    """A non-administrator is held to S2 and S4 with the switch on. (S1 and
    S3 for a non-administrator cannot arise over HTTP: the role exclusions
    keep two gate roles, and capturer with reviewer, off one person; both
    are proved in-registry.)"""
    switch(True)
    u = _u()
    lonely = assert_envelope_ok(client.post(
        "/api/v1/locations", json={"name": f"pytest-70 b {u}"}), 201)["data"]
    nobody_reviews = assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/campaigns",
        json={"name": f"pytest-70 no reviewer {u}",
              "scope": [{"location_id": lonely["id"]}],
              "capturer_ids": [_uid(client, CAP)], "reviewer_ids": []}),
        201)["data"]
    there = dict(room, campaign=nobody_reviews, room=lonely["id"])
    cap = _capture(client, there, CAP, 5)
    err = assert_envelope_err(_as(
        client, REV, "POST",
        f"/audit/captures/{cap['capture_id']}/accept", json={}), 403,
        "forbidden")
    assert "You are not a reviewer on campaign" in err["error"]["message"]
    elsewhere = assert_envelope_ok(client.post(
        "/api/v1/locations", json={"name": f"pytest-70 c {u}"}), 201)["data"]
    nobody_captures = assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/campaigns",
        json={"name": f"pytest-70 no capturer {u}",
              "scope": [{"location_id": elsewhere["id"]}],
              "capturer_ids": [], "reviewer_ids": [_uid(client, REV)]}),
        201)["data"]
    err = assert_envelope_err(_capture(
        client, dict(room, campaign=nobody_captures, room=elsewhere["id"]),
        CAP, 6, expect=403), 403, "forbidden")
    assert "You are not a capturer on campaign" in err["error"]["message"]


def test_a_machine_credential_never_overrides(client, switch):
    """The suite's own credential is a `/auth/token` token holding `admin`
    as a scope: every scope check passes, and the no-two-gates rule still
    refuses its second gate with the switch on."""
    _gated(client)
    switch(True)
    asset = gates.receive(client, name=f"pytest-70 machine {_u()}")
    submitted = assert_envelope_ok(client.post(
        f"/api/v1/assets/{asset['id']}/gates/submit", json={}))["data"]
    assert all(not a.get("as_admin")
               for a in submitted["gates"]["available"])
    r = client.post(f"/api/v1/assets/{asset['id']}/gates/verify", json={
        "checklist": {k: True for k in (
            "quantity", "specification", "condition", "price")},
        "attachments": [{"name": "s.txt", "data": "cw=="}]})
    err = assert_envelope_err(r, 409, "conflict")
    assert err["error"]["details"]["reason"] == "segregation_of_duties"


def test_the_report_filters_and_refuses_in_words(client, switch):
    assert_envelope_err(_as(client, ADMIN, "GET", REPORT,
                            params={"kind": "nope"}), 400)
    assert_envelope_err(_as(client, ADMIN, "GET", REPORT,
                            params={"since": "2026-10-10",
                                    "until": "2026-10-01"}), 400)
    tomorrow = (datetime.now(timezone(timedelta(hours=1)))
                + timedelta(days=1)).date().isoformat()
    assert assert_envelope_ok(_as(client, ADMIN, "GET", REPORT,
                                  params={"since": tomorrow}))["data"] == []
    # The Auditor reads it; a person with neither scope does not.
    assert_envelope_ok(_as(client, "auditor", "GET", REPORT))
    assert_envelope_err(_as(client, CAP, "GET", REPORT), 403, "forbidden")
    # Another route's cursor is not this report's: a 400, not page one.
    other = assert_envelope_ok(client.get(
        "/api/v1/assets", params={"limit": 1}))["pagination"]["next_cursor"]
    if other:
        assert_envelope_err(_as(client, ADMIN, "GET", REPORT,
                                params={"cursor": other}), 400)
