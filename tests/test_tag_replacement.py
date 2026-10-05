"""Reprinting a faded tag — handoff 38, over HTTP.

WHAT THIS FILE IS FOR
---------------------
NRS described the case on 30 September: *an auditor walking around notices
an air conditioner's tag is no longer very clear, and can reprint a tag for
that asset.* The model had done this for as long as the barcode station has
existed — `active → pending → scrapped`, a new number minted, the two
records naming each other — and nothing a person at a scanner could reach
drove it. These are the five routes that now do, and the properties that
stop the control being theatre:

* **A request writes nothing but the request.** The label goes to `pending`;
  no number is minted, the old label stays on the asset, and the asset's own
  record is unchanged. Every raising test reads the label back.
* **Two people.** `approver` is WHO IS BEING ASKED and comes from the
  requester's body; `approved_by` / `rejected_by` is WHO CLICKED and comes
  from the bearer token. A body naming either is REFUSED 400 rather than
  ignored, and self-approval is refused IN THE MODEL — 403 here, with
  `is_own_request` so a screen can tell *you asked for this one* from *not
  yours to decide*.
* **The reason is recorded.** `action_request_replacement` used to write
  state and requester only; *"why was this tag replaced"* had to be typed on
  the Odoo form. The route takes it and the record carries it.
* **The old number never comes back.** `_generate_tag` checks every label on
  the tenant, scrapped ones included. Proved by doing a replacement and
  reading the new number, and by the old number no longer resolving on the
  lookup routes.
* **A decision is taken once.** A second approve is a 409 naming who decided.

WHO IS WHO IN THIS FILE
-----------------------
**The second person RAISES; the suite's credential APPROVES** — the same way
round as `tests/conftest.py::second_person`, and for a related reason. A tag
replacement writes no append-only row (the concern that fixture's docstring
is about does not apply here), but an approval MINTS A TAG — a new
`nrs.asset.tag.label`, which carries `is_test_fixture` — and that row is
created under the APPROVER's credential. The suite's credential is flagged
`is_test_credential`, so with the suite approving, the only new row this
file creates says on its face that a test made it. The other way round
would leave real-looking labels on the tenant with nobody's name on them.

The cost, said rather than glossed: the REQUEST stamps (`requested_by`) on
the existing label name the second person, who is an Odoo login and not a
test credential. That is a stamp on a row the suite created, not a row of
its own, and `remove_test_residue.py` identifies the asset by its
`pytest-` name regardless.

Skips, not fails, when the tenant cannot sign in a second person: unlike a
move, a tag replacement is two-person on EVERY tenant — there is no switch —
so there is no tenant on which these could run with one.
"""
import time
import uuid

import pytest

from .conftest import (assert_envelope_err, assert_envelope_ok,
                       assert_fields_refused)

REASONS = ["damaged", "lost", "stolen", "reassign", "other"]


def _uniq(prefix):
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


# ─── the cast ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def two_people(second_person):
    """The requester (second person) and the approver (the suite).

    `second_person` only FAILS when the tenant requires approval for a
    move and nobody can be signed in; on a tenant with the move switch off
    it returns quietly with `other=None`. A tag replacement has no switch,
    so this module needs the second person either way and says so.
    """
    if second_person.other is None:
        pytest.skip(
            "a tag replacement always takes two people and this session "
            "could sign in only one. Set CADRA_SECOND_PERSON_LOGIN and "
            "CADRA_SECOND_PERSON_PASSWORD to a user who is not the suite's "
            "own credential.")
    return second_person


@pytest.fixture(scope="module")
def requester(two_people):
    """The second person's client — who ASKS."""
    return two_people.other["client"]


@pytest.fixture(scope="module")
def requester_id(two_people):
    return two_people.other["id"]


@pytest.fixture(scope="module")
def approver_id(two_people):
    """The suite's own user — who is ASKED, and who DECIDES."""
    return two_people.suite_id


