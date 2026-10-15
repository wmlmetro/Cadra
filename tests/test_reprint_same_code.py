"""A replacement keeps its number — handoff 61 §1, ruling R3, over HTTP.

WHAT CHANGED, AND WHY THIS IS NOT A REGRESSION
----------------------------------------------
Until handoff 61 an approved tag replacement scrapped the label and minted
a NEW number. On a unit that came through the receipt gates — whose label
carries its ASSET CODE (ruling 4.3) — the gated generator minted a
location-prefix number instead, so the replacement broke the ruling
(findings §5.6; on `test19`, 24 of the 172 replacements made before 61).
Ruling R3: *the number on the asset doesn't change because a sticker
faded.* The approval now VOIDS THE PRINT and REPRINTS the label under the
same number. One label record is one physical print, so the two prints are
two records with one `tag_number`, told apart by `reprint_count`; the voided
one carries `voided_at` and `void_reason`. This is announced as a BEHAVIOUR
CHANGE in the CHANGELOG.

WHAT A SCANNER CANNOT TELL, AND WHAT THE SERVER CAN
---------------------------------------------------
The voided print and its reprint encode the same value. The server refuses a
reprint's affix only while the reprint has not been PRINTED — then the label
in hand can only be the voided one — and says so in a sentence naming the
void, its date and its reason. Once a print of the reprint is recorded
(`POST /api/v1/tags/printed`, which the app's station calls, or Odoo's PDF
funnel), the same number confirms.

WHO IS WHO: as `tests/test_tag_replacement.py` — the second person RAISES,
the suite's credential APPROVES (and prints, and affixes), so the rows this
file creates are labelled as a test's.

Both gates cases are driven in ONE run, whichever way the tenant's switch is
set: `receipt_switch` sets it for the test and puts the tenant's own value
back. With the gates on, the unit is walked to the register by the demo
personas (`tests/gates.py`), exactly as a real unit gets there.
"""
import time
import uuid

import pytest

from . import gates
from .conftest import (assert_envelope_err, assert_envelope_ok,
                       assert_fields_refused)


def _uniq(prefix):
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


# ─── the cast (the same two people as test_tag_replacement.py) ───────

@pytest.fixture(scope="module")
def two_people(second_person):
    if second_person.other is None:
        pytest.skip(
            "a tag replacement always takes two people and this session "
            "could sign in only one. Set CADRA_SECOND_PERSON_LOGIN and "
            "CADRA_SECOND_PERSON_PASSWORD to a user who is not the suite's "
            "own credential.")
    return second_person


@pytest.fixture(scope="module")
def requester(two_people):
    return two_people.other["client"]


@pytest.fixture(scope="module")
def requester_id(two_people):
    return two_people.other["id"]


@pytest.fixture(scope="module")
def approver_id(two_people):
    return two_people.suite_id


@pytest.fixture
def gates_off(receipt_switch):
    receipt_switch(False)


@pytest.fixture
def gates_on(receipt_switch):
    receipt_switch(True)


# ─── helpers ─────────────────────────────────────────────────────────

def _registered(client, label):
    """An asset of this test's own, ON THE REGISTER, with its first print."""
    asset = gates.new_registered_asset(
        client, name=_uniq(f"pytest-reprint-{label}"), category_id=1,
        serial_number="PYT-RPR-" + uuid.uuid4().hex[:8].upper())
    assert asset["tag"] and asset["tagging"]["label_id"], (
        "the asset has no label to replace")
    return asset


def _tag(client, tag_id):
    return assert_envelope_ok(client.get(f"/api/v1/tags/{tag_id}"))["data"]


def _asset(client, asset_id):
    return assert_envelope_ok(client.get(f"/api/v1/assets/{asset_id}"))["data"]


def _replace(client, requester, approver_id, asset, reason="damaged"):
    """Request (second person) and approve (suite). Returns the response."""
    tag_id = asset["tagging"]["label_id"]
    assert_envelope_ok(requester.post(
        f"/api/v1/tags/{tag_id}/request-replacement",
        json={"reason": reason, "approver_id": approver_id,
              "notes": "pytest — label faded past reading"}))
    return assert_envelope_ok(client.post(
        f"/api/v1/tags/{tag_id}/approve-replacement",
        json={"reason": "sighted"}))["data"]


