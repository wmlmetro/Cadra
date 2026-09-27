"""`GET /assets/<id>/history` over the API — handoff 27, INT-10.

The ordering, the join and the honesty rules are asserted against the builder
in `myservice_api/tests/test_asset_history.py`, where time can be frozen and
a reconstructed link can be made. What is asserted HERE is what only a real
request can show: that the route publishes that builder inside the envelope,
that a real custody transfer and a real move made over HTTP come back as
events with the grades the contract promises, and that a bad `sort` is a 400
rather than a default.

`evidence` is asserted for the same reason `test_custody.py` asserts
`source`: it is what tells an append-only link from a line in a message log,
and a reader has to be able to see that without knowing to ask.
"""
import pytest

from .conftest import (assert_envelope_err, assert_envelope_ok,
                       assert_fields_refused)

_GRADES = ["append_only", "system_stamp", "guarded_record",
           "editable_record", "chatter"]

_EVENT_KEYS = {"id", "type", "title", "summary", "at", "at_precision",
               "actor", "actor_name", "evidence", "reconstructed", "source",
               "record", "detail"}


def _history(client, asset_id, **params):
    r = client.get(f"/api/v1/assets/{asset_id}/history", params=params)
    return r, assert_envelope_ok(r)["data"]


def _new_asset(client, test_location, name):
    """An asset of this test's own, so its history is exactly what we did.

    The session-scoped `test_asset` is moved about by every other module; a
    count asserted against it would be asserting about their order.
    """
    r = client.post("/api/v1/assets", json={
        "name": name,
        "category_id": 1,  # as the session `test_asset` fixture does
        "location_id": test_location["id"]})
    return assert_envelope_ok(r, expected_status=201)["data"]


def _assert_registration_is_oldest(client, asset_id):
    """Nothing may be listed as older than the registration it followed.

    These tests register an asset and act on it within the same second, which
    is exactly the case that sorted wrongly: a whole-second timestamp compared
    raw against `create_date`'s microseconds put the act BEFORE the asset
    existed. Seen on the screen in handoff 27 before any test saw it.
    """
    _, oldest = _history(client, asset_id, sort="oldest")
    assert oldest["events"][0]["type"] == "registered"
    _, newest = _history(client, asset_id)
    assert newest["events"][-1]["type"] == "registered"


def _two_employees(client):
    r = client.get("/api/v1/identity/employees", params={"limit": 2})
    rows = (r.json().get("data") or []) if r.status_code == 200 else []
    return (rows[0]["id"], rows[1]["id"]) if len(rows) >= 2 else None


def test_history_is_published_in_the_envelope(client, test_asset, capture):
    """GET /api/v1/assets/<id>/history — the shape, on a lived-in asset."""
    r, data = _history(client, test_asset["id"])
    capture("assets/history", r)
    assert data["asset"]["id"] == test_asset["id"]
    assert data["order"] == "newest_first"
    assert set(data) == {"asset", "order", "summary", "fidelity", "events"}
    assert data["summary"]["statement"]
    assert data["summary"]["events"] == len(data["events"])
    for event in data["events"]:
        assert set(event) == _EVENT_KEYS
        assert event["evidence"] in _GRADES


def test_the_boundary_arrives_with_the_events(client, test_asset):
    """What it cannot say is on EVERY response, not only an empty one."""
    _, data = _history(client, test_asset["id"])
    fidelity = data["fidelity"]
    assert [g["grade"] for g in fidelity["evidence_grades"]] == _GRADES
    assert all(g["meaning"] for g in fidelity["evidence_grades"])
    named = {n["event"] for n in fidelity["not_recorded"]}
    assert {"financial_change", "sap_change",
            "provenance_change", "deleted_records"} <= named
    assert fidelity["custody"]["statement"]
    assert fidelity["registered_at"]


