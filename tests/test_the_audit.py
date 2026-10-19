"""The audit in the room (handoff 66 §8.1–§8.5), through the HTTP routes, as
the personas.

A campaign over two rooms of a building made for the test, with SAP mirror
records in the export's SHAPES (`sap_export_shapes`, invented, imported
through the real upload route) under an office code that exists nowhere
else, and Cadra assets made for the test. The Asset Controller registers a
device bound to the capturer and issues it a block; the capturer captures
from it; the reviewer — a different person — accepts or returns.

What is pinned:
* outcome a: a register asset found in the other room — moved, its
  condition written, verified (by the capturer), the photo on it, its
  missing label reprinted under the same code (R3), one history line;
* outcome b: a new register asset with SAP's number and class date and the
  code the phone printed, `registered`, the source `audit_from_sap_mirror`,
  the code `active` in the ledger;
* outcome c: an exception, its code held `in_review`; registered as new
  (waiting on the Register Maker, the label on it), or voided with a reason
  (its code voided);
* every refusal in words; a duplicate HELD beside the first, refused only at
  acceptance once its twin is accepted; a capture synced twice is one;
* the block: issued, used, returned — the unused codes voided;
* the campaign refuses to close while a capture waits, then closes with both
  lists, the CSV included;
* the capturer is refused review (403, the scope), and nobody may be granted
  both roles (the role exclusion, at grant).
"""
import base64
import importlib.util
import json
import pathlib
import struct
import time
import uuid
import zlib
from datetime import datetime, timedelta, timezone

import pytest
import requests

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok

_SHAPES = (pathlib.Path(__file__).resolve().parents[1]
           / "myservice_asset_register" / "tests" / "sap_export_shapes.py")
_spec = importlib.util.spec_from_file_location("sap_export_shapes", _SHAPES)
shapes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shapes)

CAP, REV, CTL = "audit_capturer", "audit_reviewer", "asset_controller"


def _u():
    return uuid.uuid4().hex[:6].upper()


def _as(client, key, method, path, device=None, **kw):
    headers = {"Authorization": f"Bearer {gates._token(client, key)}"} \
        if key else {"Authorization": client.session.headers.get(
            "Authorization", "")}
    if device:
        headers["X-Cadra-Device"] = device
    return requests.request(method, f"{client.base}/api/v1{path}",
                            timeout=120, headers=headers, **kw)


def _uid(client, key):
    token = gates._token(client, key)
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return int(json.loads(base64.urlsafe_b64decode(payload))["uid"])


def _png(seed):
    """A small valid PNG whose bytes differ per seed."""
    w, h = 8, 8
    raw = b"".join(
        b"\x00" + b"".join(bytes(((seed * 37 + x * 11 + y * 7) % 256,
                                   (seed * 13 + x) % 256, y * 30 % 256))
                            for x in range(w)) for y in range(h))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _import(client, rows):
    deadline = time.time() + 240
    while True:
        r = _as(client, "administrator", "POST", "/sap-assets/imports",
                files={"file": ("export.xlsx", shapes.build_xlsx(rows))},
                data={"mark_absent": "true"})
        if r.status_code != 409 or time.time() > deadline:
            break
        time.sleep(3)
    assert r.status_code == 202, r.text
    run_id = r.json()["data"]["id"]
    while time.time() < deadline:
        run = _as(client, "administrator", "GET",
                  f"/sap-assets/imports/{run_id}").json()["data"]
        if run["state"] in ("done", "failed", "held"):
            assert run["state"] == "done", run
            return run
        time.sleep(2)
    pytest.fail(f"import {run_id} did not finish")


def _location(client, name, parent=None):
    body = {"name": name}
    if parent:
        body["parent_id"] = parent
    return assert_envelope_ok(client.post("/api/v1/locations", json=body),
                              201)["data"]["id"]