def _affix(client, asset, number):
    body = {"tag_number": number}
    if asset.get("identification_mode") == "tag_id":
        body["attributes_confirmed"] = True
    return client.post(f"/api/v1/assets/{asset['id']}/tag-affixed", json=body)


def _history(client, asset_id):
    return assert_envelope_ok(client.get(
        f"/api/v1/assets/{asset_id}/history"))["data"]["events"]


def _assert_reprinted_under(data, number, asset):
    """The shape every replacement now has, whatever the number is."""
    old, new = data["tag"], data["new_tag"]
    assert old["tag_number"] == new["tag_number"] == number, (
        "the replacement changed the number: %s → %s"
        % (old["tag_number"], new["tag_number"]))
    assert old["state"] == "scrapped" and old["label_state"] == "scrapped"
    assert old["reprint_count"] == 0 and new["reprint_count"] == 1
    assert old["voided_at"] and old["void_reason"] == "damaged"
    assert new["state"] == "active" and new["label_state"] == "issued"
    assert new["voided_at"] is None and new["void_reason"] is None
    assert new["replaces"] == {"id": old["id"], "tag_number": number,
                               "reprint_count": 0}
    assert old["replaced_by"] == {"id": new["id"], "tag_number": number,
                                  "reprint_count": 1}
    assert new["asset"]["id"] == asset["id"]
    return old, new


# ─── the number stays, gates off and gates on ────────────────────────

def test_a_location_prefix_label_is_reprinted_under_its_own_number(
        client, requester, approver_id, gates_off):
    """Gates OFF: the label minted at creation carries a location-prefix
    number, which is NOT the asset code. Its replacement keeps THAT number —
    the rule is the same whatever the number is."""
    asset = _registered(client, "prefix")
    number = asset["tag"]
    assert number != asset["asset_code"], (
        "with the gates off the label should be the location-prefix number, "
        "not the asset code: %s" % number)

    data = _replace(client, requester, approver_id, asset)
    old, new = _assert_reprinted_under(data, number, asset)

    after = _asset(client, asset["id"])
    assert after["tag"] == number
    assert after["asset_code"] == asset["asset_code"]
    assert after["tagging"]["label_id"] == new["id"]
    hit = assert_envelope_ok(client.get(
        "/api/v1/barcode/lookup", params={"query": number}))["data"]
    assert hit["matched_by"] == "tag_number" and hit["tag_id"] == new["id"]


def test_a_gated_units_label_is_reprinted_under_its_asset_code(
        client, requester, approver_id, gates_on):
    """Gates ON: the label is the ASSET CODE (ruling 4.3). Until handoff 61
    its replacement was a location-prefix number (findings §5.6) — the
    defect this test exists to keep gone."""
    asset = _registered(client, "gated")
    assert asset["register_state"] == "registered"
    code = asset["asset_code"]
    assert asset["tag"] == code, (
        "a gated unit's label must carry its asset code: %s vs %s"
        % (asset["tag"], code))

    data = _replace(client, requester, approver_id, asset)
    old, new = _assert_reprinted_under(data, code, asset)
    assert new["tag_number"] == code, (
        "the gated replacement was not the asset code — findings §5.6")

    after = _asset(client, asset["id"])
    assert after["tag"] == code and after["asset_code"] == code
    assert after["register_state"] == "registered"
    assert after["tagging"]["label_id"] == new["id"]


def test_a_second_replacement_is_reprint_two_of_the_same_number(
        client, requester, approver_id, gates_off):
    asset = _registered(client, "twice")
    number = asset["tag"]
    first = _replace(client, requester, approver_id, asset)
    asset = _asset(client, asset["id"])
    second = _replace(client, requester, approver_id, asset, reason="lost")
    assert second["tag"]["id"] == first["new_tag"]["id"]
    assert second["tag"]["reprint_count"] == 1
    assert second["tag"]["void_reason"] == "lost"
    assert second["new_tag"]["tag_number"] == number
    assert second["new_tag"]["reprint_count"] == 2
    assert second["new_tag"]["replaces"]["reprint_count"] == 1
    # Three prints of one number, exactly one of them in service.
    prints = [first["tag"]["id"], first["new_tag"]["id"],
              second["new_tag"]["id"]]
    states = [_tag(client, i)["state"] for i in prints]
    assert states == ["scrapped", "scrapped", "active"], states