def test_a_new_asset_says_it_has_no_history_in_words(client, test_location):
    """The defect that produced the handoff was an empty panel."""
    asset = _new_asset(client, test_location, "pytest-history-empty")
    _, data = _history(client, asset["id"])
    assert data["summary"]["events_after_registration"] == 0
    assert data["summary"]["statement"].startswith(
        "There is no recorded history for this asset")
    types = [e["type"] for e in data["events"]]
    assert "registered" in types
    registered = next(e for e in data["events"] if e["type"] == "registered")
    assert registered["evidence"] == "system_stamp"
    # Handoff 08: a client acts as itself, so the registration names it.
    assert registered["actor"] is not None


def test_a_custody_transfer_is_an_append_only_event(
        client, test_location, second_person):
    pair = _two_employees(client)
    if not pair:
        pytest.skip("tenant has no two employees to transfer between")
    asset = _new_asset(client, test_location, "pytest-history-custody")
    # Handoff 35: on a tenant that requires a second person this is a request
    # and an approval rather than one call, and the append-only link is
    # written by the APPROVAL, never by the request. `second_person` is the
    # one place that knows which kind of tenant this is; what is asserted
    # below is unchanged, because the record is meant to be unchanged.
    link_id = second_person.transfer_custody(
        asset["id"], pair[0],
        reason="test_asset_history.custody")["custody_id"]
    _, data = _history(client, asset["id"])
    events = [e for e in data["events"] if e["type"] == "custody_changed"]
    assert len(events) == 1, (
        "`custodian_id` is tracked as well; the chain supersedes that row "
        "and the change must be listed once")
    event = events[0]
    assert event["record"] == {"model": "nrs.asset.custody", "id": link_id}
    assert event["evidence"] == "append_only"
    assert event["reconstructed"] is False
    # See test_custody.py: `test` is `api_transfer` relabelled by the
    # credential. Either is a source; null would mean it stopped travelling.
    assert event["source"] in ("api_transfer", "test")
    assert event["actor"] is not None
    assert event["detail"]["reason"] == "test_asset_history.custody"
    _assert_registration_is_oldest(client, asset["id"])
    assert data["summary"]["events_after_registration"] >= 1
    assert not data["summary"]["statement"].startswith("There is no")


def _real_moves(data):
    """Moves, not the opening "Placed at" — which has no `from`."""
    return [e for e in data["events"] if e["type"] == "location_moved"
            and e["detail"]["from_location"]]


def test_a_move_is_one_event_and_says_what_its_record_is_worth(
        client, test_location, any_location, second_person):
    """A move leaves a movement, a transfer AND a chatter row: one line.

    Handoff 27 asserted `editable_record` here, because a transfer row was
    the best record a move had. Since handoff 28 the move has a record of its
    own, written underneath every writer, and THAT is what it rests on.

    Handoff 35 changed WHO writes it — `action_approve` rather than the route
    — and changed nothing about what is written, which is the property this
    test now also carries: the same three records, the same grade, the same
    reason, whether the move took one person or two.
    """
    if any_location == test_location["id"]:
        pytest.skip("tenant has no second location to move to")
    asset = _new_asset(client, test_location, "pytest-history-move")
    moved = second_person.move(asset["id"], any_location,
                               reason="test_asset_history.move")
    # The append-only record this produced, and the document beside it. Both
    # come back from `/move` directly or off the approved request; the helper
    # normalises the two shapes and the ids are the same rows either way.
    assert moved["movement_id"]
    _, data = _history(client, asset["id"])
    moves = _real_moves(data)
    assert len(moves) == 1
    move = moves[0]
    assert move["evidence"] == "append_only"
    assert move["record"] == {"model": "nrs.asset.movement",
                              "id": moved["movement_id"]}
    # See test_custody.py: `test` is the route's own source (`api_move`, or
    # `approval` when a second person decided) relabelled by the credential
    # that wrote the row.
    assert move["source"] in ("api_move", "approval", "test")
    assert move["detail"]["reason"] == "test_asset_history.move"
    assert move["detail"]["transfer"]["reference"] == moved["transfer_reference"]
    # `nrs.asset.change.request` joins the list when a SECOND PERSON decided
    # the move — handoff 36 §C. On a tenant with approval switched off the
    # same move has three records and no approval block, so the list is
    # asserted against what the tenant actually does rather than pinned to
    # one shape. `records` names the models the event was read FROM, and on
    # an approved move it was genuinely read from four.
    expected_records = ["nrs.asset.movement", "nrs.asset.transfer"]
    if move["detail"].get("approval"):
        expected_records.append("nrs.asset.change.request")
    expected_records.append("mail.message")
    assert move["detail"]["records"] == expected_records, (
        "records must name every model the event was read from")
    # BOTH PEOPLE, on a move that took two. The whole point of the block.
    if move["detail"].get("approval"):
        block = move["detail"]["approval"]
        assert block["requested_by"] and block["approved_by"]
        assert block["requested_by"]["id"] != block["approved_by"]["id"], (
            "an approval is two people, and never the same one twice")
        assert block["evidence"] == "append_only"
    assert move["actor"] is not None
    _assert_registration_is_oldest(client, asset["id"])


