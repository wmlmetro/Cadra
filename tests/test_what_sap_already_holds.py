"""What SAP already holds — handoff 59, over HTTP.

SAP's asset master for NRS (October 2026 export) answered three items on
the go-live list and raised a fourth. Each is driven here through the
published surface, as the people who use it:

* §1 — a registration is refused, at the maker's submission and at the
  checker's approval, when its class carries no SAP asset class; the Asset
  Controller sets the class, the Store Officer cannot; the change is on the
  configuration record.
* §2 — `record_only`: a unit nothing can be fixed to (land, buildings,
  software) received with no serial and a reference, refused with a serial,
  and passed through FIVE gates as five people — the two tagging gates
  skipped, never fired, and said so in the history.
* §3 — placeholder serials refused as placeholders, never as duplicates of
  the legacy assets that already carry them.
* §4 — SAP asset numbers in both shapes, unique once normalised, and the
  class-digit warning.

Every SAP number and serial here is INVENTED at run time, in the shapes the
export uses (11 digits; letters and digits) — never one of NRS's.

Fixture categories are found-or-created by a fixed name, because a category
holding assets can never be deleted: one per run would pile up.
"""
import random
import time
import uuid

import pytest

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok

SETTINGS_GATE = "/api/v1/settings/receipt-gate"
PLACEHOLDERS = "/api/v1/settings/serial-placeholders"

#: The handoff's sentences, verbatim.
NO_SAP_CLASS = ("{cls} has no SAP asset class, so SAP would reject this "
                "asset. An Asset Controller sets it under Settings → Asset "
                "Categories.")
PLACEHOLDER = ("'{value}' is a placeholder, not a serial number. Capture the "
               "serial printed on the item.")
SKIP_REASON = "no label: {cls} is identified by its record"

LAND = "pytest-59 Land (record_only)"
NO_CLASS = "pytest-59 No SAP class"
NUMBERED = "pytest-59 Numbered (class 3000)"


def _uniq(prefix):
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


def _digits(n):
    return "".join(random.choice("0123456789") for _ in range(n))


def _sap_number(first_digit):
    """An invented 11-digit SAP asset number starting with `first_digit`."""
    return str(first_digit) + _digits(10)


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


def _category(client, name, **vals):
    """The fixture category `name`, created if absent, then set to `vals`
    so its state is known whatever the last run left."""
    row = next((c for c in _categories(client) if c["name"] == name), None)
    if row is None:
        row = assert_envelope_ok(client.post(
            "/api/v1/asset-categories", json={"name": name}), 201)["data"]
    if vals:
        row = assert_envelope_ok(client.patch(
            f"/api/v1/asset-categories/{row['id']}", json=vals))["data"]
    return row


SERIAL = "pytest-59 Serial class"


def _serial_class(client):
    """A serial-mode class with its default schema, whatever the tenant's
    category 1 is (verification pass): the sentences asserted below are the
    serial-mode ones."""
    return _category(client, SERIAL, identification_mode="serial",
                     class_attributes_schema=None)["id"]


def _register_total(client):
    """The register's count, as the All Assets list reads it."""
    return assert_envelope_ok(client.get(
        "/api/v1/assets", params={"limit": 1}))["pagination"]["total_estimate"]


def _fire(client, persona, asset_id, action, body=None):
    return gates._as(client, persona, "POST",
                     f"/assets/{asset_id}/gates/{action}", body or {})


def _register_body(asset, code):
    return {"sap_asset_code": code, "cost": 25000.0, "cost_centre": "CC-59",
            "capitalisation_date": time.strftime("%Y-%m-%d"),
            "asset_class": asset["category"]["id"]}


# ── §1 · SAP's asset class on every category ──────────────────────────

def test_every_category_publishes_its_sap_asset_class(client):
    rows = _categories(client)
    assert rows
    for row in rows:
        assert "sap_asset_class" in row
        value = row["sap_asset_class"]
        assert value is None or (len(value) == 4 and value.isdigit()), value
        assert row["identification_mode"] in (
            "serial", "tag_id", "pool", "record_only")