def test_the_history_says_which_print_and_why_the_last_was_voided(
        client, requester, approver_id, gates_off):
    """Both prints are in the asset's history as their own records, and the
    voided one says when and why. Depends on `asset_history.py` publishing
    `reprint_count` and the void on the tag events (handoff 61)."""
    asset = _registered(client, "history")
    data = _replace(client, requester, approver_id, asset)
    old, new = data["tag"], data["new_tag"]
    events = _history(client, asset["id"])
    mine = {(e["type"], e["record"]["id"]): e for e in events
            if e["record"] and e["record"]["model"] == "nrs.asset.tag.label"}
    issued_new = mine[("tag_issued", new["id"])]
    scrapped_old = mine[("tag_scrapped", old["id"])]
    assert issued_new["detail"]["reprint_count"] == 1
    assert scrapped_old["detail"]["reprint_count"] == 0
    assert scrapped_old["detail"]["void_reason"] == "damaged"
    assert "reprint 1" in issued_new["summary"], issued_new["summary"]


# ─── the affix check ─────────────────────────────────────────────────

def test_the_voided_print_scanned_before_the_reprint_is_printed_is_refused(
        client, requester, approver_id, gates_off, capture):
    """The two prints encode the same value, so a scanner cannot tell them
    apart. While the reprint has not been printed the label in hand can
    only be the voided one: refused, naming the void, its date and reason,
    and recorded as an `affix_refused` event with reason `voided_print`."""
    asset = _registered(client, "voided-scan")
    data = _replace(client, requester, approver_id, asset)
    old, new = data["tag"], data["new_tag"]
    number = new["tag_number"]

    r = _affix(client, asset, number)
    capture("assets/tag_affixed_voided_print", r)
    message = assert_envelope_err(r, 400, "validation_failed")["error"]["message"]
    voided_on = old["voided_at"][:10]
    expected = (
        "Tag %s is reprint 1 and has not been printed yet, so the label "
        "being scanned can only be the original print, voided on " % number)
    assert expected in message, message
    assert "(Damaged / Unreadable). Print reprint 1, then confirm it." \
        in message, message
    # The Lagos day of the void — one day either side of the UTC date.
    assert any(d in message for d in _days_around(voided_on)), message

    after = _asset(client, asset["id"])
    assert after["tagging"]["label_id"] == new["id"]
    assert after["tagging"]["label_state"] == "issued"
    assert after["tagging"]["is_tagged"] is False
    refusals = [e for e in _history(client, asset["id"])
                if e["type"] == "affix_refused"]
    assert refusals, "the refused scan left no record"
    assert refusals[0]["detail"]["reason"] == "voided_print"
    assert refusals[0]["detail"]["scanned"] == number


def test_a_printed_reprint_is_affixed_like_a_first_print(
        client, requester, approver_id, gates_off, capture):
    asset = _registered(client, "printed")
    data = _replace(client, requester, approver_id, asset)
    new = data["new_tag"]

    r = client.post("/api/v1/tags/printed", json={"tag_ids": [new["id"]]})
    capture("tags/printed", r)
    body = assert_envelope_ok(r)["data"]
    assert [t["id"] for t in body["recorded"]] == [new["id"]]
    assert body["recorded"][0]["label_state"] == "printed"
    assert body["not_recorded"] == []

    r = _affix(client, asset, new["tag_number"])
    tagging = assert_envelope_ok(r)["data"]["tagging"]
    assert tagging["label_id"] == new["id"]
    assert tagging["label_state"] == "affixed"
    assert tagging["is_tagged"] is True
    assert tagging["printed_at"], "the print is still on the record"


def test_a_first_print_is_affixed_without_a_recorded_print_as_before(
        client, gates_off):
    """The voided-print check is about reprints only: a first print has no
    earlier print it could be confused with, and 3,068 of the 3,069 labels
    ever affixed on the local tenants went `issued → affixed` with no print
    on record. Unchanged."""
    asset = _registered(client, "first-print")
    assert asset["tagging"]["label_state"] == "issued"
    assert_envelope_ok(_affix(client, asset, asset["tag"]))


# ─── recording a print ───────────────────────────────────────────────

