"""What has happened to an asset, recorded so that nobody can alter it — over
the API. Handoff 30.

Three things an auditor asks and one overwritten column could not answer:
*every time this asset was checked, and by whom*; *why is it missing*; and
*who changed the GRN, the purchase order or the SAP number*. Each is now an
`nrs.asset.event`, append-only, written underneath every writer in
`nrs.asset.write`. With it came a rule in the same place — **disposed is
terminal** — and two routes that exist to carry what a PATCH has nowhere to
put: `POST /assets/<id>/mark-missing` (a reason) and `POST /assets/<id>/condemn`
(a reason, and a disposal date taken off the server's clock rather than a
browser's).

Handoff 31 added the third such route, `POST /assets/<id>/mark-found` —
*where it turned up* is as much an audit fact as *why it went* — and moved the
disposal stamp underneath every writer, so a bare `PATCH {"state":
"disposed"}` is dated and decommissioned exactly as `/condemn` is. It also
ruled that a disposed asset can still be verified. All three are held here.

Handoff 32 §C closed the two holes report 31 left open in that stamp, and
both are about the same word: WHEN. A disposal's date cannot be taken off
its record — `PATCH {"disposal_date": null}` was the one remaining way to
raise the disposal report's `no_disposal_date` finding against a disposal
made this week — and a date that was already sitting on a live asset is not
a date the caller sent with the disposal, so it no longer survives one.

The model's own guarantees — that an event cannot be edited, deleted or
hand-written, and what each type may carry — are asserted in the registry, in
`myservice_asset_register/tests/test_asset_event.py`, where the ORM can be
called directly. What is asserted HERE is what only a real request can show:
that the routes publish the envelope and refuse before they write; that a
refusal raised in the MODEL comes back as a 400 and leaves nothing behind —
a transfer document included, which is the defect handoff 28 shipped on
`/move`; that the history lists each act ONCE, from the record nobody can
alter rather than from the message-log line of the same act; and that a
replayed request writes no second event.

**Every asset here is this module's own.** The record is append-only and
`ondelete='restrict'`, so nothing below can be cleaned up and none of it is:
that is the record working. `test_an_event_this_suite_wrote_says_so` is what
makes that acceptable.

`sap_asset_number` is the third recorded reference and is NOT exercised here:
it is deliberately absent from `_WRITABLE_FIELDS`, so no request this suite
can make changes it. It is held in the registry.
"""
import datetime
import time
import uuid

import pytest

from .conftest import (assert_envelope_err, assert_envelope_ok,
                       assert_fields_refused, ids_matching)

_EVENT_RECORD = "nrs.asset.event"

# The six published event types an `nrs.asset.event` can appear as, in the
# order `fidelity.events` lists them. `reference_changed` is the STORED type;
# it is published as `provenance_changed`, the type a change to a GRN
# reference has carried since handoff 28 — renaming a published type would
# have been a breaking change for a reader who already filters on it.
# `warranty_changed` is handoff 34's, stored and published under one name;
# `affix_refused` is handoff 51's — the one type that records a write the
# register REFUSED, written beside the check on its own cursor so the 400's
# rollback cannot unwind it.
# `gate_fired` is handoff 57's — a receipt gate (scaffolding, replaced by 58).
_RECORDED_TYPES = ["verified", "verification_date_set", "status_changed",
                   "provenance_changed", "warranty_changed", "affix_refused",
                   "gate_fired"]

_HIERARCHY_FIELDS = ("building_id", "floor_id", "room_id")


# ─── helpers ─────────────────────────────────────────────────────────

def _new_asset(client, test_location, name, **extra):
    """An asset of this test's own, so its history is exactly what we did."""
    body = {"name": name, "category_id": 1,
            "location_id": test_location["id"]}
    body.update(extra)
    r = client.post("/api/v1/assets", json=body)
    return assert_envelope_ok(r, expected_status=201)["data"]


def _asset(client, asset_id, **params):
    return assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset_id}", params=params))["data"]


def _history(client, asset_id, **params):
    return assert_envelope_ok(client.get(
        f"/api/v1/assets/{asset_id}/history", params=params))["data"]


def _events(history, etype):
    return [e for e in history["events"] if e["type"] == etype]


def _recorded(history):
    """Every event in the history that rests on an `nrs.asset.event`."""
    return [e for e in history["events"]
            if e["record"]["model"] == _EVENT_RECORD]


def _mark_missing(client, asset_id, reason, **kw):
    return client.post(f"/api/v1/assets/{asset_id}/mark-missing",
                       json={"reason": reason}, **kw)


def _mark_found(client, asset_id, reason, **kw):
    return client.post(f"/api/v1/assets/{asset_id}/mark-found",
                       json={"reason": reason}, **kw)


def _condemn(client, asset_id, reason, **kw):
    return client.post(f"/api/v1/assets/{asset_id}/condemn",
                       json={"reason": reason}, **kw)


def _condemned(client, test_location, name, **extra):
    """A disposed asset, disposed of the way the app now does it."""
    asset = _new_asset(client, test_location, name, **extra)
    r = _condemn(client, asset["id"], "test_asset_events_api — fixture")
    return assert_envelope_ok(r)["data"]["asset"]


def _lagos_today():
    """Today's date IN LAGOS — UTC+1, fixed; Nigeria keeps no summer time."""
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=1)).date()


def _an_employee(client):
    r = client.get("/api/v1/identity/employees", params={"limit": 1})
    rows = (r.json().get("data") or []) if r.status_code == 200 else []
    return rows[0]["id"] if rows else None


@pytest.fixture(scope="module")
def me(client):
    """Who this suite's credential acts as, and what it holds.

    Handoff 08: an API client acts as its own `res.users`, so the ACTOR of an
    event written by this suite is this user and nobody else — not
    `Administrator`, and not blank.
    """
    data = assert_envelope_ok(client.get("/api/v1/auth/whoami"))["data"]
    scopes = data.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    return {"id": data["id"], "scopes": set(scopes)}


def _holds(me, scope):
    """The question `require_jwt` asks: `admin` and `*` grant everything."""
    return bool({scope, "admin", "*"} & me["scopes"])


def _status_snapshot(client, asset_id):
    """Everything a refused request could have disturbed, in one comparable
    value: the asset's own fields, its transfer documents, its chain of
    custody, and the id of every line in its history."""
    asset = _asset(client, asset_id, include="transfers,custody")
    history = _history(client, asset_id, sort="oldest")
    return {
        "state": asset["state"],
        "condition": asset["condition"],
        "location": (asset["current_location"] or {}).get("id"),
        "custodian": (asset["current_custodian"] or {}).get("id"),
        "notes": asset["notes"],
        "disposal": asset["disposal"],
        "transfers": [t["id"] for t in asset["transfers"]],
        "custody": [c["id"] for c in asset["custody"]],
        "events": [e["id"] for e in history["events"]],
    }


# ─── mark missing ────────────────────────────────────────────────────

def test_marking_an_asset_missing_records_why(client, test_location, me,
                                              capture):
    """POST /api/v1/assets/<id>/mark-missing — the reason becomes evidence.

    An asset that cannot be found may be a loss, and *why* is the first
    question anybody asks. Until handoff 30 it had nowhere to live: the app's
    dialog asked for no reason because the API had nowhere to put one. It is
    NOT a field on the asset. It is on the event — what was said when it was
    marked, by whom, which nobody can tidy up afterwards.
    """
    asset = _new_asset(client, test_location, "pytest-events-missing")
    reason = "test_asset_events_api — not at desk 4F-12 during the Q3 count"
    r = _mark_missing(client, asset["id"], reason)
    capture("assets/mark_missing", r)
    data = assert_envelope_ok(r)["data"]
    assert set(data) == {"asset", "event_id"}
    assert data["asset"]["id"] == asset["id"]
    assert data["asset"]["state"] == "missing"
    assert isinstance(data["event_id"], int) and data["event_id"] > 0

    changed = _events(_history(client, asset["id"]), "status_changed")
    assert len(changed) == 1, (
        "`state` is tracked as well, so the same act also left a message-log "
        "line; the append-only record supersedes it and the change must be "
        "listed once. Listed: %s" % [e["id"] for e in changed])
    event = changed[0]
    assert event["record"] == {"model": _EVENT_RECORD, "id": data["event_id"]}
    assert event["evidence"] == "append_only"
    assert event["reconstructed"] is False
    assert event["detail"]["from"] == "active"
    assert event["detail"]["to"] == "missing"
    assert event["detail"]["reason"] == reason
    assert event["actor"] is not None and event["actor"]["id"] == me["id"], (
        "the event names %r; this request was made as user %s"
        % (event["actor"], me["id"]))
    # `test` is `api_mark_missing` relabelled by the credential — see
    # test_an_event_this_suite_wrote_says_so. Null would mean the source
    # stopped travelling.
    assert event["source"] in ("api_mark_missing", "test")


@pytest.mark.parametrize("label,body", [
    ("no body at all", None),
    ("an empty object", {}),
    ("a null reason", {"reason": None}),
    ("an empty reason", {"reason": ""}),
    ("a reason of spaces", {"reason": "   \n\t "}),
    ("a number", {"reason": 7}),
    ("a list", {"reason": ["lost"]}),
    ("a boolean", {"reason": True}),
])
def test_mark_missing_without_a_reason_is_refused_and_changes_nothing(
        client, test_location, label, body):
    """`reason` is REQUIRED, and a blank one is no reason.

    Deliberate on a new route: loosening it later breaks nobody, tightening
    it later would. And a 400 must not write — `err()` is a response, not a
    rollback (CLAUDE.md), so the refusal has to come before the act.
    """
    asset = _new_asset(client, test_location, "pytest-events-missing-400")
    url = f"/api/v1/assets/{asset['id']}/mark-missing"
    r = client.post(url) if body is None else client.post(url, json=body)
    assert_envelope_err(r, 400, "invalid_request")
    assert _asset(client, asset["id"])["state"] == "active", (
        "%s was refused with a 400 and the asset was marked missing anyway"
        % label)
    assert _events(_history(client, asset["id"]), "status_changed") == []