def _tagged_asset(client, label):
    """A new asset of this test's own, with the tag `nrs.asset.create`
    mints, and a serial so the lookup-by-serial assertions have one."""
    serial = "PYT-TAG-" + uuid.uuid4().hex[:8].upper()
    asset = assert_envelope_ok(client.post("/api/v1/assets", json={
        "name": _uniq(f"pytest-tagrepl-{label}"),
        "category_id": 1,
        "serial_number": serial,
    }), 201)["data"]
    assert asset["tag"] and asset["tagging"]["label_id"], (
        "nrs.asset.create is supposed to mint a tag; without one there is "
        "nothing to replace")
    return asset


def _tag(client, tag_id):
    return assert_envelope_ok(client.get(f"/api/v1/tags/{tag_id}"))["data"]


def _asset(client, asset_id):
    return assert_envelope_ok(client.get(f"/api/v1/assets/{asset_id}"))["data"]


def _lookup(client, query):
    return client.get("/api/v1/barcode/lookup", params={"query": query})


def _request(who, tag_id, approver, reason="damaged", notes=None, **extra):
    body = {"reason": reason, "approver_id": approver, **extra}
    if notes is not None:
        body["notes"] = notes
    return who.post(f"/api/v1/tags/{tag_id}/request-replacement", json=body)


# ─── asking ──────────────────────────────────────────────────────────

def test_requesting_marks_the_label_pending_and_mints_nothing(
        client, requester, requester_id, approver_id, capture):
    """The request step, read back from the record.

    The reason and the notes are on the label — the thing handoff 38 §B.2
    asked for, because until now the reason could only be typed on the Odoo
    form and the API's own request would have recorded none.
    """
    asset = _tagged_asset(client, "request")
    tag_id, old_number = asset["tagging"]["label_id"], asset["tag"]

    r = _request(requester, tag_id, approver_id, reason="damaged",
                 notes="label on the AC unit has faded past reading")
    capture("tags/request_replacement", r)
    data = assert_envelope_ok(r)["data"]
    assert data["pending_approval"] is True, (
        "the first key of this response must say nothing has been "
        "replaced yet")
    tag = data["tag"]
    assert tag["id"] == tag_id
    assert tag["state"] == "pending"
    assert tag["tag_number"] == old_number, "no new number on a request"
    assert tag["replacement_reason"] == "damaged"
    assert tag["replacement_notes"] == \
        "label on the AC unit has faded past reading"
    assert tag["requested_by"]["id"] == requester_id
    assert tag["requested_at"]
    assert tag["approver"]["id"] == approver_id
    assert tag["approved_by"] is None and tag["rejected_by"] is None
    assert tag["replaced_by"] is None, "nothing minted on a request"
    assert tag["asset"]["id"] == asset["id"]
    assert tag["serial_number"] == asset["serial_number"]
    assert tag["can_decide"] is False, (
        "the requester's own view of the label says they may decide it")

    # Read back, not trusted from the response.
    again = _tag(client, tag_id)
    assert again["state"] == "pending"
    assert again["replacement_reason"] == "damaged"
    # The APPROVER's view says they may decide it.
    assert again["can_decide"] is True
    # The asset itself is untouched: the number it displays is the old one.
    assert data["asset"]["tag"] == old_number
    assert _asset(client, asset["id"])["tag"] == old_number


def test_a_pending_label_still_resolves_by_code_and_serial_but_not_by_number(
        client, requester, approver_id, capture):
    """Decision 5 of the handoff-38 contract, asserted from both sides.

    A pending tag's NUMBER no longer resolves — only `active` tags match by
    number, unchanged from before. But the asset is still there and still
    scannable by code or serial, and the lookup then carries the PENDING
    tag's block with `tagged: false`, so a screen can say *replacement
    pending* rather than *untagged* for a label that is physically on the
    asset. This is also the nearest reachable case to "an asset with no
    active tag", which `tests/test_barcode.py` names as inexpressible.
    """
    asset = _tagged_asset(client, "pending-lookup")
    tag_id, number = asset["tagging"]["label_id"], asset["tag"]
    assert_envelope_ok(_request(requester, tag_id, approver_id))

    assert_envelope_err(_lookup(client, number), 404, "not_found")

    r = _lookup(client, asset["serial_number"])
    capture("barcode/lookup_pending_tag_by_serial", r)
    data = assert_envelope_ok(r)["data"]
    assert data["asset_id"] == asset["id"]
    assert data["matched_by"] == "serial_number"
    assert data["tagged"] is False
    assert data["tag_id"] == tag_id
    assert data["tag_number"] == number
    assert data["tag_state"] == "pending"

    by_code = assert_envelope_ok(_lookup(client, asset["asset_code"]))["data"]
    assert by_code["matched_by"] == "asset_code"
    assert by_code["tagged"] is False
    assert by_code["tag_state"] == "pending"


