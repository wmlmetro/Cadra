"""The station captures (handoff 67 §2–§3), through the HTTP routes, as the
personas.

The four gaps the mobile team listed in report 66 §10, each with its
refusals, and the two PRD alignments:

* §2.1 an audit photo identified by its id — uploaded once, identified,
  named by the capture; a suggestion made from it can name no other
  capture's photos, and nobody identifies another person's audit photo;
* §2.2 one spoiled code voided by the person it is reserved to, with a
  reason, never reissued;
* §2.3 the capturer returns their OWN block (unused codes voided), never
  somebody else's;
* §2.4 GPS on a capture, optional, stored on the capture only; the identify
  route has no part that could carry it;
* §1 a station's print of a block code is recorded, refused for a code that
  is not the caller's on that device;
* §3 the size band on the identify answer, labelled approximate, and the
  acceptance dashboard's counts moving by exactly what the test did.

A world of its own: a building and a room made for the test, a device bound
to the capturer, a block, a campaign over the building. No SAP records: the
outcomes used here are a (on the register) and c (in neither).
"""
import uuid

import pytest
import requests

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok
from .test_the_audit import (CAP, CTL, REV, _as, _location, _now, _png,
                             _u, _uid)
from .test_what_the_photo_says import AI, IDENTIFY, ai_on  # noqa: F401

ACCEPTANCE = AI + "/acceptance"


@pytest.fixture(scope="module")
def station(client):
    u = _u()
    building = _location(client, f"pytest-station {u}")
    room = _location(client, f"pytest-station {u} room", building)
    cap_id, rev_id = _uid(client, CAP), _uid(client, REV)
    device = assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/devices",
        json={"name": f"pytest station {u}", "user_id": cap_id}),
        201)["data"]
    block = assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/blocks",
        json={"device_id": device["id"], "size": 6}), 201)["data"]
    campaign = assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/campaigns",
        json={"name": f"pytest station {u}",
              "scope": [{"location_id": building}],
              "capturer_ids": [cap_id], "reviewer_ids": [rev_id]}),
        201)["data"]
    asset = gates.new_registered_asset(
        client, name=f"pytest-station chair {u}", location_id=room)
    return {"u": u, "building": building, "room": room, "device": device,
            "dev": device["device_code"], "block": block,
            "codes": [c["code"] for c in block["codes"]],
            "campaign": campaign, "asset": asset,
            "category": gates.receipt_body(client)["category_id"],
            "cap_id": cap_id, "rev_id": rev_id}


_seed = [1000]


def _photo(client, name="item"):
    _seed[0] += 1
    r = _as(client, CAP, "POST", "/audit/photos",
            files={"file": (f"{name}-{_seed[0]}.png", _png(_seed[0]),
                            "image/png")},
            data={"source": "mobile"})
    return assert_envelope_ok(r, 201)["data"]["id"]


def _identify_audit(client, photo_id, key=CAP, **extra):
    files = {"audit_photo_id": (None, str(photo_id))}
    files.update({k: (None, v) for k, v in extra.items()})
    if key is None:
        return client.post(IDENTIFY, files=files)
    return _as(client, key, "POST", "/ai/identify", files=files)


def _body(s, photo, **extra):
    """An outcome-a capture of the world's register asset, from `photo`."""
    body = {"capture_id": str(uuid.uuid4()),
            "campaign_id": s["campaign"]["id"], "location_id": s["room"],
            "outcome": "on_register", "asset_id": s["asset"]["id"],
            "photo_ids": [photo], "captured_at": _now(),
            "fields": {"condition": "fair"}}
    body.update(extra)
    return body


def _send(client, s, body, expect=201):
    r = _as(client, CAP, "POST", "/audit/captures", device=s["dev"],
            json=body)
    if expect == 201:
        return assert_envelope_ok(r, 201)["data"]
    return r


def _code(client, code):
    rows = assert_envelope_ok(_as(client, CTL, "GET", "/audit/codes",
                                  params={"code": code}))["data"]
    assert len(rows) == 1, rows
    return rows[0]


# ── §2.1 identify an audit photo by its id ────────────────────────────────