def test_marking_a_missing_asset_missing_again_is_a_conflict(
        client, test_location):
    """409, not a 200 for nothing.

    Asking again would append no event — the status does not change — and a
    200 would tell the caller its second reason had been recorded.
    """
    asset = _new_asset(client, test_location, "pytest-events-missing-twice")
    assert_envelope_ok(_mark_missing(client, asset["id"], "first report"))
    r = _mark_missing(client, asset["id"], "second report")
    body = assert_envelope_err(r, 409, "conflict")
    # A subset: the envelope adds `http_status` to every `details`.
    details = body["error"]["details"]
    assert (details["asset_id"], details["state"]) == (asset["id"], "missing")
    changed = _events(_history(client, asset["id"]), "status_changed")
    assert [e["detail"]["reason"] for e in changed] == ["first report"]


def test_mark_missing_on_an_unknown_asset_is_a_404(client):
    r = _mark_missing(client, 999999999, "there is no such asset")
    assert_envelope_err(r, 404, "not_found")


def test_a_replayed_mark_missing_writes_no_second_event(client, test_location):
    """`X-Idempotency-Key` — the replay is the original answer, exactly.

    Without the key a second call is a 409 (above). With it, a client whose
    first response was lost gets that response back — same `event_id`, same
    `request_id` — and the asset's record gains nothing. An append-only
    table is the worst place for a retry to leave a duplicate: nobody can
    remove it afterwards.
    """
    asset = _new_asset(client, test_location, "pytest-events-missing-replay")
    key = f"pytest-events-missing-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    first = assert_envelope_ok(_mark_missing(
        client, asset["id"], "sent once",
        headers={"X-Idempotency-Key": key}))
    second = assert_envelope_ok(_mark_missing(
        client, asset["id"], "SHOULD-BE-IGNORED",
        headers={"X-Idempotency-Key": key}))
    assert second["data"]["event_id"] == first["data"]["event_id"]
    assert second["meta"]["request_id"] == first["meta"]["request_id"], (
        "the second call was processed rather than replayed")
    changed = _events(_history(client, asset["id"]), "status_changed")
    assert [e["detail"]["reason"] for e in changed] == ["sent once"]


def test_mark_missing_needs_a_credential(client, unauthed_client,
                                         test_location):
    asset = _new_asset(client, test_location, "pytest-events-missing-401")
    r = unauthed_client.post(f"/api/v1/assets/{asset['id']}/mark-missing",
                             json={"reason": "nobody is asking"})
    assert_envelope_err(r, 401, "unauthorized")
    assert _asset(client, asset["id"])["state"] == "active"


# ─── missing is not terminal ─────────────────────────────────────────

def test_a_missing_asset_that_turns_up_goes_back_into_service(
        client, test_location):
    """Missing is NOT terminal: an asset that is found is ordinary.

    And the way back is recorded exactly as the way out was — a PATCH of
    `state` is a change of status as surely as the route is, which is the
    reason the recorder is in `nrs.asset.write` and not in a controller.
    """
    asset = _new_asset(client, test_location, "pytest-events-found-again")
    assert_envelope_ok(_mark_missing(client, asset["id"], "not at its desk"))
    r = client.patch(f"/api/v1/assets/{asset['id']}", json={"state": "active"})
    assert assert_envelope_ok(r)["data"]["state"] == "active"

    changed = _events(_history(client, asset["id"], sort="oldest"),
                      "status_changed")
    assert [(e["detail"]["from"], e["detail"]["to"]) for e in changed] == [
        ("active", "missing"), ("missing", "active")]
    found = changed[1]
    assert found["evidence"] == "append_only"
    assert found["record"]["model"] == _EVENT_RECORD
    # A PATCH has nowhere to put a sentence, and none is invented for it.
    assert found["detail"]["reason"] is None
    assert found["source"] in ("api_write", "test")
    assert found["actor"] is not None


def test_a_missing_asset_can_still_be_disposed_of(client, test_location):
    """Writing off an asset that was never found is the ordinary end of one."""
    asset = _new_asset(client, test_location, "pytest-events-missing-writeoff")
    assert_envelope_ok(_mark_missing(client, asset["id"], "not found"))
    data = assert_envelope_ok(
        _condemn(client, asset["id"], "written off after the Q3 count"))["data"]
    assert data["asset"]["state"] == "disposed"
    changed = _events(_history(client, asset["id"], sort="oldest"),
                      "status_changed")
    assert [(e["detail"]["from"], e["detail"]["to"]) for e in changed] == [
        ("active", "missing"), ("missing", "disposed")]


# ─── mark found ──────────────────────────────────────────────────────

def test_marking_an_asset_found_records_where_it_turned_up(
        client, test_location, me, capture):
    """POST /api/v1/assets/<id>/mark-found — handoff 31 §C3.

    *Where it turned up* is as much an audit fact as *why it went missing*.
    The PATCH above still works, and still records the most interesting
    event in an asset's life as a change of one word with a null beside it.
    This route exists to carry the sentence: it is written to the
    append-only `status_changed` event, beside the one that says why the
    asset went.

    It sets the status back to `active` and does NOT verify the asset:
    whoever found it may not be whoever checks it.
    """
    asset = _new_asset(client, test_location, "pytest-events-found")
    assert_envelope_ok(_mark_missing(client, asset["id"], "not at its desk"))
    reason = ("test_asset_events_api — found in the 2nd-floor store during "
              "the October count, tag intact")
    r = _mark_found(client, asset["id"], reason)
    capture("assets/mark_found", r)
    data = assert_envelope_ok(r)["data"]
    assert set(data) == {"asset", "event_id"}
    assert data["asset"]["id"] == asset["id"]
    assert data["asset"]["state"] == "active"
    assert isinstance(data["event_id"], int) and data["event_id"] > 0
    assert data["asset"]["dates"]["last_verified_date"] is None, (
        "finding an asset is not verifying it")
    assert data["asset"]["last_verified_by"] is None

    history = _history(client, asset["id"])
    assert _events(history, "verified") == []
    found = [e for e in _events(history, "status_changed")
             if e["detail"]["to"] == "active"]
    assert len(found) == 1, (
        "one act, listed once: the message-log line of the same change must "
        "be folded into the record. Listed: %s" % [e["id"] for e in found])
    event = found[0]
    assert event["record"] == {"model": _EVENT_RECORD, "id": data["event_id"]}
    assert event["evidence"] == "append_only"
    assert event["reconstructed"] is False
    assert event["detail"]["from"] == "missing"
    assert event["detail"]["reason"] == reason
    assert event["actor"] is not None and event["actor"]["id"] == me["id"]
    # `test` is `api_mark_found` relabelled by the credential.
    assert event["source"] in ("api_mark_found", "test")


def test_going_missing_and_turning_up_read_in_order_each_with_its_reason(
        client, test_location):
    """The pair an auditor reads together: why it went, where it turned up.

    Two rows of one append-only table, and each keeps ITS OWN reason — the
    asset has no column for either, so there is nothing for the second to
    overwrite.
    """
    asset = _new_asset(client, test_location, "pytest-events-found-pair")
    went = assert_envelope_ok(_mark_missing(
        client, asset["id"], "not in the store at the Q3 count"))["data"]
    came = assert_envelope_ok(_mark_found(
        client, asset["id"], "in the annex, moved there for a repaint"))["data"]
    assert came["event_id"] > went["event_id"]

    oldest = _events(_history(client, asset["id"], sort="oldest"),
                     "status_changed")
    assert [(e["detail"]["from"], e["detail"]["to"], e["detail"]["reason"],
             e["record"]["id"]) for e in oldest] == [
        ("active", "missing", "not in the store at the Q3 count",
         went["event_id"]),
        ("missing", "active", "in the annex, moved there for a repaint",
         came["event_id"])]
    newest = _events(_history(client, asset["id"]), "status_changed")
    assert [e["record"]["id"] for e in newest] == [
        came["event_id"], went["event_id"]], "newest first is the default"
    assert all(e["evidence"] == "append_only" for e in oldest)


@pytest.mark.parametrize("label,body", [
    ("no body at all", None),
    ("an empty object", {}),
    ("a null reason", {"reason": None}),
    ("an empty reason", {"reason": ""}),
    ("a reason of spaces", {"reason": "   \n\t "}),
    ("a number", {"reason": 7}),
    ("a list", {"reason": ["found"]}),
])
def test_mark_found_without_a_reason_is_refused_and_the_asset_stays_missing(
        client, test_location, label, body):
    """`reason` is REQUIRED, for `mark-missing`'s reason — and the whole
    point of the route is the sentence. A caller with nothing to say still
    has `PATCH {"state": "active"}`, which has always worked and records
    exactly that: a change, and no reason. A 400 must not write."""
    asset = _new_asset(client, test_location, "pytest-events-found-400")
    assert_envelope_ok(_mark_missing(client, asset["id"], "gone"))
    before = _status_snapshot(client, asset["id"])
    url = f"/api/v1/assets/{asset['id']}/mark-found"
    r = client.post(url) if body is None else client.post(url, json=body)
    assert_envelope_err(r, 400, "invalid_request")
    after = _status_snapshot(client, asset["id"])
    assert after["state"] == "missing", (
        "%s was refused with a 400 and the asset was marked found anyway"
        % label)
    assert after == before