@pytest.mark.parametrize("bad", ["300", "30000", "3A00", " 30 0", 3000])
def test_a_sap_asset_class_is_four_digits(client, admin_scope, bad):
    row = _category(client, NO_CLASS)
    err = assert_envelope_err(client.patch(
        f"/api/v1/asset-categories/{row['id']}",
        json={"sap_asset_class": bad}), 400, "invalid_request")["error"]
    assert err["message"] == ("`sap_asset_class` must be SAP's four-digit "
                              "asset class code, for example 3000.")
    assert err["details"]["field"] == "sap_asset_class"


def test_the_asset_controller_sets_the_class_and_the_store_officer_cannot(
        client, admin_scope):
    row = _category(client, NO_CLASS, sap_asset_class=None)
    path = f"/asset-categories/{row['id']}"
    try:
        r = gates._as(client, "asset_controller", "PATCH", path,
                      {"sap_asset_class": "4000"})
        assert r.status_code == 200, r.text[:300]
        assert r.json()["data"]["sap_asset_class"] == "4000"
        r = gates._as(client, "storekeeper", "PATCH", path,
                      {"sap_asset_class": "2000"})
        assert r.status_code == 403, r.text[:300]
        assert "settings:classes" in r.json()["error"]["message"]
        again = next(c for c in _categories(client) if c["id"] == row["id"])
        assert again["sap_asset_class"] == "4000"
        report = assert_envelope_ok(client.get(
            "/api/v1/reports/configuration-changes",
            params={"from": time.strftime("%Y-%m-%d"),
                    "to": time.strftime("%Y-%m-%d"), "limit": 500}))["data"]
        key = f"cadra.class_sap_asset_class.{row['id']}"
        rows = [x for x in report["parameters"] if x["key"] == key]
        assert rows, f"{key} is on the configuration record"
        assert rows[0]["current_value"] == f"4000; class: {NO_CLASS}"
        print(f"\nconfiguration record: {key} = {rows[0]['current_value']!r}"
              f" (last writer {rows[0].get('last_written_by')})")
    finally:
        _category(client, NO_CLASS, sap_asset_class=None)


def test_registration_is_refused_without_a_sap_class_at_submit_and_at_approve(
        client, gated):
    row = _category(client, NO_CLASS, sap_asset_class=None)
    sentence = NO_SAP_CLASS.format(cls=NO_CLASS)
    a = gates.receive(client, name=_uniq("pytest-59-noclass"),
                      category_id=row["id"])
    a = gates._walk(client, a, "tagged")
    # At the maker's submission: refused, nothing written.
    r = _fire(client, "register_maker", a["id"], "register",
              _register_body(a, "ZQ" + _digits(9)))
    assert r.status_code == 400, r.text[:300]
    assert r.json()["error"]["message"] == sentence
    assert r.json()["error"]["details"]["field"] == "sap_asset_class"
    print(f"\nat submit: {r.status_code} {r.json()['error']['message']}")
    still = assert_envelope_ok(client.get(f"/api/v1/assets/{a['id']}"))["data"]
    assert still["register_state"] == "tagged"
    assert still["sap"]["asset_number"] in (None, "")
    # Set, submitted; cleared before the checker — refused again.
    _category(client, NO_CLASS, sap_asset_class="7000")
    r = _fire(client, "register_maker", a["id"], "register",
              _register_body(a, "ZQ" + _digits(9)))
    assert r.status_code == 200, r.text[:300]
    _category(client, NO_CLASS, sap_asset_class=None)
    r = _fire(client, "register_checker", a["id"], "approve-registration")
    assert r.status_code == 400, r.text[:300]
    assert r.json()["error"]["message"] == sentence
    print(f"at approve: {r.status_code} {r.json()['error']['message']}")
    still = assert_envelope_ok(client.get(f"/api/v1/assets/{a['id']}"))["data"]
    assert still["register_state"] == "reg_submitted"
    # The class set again: the checker approves.
    _category(client, NO_CLASS, sap_asset_class="7000")
    r = _fire(client, "register_checker", a["id"], "approve-registration")
    assert r.status_code == 200, r.text[:300]
    assert r.json()["data"]["register_state"] == "registered"
    _category(client, NO_CLASS, sap_asset_class=None)