def test_an_audit_photo_is_identified_by_its_id(client, station, ai_on):
    s = station
    pid = _photo(client, "chair")
    r = _identify_audit(client, pid)
    sug = assert_envelope_ok(r, 201)["data"]
    assert sug["photo"] == {"kind": "audit_photo", "id": pid}, sug["photo"]
    # §3 the size band: approximate, in words; dimensions untouched.
    band = sug["size_band"]
    assert band["value"] == "medium" and band["approximate"] is True, band
    assert band["label"] == "Approximate size"
    assert set(band["definitions"]) == {"small", "medium", "large"}
    assert band["definition"] == band["definitions"]["medium"]
    assert sug["attributes"]["dimensions"] is None

    # The capture names it with its photo.
    cap = _send(client, s, _body(s, pid,
                                 ai_suggestion_id=sug["suggestion_id"]))
    assert cap["ai_suggestion"]["id"] == sug["suggestion_id"]

    # Named by a capture WITHOUT the photo it came from: refused.
    pid2 = _photo(client)
    sug2 = assert_envelope_ok(_identify_audit(client, pid2), 201)["data"]
    other = _photo(client)
    r = _send(client, s, _body(s, other,
                               ai_suggestion_id=sug2["suggestion_id"]),
              expect=400)
    e = assert_envelope_err(r, 400)
    assert "does not carry" in e["error"]["message"], e


def test_identify_by_audit_photo_refusals(client, station, ai_on):
    pid = _photo(client)
    # Two photo parts at once.
    r = _as(client, CAP, "POST", "/ai/identify",
            files={"audit_photo_id": (None, str(pid)),
                   "photo_id": (None, "1")})
    e = assert_envelope_err(r, 400)
    assert e["error"]["details"]["received"] == ["audit_photo_id",
                                                 "photo_id"]
    # `source` belongs with a file.
    e = assert_envelope_err(_identify_audit(client, pid, source="mobile"),
                            400)
    assert "source" in e["error"]["details"]["rejected_fields"]
    # Somebody else's audit photo (the suite's credential holds
    # `assets:write`, so it reaches the route).
    e = assert_envelope_err(_identify_audit(client, pid, key=None), 403)
    assert e["error"]["details"]["reason"] == "not_yours"
    # No such photo.
    assert_envelope_err(_identify_audit(client, 2_000_000_000), 404)
    # §2.4: the identify route has no part a position could ride in.
    r = _as(client, CAP, "POST", "/ai/identify",
            files={"audit_photo_id": (None, str(pid)),
                   "latitude": (None, "9.05")})
    assert_envelope_err(r, 400)


# ── §2.2 void one spoiled code ────────────────────────────────────────────

def test_the_holder_voids_one_spoiled_code(client, station):
    s = station
    code = s["codes"][-1]
    path = f"/audit/codes/{code}/void"
    e = assert_envelope_err(_as(client, CAP, "POST", path, json={}), 400)
    assert e["error"]["details"]["field"] == "reason"
    e = assert_envelope_err(_as(client, CAP, "POST", path,
                                json={"reason": "  "}), 400)
    # The reviewer holds no `audit:capture`: the scope gate.
    assert_envelope_err(_as(client, REV, "POST", path,
                            json={"reason": "torn"}), 403)
    assert_envelope_err(_as(client, CAP, "POST",
                            "/audit/codes/NO-SUCH-CODE/void",
                            json={"reason": "torn"}), 404)
    row = assert_envelope_ok(_as(client, CAP, "POST", path,
                                 json={"reason": "label torn at print"}))[
        "data"]
    assert row["state"] == "void" and "label torn at print" in \
        row["void_reason"], row
    assert row["voided_by"]["id"] == s["cap_id"]
    # Twice: it is no longer reserved.
    e = assert_envelope_err(_as(client, CAP, "POST", path,
                                json={"reason": "again"}), 409)
    assert e["error"]["details"]["code_state"] == "void"
    # Never reissued: a capture cannot use it.
    pid = _photo(client)
    r = _send(client, s, {
        "capture_id": str(uuid.uuid4()), "campaign_id": s["campaign"]["id"],
        "location_id": s["room"], "outcome": "in_neither",
        "photo_ids": [pid], "captured_at": _now(), "code": code,
        "scanned_label": code,
        "fields": {"condition": "good", "category_id": s["category"],
                   "name": "pytest-station torn"}}, expect=409)
    assert "already used" in assert_envelope_err(r, 409)["error"]["message"]


def test_a_code_reserved_to_somebody_else_is_not_theirs_to_void(client,
                                                                 station):
    # A code the ledger holds that no block reserved to the capturer: the
    # registered asset's own code.
    code = station["asset"]["asset_code"]
    e = assert_envelope_err(_as(client, CAP, "POST",
                                f"/audit/codes/{code}/void",
                                json={"reason": "torn"}), 403)
    assert "not reserved to you" in e["error"]["message"]


# ── §1 the station's print, recorded ─────────────────────────────────────