def test_the_pending_queue_lists_it_newest_first(client, requester,
                                                 approver_id, capture):
    a = _tagged_asset(client, "queue-a")
    b = _tagged_asset(client, "queue-b")
    assert_envelope_ok(_request(requester, a["tagging"]["label_id"],
                                approver_id))
    assert_envelope_ok(_request(requester, b["tagging"]["label_id"],
                                approver_id))

    r = client.get("/api/v1/tags/pending-replacements",
                   params={"limit": 50})
    capture("tags/pending_replacements", r)
    body = assert_envelope_ok(r)
    ids = [row["id"] for row in body["data"]]
    assert b["tagging"]["label_id"] in ids and a["tagging"]["label_id"] in ids
    assert ids.index(b["tagging"]["label_id"]) < \
        ids.index(a["tagging"]["label_id"]), "newest first"
    assert all(row["state"] == "pending" for row in body["data"])
    assert body["pagination"]["total_estimate"] >= 2


def test_what_happened_to_mine_is_answerable_after_the_decision(
        client, requester, requester_id, approver_id, capture):
    """Handoff 51 §1a, the reason the sibling route exists.

    The requester's question is not "what is pending", it is "what
    happened to mine" — and a pending-only endpoint answers "nothing" the
    moment the request is decided, however many filters it grows. So:
    request, decide, then ask both routes.
    """
    asset = _tagged_asset(client, "mine-decided")
    tag_id = asset["tagging"]["label_id"]
    assert_envelope_ok(_request(requester, tag_id, approver_id))
    assert_envelope_ok(client.post(
        f"/api/v1/tags/{tag_id}/approve-replacement", json={}))

    # The pending queue now honestly answers "nothing" about it.
    pending = assert_envelope_ok(client.get(
        "/api/v1/tags/pending-replacements", params={"limit": 100}))["data"]
    assert tag_id not in [row["id"] for row in pending]

    # The record answers the requester.
    r = requester.get("/api/v1/tags/replacements",
                      params={"raised_by_me": "true", "limit": 100})
    capture("tags/replacements_raised_by_me", r)
    rows = assert_envelope_ok(r)["data"]
    mine = [row for row in rows if row["id"] == tag_id]
    assert len(mine) == 1, (
        "the decided request must still be on the requester's own list")
    row = mine[0]
    assert row["state"] == "scrapped", "approved means replaced"
    assert row["requested_by"]["id"] == requester_id
    assert row["approved_by"]["id"] == approver_id
    assert row["replaced_by"]["id"], "the successor label is on the row"
    assert row["can_decide"] is False, "nothing left to decide"
    # And every row on the requester's list is genuinely theirs.
    assert all(x["requested_by"]["id"] == requester_id for x in rows)


def test_the_replacements_record_lists_requests_not_labels(
        client, requester, approver_id, capture):
    """A label nobody has asked about is not a replacement request.

    Every asset mints a label at creation, so without the base domain this
    route would be a label list wearing a replacement route's name — one
    published name carrying two meanings, the defect class §1a names.
    """
    fresh = _tagged_asset(client, "never-asked")
    asked = _tagged_asset(client, "asked")
    assert_envelope_ok(_request(requester, asked["tagging"]["label_id"],
                                approver_id))

    r = client.get("/api/v1/tags/replacements", params={"limit": 100})
    capture("tags/replacements_base_domain", r)
    rows = assert_envelope_ok(r)["data"]
    ids = [row["id"] for row in rows]
    assert asked["tagging"]["label_id"] in ids
    assert fresh["tagging"]["label_id"] not in ids, (
        "a never-requested label leaked onto the replacements record")
    assert all(row["requested_by"] for row in rows)