def test_a_patched_location_is_recorded_like_any_other_move(
        client, test_location, any_location, second_person):
    """The quiet door — open on one kind of tenant, SHUT on the other.

    Handoff 27 asserted `chatter` here: PATCH moved an asset and left a
    message-log line and nothing else. Handoff 28 did NOT close this door
    and did NOT make it write a transfer; it recorded underneath every door.

    **Handoff 35 closed it, but only where a move needs a second person.**
    PATCH is how the Cadra app's edit form saves, and a whole object arrives
    in it; turning the location half into an approval request and writing the
    rest would leave the caller with a half-applied save and no way to tell
    which half. So the WHOLE body is refused, 400, with `use_instead` naming
    `/move`. On a tenant that has switched the rule off, PATCH still moves
    the asset and this test asserts exactly what it asserted before.

    Both branches assert the same underlying property from opposite sides:
    **whatever happens to `location_id`, the register knows about it.** The
    refusal branch proves the door is shut AND that nothing was written on
    the way to the 400 — which is not free, because `err()` returns a
    response and does not roll a transaction back (CLAUDE.md).
    """
    if any_location == test_location["id"]:
        pytest.skip("tenant has no second location to move to")
    asset = _new_asset(client, test_location, "pytest-history-patch-move")
    r = client.patch(f"/api/v1/assets/{asset['id']}",
                     json={"location_id": any_location})

    if second_person.required:
        details = assert_fields_refused(r, "location_id")
        assert details["approval_required"] is True
        assert "/move" in details["use_instead"]["location_id"]
        assert "location_id" not in details["writable"], (
            "the same response refuses `location_id` and lists it as "
            "writable, so a caller repairing itself from `details.writable` "
            "sends it straight back")
        after = assert_envelope_ok(
            client.get(f"/api/v1/assets/{asset['id']}"))["data"]
        assert after["current_location"]["id"] == test_location["id"], (
            "the PATCH was refused and the asset moved anyway")
        _, data = _history(client, asset["id"])
        assert _real_moves(data) == [], (
            "a refused PATCH left a movement row behind — a permanent, "
            "append-only record of a move that never happened")
        return

    assert_envelope_ok(r)
    _, data = _history(client, asset["id"])
    moves = _real_moves(data)
    assert len(moves) == 1
    assert moves[0]["evidence"] == "append_only"
    assert moves[0]["source"] in ("api_write", "test")
    # A move is not always a transfer, and none is invented for this one.
    assert moves[0]["detail"]["transfer"] is None
    # A LATER request is a later transaction: this is history, not the
    # opening state, and an in-registry test cannot show that — everything
    # there shares one transaction.
    assert data["summary"]["events_after_registration"] >= 1
    _assert_registration_is_oldest(client, asset["id"])


def test_sort_oldest_is_the_exact_reverse(client, test_asset):
    _, newest = _history(client, test_asset["id"])
    _, oldest = _history(client, test_asset["id"], sort="oldest")
    assert oldest["order"] == "oldest_first"
    assert ([e["id"] for e in oldest["events"]]
            == [e["id"] for e in reversed(newest["events"])])
    _, explicit = _history(client, test_asset["id"], sort="newest")
    assert ([e["id"] for e in explicit["events"]]
            == [e["id"] for e in newest["events"]])