# ── §2 · record_only — the class that carries no label ────────────────

@pytest.fixture
def land(client):
    return _category(client, LAND, identification_mode="record_only",
                     sap_asset_class="6000", class_attributes_schema=None)


def test_record_only_is_published_with_its_default_schema(client, land):
    assert land["identification_mode"] == "record_only"
    assert land["class_attributes_schema"]["mandatory"] == ["name",
                                                            "record_reference"]


def test_a_record_only_unit_is_refused_a_serial_and_needs_its_reference(
        client, gated, land):
    err = assert_envelope_err(client.post("/api/v1/assets", json={
        "name": _uniq("pytest-59-plot"), "category_id": land["id"],
        "record_reference": "PLOT " + _digits(5),
        "serial_number": "SN" + _digits(8)}),
        400, "validation_failed")["error"]
    assert err["details"]["field"] == "serial_number"
    assert err["message"] == (
        f"{LAND} is identified by its SAP record and carries no serial "
        "number; send the unit without one (its title, plot number, licence "
        "key or contract goes in `record_reference`).")
    err = assert_envelope_err(client.post("/api/v1/assets", json={
        "name": _uniq("pytest-59-plot"), "category_id": land["id"]}),
        400, "validation_failed")["error"]
    assert err["details"]["missing_fields"] == ["record_reference"]


def test_a_record_only_unit_passes_five_gates_as_five_people(
        client, gated, land):
    """No serial, a reference, five people, no label — and the register
    count moving only at the checker."""
    a = assert_envelope_ok(client.post("/api/v1/assets", json={
        "name": _uniq("pytest-59-plot"), "category_id": land["id"],
        "record_reference": "C OF O " + _digits(6)}), 201)["data"]
    assert a["register_state"] == "captured"
    assert a["identification_mode"] == "record_only"
    assert a["serial_number"] is None and a["tag"] is None
    assert a["asset_code"], "the asset code is its identity from creation"
    seen = [(a["register_state"], a["gates"]["waiting_on"])]
    total = _register_total(client)
    crew = [("storekeeper", "submit", None),
            ("iad_officer", "verify",
             {"checklist": {"quantity": True, "specification": True,
                            "condition": True, "price": True},
              "attachments": [{"name": "title.txt", "data": "dGl0bGU="}]}),
            ("iad_approver", "approve", None),
            ("register_maker", "register",
             _register_body(a, _sap_number(6))),
            ("register_checker", "approve-registration", None)]
    for persona, action, body in crew:
        if action == "approve-registration":
            assert _register_total(client) == total, (
                "the register moved before the checker approved")
        r = _fire(client, persona, a["id"], action, body)
        assert r.status_code == 200, f"{action} as {persona}: {r.text[:300]}"
        a = r.json()["data"]
        seen.append((a["register_state"], a["gates"]["waiting_on"]))
        if action == "approve":
            # Skipped, not fired: straight to the maker, and the Asset
            # Controller is offered nothing.
            assert a["register_state"] == "reg_ready"
            r = _fire(client, "asset_controller", a["id"], "request-tagging")
            assert r.status_code == 409, r.text[:300]
            assert r.json()["error"]["details"]["reason"] == "invalid_state"
    print("\nwaiting_on at every step: " + " → ".join(
        f"{state} ({who})" for state, who in seen))
    assert [s for s, _w in seen] == [
        "captured", "vfm_pending", "vfm_verified", "reg_ready",
        "reg_submitted", "registered"]
    assert [w for _s, w in seen] == [
        "store", "iad", "iad_approver", "maker", "checker", None]
    assert _register_total(client) == total + 1
    # No label, ever.
    assert a["tag"] is None
    assert not (a.get("tagging") or {}).get("tag_number")
    history = assert_envelope_ok(client.get(
        f"/api/v1/assets/{a['id']}/history"))["data"]["events"]
    gate_rows = [e for e in history if e.get("type") == "gate_fired"]
    actions = [(e.get("detail") or {}).get("action") for e in gate_rows]
    assert "skip-tagging" in actions
    assert "request-tagging" not in actions and "affix" not in actions
    skip = next(e for e in gate_rows
                if (e.get("detail") or {}).get("action") == "skip-tagging")
    assert skip["detail"]["reason"] == SKIP_REASON.format(cls=LAND)
    assert skip["detail"]["gate"] is None, "skipped, not fired"
    print(f"history: {skip['summary']}")
    # The register count moved at the checker's step and only there.
    found = assert_envelope_ok(client.get(
        "/api/v1/assets", params={"q": a["asset_code"]}))["data"]
    assert [x["id"] for x in found] == [a["id"]]