@pytest.mark.parametrize("state", ["active", "disposed"])
def test_an_asset_that_is_not_missing_cannot_be_marked_found(
        client, test_location, state):
    """409 — there is nothing to find.

    For an ACTIVE asset a 200 would append no event, because the status
    does not change, and would tell the caller its sentence had been
    recorded. For a DISPOSED one it is the terminal rule's tenth door:
    `mark-found` writes `active`, which is a way out of `disposed` for
    anybody who thought to ask. The route answers before the model has to,
    and the record is compared WHOLE, as it is for every other closed door.
    """
    asset = (_condemned(client, test_location, "pytest-events-found-409")
             if state == "disposed"
             else _new_asset(client, test_location, "pytest-events-found-409"))
    before = _status_snapshot(client, asset["id"])
    assert before["state"] == state

    r = _mark_found(client, asset["id"], "it was never lost")
    details = assert_envelope_err(r, 409, "conflict")["error"]["details"]
    # A subset: the envelope adds `http_status` to every `details`.
    assert (details["asset_id"], details["state"]) == (asset["id"], state)
    assert _status_snapshot(client, asset["id"]) == before


def test_mark_found_on_an_unknown_asset_is_a_404(client):
    assert_envelope_err(_mark_found(client, 999999999, "no such asset"),
                        404, "not_found")


def test_a_replayed_mark_found_writes_no_second_event(client, test_location):
    """Without the key a second call is a 409 — the asset is no longer
    missing. With it, a client whose first response was lost gets that
    response back, and the append-only table gains nothing."""
    asset = _new_asset(client, test_location, "pytest-events-found-replay")
    assert_envelope_ok(_mark_missing(client, asset["id"], "gone"))
    key = f"pytest-events-found-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    first = assert_envelope_ok(_mark_found(
        client, asset["id"], "sent once",
        headers={"X-Idempotency-Key": key}))
    second = assert_envelope_ok(_mark_found(
        client, asset["id"], "SHOULD-BE-IGNORED",
        headers={"X-Idempotency-Key": key}))
    assert second["data"]["event_id"] == first["data"]["event_id"]
    assert second["meta"]["request_id"] == first["meta"]["request_id"], (
        "the second call was processed rather than replayed")
    back = [e for e in _events(_history(client, asset["id"]), "status_changed")
            if e["detail"]["to"] == "active"]
    assert [e["detail"]["reason"] for e in back] == ["sent once"]


def test_mark_found_needs_a_credential(client, unauthed_client, test_location):
    asset = _new_asset(client, test_location, "pytest-events-found-401")
    assert_envelope_ok(_mark_missing(client, asset["id"], "gone"))
    r = unauthed_client.post(f"/api/v1/assets/{asset['id']}/mark-found",
                             json={"reason": "nobody is asking"})
    assert_envelope_err(r, 401, "unauthorized")
    assert _asset(client, asset["id"])["state"] == "missing"


# ─── condemn ─────────────────────────────────────────────────────────

def test_condemning_an_asset_sets_everything_in_one_place(
        client, test_location, capture):
    """POST /api/v1/assets/<id>/condemn — status, condition, date, reason.

    Until handoff 30 the app condemned with a PATCH of four fields, one of
    them a disposal DATE read off the browser's clock. This route is sent no
    date at all.

    The expected date is computed as **(UTC now + 1 hour).date()** and NOT as
    `date.today()`, and that is the point of the assertion rather than a
    detail of it. `date.today()` is the date on whatever machine runs this
    suite, in whatever timezone it keeps — a fact about a laptop. The server
    stamps a LAGOS day, the same day the register snapshot cuts on; stamped
    with the acting user's timezone instead (unset for every API credential,
    therefore UTC) it would date every disposal made between 00:00 and 01:00
    in Lagos to the day before. CI runs in UTC and can only see that with the
    offset written out. Taken either side of the call, so a run that
    straddles Lagos midnight asserts something true.
    """
    asset = _new_asset(client, test_location, "pytest-events-condemn",
                       condition="fair")
    reason = "test_asset_events_api — beyond economic repair"
    before = _lagos_today()
    r = _condemn(client, asset["id"], reason)
    after = _lagos_today()
    capture("assets/condemn", r)
    data = assert_envelope_ok(r)["data"]
    assert set(data) == {"asset", "disposal", "event_id"}
    assert isinstance(data["event_id"], int) and data["event_id"] > 0

    condemned = data["asset"]
    assert condemned["state"] == "disposed"
    assert condemned["condition"] == "decommissioned"
    assert condemned["disposal_reason"] == reason
    assert condemned["dates"]["disposal_date"] in {
        before.isoformat(), after.isoformat()}, (
        "the disposal is dated %s; in Lagos it is %s"
        % (condemned["dates"]["disposal_date"], after.isoformat()))

    disposal = data["disposal"]
    assert disposal == condemned["disposal"], (
        "`data.disposal` and `data.asset.disposal` read the same columns")
    assert disposal["date"] == condemned["dates"]["disposal_date"]
    assert disposal["reason"] == reason
    assert disposal["date_reconstructed"] is False
    # What was sent is what was written, and it stays where it was.
    assert condemned["current_location"]["id"] == test_location["id"]


def test_condemning_an_asset_does_not_approve_its_disposal(
        client, test_location):
    """Carrying a disposal out is not authorising it.

    `no_approver` is one of the disposal report's findings. A route that
    stamped whoever called it as the approving authority would manufacture
    exactly the evidence that finding exists to look for; approval is
    `POST /assets/<id>/approve-disposal`, under a different scope.
    """
    asset = _new_asset(client, test_location, "pytest-events-condemn-approver")
    disposal = assert_envelope_ok(
        _condemn(client, asset["id"], "end of life"))["data"]["disposal"]
    assert disposal["approved_by"] is None
    assert disposal["approved_at"] is None


def test_the_history_names_who_carried_a_disposal_out(client, test_location,
                                                      me):
    """`disposal_executor`, closed going forward.

    The approval has always recorded its approver; the act of disposing
    recorded a date and no person. The actor of the append-only change INTO
    `disposed` is that person, and it is the one line of a disposal that
    nobody can rewrite — the condition and the paperwork beside it are still
    message-log lines, and still say so.
    """
    asset = _new_asset(client, test_location, "pytest-events-condemn-actor",
                       condition="good")
    reason = "test_asset_events_api — who disposed of this"
    data = assert_envelope_ok(_condemn(client, asset["id"], reason))["data"]
    history = _history(client, asset["id"])

    changed = _events(history, "status_changed")
    assert len(changed) == 1, "one disposal, listed once"
    event = changed[0]
    assert event["record"] == {"model": _EVENT_RECORD, "id": data["event_id"]}
    assert event["evidence"] == "append_only"
    assert (event["detail"]["from"], event["detail"]["to"]) == (
        "active", "disposed")
    assert event["detail"]["reason"] == reason
    assert event["actor"] is not None and event["actor"]["id"] == me["id"]
    assert event["source"] in ("api_condemn", "test")

    # The same request changed the condition. THAT has no record of its own
    # and must not borrow this one's grade.
    condition = _events(history, "condition_changed")
    assert len(condition) == 1
    assert condition[0]["evidence"] == "chatter"


def test_condemning_a_disposed_asset_is_a_conflict(client, test_location):
    """Disposal is terminal, so there is nothing to do twice.

    And the first disposal's date and reason must survive the second request:
    a 409 that had already overwritten `disposal_reason` would be a refusal
    in the response and an edit in the register.
    """
    asset = _new_asset(client, test_location, "pytest-events-condemn-twice")
    first = assert_envelope_ok(
        _condemn(client, asset["id"], "the real reason"))["data"]
    r = _condemn(client, asset["id"], "a different story")
    body = assert_envelope_err(r, 409, "conflict")
    details = body["error"]["details"]
    assert details["asset_id"] == asset["id"]
    assert details["state"] == "disposed"
    assert details["disposal_date"] == first["disposal"]["date"]
    after = _asset(client, asset["id"])
    assert after["disposal"] == first["disposal"]
    assert len(_events(_history(client, asset["id"]), "status_changed")) == 1


@pytest.mark.parametrize("label,body", [
    ("no body at all", None),
    ("an empty object", {}),
    ("an empty reason", {"reason": ""}),
    ("a reason of spaces", {"reason": "  "}),
    ("a number", {"reason": 0}),
])
def test_condemn_without_a_reason_is_refused_and_disposes_of_nothing(
        client, test_location, label, body):
    asset = _new_asset(client, test_location, "pytest-events-condemn-400",
                       condition="good")
    url = f"/api/v1/assets/{asset['id']}/condemn"
    r = client.post(url) if body is None else client.post(url, json=body)
    assert_envelope_err(r, 400, "invalid_request")
    after = _asset(client, asset["id"])
    assert (after["state"], after["condition"]) == ("active", "good"), (
        "%s was refused with a 400 and the asset was changed anyway" % label)
    assert after["dates"]["disposal_date"] is None
    assert after["disposal_reason"] is None