def test_a_bad_sort_is_a_400_not_a_default(client, test_asset):
    r = client.get(f"/api/v1/assets/{test_asset['id']}/history",
                   params={"sort": "latest"})
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["allowed_values"] == ["newest", "oldest"]


def test_history_of_an_unknown_asset_is_a_404(client):
    r = client.get("/api/v1/assets/999999999/history")
    assert_envelope_err(r, 404, "not_found")


def test_the_history_has_no_write_endpoint(client, test_asset):
    """It is a reading of other records. There is nothing to POST."""
    r = client.post(f"/api/v1/assets/{test_asset['id']}/history", json={})
    assert r.status_code in (404, 405)


def test_the_history_says_where_the_movement_record_begins(client, test_asset):
    _, data = _history(client, test_asset["id"])
    location = data["fidelity"]["location"]
    assert location["statement"]
    assert location["recording_began_at"], (
        "this suite has moved assets on this tenant, so recording has begun")
    # Created by this session, at a location, under the recorder: its record
    # opens where it was placed, so nothing about it predates the record.
    assert location["located_before_first_movement"] is False
    assert location["movements"] >= 1


def test_verify_records_who_verified(client, test_location, capture):
    """POST /api/v1/assets/<id>/verify — a date AND a person.

    `PATCH {"last_verified_date": …}` has always been able to mark an asset
    verified, and it records no person: `last_verified_by` is not writable,
    on purpose. Until handoff 28 that PATCH was what the Cadra app's own
    Verify button sent.
    """
    asset = _new_asset(client, test_location, "pytest-history-verify")
    assert asset["last_verified_by"] is None
    r = client.post(f"/api/v1/assets/{asset['id']}/verify",
                    json={"notes": "test_asset_history.verify"})
    capture("assets/verify", r)
    data = assert_envelope_ok(r)["data"]
    assert data["verification"]["verified_by"] is not None
    assert data["verification"]["verified_on"]
    assert data["verification"]["notes"] == "test_asset_history.verify"
    assert data["asset"]["last_verified_by"] == data["verification"]["verified_by"]
    assert data["asset"]["is_verified"] is True
    _, history = _history(client, asset["id"])
    verified = [e for e in history["events"] if e["type"] == "verified"]
    # ONE, although the same act also left a message-log line: the record
    # supersedes the tracked `last_verified_date` / `last_verified_by` rows.
    assert len(verified) == 1
    assert verified[0]["actor"]["id"] == data["verification"]["verified_by"]["id"]
    # Handoff 28 asserted `chatter` here, and said why: the route recorded
    # WHO and did not make the record of it any harder to delete. Since
    # handoff 30 each call appends an `nrs.asset.event` nobody can edit or
    # delete, and THAT is what the event rests on — `data.event_id` names it.
    assert verified[0]["evidence"] == "append_only"
    assert verified[0]["record"] == {"model": "nrs.asset.event",
                                     "id": data["event_id"]}