def test_the_replacements_filters_are_the_approvals_filters(
        client, requester, approver_id, capture):
    """`state` (the model's own values), `waiting_on_me`, `raised_by_me`.

    `waiting_on_me` is the approver's queue — requests NAMING the caller.
    The suite's user is the nominated approver here, so its own
    `waiting_on_me` must carry the pending row, and `state=pending` must
    agree with the pending-only route about what is pending.
    """
    asset = _tagged_asset(client, "filters")
    tag_id = asset["tagging"]["label_id"]
    assert_envelope_ok(_request(requester, tag_id, approver_id))

    waiting = assert_envelope_ok(client.get(
        "/api/v1/tags/replacements",
        params={"waiting_on_me": "true", "limit": 100}))["data"]
    assert tag_id in [row["id"] for row in waiting]
    assert all(row["approver"]["id"] == approver_id for row in waiting)

    by_state = assert_envelope_ok(client.get(
        "/api/v1/tags/replacements",
        params={"state": "pending", "limit": 100}))["data"]
    assert tag_id in [row["id"] for row in by_state]
    assert all(row["state"] == "pending" for row in by_state)

    # An explicit false means "do not filter", not "filter on nothing" —
    # handoff 22's lesson, held here as it is on /approvals.
    unfiltered = assert_envelope_ok(client.get(
        "/api/v1/tags/replacements",
        params={"waiting_on_me": "false", "limit": 100}))["data"]
    assert tag_id in [row["id"] for row in unfiltered]

    r = client.get("/api/v1/tags/replacements", params={"state": "bogus"})
    capture("tags/replacements_bad_state", r)
    details = assert_envelope_err(
        r, 400, "invalid_request")["error"].get("details") or {}
    assert "allowed_values" in details, (
        "a refused filter names the values it accepts")
    assert sorted(details["allowed_values"]) == \
        sorted(["active", "pending", "scrapped"])


def test_a_rejected_request_stays_on_the_record_as_active_with_who_refused(
        client, requester, requester_id, approver_id, capture):
    """The third outcome: rejected goes back to `active`, and the row says
    who refused and why — which is how the requester finds out."""
    asset = _tagged_asset(client, "rejected-record")
    tag_id = asset["tagging"]["label_id"]
    assert_envelope_ok(_request(requester, tag_id, approver_id))
    assert_envelope_ok(client.post(
        f"/api/v1/tags/{tag_id}/reject-replacement",
        json={"reason": "The label is legible — clean it instead."}))

    r = requester.get("/api/v1/tags/replacements",
                      params={"raised_by_me": "true", "state": "active",
                              "limit": 100})
    capture("tags/replacements_rejected", r)
    rows = assert_envelope_ok(r)["data"]
    mine = [row for row in rows if row["id"] == tag_id]
    assert len(mine) == 1
    assert mine[0]["rejected_by"]["id"] == approver_id
    assert mine[0]["decision_reason"] == \
        "The label is legible — clean it instead."


def test_a_second_request_on_a_pending_label_is_refused_naming_the_first(
        client, requester, requester_id, approver_id, capture):
    asset = _tagged_asset(client, "twice")
    tag_id = asset["tagging"]["label_id"]
    assert_envelope_ok(_request(requester, tag_id, approver_id))
    before = _tag(client, tag_id)

    r = _request(requester, tag_id, approver_id, reason="lost")
    capture("tags/request_replacement_already_pending", r)
    details = assert_envelope_err(r, 409, "conflict")["error"]["details"]
    assert details["tag_id"] == tag_id
    assert details["state"] == "pending"
    assert details["requested_by"]["id"] == requester_id
    assert details["approver"]["id"] == approver_id
    assert details["replaced_by"] is None
    assert _tag(client, tag_id) == before, (
        "a refused second request changed the first")


# ─── what the body may not say ───────────────────────────────────────

def test_a_reason_outside_the_set_is_refused_with_the_set_named(
        client, requester, approver_id, capture):
    asset = _tagged_asset(client, "bad-reason")
    tag_id = asset["tagging"]["label_id"]

    for bad in ("faded", "", None):
        body = {"reason": bad, "approver_id": approver_id}
        if bad is None:
            del body["reason"]
        r = requester.post(f"/api/v1/tags/{tag_id}/request-replacement",
                           json=body)
        if bad == "faded":
            capture("tags/request_replacement_bad_reason", r)
        details = assert_envelope_err(
            r, 400, "invalid_request")["error"]["details"]
        assert details["allowed_values"] == REASONS, details
        assert details["field"] == "reason"
    assert _tag(client, tag_id)["state"] == "active", (
        "a refused reason moved the label anyway")