def test_condemn_on_an_unknown_asset_is_a_404(client):
    assert_envelope_err(_condemn(client, 999999999, "no such asset"),
                        404, "not_found")


def test_a_replayed_condemn_writes_no_second_event(client, test_location):
    asset = _new_asset(client, test_location, "pytest-events-condemn-replay")
    key = f"pytest-events-condemn-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    first = assert_envelope_ok(_condemn(
        client, asset["id"], "sent once", headers={"X-Idempotency-Key": key}))
    second = assert_envelope_ok(_condemn(
        client, asset["id"], "SHOULD-BE-IGNORED",
        headers={"X-Idempotency-Key": key}))
    assert second["data"]["event_id"] == first["data"]["event_id"]
    assert second["meta"]["request_id"] == first["meta"]["request_id"]
    assert _asset(client, asset["id"])["disposal_reason"] == "sent once"
    assert len(_events(_history(client, asset["id"]), "status_changed")) == 1


def test_condemn_needs_a_credential(client, unauthed_client, test_location):
    asset = _new_asset(client, test_location, "pytest-events-condemn-401")
    r = unauthed_client.post(f"/api/v1/assets/{asset['id']}/condemn",
                             json={"reason": "nobody is asking"})
    assert_envelope_err(r, 401, "unauthorized")
    assert _asset(client, asset["id"])["state"] == "active"


def test_the_three_routes_publish_their_whole_contract(client):
    """Scope, the required reason, the conflict, and the idempotency header.

    `reason` is `required` in the published schema and not only in the
    handler: a generated client that treats it as optional finds out from a
    400 in production. `mark-found` joined the two in handoff 31 and is held
    to exactly what they are.
    """
    spec = client.get("/api/v1/openapi.json").json()
    for path in ("/api/v1/assets/{id}/mark-missing",
                 "/api/v1/assets/{id}/mark-found",
                 "/api/v1/assets/{id}/condemn"):
        assert path in spec["paths"], f"{path} is not published in openapi.json"
        op = spec["paths"][path]["post"]
        assert op["x-cadra-scopes"] == ["assets:write"], (path, op["x-cadra-scopes"])
        assert "409" in op["responses"], (
            f"{path}: 409 is a published answer — already missing, not "
            "missing, or disposed — and an integration has to be able to "
            "branch on it")
        names = {p["name"] for p in op.get("parameters", [])}
        assert "X-Idempotency-Key" in names, (
            f"{path} is declared idempotent but does not publish the header")
        schema = op["requestBody"]["content"]["application/json"]["schema"]
        assert schema.get("required") == ["reason"], (path, schema)
        assert schema["properties"]["reason"]["type"] == "string"


# ─── a disposal is stamped through ANY door ──────────────────────────
#
# Handoff 31 §C1. `/condemn` was the proper door and did not close the
# others: `PATCH {"state": "disposed"}` disposed of an asset and stamped
# nothing, which is how the disposal report came to raise `no_disposal_date`
# against disposals made last week. `nrs.asset._stamp_disposal` sits under
# every writer now; these are the PATCH door, which is the one an
# integration uses.

def test_a_disposal_made_by_a_bare_patch_is_dated_and_decommissioned(
        client, test_location):
    """`PATCH {"state": "disposed"}` and nothing else.

    The date is a LAGOS day — (UTC now + 1 hour).date(), taken either side
    of the call, for the reason `test_condemning_an_asset_sets_everything_in_
    one_place` sets out at length: every API credential's user has no
    timezone, so a date stamped from the acting user's would put a disposal
    made in the first hour of a Lagos day on the day before.
    """
    asset = _new_asset(client, test_location, "pytest-events-stamp-bare",
                       condition="fair")
    before = _lagos_today()
    r = client.patch(f"/api/v1/assets/{asset['id']}",
                     json={"state": "disposed"})
    after = _lagos_today()
    data = assert_envelope_ok(r)["data"]
    assert data["state"] == "disposed"
    assert data["condition"] == "decommissioned"
    assert data["dates"]["disposal_date"] in {
        before.isoformat(), after.isoformat()}, (
        "the disposal is dated %s; in Lagos it is %s"
        % (data["dates"]["disposal_date"], after.isoformat()))
    assert data["disposal"]["date"] == data["dates"]["disposal_date"]
    assert data["disposal"]["date_reconstructed"] is False

    # What came back is what was stored, and the stamp is not a second act:
    # one change of status, however many columns it took to record it.
    assert _asset(client, asset["id"])["disposal"] == data["disposal"]
    changed = _events(_history(client, asset["id"]), "status_changed")
    assert [(e["detail"]["from"], e["detail"]["to"]) for e in changed] == [
        ("active", "disposed")]


def test_a_disposal_cannot_arrive_in_good_condition(client, test_location):
    """The condition is not negotiable, even when the caller sends one.

    `decommissioned` is what disposed MEANS on this register. A disposed
    asset in `good` condition is how the condition tiles came to count
    things that are gone (handoff 29), and the PATCH that produces one is a
    body an integration can perfectly well send.
    """
    asset = _new_asset(client, test_location, "pytest-events-stamp-good",
                       condition="good")
    r = client.patch(f"/api/v1/assets/{asset['id']}",
                     json={"state": "disposed", "condition": "good"})
    data = assert_envelope_ok(r)["data"]
    assert (data["state"], data["condition"]) == ("disposed",
                                                  "decommissioned")
    assert _asset(client, asset["id"])["condition"] == "decommissioned"


def test_a_disposal_date_the_caller_sent_is_kept(client, test_location):
    """An integration carrying a disposal made elsewhere knows when it
    happened, and the server does not. The stamp fills a gap; it does not
    overrule a fact."""
    asset = _new_asset(client, test_location, "pytest-events-stamp-dated")
    r = client.patch(f"/api/v1/assets/{asset['id']}",
                     json={"state": "disposed",
                           "disposal_date": "2026-01-31"})
    data = assert_envelope_ok(r)["data"]
    assert data["dates"]["disposal_date"] == "2026-01-31"
    assert data["disposal"]["date"] == "2026-01-31"
    assert data["condition"] == "decommissioned"


def test_an_asset_registered_as_already_disposed_is_given_no_date(
        client, test_location):
    """NOT on create — deliberately, and this is the edge of the rule.

    An asset REGISTERED as disposed was disposed of on some earlier day this
    system never saw. Stamping today would replace a finding the disposal
    report can show — no date — with a date that is wrong, which it cannot.
    """
    asset = _new_asset(client, test_location, "pytest-events-stamp-create",
                       state="disposed")
    assert asset["state"] == "disposed"
    assert asset["dates"]["disposal_date"] is None
    assert asset["disposal"]["date"] is None
    assert _asset(client, asset["id"])["disposal"]["date"] is None
    # …and then DATED, so this test does not grow `test19`'s
    # `no_disposal_date` finding by one on every run for ever: the asset sits
    # at a location, so it has a movement row and can never be deleted. The
    # first three runs of this test left three such rows before the
    # verification pass counted them. A disposal's paperwork stays editable,
    # which is also what lets a real one be dated once somebody finds out.
    dated = assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}",
        json={"disposal_date": "2020-01-01"}))["data"]
    assert dated["disposal"]["date"] == "2020-01-01"


# ─── a stale date is not the caller's date, and a date cannot be taken
#     away — handoff 32 §C ───────────────────────────────────────────

def test_a_date_patched_long_before_the_disposal_is_not_the_callers_date(
        client, test_location):
    """Report 31 §C2. `disposal_date` is writable on a LIVE asset.

    The first stamp asked "does the asset have a date?" AFTER the write,
    which cannot tell a date sent WITH the disposal from one PATCHed months
    earlier. So an asset given 2020's date while still in service and
    disposed of today was dated 2020, and the register said it left the
    estate six years before it did — a number that reconciles against
    nothing and that no finding reports, because the row looks complete.

    Only the date in the SAME write is the caller's. The asset ends this
    test dated, so it does not grow `test19`'s `no_disposal_date` finding.
    """
    asset = _new_asset(client, test_location, "pytest-events-stamp-stale")
    staled = assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}",
        json={"disposal_date": "2020-01-01"}))["data"]
    assert staled["dates"]["disposal_date"] == "2020-01-01", (
        "the stale date was not written, so the rest of this test would "
        "prove nothing")
    assert staled["state"] == "active"

    before = _lagos_today()
    data = assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}", json={"state": "disposed"}))["data"]
    after = _lagos_today()
    assert data["state"] == "disposed"
    assert data["dates"]["disposal_date"] in {
        before.isoformat(), after.isoformat()}, (
        "a disposal made today is dated %s — the date that was sitting on "
        "the record before anybody disposed of anything"
        % data["dates"]["disposal_date"])


def test_a_disposals_date_cannot_be_taken_away_but_can_be_corrected(
        client, test_location):
    """Handoff 32 §C1, both halves in one act.

    Emptying the date is refused — it is the one remaining way to raise
    `no_disposal_date` against a disposal made this week, on a register
    whose real opening balance for that finding is zero. Correcting it to
    another day is the legitimate act beside it and is untouched: a board of
    survey that sat before the status followed is a date worth putting
    right.
    """
    asset = _condemned(client, test_location, "pytest-events-undate")
    dated = _asset(client, asset["id"])["disposal"]["date"]
    assert dated, "the fixture is undated, so there is nothing to take away"

    refused = assert_envelope_err(
        client.patch(f"/api/v1/assets/{asset['id']}",
                     json={"disposal_date": None}),
        400, "validation_failed")["error"]
    assert "disposed" in refused["message"], (
        "the refusal does not say WHY: %r" % refused["message"])
    assert _asset(client, asset["id"])["disposal"]["date"] == dated

    corrected = assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}",
        json={"disposal_date": "2026-01-31"}))["data"]
    assert corrected["disposal"]["date"] == "2026-01-31"
    assert corrected["dates"]["disposal_date"] == "2026-01-31"