def test_a_patched_verification_date_clears_the_old_verifier(
        client, test_location):
    """VERIFY FIRST, then PATCH. The order is the whole test.

    This test's first version PATCHed a never-verified asset and asserted the
    verifier was null — which it was before the PATCH, so it proved nothing.
    Meanwhile the real sequence left the PREVIOUS verifier standing beside
    the new date: "verified in June, by Alice", who checked nothing in June.
    Caught by the verification pass, with three published sentences already
    saying it could not happen.
    """
    asset = _new_asset(client, test_location, "pytest-history-verify-patch")
    r = client.post(f"/api/v1/assets/{asset['id']}/verify", json={})
    assert assert_envelope_ok(r)["data"]["asset"]["last_verified_by"]
    r = client.patch(f"/api/v1/assets/{asset['id']}",
                     json={"last_verified_date": "2026-01-15"})
    data = assert_envelope_ok(r)["data"]
    assert data["dates"]["last_verified_date"] == "2026-01-15"
    assert data["last_verified_by"] is None, (
        "a date that arrived without a verifier kept the previous one")
    # …and the clearing is itself a line in the history, not a silence.
    #
    # Handoff 28 found it as a `verified` chatter event whose `changes` named
    # `last_verified_by` going to null. Since handoff 30 the PATCH appends an
    # `nrs.asset.event` of its own TYPE — a date that was written, not a
    # verification — and that record supersedes the tracked rows of the same
    # write, so the chatter line is folded away rather than listed beside it.
    # What says the verifier is gone is `verifier_recorded`, on a record
    # nobody can alter, which is a stronger statement than the one it
    # replaces.
    _, history = _history(client, asset["id"])
    written = [e for e in history["events"]
               if e["type"] == "verification_date_set"]
    assert len(written) == 1, (
        "the verifier was cleared and the history does not say so")
    assert written[0]["evidence"] == "append_only"
    assert written[0]["detail"]["verifier_recorded"] is False
    assert written[0]["detail"]["verified_on"] == "2026-01-15"
    assert written[0]["detail"]["previous_verified_on"], (
        "the date it replaced — the real verification's — is not carried")
    # The verification that DID happen is still there, and still one event:
    # the PATCH must not be listed as a second one, nor erase the first.
    verified = [e for e in history["events"] if e["type"] == "verified"]
    assert len(verified) == 1
    assert verified[0]["detail"]["verifier_recorded"] is True


def test_a_second_verification_on_one_day_is_not_invisible(
        client, test_location):
    """Two verifications on one day change no DATE. The verifier's notes do
    not carry over either: they describe a verification, not an asset."""
    asset = _new_asset(client, test_location, "pytest-history-verify-twice")
    client.post(f"/api/v1/assets/{asset['id']}/verify",
                json={"notes": "first check"})
    r = client.post(f"/api/v1/assets/{asset['id']}/verify", json={})
    data = assert_envelope_ok(r)["data"]
    assert data["verification"]["notes"] is None, (
        "a note-less verification returned the previous verifier's notes")


def test_a_client_cannot_name_its_own_verifier(client, test_location):
    """`last_verified_by` is written by `POST /assets/<id>/verify` and by
    nothing a caller sends. Refused — a 400 since handoff 31, where it was a
    200 that dropped the name and wrote the `notes` beside it. A caller that
    believed it had named a verifier is now told it has not, and the note
    that travelled with the claim is not left on the asset as though the
    request had half-succeeded."""
    asset = _new_asset(client, test_location, "pytest-history-verify-claim")
    r = client.patch(f"/api/v1/assets/{asset['id']}",
                     json={"last_verified_by": 1, "notes": "claim"})
    assert_fields_refused(r, "last_verified_by")
    after = assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset['id']}"))["data"]
    assert after["last_verified_by"] is None
    assert after["notes"] == asset["notes"], (
        "the request was refused and its writable half was written anyway")