def test_a_station_print_of_a_block_code_is_recorded(client, station):
    s = station
    code = s["codes"][0]
    r = _as(client, CAP, "POST", "/audit/codes/printed", device=s["dev"],
            json={"codes": [code]})
    out = assert_envelope_ok(r)["data"]["recorded"]
    assert out[0]["code"] == code and out[0]["print_count"] == 1
    out = assert_envelope_ok(_as(client, CAP, "POST", "/audit/codes/printed",
                                 device=s["dev"],
                                 json={"codes": [code]}))["data"]["recorded"]
    assert out[0]["print_count"] == 2
    row = _code(client, code)
    assert row["print_count"] == 2 and row["state"] == "reserved"
    assert row["last_printed_by"]["id"] == s["cap_id"]
    # No device named: refused in words, nothing recorded.
    e = assert_envelope_err(_as(client, CAP, "POST", "/audit/codes/printed",
                                json={"codes": [code]}), 400)
    assert "X-Cadra-Device" in e["error"]["message"]
    # A code that is not the capturer's, beside one that is: the whole
    # request refused, the good one's count unmoved.
    e = assert_envelope_err(_as(
        client, CAP, "POST", "/audit/codes/printed", device=s["dev"],
        json={"codes": [code, s["asset"]["asset_code"]]}), 403)
    assert _code(client, code)["print_count"] == 2
    # Unknown, and an empty list.
    assert_envelope_err(_as(client, CAP, "POST", "/audit/codes/printed",
                            device=s["dev"], json={"codes": ["NOPE-1"]}),
                        400)
    assert_envelope_err(_as(client, CAP, "POST", "/audit/codes/printed",
                            device=s["dev"], json={"codes": []}), 400)


# ── §2.4 GPS on a capture ────────────────────────────────────────────────

def test_gps_is_stored_on_the_capture_only(client, station):
    s = station
    cap = _send(client, s, _body(s, _photo(client), gps={
        "latitude": 9.0579, "longitude": 7.4951, "accuracy_m": 12.5}))
    assert cap["gps"] == {"latitude": 9.0579, "longitude": 7.4951,
                          "accuracy_m": 12.5}, cap["gps"]
    again = assert_envelope_ok(_as(
        client, CTL, "GET", f"/audit/captures/{cap['capture_id']}"))["data"]
    assert again["gps"]["latitude"] == 9.0579
    plain = _send(client, s, _body(s, _photo(client)))
    assert plain["gps"] is None
    # Not a position: refused before anything is written.
    for bad, field in (({"latitude": 91, "longitude": 7}, "gps.latitude"),
                       ({"latitude": 9}, "gps.longitude"),
                       ({"latitude": True, "longitude": 7}, "gps.latitude"),
                       ({"latitude": 9, "longitude": 7, "altitude": 3},
                        "gps"),
                       ("9.05,7.49", "gps")):
        r = _send(client, s, _body(s, _photo(client), gps=bad),
                  expect=400)
        e = assert_envelope_err(r, 400)
        assert e["error"]["details"]["field"] == field, (bad, e)
    # The asset never gains it.
    asset = assert_envelope_ok(client.get(
        f"/api/v1/assets/{s['asset']['id']}"))["data"]
    assert "gps" not in asset and "gps_latitude" not in asset


# ── §2.3 return their own block ──────────────────────────────────────────

def test_the_capturer_returns_their_own_block_not_anybody_elses(client,
                                                                station):
    s = station
    # A second device, bound to the reviewer, with a block of its own.
    dev2 = assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/devices",
        json={"name": f"pytest station2 {s['u']}", "user_id": s["rev_id"]}),
        201)["data"]
    blk2 = assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/blocks",
        json={"device_id": dev2["id"], "size": 2}), 201)["data"]
    e = assert_envelope_err(_as(client, CAP, "POST",
                                f"/audit/blocks/{blk2['id']}/return",
                                json={}), 403)
    assert "not to you" in e["error"]["message"]
    # The reviewer holds neither scope.
    assert_envelope_err(_as(client, REV, "POST",
                            f"/audit/blocks/{blk2['id']}/return", json={}),
                        403)
    # The controller still returns anybody's.
    out = assert_envelope_ok(_as(client, CTL, "POST",
                                 f"/audit/blocks/{blk2['id']}/return",
                                 json={}))["data"]
    assert out["voided_now"] == 2

    # The capturer's own: every reserved code voided, the used ones kept.
    blk = s["block"]
    before = assert_envelope_ok(_as(client, CTL, "GET",
                                    f"/audit/blocks/{blk['id']}"))["data"]
    reserved = before["codes_by_state"].get("reserved", 0)
    out = assert_envelope_ok(_as(client, CAP, "POST",
                                 f"/audit/blocks/{blk['id']}/return",
                                 json={"reason": "end of shift"}))["data"]
    assert out["state"] == "returned" and out["voided_now"] == reserved
    assert out["returned_by"]["id"] == s["cap_id"]
    assert out["return_reason"] == "end of shift"
    assert out["codes_by_state"].get("reserved", 0) == 0
    e = assert_envelope_err(_as(client, CAP, "POST",
                                f"/audit/blocks/{blk['id']}/return",
                                json={}), 409)
    assert "already returned" in e["error"]["message"]