def test_a_returned_record_only_registration_goes_back_to_the_maker(
        client, gated, land):
    a = assert_envelope_ok(client.post("/api/v1/assets", json={
        "name": _uniq("pytest-59-licence"), "category_id": land["id"],
        "record_reference": "LIC-" + _digits(8)}), 201)["data"]
    a = gates._walk(client, a, "reg_submitted")
    r = _fire(client, "register_checker", a["id"], "return-registration",
              {"reason": "Wrong cost centre."})
    assert r.status_code == 200, r.text[:300]
    data = r.json()["data"]
    assert data["register_state"] == "reg_ready"
    assert data["gates"]["waiting_on"] == "maker"
    done = gates.on_the_register(client, data)
    assert done["register_state"] == "registered"
    assert done["tag"] is None


# ── §3 · placeholder serials ─────────────────────────────────────────

SEEDED = ["XXXX", "XXX", "x", "0", "0000", "4A12345FD", "5d12345m",
          "12345AB", "12345ABC", "12345HFD", "123456", "N/A", "na", " Nil ",
          "NONE", "no   serial"]


@pytest.mark.parametrize("value", SEEDED)
def test_each_seeded_placeholder_is_refused_at_a_gated_receipt(
        client, gated, value):
    body = gates.receipt_body(client, name=_uniq("pytest-59-ph"),
                              category_id=_serial_class(client), serial_number=value)
    err = assert_envelope_err(client.post("/api/v1/assets", json=body),
                              400, "validation_failed")["error"]
    assert err["message"] == PLACEHOLDER.format(value=value.strip())
    assert err["details"]["placeholder"] is True


def test_a_real_serial_is_accepted_where_a_placeholder_sits_on_legacy(
        client, receipt_switch):
    # The legacy register, as an import leaves it: gates off, a placeholder
    # serial and a real one on two assets.
    receipt_switch(False)
    real_legacy = "PYT59" + _digits(8)
    for serial in ("XXXX", real_legacy):
        assert_envelope_ok(client.post("/api/v1/assets", json={
            "name": _uniq("pytest-59-legacy"), "category_id": _serial_class(client),
            "serial_number": serial}), 201)
    receipt_switch(True)
    # A real new serial: accepted.
    fresh = gates.receive(client, name=_uniq("pytest-59-new"), category_id=_serial_class(client),
                          serial_number="PYT59" + _digits(8))
    assert fresh["register_state"] == "captured"
    # The placeholder: refused AS a placeholder, never as a duplicate.
    err = assert_envelope_err(client.post("/api/v1/assets", json=(
        gates.receipt_body(client, name=_uniq("pytest-59-ph"), category_id=_serial_class(client),
                           serial_number="xxxx"))),
        400, "validation_failed")["error"]
    assert err["message"] == PLACEHOLDER.format(value="xxxx")
    assert "already registered" not in err["message"]
    # A real serial already on the register: refused as the duplicate it is.
    err = assert_envelope_err(client.post("/api/v1/assets", json=(
        gates.receipt_body(client, name=_uniq("pytest-59-dup"), category_id=_serial_class(client),
                           serial_number=real_legacy.lower()))),
        400, "validation_failed")["error"]
    assert "is already registered as an asset in Cadra" in err["message"]


