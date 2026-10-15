"""Seventy a day — handoff 60, over HTTP.

The batch gates, the per-person count and the oldest-first list, driven as
the demo personas through `tests/gates.py` (the no-two-gates rule refuses one
credential at a second gate, so a walk needs seven people).

The rule this file exists to hold: **a batch is N single-unit fires.** Each
unit is checked by every rule a single fire meets and writes its own events;
one refused unit never rolls back the others; and a unit refused inside a
batch is refused with the status, code and sentence it would have had alone.

The suite credential holds `admin`, so it may fire any gate — which is what
lets it be BARRED: it submits some units itself, and the no-two-gates rule
then refuses it their verification.

Every test that turns the receipt switch puts it back (`gated`).
"""
import base64
import json
import time
import uuid

import pytest

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok

SETTINGS_GATE = "/api/v1/settings/receipt-gate"
CHECKLIST = {"quantity": True, "specification": True, "condition": True,
             "price": True}
NOTE = b"Delivery note, one per receipt."
EVIDENCE = [{"name": "delivery-note.txt", "mimetype": "text/plain",
             "data": base64.b64encode(NOTE).decode()}]


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


def _receive_grn(client, n, grn=None, cost=1850.0):
    """`n` units on one GRN, each at a cost, as a receipt carries them —
    the maker's paste takes the unit's own cost."""
    grn = grn or _uniq("GRN60")
    return grn, [gates.receive(client, grn_reference=grn, name=f"Unit {i}",
                               acquisition_cost=cost)
                 for i in range(n)]


def _as(client, key, method, path, body=None):
    """As a persona, or as the suite credential when `key` is None."""
    if key is None:
        return getattr(client, method.lower())(f"/api/v1{path}", json=body) \
            if body is not None else getattr(client, method.lower())(
                f"/api/v1{path}")
    return gates._as(client, key, method, path, body)


def _fire(client, key, asset_id, action, body=None):
    r = _as(client, key, "POST", f"/assets/{asset_id}/gates/{action}",
            body or {})
    assert r.status_code == 200, (action, key, r.status_code, r.text[:300])
    return r.json()["data"]


def _mine(client, key, grn):
    """`(total, ids)` of the GRN's units waiting on `key` — the badge's own
    query, narrowed to this test's receipt so the tenant's other units do
    not move the number."""
    r = _as(client, key, "GET",
            f"/candidates?waiting_on_me=true&q={grn}&limit=100")
    assert r.status_code == 200, (key, r.status_code, r.text[:300])
    body = r.json()
    return body["pagination"]["total_estimate"], {a["id"] for a in body["data"]}


def _gate_list(client, grn, waiting_on):
    r = client.get(f"/api/v1/candidates?waiting_on={waiting_on}&q={grn}"
                   f"&limit=100")
    body = assert_envelope_ok(r)
    return {a["id"]: a for a in body["data"]}


def _verify_batch(client, key, ids, **extra):
    return _as(client, key, "POST", "/candidates/gates/verify",
               {"asset_ids": ids, "checklist": CHECKLIST,
                "attachments": EVIDENCE, **extra})


# ── the batch rules (§4.4) and the badge (§4.5) ─────────────────────────