# ── §3 the acceptance dashboard ──────────────────────────────────────────

def _row(rows, key):
    return next((r for r in rows if r["key"] == key),
                {"made": 0, "identified": 0, "used": 0,
                 "accepted_unchanged": 0})


def test_the_acceptance_dashboard_counts_what_was_done(client, station,
                                                       ai_on):
    """Three identifications: one used unchanged by a capture, one used
    with a field changed, one never used. The totals, the model's row and
    the campaign location's row move by exactly that."""
    s = station
    before = assert_envelope_ok(client.get(ACCEPTANCE))["data"]
    assert before["window"]["days"] == 30
    assert set(before["definitions"]) >= {
        "made", "identified", "used", "accepted_unchanged",
        "share_accepted_unchanged", "by_category", "by_site", "by_model"}

    def identify():
        pid = _photo(client, "chair")
        return pid, assert_envelope_ok(_identify_audit(client, pid),
                                       201)["data"]

    def kept(sug):
        attrs = sug["attributes"]
        f = {"category_id": sug["category"]["id"],
             "condition": sug["condition"]["value"]}
        f.update({k: v for k, v in attrs.items() if v})
        return f

    pid, s1 = identify()
    _send(client, s, _body(s, pid, fields=kept(s1),
                           ai_suggestion_id=s1["suggestion_id"]))
    pid, s2 = identify()
    changed = dict(kept(s2), colour="PURPLE")
    _send(client, s, _body(s, pid, fields=changed,
                           ai_suggestion_id=s2["suggestion_id"]))
    identify()

    after = assert_envelope_ok(client.get(ACCEPTANCE))["data"]
    t0, t1 = before["totals"], after["totals"]
    assert t1["made"] - t0["made"] == 3
    assert t1["identified"] - t0["identified"] == 3
    assert t1["used"] - t0["used"] == 2
    assert t1["accepted_unchanged"] - t0["accepted_unchanged"] == 1
    m0 = _row(before["by_model"], "cadra-fake-1")
    m1 = _row(after["by_model"], "cadra-fake-1")
    assert (m1["made"] - m0["made"], m1["used"] - m0["used"],
            m1["accepted_unchanged"] - m0["accepted_unchanged"]) == (3, 2, 1)
    b0 = _row(before["by_site"], str(s["building"]))
    site = _row(after["by_site"], str(s["building"]))
    assert (site["made"] - b0["made"], site["used"] - b0["used"],
            site["accepted_unchanged"] - b0["accepted_unchanged"]) == \
        (2, 2, 1), after["by_site"]
    assert site["share_accepted_unchanged"] == round(
        site["accepted_unchanged"] / site["used"], 4)
    assert "pytest-station" in site["label"]
    days = assert_envelope_ok(client.get(ACCEPTANCE,
                                         params={"days": 1}))["data"]
    assert days["window"]["from"] == days["window"]["to"]
    for bad in ("0", "366", "x"):
        assert_envelope_err(client.get(ACCEPTANCE, params={"days": bad}),
                            400)
    # Settings readers only.
    r = requests.get(client.base + ACCEPTANCE, timeout=60, headers={
        "Authorization": f"Bearer {gates._token(client, CAP)}"})
    assert_envelope_err(r, 403)


def test_a_capture_cannot_name_a_call_that_identified_nothing(client,
                                                              station, ai_on):
    """Verification pass, 67: a 503's details carry the failed call's id; a
    capture naming it is refused, as an asset save is, and nothing is
    written."""
    s = station
    pid = _photo(client, "timeout")
    e = assert_envelope_err(_identify_audit(client, pid), 503)
    sid = e["error"]["details"]["suggestion_id"]
    r = _send(client, s, _body(s, pid, ai_suggestion_id=sid), expect=400)
    e = assert_envelope_err(r, 400)
    assert e["error"]["details"]["reason"] == "not_identified", e