def test_a_stray_body_key_is_refused_and_nothing_written(
        client, requester, approver_id):
    """Handoff 31's contract: a key the route does not accept is a 400 and
    NOTHING is written — not the keys beside it either."""
    asset = _tagged_asset(client, "stray-key")
    tag_id = asset["tagging"]["label_id"]
    details = assert_fields_refused(
        _request(requester, tag_id, approver_id, colour="red"), "colour")
    assert details["writable"] == ["approver_id", "notes", "reason"]
    tag = _tag(client, tag_id)
    assert tag["state"] == "active"
    assert tag["replacement_reason"] is None
    assert tag["requested_by"] is None


@pytest.mark.parametrize("claim", ["requested_by", "approved_by", "state",
                                   "rejected_by", "replaced_by_id"])
def test_a_body_naming_who_asked_or_decided_is_refused(
        client, requester, approver_id, claim):
    """Who asked and who decided are taken from the token and the act. A
    client able to write them could stamp any user as the authority."""
    asset = _tagged_asset(client, f"claim-{claim}")
    tag_id = asset["tagging"]["label_id"]
    details = assert_fields_refused(
        _request(requester, tag_id, approver_id, **{claim: 2}), claim)
    assert details["writable"] == ["approver_id", "notes", "reason"]
    assert _tag(client, tag_id)["state"] == "active"


def test_the_approver_must_be_named_and_cannot_be_yourself(
        client, requester, requester_id, approver_id, capture):
    """The same two refusals `/assets/<id>/move` gives, because it is the
    same helper: no `approver_id` lists who may be asked; naming yourself
    is refused before the model sees it."""
    asset = _tagged_asset(client, "approver")
    tag_id = asset["tagging"]["label_id"]

    r = requester.post(f"/api/v1/tags/{tag_id}/request-replacement",
                       json={"reason": "damaged"})
    capture("tags/request_replacement_no_approver", r)
    details = assert_envelope_err(
        r, 400, "invalid_request")["error"]["details"]
    assert details["approval_required"] is True
    assert isinstance(details["approvers"], list)
    assert requester_id not in [u["id"] for u in details["approvers"]], (
        "the list of who may be asked offers the caller themself")

    r = _request(requester, tag_id, requester_id)
    assert_envelope_err(r, 400, "invalid_request")
    assert _tag(client, tag_id)["state"] == "active"


def test_an_unknown_label_is_a_404_on_every_route(client, requester,
                                                  approver_id):
    missing = 2_000_000_000
    assert_envelope_err(client.get(f"/api/v1/tags/{missing}"), 404,
                        "not_found")
    assert_envelope_err(_request(requester, missing, approver_id), 404,
                        "not_found")
    assert_envelope_err(client.post(
        f"/api/v1/tags/{missing}/approve-replacement", json={}), 404,
        "not_found")
    assert_envelope_err(client.post(
        f"/api/v1/tags/{missing}/reject-replacement",
        json={"reason": "x"}), 404, "not_found")


# ─── deciding ────────────────────────────────────────────────────────

def test_self_approval_is_refused_with_the_reason_named(
        client, requester, requester_id, approver_id, capture):
    """403 and `is_own_request`, and the label stays pending.

    The flag matters as much as the status: *you asked for this one* and
    *not yours to decide* are different messages to put on a screen.
    """
    asset = _tagged_asset(client, "self-approve")
    tag_id = asset["tagging"]["label_id"]
    assert_envelope_ok(_request(requester, tag_id, approver_id))

    r = requester.post(f"/api/v1/tags/{tag_id}/approve-replacement", json={})
    capture("tags/self_approval_refused", r)
    details = assert_envelope_err(r, 403, "forbidden")["error"]["details"]
    assert details["is_own_request"] is True
    assert details["tag_id"] == tag_id
    assert details["requested_by"]["id"] == requester_id

    r = requester.post(f"/api/v1/tags/{tag_id}/reject-replacement",
                       json={"reason": "changed my mind"})
    assert assert_envelope_err(
        r, 403, "forbidden")["error"]["details"]["is_own_request"] is True

    tag = _tag(client, tag_id)
    assert tag["state"] == "pending"
    assert tag["approved_by"] is None and tag["rejected_by"] is None
    assert tag["replaced_by"] is None