def test_twenty_units_barred_on_three_seventeen_fire(client, gated):
    """A batch of 20 where the actor is barred on 3 → 17 fired, 3 refused
    with the no-two-gates sentence; and the per-person count at each step
    counts nothing its holder cannot do."""
    grn, units = _receive_grn(client, 20)
    ids = [u["id"] for u in units]

    # Received: waiting on Store, and on nobody else.
    assert _mine(client, "storekeeper", grn)[0] == 20
    for key in ("iad_officer", "iad_approver", "register_maker",
                "register_checker"):
        assert _mine(client, key, grn)[0] == 0, key

    # The suite credential submits 3, Store the other 17.
    barred, others = ids[:3], ids[3:]
    for i in barred:
        _fire(client, None, i, "submit")
    for i in others:
        _fire(client, "storekeeper", i, "submit")
    assert _mine(client, "storekeeper", grn)[0] == 0
    assert _mine(client, "iad_officer", grn) == (20, set(ids))
    # The suite credential may verify — but not the 3 it received: zero
    # for barred units. They stay under the plain gate filter, refused.
    total, mine = _mine(client, None, grn)
    assert total == 17 and mine == set(others)
    plain = _gate_list(client, grn, "iad")
    assert set(plain) == set(ids)
    for i in barred:
        verify = next(a for a in plain[i]["gates"]["available"]
                      if a["action"] == "verify")
        assert verify["can_fire"] is False
        assert verify["refusal"].startswith("You received this unit on ")

    # The batch: 17 fired, 3 refused, each with the sentence a single
    # fire gives — and the 3 are not rolled back into anything.
    r = _verify_batch(client, None, ids)
    data = assert_envelope_ok(r)["data"]
    assert r.status_code == 200
    assert (data["total"], data["fired"], data["refused"]) == (20, 17, 3)
    by_id = {l["asset_id"]: l for l in data["results"]}
    assert [l["asset_id"] for l in data["results"]] == ids, "order kept"
    for i in others:
        assert by_id[i]["outcome"] == "fired"
        assert by_id[i]["register_state"] == "vfm_verified"
    for i in barred:
        line = by_id[i]
        assert line["outcome"] == "refused"
        assert (line["status"], line["code"]) == (409, "conflict")
        assert line["details"]["reason"] == "segregation_of_duties"
        assert line["message"].startswith("You received this unit on ")
        assert line["message"].endswith("; a different person must verify it.")
        assert line["register_state"] == "vfm_pending"
        # The same sentence as alone.
        alone = client.post(f"/api/v1/assets/{i}/gates/verify",
                            json={"checklist": CHECKLIST,
                                  "attachments": EVIDENCE})
        assert assert_envelope_err(alone, 409, "conflict")["error"][
            "message"] == line["message"]

    # Evidence stored ONCE, linked from every fired unit's event.
    stored = data["evidence"]["attachment_ids"]
    assert len(stored) == 1
    for i in others:
        ev = assert_envelope_ok(
            _as(client, "iad_approver", "GET", f"/assets/{i}/evidence"))
        files = ev["data"]["verifications"][0]["files"]
        assert [f["id"] for f in files] == stored

    # Next step: the approver's 17; the officer's remaining 3.
    assert _mine(client, "iad_approver", grn) == (17, set(others))
    assert _mine(client, "iad_officer", grn) == (3, set(barred))
    # The suite credential holds every scope, and may approve NONE of them:
    # it verified the 17 and received the 3. A count of work it cannot do
    # would be 20.
    assert _mine(client, None, grn) == (0, set())

    # Batch approve as the approver: 17 fired.
    r = _as(client, "iad_approver", "POST", "/candidates/gates/approve",
            {"asset_ids": others})
    data = assert_envelope_ok(r)["data"]
    assert (data["fired"], data["refused"]) == (17, 0)
    assert _mine(client, "iad_approver", grn)[0] == 0
    assert _mine(client, "asset_controller", grn)[0] == 17


def test_a_batch_unit_reads_like_a_single_fire(client, gated):
    """The history and the evidence of a unit verified in a batch have the
    shape of one verified alone."""
    grn, units = _receive_grn(client, 3)
    ids = [u["id"] for u in units]
    for i in ids:
        _fire(client, "storekeeper", i, "submit")
    _fire(client, "iad_officer", ids[0], "verify",
          {"checklist": CHECKLIST, "attachments": EVIDENCE})
    data = assert_envelope_ok(_verify_batch(client, "iad_officer",
                                            ids[1:]))["data"]
    assert data["fired"] == 2

    def verify_event(i):
        h = assert_envelope_ok(client.get(
            f"/api/v1/assets/{i}/history"))["data"]
        rows = [e for e in h["events"]
                if (e.get("detail") or {}).get("action") == "verify"]
        assert len(rows) == 1, rows
        return rows[0]

    alone, batched = verify_event(ids[0]), verify_event(ids[1])
    assert set(alone) == set(batched)
    assert set(alone["detail"]) == set(batched["detail"])
    assert set(alone["detail"]["evidence"]) == set(batched["detail"]["evidence"])
    assert alone["summary"] == batched["summary"]
    assert batched["detail"]["evidence"]["checklist"] == CHECKLIST
    # One event per unit, not one for the batch.
    other = verify_event(ids[2])
    assert other["detail"]["evidence"]["attachment_ids"] == \
        batched["detail"]["evidence"]["attachment_ids"]


def test_a_verify_mixing_receipts_is_refused_whole(client, gated):
    grn_a, a = _receive_grn(client, 2)
    grn_b, b = _receive_grn(client, 1)
    _grn_c, c = _receive_grn(client, 1)
    ids = [u["id"] for u in a + b + c]
    for i in ids:
        _fire(client, "storekeeper", i, "submit")
    body = assert_envelope_err(_verify_batch(client, "iad_officer", ids),
                               400, "validation_failed")
    assert body["error"]["message"] == (
        "These units come from 3 receipts; verify one receipt at a time so "
        "the evidence matches.")
    # Nothing written.
    for i in ids:
        got = assert_envelope_ok(client.get(f"/api/v1/assets/{i}"))["data"]
        assert got["register_state"] == "vfm_pending"