def test_a_live_assets_disposal_date_can_still_be_cleared(
        client, test_location):
    """The rule belongs to a DISPOSAL, not to the column. An asset still in
    service whose date was keyed in by mistake has to be able to lose it, or
    the mistake is permanent and the register carries a disposal date for
    something nobody has disposed of."""
    asset = _new_asset(client, test_location, "pytest-events-undate-live")
    assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}",
        json={"disposal_date": "2020-01-01"}))
    data = assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}",
        json={"disposal_date": None}))["data"]
    assert data["state"] == "active"
    assert data["dates"]["disposal_date"] is None
    assert data["disposal"]["date"] is None


def test_a_disposed_asset_somebody_finds_on_the_premises_can_be_verified(
        client, test_location, me):
    """Handoff 31 §C2 — ALLOWED, by ruling, and in these words: a disposed
    asset somebody physically finds on the premises is an audit finding, and
    a register that refuses to record "I saw it, today" is suppressing the
    one fact that matters.

    The Odoo form used to hide the button the app offered: two surfaces, one
    rule, two answers. This is the API's half of the agreed answer. Do not
    tidy it into `_CLOSED_DOORS`.
    """
    asset = _condemned(client, test_location, "pytest-events-verify-disposed")
    r = client.post(f"/api/v1/assets/{asset['id']}/verify",
                    json={"notes": "sighted in the yard, awaiting collection"})
    data = assert_envelope_ok(r)["data"]
    assert data["asset"]["state"] == "disposed", (
        "verifying a disposed asset brought it back onto the register")
    assert data["asset"]["disposal"] == asset["disposal"]

    verified = _events(_history(client, asset["id"]), "verified")
    assert len(verified) == 1
    event = verified[0]
    assert event["record"] == {"model": _EVENT_RECORD, "id": data["event_id"]}
    assert event["evidence"] == "append_only"
    assert event["actor"]["id"] == me["id"]
    assert event["detail"]["notes"] == \
        "sighted in the yard, awaiting collection"


# ─── disposed is terminal — every door ───────────────────────────────

_OTHER_LOCATION = object()
_AN_EMPLOYEE = object()

#: Nothing here any more, and the history is why the name survives.
#:
#: These two PATCH doors used to answer with the APPROVAL refusal rather than
#: the disposed-is-terminal one — `400 invalid_request` *"this register
#: requires a second person"* instead of `400 validation_failed` *"...has
#: been disposed of"* — because the approval gate sat above the write and the
#: terminal rule lives in the write.
#:
#: The door was never open and nothing was written; what was wrong was the
#: SENTENCE, which told the caller to go and use `/move` or
#: `/transfer-custody` on an asset those routes would themselves refuse. That
#: is a remedy which cannot work, the same shape as the un-assign dead end
#: handoff 35 found one route along, and it was fixed rather than kept:
#: `patch_asset` now calls `_assert_disposed_is_terminal` above the approval
#: block, as both ACTION routes already did.
#:
#: **This tuple is kept as an empty override so the table's shape does not
#: change and this paragraph stays attached to the two rows it is about.**
#: Both now expect the ordinary answer.
_APPROVAL_ANSWERS_FIRST = None

# (label, method, path suffix, body, status, code[, when_approval_required]).
# The sentinels are filled in from the tenant; a door that needs something the
# tenant lacks skips, in the idiom of `test_asset_history.py`.
_CLOSED_DOORS = [
    ("PATCH state → missing", "patch", "",
     {"state": "missing"}, 400, "validation_failed"),
    ("PATCH state → active", "patch", "",
     {"state": "active"}, 400, "validation_failed"),
    ("PATCH state → in_repair", "patch", "",
     {"state": "in_repair"}, 400, "validation_failed"),
    ("PATCH state → transferred", "patch", "",
     {"state": "transferred"}, 400, "validation_failed"),
    ("PATCH location_id", "patch", "",
     {"location_id": _OTHER_LOCATION}, 400, "validation_failed",
     _APPROVAL_ANSWERS_FIRST),
    ("PATCH custodian_id", "patch", "",
     {"custodian_id": _AN_EMPLOYEE}, 400, "validation_failed",
     _APPROVAL_ANSWERS_FIRST),
    # The refusal is for the WHOLE request: `notes` is an allowed edit, and
    # it must not be written on the way to a 400.
    ("PATCH notes + state → missing", "patch", "",
     {"notes": "SHOULD-NOT-BE-WRITTEN", "state": "missing"},
     400, "validation_failed"),
    # Handoff 32 §C1. Not "nothing leaves disposed" but the same rule in the
    # same place: a disposal's DAY cannot be taken off its record. This was
    # the one remaining way to manufacture the disposal report's
    # `no_disposal_date` finding against a new disposal.
    ("PATCH disposal_date → null", "patch", "",
     {"disposal_date": None}, 400, "validation_failed"),
    ("PATCH notes + disposal_date → null", "patch", "",
     {"notes": "SHOULD-NOT-BE-WRITTEN", "disposal_date": None},
     400, "validation_failed"),
    ("POST /move", "post", "/move",
     {"to_location_id": _OTHER_LOCATION, "reason": "a disposed asset moved"},
     400, "validation_failed"),
    ("POST /transfer-custody", "post", "/transfer-custody",
     {"to_custodian_id": _AN_EMPLOYEE, "reason": "a disposed asset handed on"},
     400, "validation_failed"),
    ("POST /mark-missing", "post", "/mark-missing",
     {"reason": "a disposed asset went missing"}, 409, "conflict"),
    ("POST /condemn", "post", "/condemn",
     {"reason": "a disposed asset disposed of again"}, 409, "conflict"),
]


@pytest.mark.parametrize(
    "door", _CLOSED_DOORS, ids=[door[0] for door in _CLOSED_DOORS])
def test_nothing_leaves_disposed_by_any_door(
        client, test_location, any_location, second_person, capture, door):
    """Disposed is TERMINAL — not missing, not moved, not handed to anybody.

    Until handoff 30 a disposed asset could be marked missing, which
    overwrote `disposed` and put it back on the register with a 200. The rule
    is in `nrs.asset.write`, where every writer passes, so it is asserted
    here door by door: disabling a button closes one of these and leaves the
    rest open.

    **And a refusal writes NOTHING.** Asserted as a whole-record comparison
    and not as "the state is still disposed", because the defect this guards
    is the one handoff 28 shipped: `/move` builds its transfer document
    BEFORE it writes the location, so a refusal that came back as an error
    RESPONSE rather than an exception would answer 400 and leave a `done`
    transfer behind for a move that never happened. A refusal raised in the
    model rolls the transaction back, and the document goes with it.

    **Three of these doors answer with a different refusal on a tenant that
    requires a second person** — see `_APPROVAL_ANSWERS_FIRST` above for
    which, and for why that is a weaker sentence rather than an open door.
    The half of this test that matters, the whole-record comparison, is
    identical in both worlds.
    """
    label, method, suffix, body, status, code = door[:6]
    instead = door[6] if len(door) > 6 else None
    expects_disposed_in_message = True
    if instead and second_person.required:
        status, code, expects_disposed_in_message = (
            instead[0], instead[1], False)
        must_say = instead[2]

    filled = dict(body)
    if _OTHER_LOCATION in filled.values():
        if any_location == test_location["id"]:
            pytest.skip("tenant has no second location to move to")
        filled = {k: (any_location if v is _OTHER_LOCATION else v)
                  for k, v in filled.items()}
    if _AN_EMPLOYEE in filled.values():
        employee = _an_employee(client)
        if not employee:
            pytest.skip("tenant has no employee to hand the asset to")
        filled = {k: (employee if v is _AN_EMPLOYEE else v)
                  for k, v in filled.items()}

    asset = _condemned(client, test_location, "pytest-events-terminal")
    before = _status_snapshot(client, asset["id"])
    assert before["state"] == "disposed"

    r = getattr(client, method)(f"/api/v1/assets/{asset['id']}{suffix}",
                                json=filled)
    if label == "POST /move":
        capture("assets/disposed_is_terminal", r)
    error = assert_envelope_err(r, status, code)["error"]
    if expects_disposed_in_message:
        assert "disposed" in error["message"], (
            "the refusal does not say WHY: %r" % error["message"])
    else:
        # It says WHY, truthfully, about a different rule. Pinned to the
        # exact sentence so that this branch cannot quietly become "any 400
        # will do" — which is what would let a real regression through.
        assert must_say in error["message"], (
            "%s was expected to be refused by the approval gate on this "
            "tenant and said something else instead: %r"
            % (label, error["message"]))

    after = _status_snapshot(client, asset["id"])
    assert after == before, (
        "%s was refused with a %s and still changed the record: %s"
        % (label, status,
           {k: (before[k], after[k]) for k in before if before[k] != after[k]}))


def _pending_change_requests(client, asset_id):
    """Every pending approval request against one asset. Handoff 35.

    An asset may hold ONE, enforced by a partial unique index, so a refused
    route that left one behind does not merely litter — it blocks the next
    legitimate request until somebody withdraws a request nobody made on
    purpose.
    """
    body = assert_envelope_ok(client.get(
        "/api/v1/approvals", params={"asset_id": asset_id,
                                     "state": "pending", "limit": 20}))
    return body["data"]