def _now(days=0):
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(scope="module")
def world(client):
    u = _u()
    office = f"A{u}"
    building = _location(client, f"pytest-audit {u}")
    rooms = [_location(client, f"pytest-audit {u} room {i}", building)
             for i in (1, 2)]
    outside = _location(client, f"pytest-audit {u} elsewhere")
    tags = {k: f"FIRS/{office}/{i:04d}" for i, k in
            enumerate(("b", "dup", "missing", "b2"), 1)}
    numbers = {k: f"2A{u}{i:03d}" for i, k in enumerate(tags, 1)}
    _import(client, [shapes.record(numbers[k], cls="2000", tag=tags[k],
                                   description="OFFICE CHAIR")
                     for k in tags])
    sap = {}
    for k, n in numbers.items():
        rows = assert_envelope_ok(_as(client, CTL, "GET", "/sap-assets",
                                      params={"office": office,
                                              "limit": 50}))["data"]
        sap[k] = next(r["id"] for r in rows if r["asset_number"] == n)
    asset_a = gates.new_registered_asset(
        client, name=f"pytest-audit chair {u}", location_id=rooms[1])
    cap_id, rev_id = _uid(client, CAP), _uid(client, REV)
    device = assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/devices",
        json={"name": f"pytest phone {u}", "user_id": cap_id}),
        201)["data"]
    block = assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/blocks",
        json={"device_id": device["id"], "size": 6}), 201)["data"]
    campaign = assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/campaigns",
        json={"name": f"pytest audit {u}",
              "scope": [{"location_id": building, "office_code": office}],
              "capturer_ids": [cap_id], "reviewer_ids": [rev_id]}),
        201)["data"]
    category = gates.receipt_body(client)["category_id"]
    return {"u": u, "office": office, "rooms": rooms, "outside": outside,
            "sap": sap, "numbers": numbers, "asset_a": asset_a,
            "device": device, "codes": [c["code"] for c in block["codes"]],
            "block": block, "campaign": campaign, "category": category,
            "cap_id": cap_id, "rev_id": rev_id}


def _photo(client, w, seed):
    r = _as(client, CAP, "POST", "/audit/photos",
            files={"file": (f"item-{seed}.png", _png(seed), "image/png")},
            data={"source": "mobile"})
    return assert_envelope_ok(r, 201)["data"]["id"]


def _capture(client, w, outcome, seed, *, room=0, expect=201, **extra):
    body = {"capture_id": str(uuid.uuid4()),
            "campaign_id": w["campaign"]["id"],
            "location_id": w["rooms"][room], "outcome": outcome,
            "photo_ids": [_photo(client, w, seed)],
            "captured_at": _now(),
            "fields": {"condition": "fair", "category_id": w["category"],
                       "name": f"pytest-audit item {seed}"}}
    body.update(extra)
    r = _as(client, CAP, "POST", "/audit/captures",
            device=w["device"]["device_code"], json=body)
    if expect == 201:
        return assert_envelope_ok(r, 201)["data"]
    return r


def _accept(client, capture, key=REV, status=200):
    r = _as(client, key, "POST",
            f"/audit/captures/{capture['capture_id']}/accept", json={})
    if status == 200:
        return assert_envelope_ok(r)["data"]
    return r


def _code(client, code):
    rows = assert_envelope_ok(_as(client, CTL, "GET", "/audit/codes",
                                  params={"code": code}))["data"]
    assert len(rows) == 1, rows
    return rows[0]


# ── §8.1 the three outcomes ──────────────────────────────────────────────

def test_outcome_a_verifies_in_place_moves_and_reprints(client, world):
    w = world
    a = w["asset_a"]
    cap = _capture(client, w, "on_register", 1, asset_id=a["id"],
                   label="missing")
    assert cap["state"] == "pending_review"
    assert cap["code"] is None and cap["asset"]["id"] == a["id"]
    done = _accept(client, cap)
    assert done["state"] == "accepted"
    assert done["reviewed_by"]["id"] == w["rev_id"]
    assert done["reprint_label_id"]
    assert done["photos_copied"] == 1
    asset = assert_envelope_ok(client.get(f"/api/v1/assets/{a['id']}"))[
        "data"]
    assert asset["current_location"]["id"] == w["rooms"][0], asset
    assert asset["condition"] == "fair"
    assert asset["asset_code"] == a["asset_code"]
    history = assert_envelope_ok(client.get(
        f"/api/v1/assets/{a['id']}/history"))["data"]
    text = json.dumps(history)
    assert "audit" in text.lower()