def test_one_duplicated_sap_code_in_a_paste_refuses_only_its_line(
        client, gated):
    grn, units = _receive_grn(client, 3)
    tagged = [gates._walk(client, u, "tagged") for u in units]
    # The class needs SAP's asset class to be registered (handoff 59 §1);
    # the walk sets it only at the maker's own step.
    gates._class_has_sap_class(client, tagged[0])
    sap = "3" + uuid.uuid4().int.__str__()[:10]
    other = "3" + uuid.uuid4().int.__str__()[:10]
    body = {"lines": [
        {"asset_code": tagged[0]["asset_code"], "sap_asset_code": sap},
        {"asset_code": tagged[1]["asset_code"], "sap_asset_code": sap},
        {"asset_code": tagged[2]["asset_code"].lower(),
         "sap_asset_code": other},
        {"asset_code": "NO-SUCH-CODE-60", "sap_asset_code": "3999"},
    ], "cost_centre": "CC-60", "capitalisation_date": time.strftime("%Y-%m-%d")}

    # The preview is the real answer, and writes nothing.
    preview = assert_envelope_ok(_as(client, "register_maker", "POST",
                                      "/candidates/gates/register",
                                      {**body, "dry_run": True}))["data"]
    assert preview["dry_run"] is True, preview
    assert preview["results"][0]["outcome"] == "would_fire", \
        preview["results"][0]["message"] or \
        preview["results"][0]
    assert [l["outcome"] for l in preview["results"]] == [  # noqa

        "would_fire", "refused", "would_fire", "refused"]
    assert [l["line"] for l in preview["results"]] == [1, 2, 3, 4]
    assert preview["results"][1]["message"] == (
        "SAP asset code %s is already on another asset (%s)."
        % (sap, tagged[0]["asset_code"]))
    assert preview["results"][3]["status"] == 404
    assert preview["results"][0]["category"]["sap_asset_class"]
    for u in tagged:
        got = assert_envelope_ok(client.get(f"/api/v1/assets/{u['id']}"))
        assert got["data"]["register_state"] == "tagged"
        assert got["data"]["gates"]["registration"] is None

    done = assert_envelope_ok(_as(client, "register_maker", "POST",
                                   "/candidates/gates/register",
                                   body))["data"]
    assert [l["outcome"] for l in done["results"]] == [
        "fired", "refused", "fired", "refused"]
    assert done["results"][1]["message"] == preview["results"][1]["message"]
    states = [assert_envelope_ok(client.get(
        f"/api/v1/assets/{u['id']}"))["data"] for u in tagged]
    assert [s["register_state"] for s in states] == [
        "reg_submitted", "tagged", "reg_submitted"]
    reg = states[0]["gates"]["registration"]
    assert reg["sap_asset_code"] == sap and reg["cost_centre"] == "CC-60"
    assert reg["cost"] == 1850.0, "the unit's own cost"

    # The checker: both approved in one batch, each its own fire.
    checked = assert_envelope_ok(_as(
        client, "register_checker", "POST",
        "/candidates/gates/approve-registration",
        {"asset_ids": [tagged[0]["id"], tagged[2]["id"]]}))["data"]
    assert (checked["fired"], checked["refused"]) == (2, 0)


def test_a_paste_with_no_cost_centre_is_refused_before_anything(
        client, gated):
    body = assert_envelope_err(_as(
        client, "register_maker", "POST", "/candidates/gates/register",
        {"lines": [{"asset_code": "X", "sap_asset_code": "Y"}],
         "capitalisation_date": "2026-10-15"}), 400, "validation_failed")
    assert body["error"]["message"] == "The cost centre is required."


def test_batch_bodies_are_refused_in_words(client, gated):
    assert_envelope_err(_as(client, "iad_approver", "POST",
                            "/candidates/gates/approve",
                            {"asset_ids": [1, 1]}), 400, "invalid_request")
    assert_envelope_err(_as(client, "iad_approver", "POST",
                            "/candidates/gates/approve",
                            {"asset_ids": list(range(1, 102))}),
                        400, "invalid_request")
    refused = assert_envelope_err(_as(
        client, "iad_approver", "POST", "/candidates/gates/approve",
        {"asset_ids": [1], "bogus": True}), 400, "invalid_request")
    assert refused["error"]["details"]["rejected_fields"] == ["bogus"]
    # The scope gate is the route's, as for one unit.
    assert_envelope_err(_as(client, "iad_officer", "POST",
                            "/candidates/gates/approve",
                            {"asset_ids": [1]}), 403, "forbidden")
    # A missing unit is one refused line, not a failed batch.
    data = assert_envelope_ok(_as(client, "iad_approver", "POST",
                                  "/candidates/gates/approve",
                                  {"asset_ids": [987654321]}))["data"]
    assert data["results"][0]["status"] == 404