def test_a_changed_grn_reference_is_recorded_where_nobody_can_alter_it(
        client, test_location):
    """Tracked since handoff 28 — visible, which it was not, and deletable.
    Recorded since handoff 30, because a change to what an auditor reconciles
    against Vendra is exactly the event somebody would want to hide.

    This test was `…is_now_visible_and_is_only_chatter` and asserted the
    `chatter` grade. The name said what was true then."""
    r = client.post("/api/v1/assets", json={
        "name": "pytest-history-provenance", "category_id": 1,
        "location_id": test_location["id"], "grn_reference": "GRN-BEFORE"})
    asset = assert_envelope_ok(r, expected_status=201)["data"]
    r = client.patch(f"/api/v1/assets/{asset['id']}",
                     json={"grn_reference": "GRN-AFTER"})
    assert_envelope_ok(r)
    _, data = _history(client, asset["id"])
    changed = [e for e in data["events"] if e["type"] == "provenance_changed"]
    # ONE: `grn_reference` is still tracked, so the same PATCH also left a
    # message-log row, and the record supersedes it.
    assert len(changed) == 1
    assert changed[0]["evidence"] == "append_only"
    assert changed[0]["record"]["model"] == "nrs.asset.event"
    change = changed[0]["detail"]["changes"][0]
    assert (change["field"], change["old"], change["new"]) == (
        "grn_reference", "GRN-BEFORE", "GRN-AFTER")
    assert changed[0]["actor"] is not None
    named = {n["event"] for n in data["fidelity"]["not_recorded"]}
    # The KEY is unchanged from handoff 27 — renaming a published key is a
    # breaking change. What changed is what it says: no longer "never
    # recorded", but "not recorded before tracking began".
    entry = next(n for n in data["fidelity"]["not_recorded"]
                 if n["event"] == "provenance_change")
    assert "before those fields began to be tracked" in entry["statement"]
    # Present on every database: an upgrade stamps it by migration and a
    # fresh install — which is what CI builds — by `post_init_hook`.
    assert data["fidelity"]["provenance_tracked_from"]


def test_a_movement_this_suite_wrote_says_so(client, test_location,
                                             any_location, second_person):
    """The suite moves real assets, and the record of a move is PERMANENT.

    Same argument as `test_custody.test_a_link_this_suite_wrote_says_so`: that
    is accepted, because a test that does not exercise the recorder proves
    nothing about whether a move is recorded at all. What is not acceptable
    is a reader being unable to tell. `tests/test_source_guards.py` lists
    `nrs.asset.movement` as self-labelling on the strength of this.

    **This is why `second_person` has the suite APPROVE rather than raise.**
    The row is written by `action_approve`, under the approver's user, and
    only a row written under a credential flagged `is_test_credential` gets
    relabelled `test`. Had the suite raised and a human approved, every move
    this suite makes on an approval-required tenant would come back
    `approval` — accurate about the route and silent about the one thing this
    test exists to assert. The full reasoning, and what that arrangement
    costs elsewhere, is in the fixture's own docstring.
    """
    if any_location == test_location["id"]:
        pytest.skip("tenant has no second location to move to")
    asset = _new_asset(client, test_location, "pytest-history-move-label")
    second_person.move(asset["id"], any_location)
    _, data = _history(client, asset["id"])
    sources = {e["source"] for e in data["events"]
               if e["type"] == "location_moved"}
    if sources == {"api_write", "api_move"} or sources == {"approval"}:
        pytest.skip("this credential is not flagged `is_test_credential`; "
                    "its movements are labelled by route, not as artefacts")
    assert sources == {"test"}, (
        "a movement written by the test suite came back as %s. These rows "
        "are permanent and append-only; a reader who was never told this "
        "suite exists must still be able to see that they are artefacts."
        % sorted(sources))


def test_a_refused_move_leaves_nothing_behind(client, test_location, any_location):
    """A 400 must not write. An error RESPONSE does not roll anything back.

    The first draft of handoff 28 checked `reason` after the transfer
    document had been created, so this exact request returned 400 and left a
    transfer in state `done` for a move that never happened.
    """
    if any_location == test_location["id"]:
        pytest.skip("tenant has no second location to move to")
    asset = _new_asset(client, test_location, "pytest-history-refused-move")
    r = client.post(f"/api/v1/assets/{asset['id']}/move",
                    json={"to_location_id": any_location, "reason": 7})
    assert_envelope_err(r, 400, "invalid_request")
    after = assert_envelope_ok(client.get(
        f"/api/v1/assets/{asset['id']}",
        params={"include": "transfers"}))["data"]
    assert after["current_location"]["id"] == test_location["id"]
    assert after["transfers"] == [], (
        "a refused move left a transfer document behind")
    _, history = _history(client, asset["id"])
    assert _real_moves(history) == []
    assert not [e for e in history["events"]
                if e["type"] == "transfer_recorded"]