def test_approving_scraps_the_label_mints_the_next_and_keeps_the_chain(
        client, requester, requester_id, approver_id, capture):
    """The whole of §B, read off the records.

    Old label scrapped, new number minted, `replaces` / `replaced_by`
    naming each other, the reason recorded, who asked and who agreed two
    different people — and the old number not reissued, which is proved
    here by comparison and below by the lookup routes.
    """
    asset = _tagged_asset(client, "approve")
    tag_id, old_number = asset["tagging"]["label_id"], asset["tag"]
    assert_envelope_ok(_request(requester, tag_id, approver_id,
                                reason="damaged",
                                notes="faded past reading"))

    r = client.post(f"/api/v1/tags/{tag_id}/approve-replacement",
                    json={"reason": "sighted it — unreadable"})
    capture("tags/approve_replacement", r)
    data = assert_envelope_ok(r)["data"]
    old, new = data["tag"], data["new_tag"]

    # The old label.
    assert old["id"] == tag_id
    assert old["state"] == "scrapped"
    assert old["label_state"] == "scrapped"
    assert old["scrapped_date"]
    assert old["tag_number"] == old_number
    assert old["replacement_reason"] == "damaged"
    assert old["replacement_notes"] == "faded past reading"
    assert old["requested_by"]["id"] == requester_id
    assert old["approved_by"]["id"] == approver_id
    assert old["approved_at"]
    assert old["decision_reason"] == "sighted it — unreadable"
    assert old["approved_by"]["id"] != old["requested_by"]["id"], (
        "the same user is recorded as having asked and as having agreed")
    assert old["can_decide"] is False

    # The new label, and the chain.
    assert new["id"] != old["id"]
    assert new["state"] == "active"
    assert new["asset"]["id"] == asset["id"]
    assert new["tag_number"] != old_number, (
        "the old number was reissued — the replacement history is now "
        "ambiguous between two physical labels")
    assert old["replaced_by"] == {"id": new["id"],
                                  "tag_number": new["tag_number"]}
    assert new["replaces"] == {"id": old["id"], "tag_number": old_number}
    assert new["replaced_by"] is None

    # The asset now displays the new number, in the response and on a read.
    assert data["asset"]["tag"] == new["tag_number"]
    after = _asset(client, asset["id"])
    assert after["tag"] == new["tag_number"]
    assert after["tagging"]["label_id"] == new["id"]

    # The lookup routes: the old number is gone, the new one resolves.
    assert_envelope_err(_lookup(client, old_number), 404, "not_found")
    hit = assert_envelope_ok(_lookup(client, new["tag_number"]))["data"]
    assert hit["asset_id"] == asset["id"]
    assert hit["matched_by"] == "tag_number"
    assert hit["tag_id"] == new["id"]
    assert hit["tagged"] is True

    # Read back from the records, not trusted from the response.
    assert _tag(client, tag_id)["state"] == "scrapped"
    assert _tag(client, new["id"])["replaces"]["id"] == tag_id


def test_a_decision_is_taken_once(client, requester, approver_id, capture):
    asset = _tagged_asset(client, "decide-once")
    tag_id = asset["tagging"]["label_id"]
    assert_envelope_ok(_request(requester, tag_id, approver_id))
    first = assert_envelope_ok(client.post(
        f"/api/v1/tags/{tag_id}/approve-replacement", json={}))["data"]

    r = client.post(f"/api/v1/tags/{tag_id}/approve-replacement", json={})
    capture("tags/approve_replacement_twice", r)
    details = assert_envelope_err(r, 409, "conflict")["error"]["details"]
    assert details["tag_id"] == tag_id
    assert details["state"] == "scrapped"
    assert details["decided_by"]["id"] == approver_id
    assert details["decided_at"]
    # And a request against the scrapped label names what replaced it.
    details = assert_envelope_err(
        _request(requester, tag_id, approver_id), 409,
        "conflict")["error"]["details"]
    assert details["state"] == "scrapped"
    assert details["replaced_by"]["id"] == first["new_tag"]["id"]