def test_evidence_files_are_served_only_for_their_unit(client, gated):
    grn, units = _receive_grn(client, 2)
    a, b = (u["id"] for u in units)
    for i in (a, b):
        _fire(client, "storekeeper", i, "submit")
    _fire(client, "iad_officer", a, "verify",
          {"checklist": CHECKLIST, "attachments": EVIDENCE})
    ev = assert_envelope_ok(_as(client, "iad_approver", "GET",
                                f"/assets/{a}/evidence"))["data"]
    [v] = ev["verifications"]
    assert v["checklist"] == CHECKLIST
    [f] = v["files"]
    got = gates._as(client, "iad_approver", "GET",
                    f"/assets/{a}/evidence/{f['id']}")
    assert got.status_code == 200 and got.content == NOTE
    assert "delivery-note.txt" in got.headers["Content-Disposition"]
    # Not through another unit's address.
    other = gates._as(client, "iad_approver", "GET",
                      f"/assets/{b}/evidence/{f['id']}")
    assert other.status_code == 404
    assert assert_envelope_ok(_as(client, "iad_approver", "GET",
                                  f"/assets/{b}/evidence"))["data"][
        "verifications"] == []


def test_the_list_reads_oldest_first_and_pages(client, gated):
    seen, cursor, pages = [], None, 0
    while pages < 3:
        url = "/api/v1/candidates?sort=oldest&limit=5"
        if cursor:
            url += f"&cursor={cursor}"
        body = assert_envelope_ok(client.get(url))
        seen += [(a["gates"]["state_since"], a["id"]) for a in body["data"]]
        cursor = body["pagination"]["next_cursor"]
        pages += 1
        if not cursor:
            break
    assert seen == sorted(seen), "oldest first, id second"
    assert len({i for _s, i in seen}) == len(seen), "no row twice"
    # A cursor from one walk is refused on the other.
    if cursor:
        assert_envelope_err(client.get(
            f"/api/v1/candidates?sort=newest&cursor={cursor}"),
            400, "invalid_request")
    assert_envelope_err(client.get("/api/v1/candidates?sort=sideways"),
                        400, "invalid_request")


def test_a_person_with_no_gate_scope_waits_on_nothing(client, gated):
    r = gates._as(client, "auditor", "GET",
                  "/candidates?waiting_on_me=true&limit=1")
    if r.status_code == 403:
        pytest.skip("the auditor persona does not hold candidates:read here")
    assert r.json()["pagination"]["total_estimate"] == 0


# ── §1.2: a new asset carries its class's mode, gates on or off ─────────

def test_a_tag_id_asset_created_with_the_gates_off_reads_tag_id(
        client, admin_scope):
    rows = assert_envelope_ok(client.get("/api/v1/asset-categories"))["data"]
    furniture = next((c for c in rows
                      if c["identification_mode"] == "tag_id"), None)
    assert furniture, "no tag_id class (19.0.1.27.0 seeds furniture as one)"
    serial = next(c for c in rows
                  if c["identification_mode"] == "serial")
    was = gates.receipt_gated(client)
    assert_envelope_ok(client.patch(SETTINGS_GATE, json={"enabled": False}))
    try:
        chair = assert_envelope_ok(client.post("/api/v1/assets", json={
            "name": _uniq("Chair 60"), "category_id": furniture["id"]}), 201)
        laptop = assert_envelope_ok(client.post("/api/v1/assets", json={
            "name": _uniq("Laptop 60"), "category_id": serial["id"]}), 201)
    finally:
        assert_envelope_ok(client.patch(SETTINGS_GATE, json={"enabled": was}))
    assert chair["data"]["register_state"] == "registered"
    assert chair["data"]["identification_mode"] == "tag_id"
    assert laptop["data"]["identification_mode"] == "serial"


# ── ruling 7: `reference` is `record_reference` ─────────────────────────

def test_the_old_name_is_refused_and_the_new_one_is_published(client):
    refused = assert_envelope_err(client.post("/api/v1/assets", json={
        "name": _uniq("pytest-60-ref"), "category_id": 1,
        "reference": "PLOT 1"}), 400, "invalid_request")
    assert refused["error"]["details"]["rejected_fields"] == ["reference"]
    a = assert_envelope_ok(client.get("/api/v1/assets?limit=1"))["data"][0]
    assert "record_reference" in a and "reference" not in a


def test_a_tampered_oldest_first_cursor_is_a_400(client):
    """Cursors are unsigned: an `after` that is not an instant is caller
    input, refused 400 — not a 500 from the ORM's datetime parse
    (verification pass)."""
    raw = base64.urlsafe_b64encode(json.dumps(
        {"last_id": 1, "by": "register_state_since", "after": "x"}).encode()
    ).decode().rstrip("=")
    assert_envelope_err(client.get(
        f"/api/v1/candidates?sort=oldest&cursor={raw}"), 400,
        "invalid_request")