def test_a_disposed_asset_cannot_be_handed_on_even_through_an_approval(
        client, test_location, second_person):
    """A disposed asset cannot even be ASKED about — and if it ever can
    again, the approval must still refuse it.

    Handoff 35 opened this and its own verification pass shut it. For a few
    hours `/transfer-custody` answered 200 to a disposed asset, raising a
    request that could never be approved and that occupied that asset's one
    pending slot until somebody withdrew it — because the route used to meet
    the model at the write, and a request never writes, so the model was
    never asked. `_assert_disposed_is_terminal` now sits above the approval
    block on both action routes.

    So the first branch below is the live one, and the second is the guard
    that matters: **if the terminal check is ever moved or lost, the approval
    itself must still refuse**, `_premise_check` must say why, and nothing
    must reach the asset. A door closed in one place is a door with one
    lock, which is the lesson of every handoff since 28.
    """
    if not second_person.required:
        pytest.skip("this tenant does not require a second person, so there "
                    "is no approval for a disposed asset to slip into")
    employee = _an_employee(client)
    if not employee:
        pytest.skip("tenant has no employee to hand the asset to")

    asset = _condemned(client, test_location, "pytest-events-terminal-approval")
    before = _status_snapshot(client, asset["id"])

    # Raised by the second person and decided by the suite, the way round
    # `tests/conftest.py::second_person` explains: nobody may approve their
    # own request, so the two halves cannot be the same credential.
    raised = second_person.requester.post(
        f"/api/v1/assets/{asset['id']}/transfer-custody",
        json={"to_custodian_id": employee,
              "approver_id": second_person.approver_id,
              "reason": "a disposed asset handed on, through the queue"})
    if raised.status_code != 200:
        # THE LIVE BRANCH. The route asks the model before it asks anybody
        # to approve anything, so no request is ever raised and no pending
        # slot is occupied.
        error = assert_envelope_err(raised, 400, "validation_failed")["error"]
        assert "disposed" in error["message"]
        assert _status_snapshot(client, asset["id"]) == before
        assert not _pending_change_requests(client, asset["id"]), (
            "a refused request was created anyway, and it now blocks every "
            "later request on this asset until somebody withdraws it")
        return

    # The fallback, kept on purpose: if the terminal check is ever moved
    # below the approval block again, the approval must still refuse.
    data = assert_envelope_ok(raised)["data"]
    assert data["pending_approval"] is True
    assert data["asset"]["state"] == "disposed"
    # Nothing was written to the ASSET by raising it, which is the property
    # the append-only records depend on: a request is not a change.
    assert _status_snapshot(client, asset["id"]) == before

    decided = second_person.suite.post(
        "/api/v1/approvals/%s/approve" % data["request"]["id"], json={})
    error = assert_envelope_err(decided, 409, "conflict")["error"]
    assert "disposed" in error["message"], (
        "the approval was refused without saying the asset had been "
        "disposed of: %r" % error["message"])
    assert error["details"]["premise_broken_reason"]
    assert _status_snapshot(client, asset["id"]) == before, (
        "a disposed asset changed hands because somebody approved it")


def test_a_refused_move_does_not_burn_a_transfer_reference(
        client, test_location, second_person):
    """A refusal happens before anything is written — a sequence included.

    `/move` draws its transfer reference from an `ir.sequence` and then
    creates the transfer. When the model refused the move of a disposed
    asset, the transfer row rolled back with the exception and the NUMBER did
    not: a sequence is not transactional. So every refused move left a gap in
    the transfer references that no transfer explained — which, in a run of
    numbered documents, is what a deleted one looks like. The route now asks
    the model's own rule before it draws anything.

    Proved by numbering: two real moves either side of a refused one must be
    consecutive. The suite runs serially against a tenant nobody else is
    moving assets on; if that ever stops being true this is the test that
    will say so, and it will be wrong about why.
    """
    import re

    elsewhere = assert_envelope_ok(client.post("/api/v1/locations", json={
        "name": "pytest-events-seq-destination"}), 201)["data"]
    live = _new_asset(client, test_location, "pytest-events-seq-live")
    dead = _condemned(client, test_location, "pytest-events-seq-dead")

    def number(reference):
        return int(re.search(r"(\d+)\D*$", reference).group(1))

    # Two REAL moves either side of the refused one. On a tenant that needs a
    # second person that is a request and an approval each, and the sequence
    # is drawn by `action_approve` instead of by the route — which is exactly
    # why this is worth re-asserting rather than retiring: the number is now
    # taken in a different place, and the property has to survive the move.
    before = number(second_person.move(
        live["id"], elsewhere["id"], reason="there")["transfer_reference"])
    assert_envelope_err(second_person.requester.post(
        f"/api/v1/assets/{dead['id']}/move",
        json={"to_location_id": elsewhere["id"], "reason": "refused",
              "approver_id": second_person.approver_id}),
        400, "validation_failed")
    after = number(second_person.move(
        live["id"], test_location["id"],
        reason="and back")["transfer_reference"])
    assert after == before + 1, (
        "the refused move consumed transfer reference(s) %s"
        % list(range(before + 1, after)))


def test_a_disposed_asset_can_still_have_its_notes_edited(
        client, test_location):
    """The rule is about status, place and custody — not about the record."""
    asset = _condemned(client, test_location, "pytest-events-terminal-notes")
    r = client.patch(f"/api/v1/assets/{asset['id']}",
                     json={"notes": "BER report filed 2026-09-21"})
    data = assert_envelope_ok(r)["data"]
    assert data["notes"] == "BER report filed 2026-09-21"
    assert data["state"] == "disposed"


def test_a_form_that_resends_the_status_and_location_is_not_refused(
        client, test_location):
    """NAMING a protected field is not CHANGING it.

    The Cadra app's edit form re-sends `state` and the location on every
    save. A rule that refused on the field's presence would make a disposed
    asset's notes uneditable from the one screen people edit them on — and
    the obvious fix for that would be to stop sending the rule the truth.
    Compared, not detected. And a value that did not change is not an event:
    the history gains no status change and no move.
    """
    asset = _condemned(client, test_location, "pytest-events-terminal-resend")
    before = _history(client, asset["id"])
    r = client.patch(f"/api/v1/assets/{asset['id']}", json={
        "state": "disposed",
        "location_id": test_location["id"],
        "notes": "saved from the edit form"})
    data = assert_envelope_ok(r)["data"]
    assert data["notes"] == "saved from the edit form"
    assert data["state"] == "disposed"
    assert data["current_location"]["id"] == test_location["id"]
    after = _history(client, asset["id"])
    for etype in ("status_changed", "location_moved"):
        assert ([e["id"] for e in _events(after, etype)]
                == [e["id"] for e in _events(before, etype)]), (
            "re-sending an unchanged value was recorded as a %s" % etype)


def test_a_disposals_paperwork_is_completed_after_it_is_disposed_of(
        client, test_location):
    """`disposal_method` and `disposal_reference` arrive AFTER the act.

    The board-of-survey reference is issued once the asset has gone. A
    terminal rule that froze the whole record would make the disposal report
    's `no_reference` finding permanent for every asset it was raised on.
    """
    asset = _condemned(client, test_location, "pytest-events-terminal-paper")
    r = client.patch(f"/api/v1/assets/{asset['id']}", json={
        "disposal_method": "scrapped",
        "disposal_reference": "BOS/2026/PYTEST-EVENTS"})
    disposal = assert_envelope_ok(r)["data"]["disposal"]
    assert disposal["method"] == "scrapped"
    assert disposal["reference"] == "BOS/2026/PYTEST-EVENTS"


def test_a_condemned_asset_can_still_be_approved(client, test_location, me):
    """Approval is the one act a disposed asset is WAITING for.

    Branches on the scope actually held, as `test_audit_logs.py` does and for
    its reason: a scope list is a fact about a tenant. Either way the rule
    under test holds — what differs is which answer proves it.
    """
    asset = _condemned(client, test_location, "pytest-events-terminal-approve")
    r = client.post(f"/api/v1/assets/{asset['id']}/approve-disposal", json={})
    if not _holds(me, "approvals:write"):
        assert_envelope_err(r, 403, "forbidden")
        return
    disposal = assert_envelope_ok(r)["data"]["disposal"]
    assert disposal["approved_by"]["id"] == me["id"]
    assert disposal["approved_at"]


# ─── verification as a record ────────────────────────────────────────

def test_verify_returns_the_record_it_wrote(client, test_location, me):
    """`data.event_id` — ADDITIVE on a published route.

    `verification` still describes the one overwritten pair of columns on
    the asset; `event_id` is the row that will still be there after the next
    verification has overwritten them.
    """
    asset = _new_asset(client, test_location, "pytest-events-verify")
    r = client.post(f"/api/v1/assets/{asset['id']}/verify",
                    json={"notes": "test_asset_events_api — sighted"})
    data = assert_envelope_ok(r)["data"]
    assert {"asset", "verification", "event_id"} <= set(data)
    assert isinstance(data["event_id"], int) and data["event_id"] > 0

    verified = _events(_history(client, asset["id"]), "verified")
    assert len(verified) == 1, (
        "one press of Verify; the message-log line of the same act must be "
        "folded into the record, not listed beside it")
    event = verified[0]
    assert event["record"] == {"model": _EVENT_RECORD, "id": data["event_id"]}
    assert event["evidence"] == "append_only"
    assert event["actor"]["id"] == me["id"]
    assert event["detail"]["verifier_recorded"] is True
    assert event["detail"]["notes"] == "test_asset_events_api — sighted"
    assert event["detail"]["verified_on"] == \
        data["asset"]["dates"]["last_verified_date"]
    assert event["detail"]["previous_verified_on"] is None