def test_with_the_gates_off_a_placeholder_is_accepted_as_before(
        client, receipt_switch):
    receipt_switch(False)
    a = assert_envelope_ok(client.post("/api/v1/assets", json={
        "name": _uniq("pytest-59-off"), "category_id": _serial_class(client),
        "serial_number": "XXXX"}), 201)["data"]
    assert a["serial_number"] == "XXXX"
    assert a["register_state"] == "registered"


def test_the_placeholder_list_is_read_edited_and_recorded(client, admin_scope):
    before = assert_envelope_ok(client.get(PLACEHOLDERS))["data"]
    assert before["parameter"] == "cadra.serial_placeholders"
    assert {"^X+$", "^0+$"} <= set(before["patterns"])
    assert {"4A12345FD", "NO SERIAL", "N/A"} <= set(before["exact"])
    legacy = before["legacy"]
    assert legacy["placeholders"] <= legacy["with_serial"] <= legacy["assets"]
    print(f"\nlegacy on this tenant: {legacy['placeholders']} of "
          f"{legacy['with_serial']} assets with a serial (of "
          f"{legacy['assets']}) carry a placeholder; top {legacy['top']}")
    r = gates._as(client, "storekeeper", "PUT", "/settings/serial-placeholders",
                  {"exact": [], "patterns": []})
    assert r.status_code == 403, r.text[:300]
    err = assert_envelope_err(client.put(PLACEHOLDERS, json={
        "exact": before["exact"], "patterns": ["(unclosed"]}),
        400, "invalid_request")["error"]
    assert "(unclosed" in err["message"]
    try:
        after = assert_envelope_ok(client.put(PLACEHOLDERS, json={
            "exact": before["exact"] + ["  to be  confirmed "],
            "patterns": before["patterns"]}))["data"]
        assert "TO BE CONFIRMED" in after["exact"]
        report = assert_envelope_ok(client.get(
            "/api/v1/reports/configuration-changes",
            params={"from": time.strftime("%Y-%m-%d"),
                    "to": time.strftime("%Y-%m-%d"), "limit": 500}))["data"]
        rows = [x for x in report["parameters"]
                if x["key"] == "cadra.serial_placeholders"]
        assert rows and "TO BE CONFIRMED" in rows[0]["current_value"]
        print(f"configuration record: cadra.serial_placeholders = "
              f"{rows[0]['current_value']}")
    finally:
        assert_envelope_ok(client.put(PLACEHOLDERS, json={
            "exact": before["exact"], "patterns": before["patterns"]}))


# ── §4 · SAP asset numbers in both formats ───────────────────────────

def test_both_sap_number_shapes_are_accepted_normalised_and_warned(
        client, gated):
    row = _category(client, NUMBERED, sap_asset_class="3000")
    units = [gates._walk(client, gates.receive(
        client, name=_uniq("pytest-59-sap"), category_id=row["id"]), "tagged")
        for _ in range(3)]
    numeric = _sap_number(3)
    legacy = "zzq" + _digits(3) + "ict" + _digits(4)
    # 11 digits, the class's first digit: accepted, no warning.
    r = _fire(client, "register_maker", units[0]["id"], "register",
              _register_body(units[0], numeric))
    assert r.status_code == 200, r.text[:300]
    assert "_warnings" not in r.json()["data"]
    # Legacy alphanumeric, typed lower-case with spaces: stored as SAP
    # writes it.
    r = _fire(client, "register_maker", units[1]["id"], "register",
              _register_body(units[1], f"  {legacy} "))
    assert r.status_code == 200, r.text[:300]
    assert r.json()["data"]["sap"]["asset_number"] == legacy.upper()
    assert "_warnings" not in r.json()["data"]
    # A duplicate once normalised: refused, naming the asset that holds it.
    r = _fire(client, "register_maker", units[2]["id"], "register",
              _register_body(units[2], legacy.upper()))
    assert r.status_code == 400, r.text[:300]
    assert r.json()["error"]["message"].startswith(
        f"SAP asset code {legacy.upper()} is already on another asset")
    # 11 digits starting with another class's digit: accepted, warned.
    wrong = _sap_number(2)
    r = _fire(client, "register_maker", units[2]["id"], "register",
              _register_body(units[2], wrong))
    assert r.status_code == 200, r.text[:300]
    warning = r.json()["data"]["_warnings"]["sap_asset_number"]
    assert warning == (f"{wrong} looks like a class 2000 number; this "
                       "category maps to 3000.")
    print(f"\nwarning: {warning}")
    for unit in units:
        gates.on_the_register(client, assert_envelope_ok(client.get(
            f"/api/v1/assets/{unit['id']}"))["data"])