def test_outcome_b_registers_from_sap_with_the_phones_code(client, world):
    w = world
    code = w["codes"][0]
    cap = _capture(client, w, "in_sap", 2, sap_record_id=w["sap"]["b"],
                   code=code, scanned_label=code)
    assert cap["code"] == code
    assert _code(client, code)["state"] == "in_review"
    done = _accept(client, cap)
    new = done["result_asset"]
    assert new["asset_code"] == code and new["register_state"] == "registered"
    asset = assert_envelope_ok(client.get(f"/api/v1/assets/{new['id']}"))[
        "data"]
    assert asset["sap"]["asset_number"] == w["numbers"]["b"]
    assert asset["sap"]["code_source"] == "audit_from_sap_mirror", asset
    assert asset["sap"].get("posting_state") in (None, "none"), asset["sap"]
    row = _code(client, code)
    assert row["state"] == "active" and row["asset_id"] == new["id"]


def test_outcome_c_is_an_exception_registered_new_or_voided(client, world):
    w = world
    c1, c2 = w["codes"][1], w["codes"][2]
    cap1 = _capture(client, w, "in_neither", 3, code=c1, scanned_label=c1)
    cap2 = _capture(client, w, "in_neither", 4, room=1, code=c2,
                    scanned_label=c2)
    for cap in (cap1, cap2):
        done = _accept(client, cap)
        assert done["exception_state"] == "open"
        assert done["result_asset"] is None
    assert _code(client, c1)["state"] == "in_review"
    open_ = assert_envelope_ok(_as(
        client, CTL, "GET", "/audit/captures",
        params={"campaign_id": w["campaign"]["id"],
                "exception_state": "open"}))["data"]
    assert {c["capture_id"] for c in open_} >= {cap1["capture_id"],
                                                cap2["capture_id"]}
    # The reviewer may not resolve it — that is the Asset Controller's.
    assert_envelope_err(_as(client, REV, "POST",
                            f"/audit/captures/{cap1['capture_id']}/"
                            "register-new", json={}), 403, "forbidden")
    reg = assert_envelope_ok(_as(
        client, CTL, "POST",
        f"/audit/captures/{cap1['capture_id']}/register-new", json={}))[
        "data"]
    assert reg["exception_state"] == "registered"
    assert reg["result_asset"]["asset_code"] == c1
    assert reg["result_asset"]["register_state"] == "tagged"
    assert_envelope_err(_as(client, CTL, "POST",
                            f"/audit/captures/{cap2['capture_id']}/void",
                            json={}), 400, "validation_failed")
    void = assert_envelope_ok(_as(
        client, CTL, "POST", f"/audit/captures/{cap2['capture_id']}/void",
        json={"reason": "a visitor's chair, taken away"}))["data"]
    assert void["exception_state"] == "voided"
    row = _code(client, c2)
    assert row["state"] == "void" and "visitor" in row["void_reason"]


# ── §8.2 refusals, duplicates and a sync twice ───────────────────────────

def test_refusals_in_words(client, world):
    w = world
    code = w["codes"][3]
    dev = w["device"]["device_code"]
    cases = [
        # a code not reserved to this device and person
        ({"code": "NRS-AST-999999", "scanned_label": "NRS-AST-999999"},
         "in_neither", "not reserved"),
        # the label scanned is not the code used
        ({"code": code, "scanned_label": code + "X"}, "in_neither",
         "not the code"),
        # a code already used (outcome b's)
        ({"code": w["codes"][0], "scanned_label": w["codes"][0]},
         "in_neither", "already used"),
        # a room outside the campaign
        ({"code": code, "scanned_label": code,
          "location_id": w["outside"]}, "in_neither", "outside campaign"),
        # captured more than five working days ago
        ({"code": code, "scanned_label": code, "captured_at": _now(-10)},
         "in_neither", "working days"),
        # and in the future
        ({"code": code, "scanned_label": code, "captured_at": _now(2)},
         "in_neither", "future"),
    ]
    for extra, outcome, words in cases:
        r = _capture(client, w, outcome, 50 + len(words), expect=None,
                     **extra)
        assert r.status_code in (400, 403, 409), (extra, r.text)
        assert words in r.json()["error"]["message"], (extra, r.text)
    # No device header, and somebody else's device
    r = _as(client, CAP, "POST", "/audit/captures", json={
        "capture_id": str(uuid.uuid4()), "campaign_id": 1,
        "location_id": 1, "outcome": "in_neither", "photo_ids": [1],
        "captured_at": _now(), "fields": {"condition": "good"}})
    assert_envelope_err(r, 400)
    assert "X-Cadra-Device" in r.json()["error"]["message"]
    # Nothing above wrote anything: the code is still reserved.
    assert _code(client, code)["state"] == "reserved"
    # The reviewer holds no capture scope.
    r = _as(client, REV, "POST", "/audit/captures", device=dev, json={})
    assert_envelope_err(r, 403, "forbidden")