def test_recording_a_print_records_only_the_label_in_service(
        client, requester, approver_id, gates_off):
    asset = _registered(client, "print-which")
    data = _replace(client, requester, approver_id, asset)
    old, new = data["tag"], data["new_tag"]
    body = assert_envelope_ok(client.post(
        "/api/v1/tags/printed",
        json={"tag_ids": [old["id"], new["id"], new["id"]]}))["data"]
    assert [t["id"] for t in body["recorded"]] == [new["id"]], (
        "a duplicate id is one label")
    assert len(body["not_recorded"]) == 1
    refused = body["not_recorded"][0]
    assert refused["id"] == old["id"]
    assert "not the label in service" in refused["reason"]
    assert _tag(client, old["id"])["label_state"] == "scrapped"


def test_recording_a_print_refuses_before_writing_anything(
        client, requester, approver_id, gates_off):
    asset = _registered(client, "print-refused")
    label_id = asset["tagging"]["label_id"]

    details = assert_fields_refused(client.post(
        "/api/v1/tags/printed",
        json={"tag_ids": [label_id], "printed_by": 2}), "printed_by")
    assert details["writable"] == ["tag_ids"]
    for bad in ([], "1", [True], [label_id, "x"], None):
        assert_envelope_err(client.post(
            "/api/v1/tags/printed", json={"tag_ids": bad}), 400,
            "invalid_request")
    r = client.post("/api/v1/tags/printed",
                    json={"tag_ids": [label_id, 2_000_000_000]})
    details = assert_envelope_err(r, 404, "not_found")["error"]["details"]
    assert details["missing"] == [2_000_000_000]
    assert _tag(client, label_id)["label_state"] == "issued", (
        "a refused call recorded a print anyway")


# ─── the approver rule, unchanged since handoff 38 ───────────────────

def test_the_requester_still_cannot_approve_and_nothing_is_reprinted(
        client, requester, requester_id, approver_id, gates_off):
    asset = _registered(client, "self-approve")
    tag_id = asset["tagging"]["label_id"]
    assert_envelope_ok(requester.post(
        f"/api/v1/tags/{tag_id}/request-replacement",
        json={"reason": "damaged", "approver_id": approver_id}))
    r = requester.post(f"/api/v1/tags/{tag_id}/approve-replacement", json={})
    details = assert_envelope_err(r, 403, "forbidden")["error"]["details"]
    assert details["is_own_request"] is True
    assert details["requested_by"]["id"] == requester_id
    tag = _tag(client, tag_id)
    assert tag["state"] == "pending" and tag["replaced_by"] is None
    assert tag["voided_at"] is None and tag["reprint_count"] == 0


def test_the_print_fields_cannot_be_claimed_in_a_body(
        client, requester, approver_id, gates_off):
    asset = _registered(client, "claim")
    tag_id = asset["tagging"]["label_id"]
    for claim in ("reprint_count", "void_reason", "voided_at"):
        assert_fields_refused(requester.post(
            f"/api/v1/tags/{tag_id}/request-replacement",
            json={"reason": "damaged", "approver_id": approver_id,
                  claim: 3}), claim)
    assert _tag(client, tag_id)["state"] == "active"


def test_the_print_fields_are_published(client):
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200, "openapi.json did not answer"
    spec = r.json()
    op = spec["paths"]["/api/v1/tags/{id}"]["get"]
    schema = op["responses"]["200"]["content"]["application/json"]["schema"]
    props = _find_properties(schema)
    for key in ("reprint_count", "voided_at", "void_reason"):
        assert key in props, f"{key} is not in the published tag schema"
    assert "/api/v1/tags/printed" in spec["paths"]
    printed = spec["paths"]["/api/v1/tags/printed"]["post"]
    assert printed["x-cadra-scopes"] == ["tagging:write"]


def _find_properties(schema):
    """The tag's own properties, wherever the envelope nests them."""
    stack = [schema]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        props = node.get("properties") or {}
        if "tag_number" in props and "label_state" in props:
            return props
        stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
        for v in node.values():
            if isinstance(v, list):
                stack.extend(x for x in v if isinstance(x, dict))
    return {}


def _days_around(iso_day):
    """The UTC date and the day after (Lagos is UTC+1)."""
    import datetime
    d = datetime.date.fromisoformat(iso_day)
    return [d.isoformat(), (d + datetime.timedelta(days=1)).isoformat()]