def test_an_asset_with_no_location_can_be_placed(client, any_location,
                                                 second_person, capture):
    """POST /assets/<id>/move on an asset that is nowhere — reported by the owner.

    It answered 400 *"Required field missing: from_location_id"*: the route
    built an `nrs.asset.transfer` regardless, and that model requires both
    locations. 358 assets on `nrs19` and 1,920 on `jaizbankplc` had no
    location, so none of them could be given one with the Move button. A
    move is not always a transfer: the asset is PLACED, the append-only
    movement records it, and no document is made for a journey from nowhere.
    """
    r = client.post("/api/v1/assets", json={
        "name": "pytest-history-unplaced", "category_id": 1})
    asset = assert_envelope_ok(r, expected_status=201)["data"]
    assert asset["current_location"] is None

    placed_by = second_person.move(asset["id"], any_location,
                                   reason="test_asset_history.placed")
    capture("assets/move_unplaced", placed_by["decision"] or placed_by["raised"])
    assert placed_by["asset"]["current_location"]["id"] == any_location
    # "From nowhere" is not a place, so no document is made — and that is
    # true of BOTH writers: the route skips the transfer when there is no
    # `from_location`, and `action_approve` skips it on the same condition.
    # A test asserting it of only one of them would have left the other free
    # to invent one.
    assert placed_by["transfer_id"] is None, (
        "no document for a journey from nowhere")
    assert placed_by["movement_id"], "the fact is recorded either way"

    after = assert_envelope_ok(client.get(
        f"/api/v1/assets/{asset['id']}", params={"include": "transfers"}))["data"]
    assert after["transfers"] == []

    _, history = _history(client, asset["id"])
    placed = [e for e in history["events"] if e["type"] == "location_moved"]
    assert len(placed) == 1
    assert placed[0]["record"] == {"model": "nrs.asset.movement",
                                   "id": placed_by["movement_id"]}
    assert placed[0]["evidence"] == "append_only"
    assert placed[0]["summary"].startswith("Placed at")
    assert placed[0]["detail"]["reason"] == "test_asset_history.placed"
    assert placed[0]["detail"]["transfer"] is None
    # A LATER request, so this is something that happened to the asset and
    # not part of its registration.
    assert history["summary"]["events_after_registration"] == 1


def test_a_placed_asset_then_moves_with_a_transfer_as_before(
        client, test_location, any_location, second_person):
    """The ordinary case is untouched, and `movement_id` is in both places.

    The "both places" property belongs to `/move`'s own payload — the
    top-level `movement_id` and the copy inside `transfer`, which handoff 28
    left where it was so a consumer reading either kept working. An approved
    request publishes the ids once, on the request, so there is no second
    place for them to disagree; what is asserted there instead is that the
    two rows both exist and that the movement points at the document.
    """
    if any_location == test_location["id"]:
        pytest.skip("tenant has no second location to move to")
    asset = _new_asset(client, test_location, "pytest-history-move-both-keys")
    moved = second_person.move(asset["id"], any_location)
    assert moved["transfer_reference"]
    assert moved["movement_id"]

    if not moved["pending"]:
        data = moved["raised"].json()["data"]
        assert data["movement_id"] == data["transfer"]["movement_id"]
        return

    _, history = _history(client, asset["id"])
    move = _real_moves(history)[0]
    assert move["record"]["id"] == moved["movement_id"]
    assert move["detail"]["transfer"]["id"] == moved["transfer_id"]
    assert move["detail"]["transfer"]["reference"] == moved["transfer_reference"]


def test_placing_an_unplaced_asset_nowhere_real_is_still_refused(client):
    r = client.post("/api/v1/assets", json={
        "name": "pytest-history-unplaced-refused", "category_id": 1})
    asset = assert_envelope_ok(r, expected_status=201)["data"]
    r = client.post(f"/api/v1/assets/{asset['id']}/move",
                    json={"to_location_id": 999999999})
    assert_envelope_err(r, 404, "not_found")
    _, history = _history(client, asset["id"])
    assert not [e for e in history["events"] if e["type"] == "location_moved"]