def test_a_closed_campaign_refuses_captures(client, world):
    w = world
    other = assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/campaigns",
        json={"name": f"pytest audit closed {w['u']}",
              "scope": [{"location_id": w["rooms"][0]}],
              "capturer_ids": [w["cap_id"]],
              "reviewer_ids": [w["rev_id"]]}), 201)["data"]
    assert_envelope_ok(_as(client, CTL, "POST",
                           f"/audit/campaigns/{other['id']}/close", json={}))
    r = _capture(client, w, "on_register", 60, expect=None,
                 campaign_id=other["id"], asset_id=w["asset_a"]["id"])
    assert_envelope_err(r, 409)
    assert "was closed" in r.json()["error"]["message"]


def test_a_duplicate_is_held_and_a_sync_twice_is_one(client, world):
    w = world
    rec = w["sap"]["dup"]
    c4, c5 = w["codes"][3], w["codes"][4]
    first = _capture(client, w, "in_sap", 70, sap_record_id=rec, code=c4,
                     scanned_label=c4)
    second = _capture(client, w, "in_sap", 71, room=1, sap_record_id=rec,
                      code=c5, scanned_label=c5)
    assert first["duplicate_of"] is None
    assert second["duplicate_of"] == first["capture_id"]
    assert second["duplicate_basis"] == "sap_record"
    held = assert_envelope_ok(_as(
        client, REV, "GET", "/audit/captures",
        params={"campaign_id": w["campaign"]["id"], "duplicates": "true",
                "state": "pending_review"}))["data"]
    assert second["capture_id"] in {c["capture_id"] for c in held}
    _accept(client, first)
    r = _accept(client, second, status=None)
    assert_envelope_err(r, 409)
    assert "already accepted" in r.json()["error"]["message"]
    # Returned with a reason, its code goes back to the capturer's reserve.
    assert_envelope_err(_as(client, REV, "POST",
                            f"/audit/captures/{second['capture_id']}/return",
                            json={}), 400)
    ret = assert_envelope_ok(_as(
        client, REV, "POST", f"/audit/captures/{second['capture_id']}/return",
        json={"reason": "the same chair as the first capture"}))["data"]
    assert ret["state"] == "returned"
    assert _code(client, c5)["state"] == "reserved"
    # The same capture synced twice is one capture.
    body = {"capture_id": str(uuid.uuid4()),
            "campaign_id": w["campaign"]["id"],
            "location_id": w["rooms"][0], "outcome": "in_neither",
            "photo_ids": [_photo(client, w, 72)], "captured_at": _now(),
            "code": c5, "scanned_label": c5,
            "fields": {"condition": "good", "category_id": w["category"],
                       "name": "pytest-audit synced twice"}}
    dev = w["device"]["device_code"]
    one = assert_envelope_ok(_as(client, CAP, "POST", "/audit/captures",
                                 device=dev, json=body), 201)["data"]
    two = assert_envelope_ok(_as(client, CAP, "POST", "/audit/captures",
                                 device=dev, json=body), 201)["data"]
    assert one["id"] == two["id"] and two["replayed"] is True
    got = assert_envelope_ok(_as(client, CAP, "GET",
                                 f"/audit/captures/{body['capture_id']}"))
    assert got["data"]["id"] == one["id"]
    w["synced_twice"] = one


