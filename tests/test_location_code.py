"""Room codes over HTTP — handoff 61 §7, ruling R8.

Every `generic.location` carries a `location_code` (`LOC-…`), unique per
tenant, generated from the hierarchy when empty, editable by
`locations:write` with a uniqueness refusal in words. A scan of one at
`GET /api/v1/barcode/lookup` answers `matched_by: "location"` — a room,
never an asset and never "not found" — and the station prints its label at
`GET /api/v1/locations/<id>/label`, medium or large, never small.

THE DENOMINATOR. "Every location has a code" is read here through the
API, which caps an external credential's view of any list at its record cap
(100 by default, `_warnings.truncated` says so). So the HTTP test checks
every location THIS CREDENTIAL CAN SEE and says how many of how many; the
whole-tenant claim is the in-registry test
(`myservice_api/tests/test_location_code.py`, every row of the table) and
the SQL in the handoff report, run per tenant after the fan-out:

    SELECT count(*), count(location_code), count(DISTINCT location_code)
      FROM generic_location;          -- all three equal, or it is a defect
"""
import re
import uuid

import pytest

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok

SHAPE = re.compile(r"^LOC(-[A-Z0-9]+)+$")


def _uniq():
    return uuid.uuid4().hex[:8].upper()


def _new_location(client, **body):
    body.setdefault("name", "pytest-room-%s" % _uniq())
    r = client.post("/api/v1/locations", json=body)
    return assert_envelope_ok(r, 201)["data"]


def _get(client, loc_id):
    return assert_envelope_ok(client.get("/api/v1/locations/%s" % loc_id))["data"]


# ─── every location has one, and none collide ────────────────────────

def test_every_visible_location_has_a_code_and_none_collide(client):
    seen, cursor, truncated, total = [], None, None, None
    for active in ("true", "false"):
        cursor = None
        while True:
            params = {"limit": 200, "active": active}
            if cursor:
                params["cursor"] = cursor
            body = assert_envelope_ok(client.get("/api/v1/locations",
                                                 params=params))
            seen += body["data"]
            truncated = truncated or body.get("_warnings", {}).get("truncated")
            if active == "true":
                total = body["pagination"]["total_estimate"]
            cursor = body["pagination"]["next_cursor"]
            if not cursor:
                break
    assert seen, "the tenant has no locations at all — nothing was checked"
    uncoded = [l["id"] for l in seen if not l.get("location_code")]
    assert not uncoded, (
        "%d of %d locations read carry no location_code (first: %s) — the "
        "fill did not run on this tenant, or a writer bypassed `create`"
        % (len(uncoded), len(seen), uncoded[:5]))
    misshapen = [l["location_code"] for l in seen
                 if not SHAPE.match(l["location_code"])]
    assert not misshapen, misshapen[:5]
    codes = [l["location_code"] for l in seen]
    assert len(set(codes)) == len(codes), (
        "%d codes for %d locations read" % (len(set(codes)), len(codes)))
    print("location_code: %d of %d active locations read%s; all coded, "
          "0 collisions" % (len([l for l in seen if l["active"]]), total,
                            " (truncated by the credential's cap)"
                            if truncated else ""))


def test_a_new_location_gets_a_code(client):
    loc = _new_location(client)
    assert loc["location_code"] == "LOC-%d" % loc["id"], (
        "a location with no zone code anywhere above it ends in its id")
    zone = "PZ%s" % _uniq()
    coded = _new_location(client, zone_code=zone.lower())
    assert coded["location_code"] in (
        "LOC-%s" % zone, "LOC-%s-%d" % (zone, coded["id"]))
    # Derived from the ZONE CODES of the chain (cleaned: `R-1` is `R1`),
    # not from the parent's stored code.
    child = _new_location(client, parent_id=coded["id"], zone_code="R-1")
    assert child["location_code"] in (
        "LOC-%s-R1" % zone, "LOC-%s-R1-%d" % (zone, child["id"]))


def test_the_list_finds_a_location_by_its_code(client):
    loc = _new_location(client, zone_code="Q%s" % _uniq())
    body = assert_envelope_ok(client.get(
        "/api/v1/locations", params={"q": loc["location_code"]}))
    assert loc["id"] in [l["id"] for l in body["data"]]


# ─── the edit ────────────────────────────────────────────────────────

def test_a_duplicate_edit_is_refused_with_nothing_written(client):
    a = _new_location(client)
    b = _new_location(client, description="before")
    r = client.patch("/api/v1/locations/%d" % b["id"], json={
        "location_code": a["location_code"], "description": "after"})
    err = assert_envelope_err(r, 409, "conflict")["error"]
    assert "already the code of" in err["message"]
    assert a["name"] in err["message"]
    assert err["details"]["held_by_location_id"] == a["id"]
    assert err["details"]["reason"] == "taken"
    now = _get(client, b["id"])
    assert now["location_code"] == b["location_code"]
    assert now["description"] == "before", (
        "the field sent beside the refused code was written")


def test_a_code_without_the_prefix_is_refused_in_words(client):
    loc = _new_location(client)
    r = client.patch("/api/v1/locations/%d" % loc["id"],
                     json={"location_code": "HQ-F10-%s" % _uniq()})
    err = assert_envelope_err(r, 400, "validation_failed")["error"]
    assert "begins LOC-" in err["message"]
    assert err["details"]["reason"] == "format"
    assert _get(client, loc["id"])["location_code"] == loc["location_code"]