def test_two_verifications_on_one_day_are_two_events(client, test_location):
    """The case one overwritten column could not express at all.

    A second check on the same day changes no DATE and no verifier, so it
    left no tracked change and therefore nothing anywhere: the asset looked
    exactly as it had after the first. Two checks are two checks.
    """
    asset = _new_asset(client, test_location, "pytest-events-verify-twice")
    first = assert_envelope_ok(client.post(
        f"/api/v1/assets/{asset['id']}/verify",
        json={"notes": "morning count"}))["data"]
    second = assert_envelope_ok(client.post(
        f"/api/v1/assets/{asset['id']}/verify",
        json={"notes": "afternoon recount"}))["data"]
    assert second["event_id"] != first["event_id"]

    verified = _events(_history(client, asset["id"], sort="oldest"), "verified")
    assert [e["record"]["id"] for e in verified] == [
        first["event_id"], second["event_id"]]
    # Each keeps ITS OWN notes; the asset keeps only the last.
    assert [e["detail"]["notes"] for e in verified] == [
        "morning count", "afternoon recount"]
    assert all(e["evidence"] == "append_only" for e in verified)


def test_a_patched_verification_date_is_a_date_and_not_a_verification(
        client, test_location, me):
    """`verification_date_set` — a TYPE of its own, not a `verified`.

    `PATCH {"last_verified_date": …}` is an integration's way to carry a
    verification made elsewhere, and what it cannot say is who checked. So
    it is listed as a date that was written: it names whoever WROTE it, and
    says in the event that no verifier is recorded. A type and not a
    `source`, because under a test credential — and this is one — every
    source reads `test`, and the difference between *"Ada checked it"* and
    *"a date was written"* must not be something a label can erase.

    TODAY's date, deliberately: the hardest case is the PATCH that looks
    most like a real verification.
    """
    asset = _new_asset(client, test_location, "pytest-events-verify-patched")
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    r = client.patch(f"/api/v1/assets/{asset['id']}",
                     json={"last_verified_date": today})
    data = assert_envelope_ok(r)["data"]
    assert data["dates"]["last_verified_date"] == today
    assert data["last_verified_by"] is None

    history = _history(client, asset["id"])
    assert _events(history, "verified") == [], (
        "a PATCHed date was listed as somebody having verified the asset")
    written = _events(history, "verification_date_set")
    assert len(written) == 1
    event = written[0]
    assert event["record"]["model"] == _EVENT_RECORD
    assert event["evidence"] == "append_only"
    assert event["detail"]["verifier_recorded"] is False
    assert event["detail"]["verified_on"] == today
    assert event["detail"]["previous_verified_on"] is None
    # The ACTOR is who wrote the date. That is a true statement and a
    # different one, and the summary has to keep them apart.
    assert event["actor"]["id"] == me["id"]
    assert "does not say who checked" in event["summary"]


def test_resending_the_same_verification_date_is_not_an_event(
        client, test_location):
    """A date that did not change is not a date that was written."""
    asset = _new_asset(client, test_location, "pytest-events-verify-resend")
    for _ in range(2):
        assert_envelope_ok(client.patch(
            f"/api/v1/assets/{asset['id']}",
            json={"last_verified_date": "2026-01-15"}))
    written = _events(_history(client, asset["id"]), "verification_date_set")
    assert len(written) == 1


# ─── the reconciled references ───────────────────────────────────────

def test_a_changed_reference_is_recorded_and_a_changed_vendor_is_not(
        client, test_location, me):
    """One PATCH, two grades — and the fold removes only what is covered.

    `grn_reference` and `purchase_order_reference` are what an auditor
    reconciles against Vendra and SAP, and a change to one is exactly the
    event somebody would want to hide: each is an append-only event with the
    value before and after AS THEY READ AT THE TIME. `purchase_vendor` was
    ruled to stay a message-log line. All three are tracked and arrive in
    ONE message, so this is also the test that the record supersedes the two
    rows it covers and leaves the third standing — not the whole message.
    """
    asset = _new_asset(client, test_location, "pytest-events-references",
                       grn_reference="GRN-BEFORE",
                       purchase_order_reference="PO-BEFORE",
                       purchase_vendor="Vendor Before Ltd")
    r = client.patch(f"/api/v1/assets/{asset['id']}", json={
        "grn_reference": "GRN-AFTER",
        "purchase_order_reference": "PO-AFTER",
        "purchase_vendor": "Vendor After Ltd"})
    assert_envelope_ok(r)

    changed = _events(_history(client, asset["id"]), "provenance_changed")
    by_field = {}
    for event in changed:
        for change in event["detail"]["changes"]:
            by_field.setdefault(change["field"], []).append((event, change))
    assert sorted(by_field) == ["grn_reference", "purchase_order_reference",
                                "purchase_vendor"]
    for field, old, new in (
            ("grn_reference", "GRN-BEFORE", "GRN-AFTER"),
            ("purchase_order_reference", "PO-BEFORE", "PO-AFTER")):
        assert len(by_field[field]) == 1, (
            "`%s` changed once and is listed %d times — the message-log row "
            "of the same act was not folded away"
            % (field, len(by_field[field])))
        event, change = by_field[field][0]
        assert event["evidence"] == "append_only"
        assert event["record"]["model"] == _EVENT_RECORD
        assert (change["old"], change["new"]) == (old, new)
        assert event["actor"]["id"] == me["id"]

    assert len(by_field["purchase_vendor"]) == 1
    event, change = by_field["purchase_vendor"][0]
    assert event["evidence"] == "chatter", (
        "the vendor was ruled to stay a message-log line, and a line that "
        "anybody who can edit the asset can delete must not be graded as a "
        "record nobody can alter")
    assert event["record"]["model"] == "mail.message"
    assert (change["old"], change["new"]) == (
        "Vendor Before Ltd", "Vendor After Ltd")


def test_a_reference_sent_unchanged_is_not_an_event(client, test_location):
    """Vendra re-sends what it holds. A re-send is not a correction."""
    asset = _new_asset(client, test_location, "pytest-events-reference-same",
                       grn_reference="GRN-UNCHANGED")
    assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}",
        json={"grn_reference": "GRN-UNCHANGED", "notes": "re-sent"}))
    assert _events(_history(client, asset["id"]), "provenance_changed") == []


def test_an_assets_opening_values_are_not_events(client, test_location):
    """An event is a CHANGE. What an asset was born with is its registration.

    Deliberately unlike custody and movement, which DO record the first
    custodian and the first placement. Every asset has a `state` from birth;
    recording it would pin every asset ever created (`ondelete='restrict'`)
    for a row that says only that it was created.
    """
    asset = _new_asset(client, test_location, "pytest-events-opening",
                       state="in_repair", grn_reference="GRN-AT-BIRTH",
                       last_verified_date="2026-01-15")
    assert _recorded(_history(client, asset["id"])) == []


# ─── the label ───────────────────────────────────────────────────────

def test_an_event_this_suite_wrote_says_so(client, test_location,
                                           database_accepts_test_writes):
    """The suite verifies, condemns and marks missing real assets, and the
    record of each is PERMANENT.

    Same argument as `test_custody.test_a_link_this_suite_wrote_says_so`:
    that is accepted, because a test that does not exercise the recorder
    proves nothing about whether anything is recorded. What is not
    acceptable is a reader being unable to tell. `tests/test_source_guards.py`
    lists `nrs.asset.event` as self-labelling on the strength of this.

    No skip for a credential that is not flagged, unlike the custody and
    movement versions of this test: since handoff 25 the session refuses to
    start without `credential_is_test`, so by the time this runs the label
    is owed, and a skip here would be a guard that passes.
    """
    assert database_accepts_test_writes["credential_is_test"] is True
    asset = _new_asset(client, test_location, "pytest-events-label",
                       grn_reference="GRN-LABEL-BEFORE")
    assert_envelope_ok(client.post(
        f"/api/v1/assets/{asset['id']}/verify", json={}))
    assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}",
        json={"last_verified_date": "2026-01-15",
              "grn_reference": "GRN-LABEL-AFTER",
              "warranty_expiry": "2027-01-15"}))
    # The refused write of the set: a wrong-number affix is a 400 and the
    # 400 is the point — the event survives it. Before the condemn, because
    # a disposed asset's label is a different refusal.
    assert_envelope_err(client.post(
        f"/api/v1/assets/{asset['id']}/tag-affixed",
        json={"tag_number": "PYTEST-NOT-THE-TAG"}),
        400, "validation_failed")
    assert_envelope_ok(_mark_missing(client, asset["id"], "label test"))
    assert_envelope_ok(_condemn(client, asset["id"], "label test"))

    recorded = _recorded(_history(client, asset["id"]))
    # Every kind but `gate_fired` (handoff 57): a gate needs a receipt
    # candidate, which exists only with the tenant's switch on, and is
    # proved in `test_receipt_gates.py` on both sides.
    assert sorted({e["type"] for e in recorded}) == sorted(
        t for t in _RECORDED_TYPES if t != "gate_fired"), (
        "this test is meant to write one event of every kind")
    sources = {e["source"] for e in recorded}
    assert sources == {"test"}, (
        "an event written by the test suite came back as %s. These rows are "
        "permanent and append-only; a reader who was never told this suite "
        "exists must still be able to see that they are artefacts."
        % sorted(sources, key=str))