# ── §8.3 the block lifecycle ────────────────────────────────────────────

def test_returning_the_block_voids_what_it_did_not_use(client, world):
    w = world
    block = w["block"]
    r = assert_envelope_ok(_as(client, CTL, "POST",
                               f"/audit/blocks/{block['id']}/return",
                               json={"reason": "end of the campaign"}))[
        "data"]
    # Six codes: one active (b), one in review (c registered as new), one
    # void (c voided), one active (the duplicate's first), one in review
    # (synced twice) — and one never used, voided now.
    assert r["state"] == "returned" and r["voided_now"] == 1, r
    unused = w["codes"][5]
    row = _code(client, unused)
    assert row["state"] == "void" and "returned" in row["void_reason"]
    assert_envelope_err(_as(client, CTL, "POST",
                            f"/audit/blocks/{block['id']}/return", json={}),
                        409)
    # Sizes are bounded.
    assert_envelope_err(_as(client, CTL, "POST", "/audit/blocks",
                            json={"device_id": w["device"]["id"],
                                  "size": 501}), 400)


# ── §8.4 closing the campaign ───────────────────────────────────────────

def test_the_campaign_closes_with_both_lists(client, world):
    w = world
    cid = w["campaign"]["id"]
    r = _as(client, CTL, "POST", f"/audit/campaigns/{cid}/close", json={})
    assert_envelope_err(r, 409)
    assert "waiting for review" in r.json()["error"]["message"]
    assert r.json()["error"]["details"]["waiting_for_review"] == 1
    _accept(client, w["synced_twice"])
    closed = assert_envelope_ok(_as(client, CTL, "POST",
                                    f"/audit/campaigns/{cid}/close",
                                    json={}))["data"]
    assert closed["state"] == "closed"
    lists = closed["lists"]
    missing = {r["asset_number"] for r in lists["in_sap_not_found"]}
    assert w["numbers"]["missing"] in missing
    assert w["numbers"]["b2"] in missing
    assert w["numbers"]["b"] not in missing   # registered by the audit
    assert w["numbers"]["dup"] not in missing  # matched by a capture
    found = {r["capture_id"] for r in lists["found_not_in_sap"]}
    assert w["synced_twice"]["capture_id"] in found
    assert all(r["office_code"] == w["office"]
               for r in lists["in_sap_not_found"])
    assert isinstance(lists["sap_records_with_no_office"], int)
    csv = _as(client, "auditor", "GET", f"/audit/campaigns/{cid}/lists.csv",
              params={"list": "in_sap_not_found"})
    assert csv.status_code == 200, csv.text
    assert csv.text.splitlines()[0].startswith("office_code,asset_number")
    assert w["numbers"]["missing"] in csv.text
    # Closed is closed.
    r = _capture(client, w, "on_register", 80, expect=None,
                 asset_id=w["asset_a"]["id"])
    assert_envelope_err(r, 409)


# ── §8.5 the second person ──────────────────────────────────────────────

def test_the_capturer_is_refused_review_and_the_pair_at_grant(client, world):
    w = world
    r = _as(client, CAP, "POST", "/audit/captures/accept",
            json={"capture_ids": [str(uuid.uuid4())]})
    assert_envelope_err(r, 403, "forbidden")
    r = client.post(f"/api/v1/users/{w['cap_id']}/roles",
                    json={"roles": ["audit_capturer", "audit_reviewer"],
                          "dry_run": True})
    err = assert_envelope_err(r, 403, "forbidden")["error"]
    assert "cannot be held by one person" in err["message"]


def test_ai_config_for_the_phone(client, world):
    data = assert_envelope_ok(_as(client, CAP, "GET", "/ai/config"))["data"]
    assert data["label"]["symbologies"][0]["format"] == "qr_code"
    assert data["capture"]["max_working_days_back"] == 5
    assert "remaining_today" in data["ai_identify"]
    assert_envelope_err(_as(client, REV, "GET", "/ai/config"), 403)