# ── found by the verification pass ───────────────────────────────────

def test_a_candidate_cannot_be_patched_round_its_receipt(client, gated, land):
    """`create` checks a gated receipt; a PATCH on the unit still in the
    chain meets the same rules — no serial on a `record_only` unit, no
    placeholder on any, no clearing what identifies it."""
    plot = assert_envelope_ok(client.post("/api/v1/assets", json={
        "name": _uniq("pytest-59-plot"), "category_id": land["id"],
        "record_reference": "PLOT " + _digits(5)}), 201)["data"]
    err = assert_envelope_err(client.patch(
        f"/api/v1/assets/{plot['id']}", json={"serial_number": "SN" + _digits(8)}),
        400, "validation_failed")["error"]
    assert err["details"]["field"] == "serial_number"
    err = assert_envelope_err(client.patch(
        f"/api/v1/assets/{plot['id']}", json={"record_reference": ""}),
        400, "validation_failed")["error"]
    assert err["details"]["missing_fields"] == ["record_reference"]
    unit = gates.receive(client, name=_uniq("pytest-59-unit"),
                         category_id=_serial_class(client))
    err = assert_envelope_err(client.patch(
        f"/api/v1/assets/{unit['id']}", json={"serial_number": "XXXX"}),
        400, "validation_failed")["error"]
    assert err["message"] == PLACEHOLDER.format(value="XXXX")


def test_the_placeholder_list_cannot_be_emptied_or_made_to_match_everything(
        client, admin_scope):
    before = assert_envelope_ok(client.get(PLACEHOLDERS))["data"]
    err = assert_envelope_err(client.put(PLACEHOLDERS, json={
        "exact": [], "patterns": []}), 400, "invalid_request")["error"]
    assert "cannot be empty" in err["message"]
    err = assert_envelope_err(client.put(PLACEHOLDERS, json={
        "exact": before["exact"], "patterns": [".*"]}),
        400, "invalid_request")["error"]
    assert "real-looking serial" in err["message"]
    after = assert_envelope_ok(client.get(PLACEHOLDERS))["data"]
    assert (after["exact"], after["patterns"]) == (before["exact"],
                                                   before["patterns"])


def test_a_registered_record_only_unit_is_never_waiting_for_a_label(
        client, gated, land):
    a = gates.new_registered_asset(client, name=_uniq("pytest-59-plot"),
                                   category_id=land["id"],
                                   record_reference="PLOT " + _digits(5))
    assert a["register_state"] == "registered" and a["tag"] is None
    untagged = assert_envelope_ok(client.get(
        "/api/v1/barcode/untagged", params={"q": a["asset_code"]}))["data"]
    assert a["id"] not in [row.get("asset_id", row.get("id"))
                           for row in (untagged or [])]
    done = assert_envelope_ok(client.post("/api/v1/barcode/generate", json={
        "asset_ids": [a["id"]]}))["data"]
    assert done["generated"] == []
    assert done["skipped"] == [{"asset_id": a["id"], "reason": "record_only"}]