# ─── what the history says about the record ──────────────────────────

def test_the_history_says_from_when_each_kind_of_event_is_recorded(
        client, test_location):
    """`fidelity.events` — PER KIND, because they share a table.

    A database whose first status change was recorded in September and whose
    first verification was recorded in March did not begin recording
    verifications in September. One `recording_began_at` for the table would
    say it had. Everything older than the instant given is still a
    message-log line and is still graded as one; this is what tells a reader
    where that line falls.
    """
    asset = _new_asset(client, test_location, "pytest-events-fidelity",
                       grn_reference="GRN-FIDELITY-BEFORE")
    # One of each, so that none of the six can honestly say "not yet".
    assert_envelope_ok(client.post(
        f"/api/v1/assets/{asset['id']}/verify", json={}))
    assert_envelope_ok(client.patch(
        f"/api/v1/assets/{asset['id']}",
        json={"last_verified_date": "2026-01-15",
              "grn_reference": "GRN-FIDELITY-AFTER",
              "warranty_expiry": "2027-01-15"}))
    assert_envelope_err(client.post(
        f"/api/v1/assets/{asset['id']}/tag-affixed",
        json={"tag_number": "PYTEST-NOT-THE-TAG"}),
        400, "validation_failed")
    assert_envelope_ok(_mark_missing(client, asset["id"], "fidelity test"))

    fidelity = _history(client, asset["id"])["fidelity"]
    entries = fidelity["events"]
    assert [e["event"] for e in entries] == _RECORDED_TYPES
    for entry in entries:
        assert set(entry) == {"event", "recording_began_at", "statement"}
        assert entry["statement"]
        if entry["event"] == "gate_fired" and not entry["recording_began_at"]:
            # This test writes no gate (a gate needs a candidate, which
            # needs the tenant's switch on — `test_receipt_gates.py`). On a
            # tenant where none has ever fired — CI's fresh database, every
            # tenant with the switch off — "not yet" is the true answer, and
            # it must be said in words, not as an earlier record to look for.
            # It passed on test19 only because spec 57 had fired gates there.
            assert entry["statement"].startswith("No receipt gate has fired"), \
                entry["statement"]
            assert "message log" not in entry["statement"], entry["statement"]
            continue
        assert entry["recording_began_at"], (
            "this suite has just written a `%s` on this tenant, so recording "
            "has begun" % entry["event"])
        # An instant, not a sentence: a consumer compares events against it.
        datetime.datetime.fromisoformat(entry["recording_began_at"])
        assert entry["statement"].startswith("From "), entry["statement"]
    # The statement that was made false by this handoff, and reworded — in
    # WORDS. Its first rewording pointed the reader at "`fidelity.events`",
    # and a standing in-registry test refused it: these sentences are shown
    # to a client on a screen, and a field name is not something a client
    # can read.
    verification = fidelity["verification"]
    assert "each time it is pressed" in verification
    assert "cannot be edited or deleted" in verification
    assert "fidelity." not in verification and "`" not in verification


def test_the_fidelity_block_is_on_an_asset_with_no_events_of_its_own(
        client, test_location):
    """`recording_began_at` is a fact about the DATABASE, not the asset.

    The question it answers is *"could an event on this asset have been
    recorded and wasn't?"* — so an asset nothing has happened to needs it
    exactly as much as one with a long history, and an array that was only
    present when populated could not be told from a server that predates it.
    """
    asset = _new_asset(client, test_location, "pytest-events-fidelity-empty")
    history = _history(client, asset["id"])
    assert _recorded(history) == []
    assert [e["event"] for e in history["fidelity"]["events"]] == \
        _RECORDED_TYPES


# ─── a maintenance request's reference ───────────────────────────────

def test_a_request_reference_is_published_to_whoever_may_read_requests(
        client, test_asset, test_request, me):
    """Handoff 30 §D1 — shaped by the caller's scopes, and SAID to be.

    The reference was withheld from everybody, on the grounds that a route
    cannot see its caller's scopes. That was false (GO-LIVE §14.1). It is
    published to a holder of `requests:read`, which is who a request belongs
    to, and withheld from a caller who holds only `assets:read` — with
    `reference_withheld` saying so, so that a null reads as WITHHELD and not
    as a request that has no reference.

    `test_request` is raised against `test_asset` by the fixtures, so the
    data exists on any tenant and this never skips for want of it. Which
    HALF runs is a fact about the tenant's credential: this suite has one
    credential and no way to mint a narrower one, so on a tenant whose
    client holds `admin` — `test19`, and CI — the withheld half is not
    exercised over HTTP. It is held in the registry, where the builder takes
    the decision as an argument.
    """
    history = _history(client, test_asset["id"])
    raised = [e for e in _events(history, "maintenance_request")
              if e["record"] == {"model": "request.request",
                                 "id": test_request["id"]}]
    assert len(raised) == 1, (
        "the request the fixtures raised against this asset is not in its "
        "history")
    event = raised[0]
    assert set(event["detail"]) == {"reference", "reference_withheld"}
    if _holds(me, "requests:read"):
        assert event["detail"]["reference_withheld"] is False
        assert event["detail"]["reference"] == test_request["reference"]
        assert test_request["reference"] in event["summary"]
    else:
        assert event["detail"]["reference_withheld"] is True
        assert event["detail"]["reference"] is None
        assert test_request["reference"] not in event["summary"], (
            "the reference was withheld from `detail` and printed in the "
            "summary")
    # Either way it is the request's existence that is published, never its
    # content, and the record it rests on is an ordinary editable one.
    assert event["evidence"] == "editable_record"


# ─── building, floor and room ────────────────────────────────────────

def test_the_location_hierarchy_is_refused_on_create_and_creates_nothing(
        client, test_location, any_location):
    """POST — `building_id`, `floor_id`, `room_id` are no longer writable.

    Rule 3: the refusal is said, never silent — and since handoff 31 it is
    said with a 400, before anything is created. Until then this was a 201:
    the asset was registered WITHOUT the building the caller sent, and the
    three names sat in `_warnings.rejected_fields` of a response most callers
    had stopped reading at the status line.

    A create has no record to read back, so "nothing was written" is asked of
    the list — and the CONTROL is what makes that answer mean something: the
    same name, sent without the three fields, is created and found.
    """
    name = f"pytest-events-hierarchy-post-{uuid.uuid4().hex[:8]}"
    assert ids_matching(client, "/api/v1/assets", name) == []
    r = client.post("/api/v1/assets", json={
        "name": name, "category_id": 1, "location_id": test_location["id"],
        **{f: any_location for f in _HIERARCHY_FIELDS}})
    details = assert_fields_refused(r, *_HIERARCHY_FIELDS)
    assert "location_id" in details["writable"], (
        "the repair — move it with `location_id` — is not in the response")
    assert ids_matching(client, "/api/v1/assets", name) == [], (
        "the hierarchy was refused with a 400 and the asset was created "
        "anyway")

    control = _new_asset(client, test_location, name)
    assert ids_matching(client, "/api/v1/assets", name) == [control["id"]]
    assert control["current_location"]["id"] == test_location["id"]


def test_the_location_hierarchy_is_refused_on_patch_and_writes_neither_half(
        client, test_location, any_location):
    """PATCH — the bug this closes answered 200 and contradicted itself.

    `PATCH {"building_id": …}` rewrote the building — and with it the
    published address and coordinates, which are computed from it — and
    moved NOTHING, because `location_id` follows the building only through a
    form onchange the API never runs. The movement record correctly said no
    move had happened; the asset's own address said otherwise.

    Handoff 30 refused the three fields and still wrote the `notes` beside
    them: *refused, not rejected whole*. Handoff 31 reversed that half, and
    this test with it. A body that is partly wrong is refused WHOLE, because
    a caller told 400 will fix the body and send all of it again — and a
    caller told 200 never learns that half of what it sent was dropped.
    """
    asset = _new_asset(client, test_location, "pytest-events-hierarchy-patch")
    r = client.patch(f"/api/v1/assets/{asset['id']}", json={
        **{f: any_location for f in _HIERARCHY_FIELDS},
        "notes": "the one writable field in this request"})
    assert_fields_refused(r, *_HIERARCHY_FIELDS)
    after = _asset(client, asset["id"])
    assert after["notes"] == asset["notes"], (
        "the request was refused and its writable half was written anyway")
    for key in ("location_hierarchy", "current_location", "address_display",
                "coordinates"):
        assert after[key] == asset[key], (
            f"`{key}` changed on a request that was refused")
    moves = [e for e in _events(_history(client, asset["id"]), "location_moved")
             if e["detail"]["from_location"]]
    assert moves == []


@pytest.mark.parametrize("field", _HIERARCHY_FIELDS)
def test_the_location_hierarchy_is_still_a_filter(client, test_asset, field):
    """Not writable is not the same as not there. Reading is untouched.

    An id nothing can carry, so the assertion is that the parameter FILTERS:
    a 200 alone would pass just as well if the list had started ignoring it
    and answering with the whole register, which is the failure handoff 21
    was about. `test_asset` is only here so the register is known not to be
    empty to begin with.
    """
    assert test_asset["id"]
    r = client.get("/api/v1/assets", params={field: 999999999, "limit": 1})
    assert assert_envelope_ok(r)["data"] == [], (
        f"`?{field}=` did not narrow the list")
