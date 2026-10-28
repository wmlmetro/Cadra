"""Where the captures went (handoff 69), through the HTTP routes, as the
personas.

Part A found two ways a stored capture is invisible on *Audit review* (a
campaign that names no reviewer; a capture in a campaign the dropdown did
not open) and one way a capture is never stored (a refusal the phone did not
show). What is pinned here:

* B1 — a campaign with 101 waiting: the review list's first page is 100,
  says there are 101, and its cursor reaches the 101st;
* B2 — `GET /audit/captures?q=` finds a capture by its id (any case), its
  code (any case, exactly) and the old tag confirmed on it (normalised as
  the SAP matcher does), combined with the other filters, in a CLOSED
  campaign too; each row says whether its campaign is open and who reviews
  it;
* B3 — `reviewers_active` on the campaign answer;
* C2 — a refused capture (label scanned ≠ code) leaves one refusal row and
  no capture, the row outliving the request's rollback (the code is still
  reserved); a replay refused again is a second row; an accepted capture
  leaves none; a refusal at the token or the scope leaves none; only the
  Asset Controller reads them.

A world of its own (no SAP import: every capture here is outcome c), so it
does not depend on `test_the_audit.py`'s.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok
from .test_the_audit import CAP, CTL, REV, _as, _location, _now, _png, _u, \
    _uid

#: Lagos is UTC+1 all year (no daylight saving).
LAGOS = timezone(timedelta(hours=1))
#: B1's campaign: one more than the review page's page.
PAGE = 100


def _photo(client, seed):
    r = _as(client, CAP, "POST", "/audit/photos",
            files={"file": (f"item-{seed}.png", _png(seed), "image/png")},
            data={"source": "mobile"})
    return assert_envelope_ok(r, 201)["data"]["id"]


def _campaign(client, name, building, cap_id, reviewers):
    return assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/campaigns",
        json={"name": name, "scope": [{"location_id": building}],
              "capturer_ids": [cap_id], "reviewer_ids": reviewers}),
        201)["data"]


@pytest.fixture(scope="module")
def place(client):
    u = _u()
    building = _location(client, f"pytest-69 {u}")
    room = _location(client, f"pytest-69 {u} room", building)
    cap_id, rev_id = _uid(client, CAP), _uid(client, REV)
    device = assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/devices",
        json={"name": f"pytest-69 phone {u}", "user_id": cap_id}),
        201)["data"]
    block = assert_envelope_ok(_as(
        client, CTL, "POST", "/audit/blocks",
        json={"device_id": device["id"], "size": PAGE + 20}), 201)["data"]
    reviewed = _campaign(client, f"pytest-69 reviewed {u}", building, cap_id,
                         [rev_id])
    unreviewed = _campaign(client, f"pytest-69 nobody reviews {u}",
                           building, cap_id, [])
    return {"u": u, "room": room, "device": device, "cap_id": cap_id,
            "rev_id": rev_id, "codes": [c["code"] for c in block["codes"]],
            "reviewed": reviewed, "unreviewed": unreviewed,
            "photo": _photo(client, 69), "building": building,
            "category": gates.receipt_body(client)["category_id"]}


def _body(p, campaign, code, **fields):
    return {"capture_id": str(uuid.uuid4()), "campaign_id": campaign["id"],
            "location_id": p["room"], "outcome": "in_neither",
            "photo_ids": [p["photo"]], "captured_at": _now(),
            "code": code, "scanned_label": code,
            "fields": {"condition": "fair", "category_id": p["category"],
                       "name": f"pytest-69 item {code}", **fields}}


def _post(client, p, body):
    return _as(client, CAP, "POST", "/audit/captures",
               device=p["device"]["device_code"], json=body)


def _find(client, q, key=REV, **params):
    return assert_envelope_ok(_as(client, key, "GET", "/audit/captures",
                                  params={"q": q, **params}))["data"]


def _refusals(client, **params):
    return assert_envelope_ok(_as(client, CTL, "GET", "/audit/refusals",
                                  params=params))


# ── B2 · find a capture ──────────────────────────────────────────────────

def test_find_a_capture_by_its_id_code_and_old_tag(client, place):
    p = place
    code = p["codes"][0]
    tag = f"FIRS/Q{p['u']}/0001"
    body = _body(p, p["unreviewed"], code,
                 legacy_asset_code=f"  {tag.lower().replace('/', ' / ')} ")
    cap = assert_envelope_ok(_post(client, p, body), 201)["data"]
    want = cap["capture_id"]
    for q in (want, want.upper(), "{%s}" % want, code, code.lower(),
              f" {code} ", tag, tag.lower()):
        rows = _find(client, q)
        assert [r["capture_id"] for r in rows] == [want], q
    # Exactly, never a fragment: a piece of a code names other codes.
    assert _find(client, code[:-1]) == []
    assert _find(client, "%") == [] and _find(client, "_" * len(code)) == []
    # Combined with the other filters.
    assert _find(client, code, state="accepted") == []
    assert len(_find(client, code, campaign_id=p["unreviewed"]["id"])) == 1
    # The row says why a reviewer would not see it.
    row = _find(client, code)[0]
    assert row["campaign"] == {"id": p["unreviewed"]["id"],
                               "name": p["unreviewed"]["name"],
                               "state": "open", "reviewers": []}
    assert row["device"]["id"] == p["device"]["id"]
    assert row["received_at"] and row["captured_at"]
    # Read with `audit:read`, the capturer included.
    assert len(_find(client, code, key=CAP)) == 1
    assert_envelope_err(_as(client, REV, "GET", "/audit/captures",
                            params={"q": "x" * 201}), 400, "invalid_request")


def test_a_capture_in_a_closed_campaign_is_found(client, place):
    p = place
    closing = _campaign(client, f"pytest-69 closing {p['u']}", p["building"],
                        p["cap_id"], [p["rev_id"]])
    code = p["codes"][1]
    cap = assert_envelope_ok(_post(client, p, _body(p, closing, code)),
                             201)["data"]
    assert_envelope_ok(_as(client, REV, "POST",
                           f"/audit/captures/{cap['capture_id']}/accept",
                           json={}))
    assert_envelope_ok(_as(client, CTL, "POST",
                           f"/audit/campaigns/{closing['id']}/close",
                           json={}))
    row, = _find(client, cap["capture_id"])
    assert row["campaign"]["state"] == "closed"
    assert row["campaign"]["reviewers"] == [
        {"id": p["rev_id"], "name": row["campaign"]["reviewers"][0]["name"]}]


# ── B3 · waiting where nobody can review it ──────────────────────────────

def test_reviewers_active_on_the_campaign(client, place):
    p = place
    one = assert_envelope_ok(_as(client, CTL, "GET",
                                 f"/audit/campaigns/{p['reviewed']['id']}"))[
        "data"]
    none = assert_envelope_ok(_as(
        client, CTL, "GET", f"/audit/campaigns/{p['unreviewed']['id']}"))[
        "data"]
    assert one["reviewers_active"] == 1 == len(one["reviewers"])
    assert none["reviewers_active"] == 0 == len(none["reviewers"])
    listed = {c["id"]: c for c in assert_envelope_ok(_as(
        client, CTL, "GET", "/audit/campaigns",
        params={"state": "open"}))["data"]}
    assert listed[p["unreviewed"]["id"]]["reviewers_active"] == 0


# ── B1 · every page ──────────────────────────────────────────────────────

def test_the_101st_waiting_capture_is_reachable(client, place):
    p = place
    many = _campaign(client, f"pytest-69 a hundred and one {p['u']}",
                     p["building"], p["cap_id"], [p["rev_id"]])
    made = [assert_envelope_ok(_post(client, p, _body(
        p, many, p["codes"][10 + i])), 201)["data"]["capture_id"]
        for i in range(PAGE + 1)]
    params = {"campaign_id": many["id"], "state": "pending_review",
              "limit": PAGE}
    first = assert_envelope_ok(_as(client, REV, "GET", "/audit/captures",
                                   params=params))
    assert len(first["data"]) == PAGE
    assert first["pagination"]["total_estimate"] == PAGE + 1
    assert first["pagination"]["next_cursor"]
    # Oldest waiting first (the ruling), so the cut-off one is the newest.
    assert made[-1] not in {r["capture_id"] for r in first["data"]}
    rest = assert_envelope_ok(_as(
        client, REV, "GET", "/audit/captures",
        params={**params, "cursor": first["pagination"]["next_cursor"]}))
    assert [r["capture_id"] for r in rest["data"]] == [made[-1]]
    assert rest["pagination"]["next_cursor"] is None


# ── C2 · refused syncs are kept ──────────────────────────────────────────

def test_a_refused_capture_leaves_one_refusal_and_no_capture(client, place):
    p = place
    code = p["codes"][2]
    body = _body(p, p["reviewed"], code)
    body["scanned_label"] = code + "X"
    r = _post(client, p, body)
    assert r.status_code in (400, 409), r.text
    sent = r.json()["error"]
    # Nothing stored, and the request was rolled back: the code is still
    # reserved — yet the refusal is there.
    assert_envelope_err(_as(client, REV, "GET",
                            f"/audit/captures/{body['capture_id']}"),
                        404, "not_found")
    code_row, = assert_envelope_ok(_as(client, CTL, "GET", "/audit/codes",
                                       params={"code": code}))["data"]
    assert code_row["state"] == "reserved"
    got = _refusals(client, capture_id=body["capture_id"])
    assert got["pagination"]["total_estimate"] == 1
    row, = got["data"]
    assert row["capture_id"] == body["capture_id"]
    assert row["user"]["id"] == p["cap_id"]
    assert row["device_code"] == p["device"]["device_code"]
    assert row["device"]["id"] == p["device"]["id"]
    assert row["campaign"]["id"] == p["reviewed"]["id"]
    assert row["location"]["id"] == p["room"]
    assert row["outcome"] == "in_neither" and row["code"] == code
    assert row["http_status"] == r.status_code
    assert row["error_code"] == sent["code"]
    assert row["message"] == sent["message"]
    assert row["request_id"] == sent["request_id"]
    # Never the body's photos, fields or GPS.
    assert not {"photo_ids", "fields", "gps", "photos"} & set(row)
    # A replay refused again is a second row, newest first.
    again = _post(client, p, body)
    assert again.status_code == r.status_code
    rows = _refusals(client, capture_id=body["capture_id"])["data"]
    assert len(rows) == 2 and rows[0]["id"] > rows[1]["id"]
    # Filters: the device, the person, the day.
    assert {x["id"] for x in rows} <= {x["id"] for x in _refusals(
        client, device_id=p["device"]["id"], user_id=p["cap_id"],
        since=_now()[:10])["data"]}
    assert _refusals(client, capture_id=body["capture_id"],
                     user_id=p["rev_id"])["data"] == []
    assert _refusals(client, capture_id=body["capture_id"],
                     device_id=999999999)["data"] == []
    # `since` a Lagos day: tomorrow's holds nothing refused today.
    tomorrow = (datetime.now(LAGOS) + timedelta(days=1)).strftime("%Y-%m-%d")
    assert _refusals(client, capture_id=body["capture_id"],
                     since=tomorrow)["data"] == []


def test_an_accepted_capture_and_a_refusal_at_the_door_leave_none(
        client, place):
    p = place
    ok = _body(p, p["reviewed"], p["codes"][3])
    assert_envelope_ok(_post(client, p, ok), 201)
    assert _refusals(client, capture_id=ok["capture_id"])["data"] == []
    # At the token (no person) and at the scope (the reviewer holds no
    # `audit:capture`): the Odoo log has these, the table does not.
    door = _body(p, p["reviewed"], p["codes"][4])
    r = requests.post(f"{client.base}/api/v1/audit/captures", json=door,
                      timeout=60,
                      headers={"X-Cadra-Device": p["device"]["device_code"]})
    assert r.status_code == 401
    assert_envelope_err(_as(client, REV, "POST", "/audit/captures",
                            device=p["device"]["device_code"], json=door),
                        403, "forbidden")
    assert _refusals(client, capture_id=door["capture_id"])["data"] == []


def test_only_the_asset_controller_reads_the_refusals(client, place):
    for key in (CAP, REV):
        assert_envelope_err(_as(client, key, "GET", "/audit/refusals"),
                            403, "forbidden")
    assert_envelope_err(_as(client, CTL, "GET", "/audit/refusals",
                            params={"since": "yesterday"}),
                        400, "invalid_request")