def test_rejecting_needs_a_reason_and_puts_the_label_back(
        client, requester, approver_id, capture):
    """The reason is REQUIRED, the refusal-for-want-of-one writes nothing,
    and a rejected label is `active` again: its number resolves, and it
    can be asked about afresh — with the earlier decision cleared."""
    asset = _tagged_asset(client, "reject")
    tag_id, number = asset["tagging"]["label_id"], asset["tag"]
    assert_envelope_ok(_request(requester, tag_id, approver_id))
    path = f"/api/v1/tags/{tag_id}/reject-replacement"

    for empty in ({}, {"reason": ""}, {"reason": "   "}):
        assert_envelope_err(client.post(path, json=empty), 400,
                            "invalid_request")
        assert _tag(client, tag_id)["state"] == "pending", (
            "a rejection refused for want of a reason decided anyway")

    r = client.post(path, json={"reason": "clean it rather than replace it"})
    capture("tags/reject_replacement", r)
    data = assert_envelope_ok(r)["data"]
    tag = data["tag"]
    assert tag["state"] == "active"
    assert tag["rejected_by"]["id"] == approver_id
    assert tag["rejected_at"]
    assert tag["decision_reason"] == "clean it rather than replace it"
    assert tag["approved_by"] is None
    assert tag["replaced_by"] is None
    assert data["asset"]["tag"] == number

    # Active again: resolves by number, and a fresh request is accepted
    # with the old decision cleared.
    assert assert_envelope_ok(_lookup(client, number))["data"]["tag_id"] \
        == tag_id
    again = assert_envelope_ok(_request(requester, tag_id, approver_id,
                                        reason="lost"))["data"]["tag"]
    assert again["state"] == "pending"
    assert again["replacement_reason"] == "lost"
    assert again["rejected_by"] is None and again["decision_reason"] is None


def test_the_decision_body_may_only_carry_a_reason(client, requester,
                                                   approver_id):
    asset = _tagged_asset(client, "decision-body")
    tag_id = asset["tagging"]["label_id"]
    assert_envelope_ok(_request(requester, tag_id, approver_id))
    before = _tag(client, tag_id)

    for claim in ("approved_by", "state", "requested_by"):
        details = assert_fields_refused(client.post(
            f"/api/v1/tags/{tag_id}/approve-replacement",
            json={claim: 2}), claim)
        assert details["writable"] == ["reason"]
    details = assert_fields_refused(client.post(
        f"/api/v1/tags/{tag_id}/reject-replacement",
        json={"reason": "x", "notes": "y"}), "notes")
    assert details["writable"] == ["reason"]
    assert _tag(client, tag_id) == before


def test_replaying_an_approval_under_the_same_key_mints_once(
        client, requester, approver_id):
    """Idempotency is load-bearing: a retry after a timeout must not scrap
    a second label or mint a second number."""
    asset = _tagged_asset(client, "idempotent")
    tag_id = asset["tagging"]["label_id"]
    assert_envelope_ok(_request(requester, tag_id, approver_id))
    path = f"/api/v1/tags/{tag_id}/approve-replacement"
    headers = {"X-Idempotency-Key": _uniq("pytest-tagrepl-idem")}

    first = assert_envelope_ok(client.post(path, json={"reason": "first"},
                                           headers=headers))
    second = assert_envelope_ok(client.post(path, json={"reason": "second"},
                                            headers=headers))
    assert second["meta"]["request_id"] == first["meta"]["request_id"], (
        "the replay was processed rather than served from the cache")
    assert second["data"] == first["data"]
    assert first["data"]["tag"]["decision_reason"] == "first"
    new_id = first["data"]["new_tag"]["id"]
    assert _tag(client, tag_id)["replaced_by"]["id"] == new_id
    assert _asset(client, asset["id"])["tagging"]["label_id"] == new_id