def test_a_duplicate_on_create_is_refused_and_creates_nothing(client):
    a = _new_location(client)
    name = "pytest-room-dup-%s" % _uniq()
    r = client.post("/api/v1/locations",
                    json={"name": name, "location_code": a["location_code"]})
    assert_envelope_err(r, 409, "conflict")
    found = assert_envelope_ok(client.get("/api/v1/locations",
                                          params={"q": name}))["data"]
    assert not found, "the refused create left a location behind"


def test_a_typed_code_is_trimmed_and_upper_cased(client):
    loc = _new_location(client)
    want = "LOC-PYT-%s" % _uniq()
    r = client.patch("/api/v1/locations/%d" % loc["id"],
                     json={"location_code": "  %s " % want.lower()})
    assert assert_envelope_ok(r)["data"]["location_code"] == want


def test_an_empty_code_is_generated_again(client):
    loc = _new_location(client)
    client.patch("/api/v1/locations/%d" % loc["id"],
                 json={"location_code": "LOC-PYT-%s" % _uniq()})
    r = client.patch("/api/v1/locations/%d" % loc["id"],
                     json={"location_code": ""})
    assert assert_envelope_ok(r)["data"]["location_code"] == "LOC-%d" % loc["id"]


# ─── the scan ────────────────────────────────────────────────────────

def _lookup(client, query):
    return client.get("/api/v1/barcode/lookup", params={"query": query})


def test_a_room_code_scan_answers_this_is_a_room(client, capture):
    parent = _new_location(client, name="pytest-floor-%s" % _uniq())
    room = _new_location(client, parent_id=parent["id"])
    r = _lookup(client, room["location_code"])
    capture("barcode/lookup_room", r)
    data = assert_envelope_ok(r)["data"]
    assert data["found"] is True
    assert data["matched_by"] == "location"
    m = data["matched_location"]
    assert m["id"] == room["id"]
    assert m["name"] == room["name"]
    assert m["location_code"] == room["location_code"]
    assert m["path"] == "%s / %s" % (parent["name"], room["name"])
    assert m["active"] is True
    assert isinstance(m["asset_count"], int)
    for asset_key in ("asset_id", "asset_name", "asset_code", "tag_number"):
        assert asset_key not in data, "a room answer names no asset"


def test_a_room_code_scan_ignores_case_and_a_trailing_space(client):
    room = _new_location(client)
    data = assert_envelope_ok(
        _lookup(client, room["location_code"].lower() + " "))["data"]
    assert data["matched_location"]["id"] == room["id"]


def test_a_tag_an_asset_code_and_a_serial_resolve_as_before(client):
    serial = "PYT-%s" % uuid.uuid4().hex[:10].upper()
    asset = gates.new_registered_asset(
        client, name="pytest-room-scan-%s" % _uniq(), category_id=1,
        serial_number=serial)
    by_tag = assert_envelope_ok(_lookup(client, asset["tag"]))["data"]
    assert (by_tag["matched_by"], by_tag["asset_id"]) == (
        "tag_number", asset["id"])
    by_code = assert_envelope_ok(_lookup(client, asset["asset_code"]))["data"]
    assert by_code["asset_id"] == asset["id"]
    assert by_code["matched_by"] in ("asset_code", "tag_number")
    by_serial = assert_envelope_ok(_lookup(client, serial))["data"]
    assert (by_serial["matched_by"], by_serial["asset_id"]) == (
        "serial_number", asset["id"])


def test_a_miss_still_answers_as_before(client):
    q = "LOC-NOSUCH-%s" % _uniq()
    err = assert_envelope_err(_lookup(client, q), 404, "not_found")["error"]
    assert err["message"].startswith(
        "No active tag, asset code or serial number matches")
    assert err["details"]["query"] == q


def test_the_portal_lookup_is_unchanged_and_does_not_resolve_rooms(client):
    room = _new_location(client)
    assert_envelope_err(client.get("/api/v1/tags/lookup",
                                   params={"query": room["location_code"]}),
                        404, "not_found")


# ─── the room label ──────────────────────────────────────────────────

@pytest.mark.parametrize("size", ["medium", "large", None])
def test_the_room_label_is_a_pdf(client, size):
    room = _new_location(client, zone_code="LB%s" % _uniq())
    params = {"size": size} if size else {}
    r = client.get("/api/v1/locations/%d/label" % room["id"], params=params)
    assert r.status_code == 200, r.text[:300]
    assert r.headers["Content-Type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF"), r.content[:40]
    assert room["location_code"] in r.headers.get("Content-Disposition", "")
    assert (size or "medium") in r.headers.get("Content-Disposition", "")


def test_the_small_room_label_is_refused_saying_why(client):
    room = _new_location(client)
    r = client.get("/api/v1/locations/%d/label" % room["id"],
                   params={"size": "small"})
    err = assert_envelope_err(r, 400, "invalid_request")["error"]
    assert "There is no small room label" in err["message"]
    assert err["details"]["allowed_values"] == ["medium", "large"]


def test_an_unknown_size_is_refused_with_the_allowed_values(client):
    room = _new_location(client)
    r = client.get("/api/v1/locations/%d/label" % room["id"],
                   params={"size": "sheet"})
    err = assert_envelope_err(r, 400, "invalid_request")["error"]
    assert err["details"]["allowed_values"] == ["medium", "large"]


def test_the_label_of_a_location_that_does_not_exist_is_a_404(client):
    assert_envelope_err(client.get("/api/v1/locations/999999999/label"),
                        404, "not_found")


def test_the_label_needs_a_token(unauthed_client, client):
    room = _new_location(client)
    r = unauthed_client.get("/api/v1/locations/%d/label" % room["id"])
    assert r.status_code == 401
