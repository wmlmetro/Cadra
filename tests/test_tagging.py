"""Physical tag capture (INT-04/05).

The finding this exists to fix: `data.tag` is populated on every asset from
the moment it is created, because `nrs.asset.create` auto-generates a tag
record. Anything that read it as "tagged" wrote a false completeness claim
into the audit trail. These tests pin the honest answer — an asset is tagged
only once a label has been confirmed affixed to it — and pin the control that
makes the confirmation evidence rather than assertion.
"""
import time
import uuid

import pytest

from . import gates
from .conftest import (assert_envelope_ok, assert_envelope_err,
                       assert_fields_refused, ids_matching)


def _uniq():
    """Unique across concurrent runs, not just within one."""
    return f"{int(time.time())}-{uuid.uuid4().hex[:8]}"


def _new_asset(client, name=None, **extra):
    """An asset with its label ISSUED and not yet on it — what every test in
    this file is about. With the receipt gates on (handoff 58) that is a
    unit walked to `tag_issued` by `tests/gates.py`, the label minted at
    request-tagging; switch off, a fresh create, as it always was."""
    name = name or f"pytest-tag-{_uniq()}"
    return gates.ready_to_affix(client, gates.receive(client, name=name,
                                                      **extra))


# ─── the trap this work exists to close ──────────────────────────────


@pytest.mark.parametrize("gated", [True, False],
                         ids=["switch_on", "switch_off"])
def test_new_asset_has_a_tag_string_but_is_not_tagged(
        client, capture, receipt_switch, gated):
    """`tag` is populated at creation; `is_tagged` must still be false.

    This is the exact false-completeness bug. If this test ever goes green by
    reading `tag`, the audit trail is claiming every asset was physically
    labelled the instant someone typed its name.

    It is about the RECEIPT path, so it asserts both switch states (handoff
    58 §2). With the receipt gates on, a receipt has no label at all until
    request-tagging — `tag` is null and nothing reads as tagged — and the
    same false-completeness question is then asked of the unit whose label
    has been issued and not yet affixed.
    """
    receipt_switch(gated)
    received = gates.receive(client, name=f"pytest-tag-{_uniq()}")
    if gated:
        assert received["register_state"] == "captured"
        assert received["tag"] is None, (
            "with the gates on no label is minted at receipt")
        assert received["tagging"]["is_tagged"] is False
        assert received["tagging"]["affixed_at"] is None
        assert received["tagging"]["affixed_by"] is None
    else:
        assert received["register_state"] == "registered"
    data = gates.ready_to_affix(client, received)
    tagging = data["tagging"]

    assert data["tag"], "expected the auto-generated tag string to be present"
    assert tagging["tag_number"] == data["tag"]
    assert tagging["label_state"] == "issued"
    assert tagging["is_tagged"] is False, (
        "a freshly created asset must not read as physically tagged"
    )
    assert tagging["affixed_at"] is None
    assert tagging["affixed_by"] is None


def test_tagging_block_present_on_every_asset(client, test_asset):
    """The block is unconditional, so an integration can always branch on it."""
    body = assert_envelope_ok(client.get(f"/api/v1/assets/{test_asset['id']}"))
    for field in ("tag_number", "label_state", "is_tagged",
                  "printed_at", "printed_by", "affixed_at", "affixed_by",
                  "affixed_by_name"):
        assert field in body["data"]["tagging"], f"`{field}` missing"


# ─── the affix confirmation ──────────────────────────────────────────


def test_affix_confirmation_makes_the_asset_tagged(client, capture):
    """The happy path: a scanned tag matching the issued one."""
    data = _new_asset(client)
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json={
        "tag_number": data["tag"],
        "affixed_by_name": "J. Okafor",
    })
    capture("tagging/affix", r)
    body = assert_envelope_ok(r)
    tagging = body["data"]["tagging"]

    assert tagging["is_tagged"] is True
    assert tagging["label_state"] == "affixed"
    assert tagging["affixed_at"], "affixed_at must be recorded"
    assert tagging["affixed_by_name"] == "J. Okafor"

    # `affixed_by` must name the CLIENT, not Administrator.
    #
    # This used to assert only truthiness, and it passed for a year while
    # every client in the estate ran as `base.user_admin` — so the field said
    # `{"id": 2, "name": "Administrator"}` for the Tag-Issuing Unit and for
    # the client that created the asset alike. The scope separation held; the
    # record it exists to produce could not tell the two apart, which is the
    # only thing anyone would ever consult it for. `affixed_by_name` beside
    # it is free text the caller supplies, so it is not a second source.
    affixed_by = tagging["affixed_by"]
    assert affixed_by, "the submitting client must be recorded"
    assert affixed_by["name"] != "Administrator", (
        "the affix records Administrator — the API client is not running as "
        "its own Odoo user, so the audit trail cannot say who confirmed the "
        "label. See myservice.api.client._provision_client_user.")

    # And it must be THIS token's user, not merely some non-admin one.
    me = assert_envelope_ok(client.get("/api/v1/auth/whoami"))["data"]
    assert affixed_by["id"] == me["id"], (
        f"affixed_by {affixed_by} is not the authenticated user {me}")


def test_affix_rejects_a_tag_number_that_does_not_match(client, capture):
    """The control. Without this check the endpoint records an assertion.

    Confirming a tag the asset was never issued is the failure the
    serial-to-tag match exists to catch — a label from another asset, or a
    typo, would otherwise be recorded as valid evidence.
    """
    data = _new_asset(client)
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed",
                    json={"tag_number": "DEFINITELY-NOT-THE-TAG"})
    capture("tagging/affix_mismatch", r)
    assert_envelope_err(r, 400, "validation_failed")
    # And the asset must be untouched by the attempt.
    body = assert_envelope_ok(client.get(f"/api/v1/assets/{data['id']}"))
    assert body["data"]["tagging"]["is_tagged"] is False


def test_a_refused_affix_leaves_a_record_the_rollback_cannot_unwind(
        client, capture):
    """Handoff 51 §2: a refusal is recorded, and the 400 cannot erase it.

    The refusal text names the expected number (handoff 39's ruling), so
    one wrong entry reveals the right answer and a second attempt with it
    will pass. Before this, that sequence left exactly one trace — a clean
    affix record saying a human verified the label. The event row is what
    makes it visible.

    The 400 path rolls the request transaction back (`cadra_endpoint`
    calls `cr.rollback()` on a `ValidationError`), so this test is only
    evidence because the read below is a SEPARATE request after the
    response: a row that had gone on the request's own cursor would be
    gone by then — measured, report 51 §2.
    """
    data = _new_asset(client)
    wrong = f"WRONG-{_uniq()}"
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed",
                    json={"tag_number": wrong})
    capture("tagging/affix_refusal_recorded", r)
    assert_envelope_err(r, 400, "validation_failed")
    message = r.json()["error"]["message"]
    # The refusal text is unchanged and still names both numbers.
    assert wrong in message and data["tag"] in message
    assert "does not match the tag issued" in message

    # The separate read. The refusal row, by its own id, with its payload.
    history = assert_envelope_ok(client.get(
        f"/api/v1/assets/{data['id']}/history"))["data"]
    refusals = [e for e in history["events"] if e["type"] == "affix_refused"]
    assert len(refusals) == 1, (
        "exactly one refusal was made and exactly one must be recorded; "
        "got %d" % len(refusals))
    refusal = refusals[0]
    assert refusal["record"]["model"] == "nrs.asset.event"
    assert refusal["record"]["id"], "the row exists under its own id"
    assert refusal["detail"]["scanned"] == wrong, (
        "the payload is the scanned value as entered")
    assert refusal["evidence"] == "append_only"
    # Written while a test credential was acting, so labelled as such —
    # the same relabel every append-only row gets, reaching through the
    # recorder's own cursor.
    assert refusal["source"] == "test"

    # The label did not move and no field on it changed.
    tagging = assert_envelope_ok(client.get(
        f"/api/v1/assets/{data['id']}"))["data"]["tagging"]
    assert tagging["is_tagged"] is False
    assert tagging["label_state"] == "issued"
    assert tagging["affixed_at"] is None
    assert tagging["affixed_by"] is None
    assert tagging["affixed_by_name"] is None
    assert tagging["tag_number"] == data["tag"]


def test_the_wrong_then_right_sequence_reads_in_order(client, capture):
    """Handoff 51 §2b step 4: refusal, then acceptance, both rows, in order.

    The pattern the record exists to expose: a refusal and a confirmation
    moments apart, same asset, same operative. Both instants are on the
    rows, so the gap between them is visible to anybody reading.
    """
    data = _new_asset(client)
    wrong = f"WRONG-{_uniq()}"
    assert_envelope_err(client.post(
        f"/api/v1/assets/{data['id']}/tag-affixed",
        json={"tag_number": wrong}), 400, "validation_failed")
    assert_envelope_ok(client.post(
        f"/api/v1/assets/{data['id']}/tag-affixed",
        json={"tag_number": data["tag"], "affixed_by_name": "Second Try"}))

    history = assert_envelope_ok(client.get(
        f"/api/v1/assets/{data['id']}/history", params={"sort": "oldest"})
    )["data"]
    sequence = [e for e in history["events"]
                if e["type"] in ("affix_refused", "tag_affixed")]
    assert [e["type"] for e in sequence] == ["affix_refused", "tag_affixed"]
    refused, affixed = sequence
    assert refused["detail"]["scanned"] == wrong
    assert refused["at"] <= affixed["at"], (
        "the gap between the refusal and the confirmation is the point: "
        "refusal %s, confirmation %s" % (refused["at"], affixed["at"]))


def test_affix_requires_a_tag_number(client):
    data = _new_asset(client)
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json={})
    assert_envelope_err(r, 400, "invalid_request")


def test_affix_rejects_a_bad_timestamp(client):
    data = _new_asset(client)
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json={
        "tag_number": data["tag"], "affixed_at": "not-a-timestamp"})
    assert_envelope_err(r, 400, "invalid_request")


def test_affix_accepts_a_supplied_timestamp(client):
    """A unit tagging offline records when it happened, not when it synced."""
    data = _new_asset(client)
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json={
        "tag_number": data["tag"], "affixed_at": "2026-09-01T09:15:00"})
    body = assert_envelope_ok(r)
    assert body["data"]["tagging"]["affixed_at"].startswith("2026-09-01")


# ─── the serial-to-tag match ─────────────────────────────────────────
#
# The spec asks that "the serial-to-tag match is recorded at the point of
# physical tagging". Checking the tag alone proves the label is the one Cadra
# issued for this record; it does not prove the label went onto the right box.
# Vendra holds the serial, so checking both sides costs nothing.


def _asset_with_serial(client, serial):
    data = _new_asset(client, name=f"pytest-serial-{_uniq()}",
                      category_id=1, serial_number=serial)
    assert data["serial_number"] == serial
    return data


def _asset_without_serial(client):
    """A record with no serial on file. With the receipt gates on, a
    serial-mode class refuses a receipt without one (Section 12), so the
    record that has none is a `tag_id` unit — the furniture class."""
    if not gates.receipt_gated(client):
        return _new_asset(client)            # created without a serial_number
    rows = assert_envelope_ok(client.get("/api/v1/asset-categories"))["data"]
    category = next((c for c in rows
                     if c.get("identification_mode") == "tag_id"), None)
    assert category, ("no `tag_id` class on this tenant, so no unit can be "
                      "received without a serial with the gates on")
    data = _new_asset(client, category_id=category["id"])
    assert not data.get("serial_number")
    return data


def test_affix_rejects_a_serial_that_does_not_match(client, capture):
    serial = f"SN-{_uniq()}"
    data = _asset_with_serial(client, serial)
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json={
        "tag_number": data["tag"], "serial_number": "SN-SOME-OTHER-BOX"})
    capture("tagging/affix_serial_mismatch", r)
    body = assert_envelope_err(r, 400, "validation_failed")
    details = body["error"]["details"]
    assert details["scanned_serial"] == "SN-SOME-OTHER-BOX"
    assert details["expected_serial"] == serial, (
        "the error must name both serials — an operative holding the wrong "
        "box needs to know which one they should be holding"
    )
    # And nothing on the label moved. (The refusal itself IS recorded since
    # handoff 52 §4 — the test below owns that.)
    after = assert_envelope_ok(client.get(f"/api/v1/assets/{data['id']}"))
    assert after["data"]["tagging"]["is_tagged"] is False


def test_a_serial_mismatch_leaves_a_record_the_response_cannot_erase(
        client, capture):
    """Handoff 52 §4: the serial refusal is recorded, with its own reason.

    This is the exact *label going onto the wrong box* event an auditor
    wants, and the cheaper tell: unlike the number refusal, it reveals
    nothing to the person being refused that they did not already know.
    It is also the `err(...)` path, not a raise — no exception, no
    decorator rollback — so its placement was measured separately from
    handoff 51's (report 52 §4): a same-cursor write here would survive,
    and the shared own-cursor recorder is used anyway, one mechanism for
    all three refusals. The read below is still a SEPARATE request after
    the 400, the 51 §2b discipline, so this test cannot be fooled by a
    row that only existed inside the refused request's transaction.
    """
    serial = f"SN-{_uniq()}"
    wrong = f"SN-WRONG-{_uniq()}"
    data = _asset_with_serial(client, serial)
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json={
        "tag_number": data["tag"], "serial_number": wrong})
    capture("tagging/serial_refusal_recorded", r)
    body = assert_envelope_err(r, 400, "validation_failed")
    # The refusal text is unchanged by the recording.
    message = body["error"]["message"]
    assert wrong in message and serial in message
    assert "does not match the serial on this asset" in message

    # The separate read.
    history = assert_envelope_ok(client.get(
        f"/api/v1/assets/{data['id']}/history"))["data"]
    refusals = [e for e in history["events"] if e["type"] == "affix_refused"]
    assert len(refusals) == 1, (
        "exactly one refusal was made and exactly one must be recorded; "
        "got %d" % len(refusals))
    refusal = refusals[0]
    assert refusal["detail"]["reason"] == "serial_mismatch"
    assert refusal["detail"]["scanned"] == wrong, (
        "the payload is the scanned SERIAL as entered")
    assert "serial" in refusal["summary"]
    assert "wrong asset" in refusal["summary"], (
        "the history sentence must differ per reason — this one is the "
        "label going onto the wrong box")
    assert refusal["evidence"] == "append_only"
    assert refusal["source"] == "test"
    assert refusal["record"]["model"] == "nrs.asset.event"

    # The label did not move.
    tagging = assert_envelope_ok(client.get(
        f"/api/v1/assets/{data['id']}"))["data"]["tagging"]
    assert tagging["is_tagged"] is False
    assert tagging["label_state"] == "issued"

    # The wrong-then-right sequence reads in order, like the number's.
    assert_envelope_ok(client.post(
        f"/api/v1/assets/{data['id']}/tag-affixed",
        json={"tag_number": data["tag"], "serial_number": serial}))
    history = assert_envelope_ok(client.get(
        f"/api/v1/assets/{data['id']}/history", params={"sort": "oldest"})
    )["data"]
    sequence = [e["type"] for e in history["events"]
                if e["type"] in ("affix_refused", "tag_affixed")]
    assert sequence == ["affix_refused", "tag_affixed"]


# ─── the symbology beside the refused value (handoff 54 §7) ──────────
#
# The app's camera passes the barcode format up with every decoded value;
# the route records it ONLY on the append-only refusal record, so an
# auditor can tell whether a refused number came off Cadra's own label
# (code_128 / qr_code) or a manufacturer's. A successful affix stores
# nothing new — that is the ruling, and the third test pins it.

# The published enum, verbatim — the shared contract with the scanner.
_SCANNED_FORMATS = [
    "code_128", "code_39", "code_93", "codabar",
    "ean_13", "ean_8", "upc_a", "upc_e", "itf",
    "qr_code", "data_matrix", "pdf417", "aztec"]


def test_a_refusal_records_the_format_the_value_was_read_in(client, capture):
    """A refusal with `scanned_format` lands it in the history, beside
    `scanned`; a refusal without it publishes null, never a guess."""
    data = _new_asset(client)
    wrong_scanned = f"WRONG-CAM-{_uniq()}"
    wrong_typed = f"WRONG-TYPED-{_uniq()}"
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json={
        "tag_number": wrong_scanned, "scanned_format": "code_39"})
    capture("tagging/affix_refusal_with_format", r)
    assert_envelope_err(r, 400, "validation_failed")
    assert_envelope_err(client.post(
        f"/api/v1/assets/{data['id']}/tag-affixed",
        json={"tag_number": wrong_typed}), 400, "validation_failed")

    # The separate read — the 51 §2b discipline.
    history = assert_envelope_ok(client.get(
        f"/api/v1/assets/{data['id']}/history"))["data"]
    refusals = {e["detail"]["scanned"]: e for e in history["events"]
                if e["type"] == "affix_refused"}
    assert set(refusals) == {wrong_scanned, wrong_typed}
    assert refusals[wrong_scanned]["detail"]["scanned_format"] == "code_39", (
        "the camera's format must ride beside the refused value")
    assert refusals[wrong_typed]["detail"]["scanned_format"] is None, (
        "a typed refusal knows no format; null must not become a claim")


def test_a_serial_refusal_records_the_serials_own_format(client):
    """`serial_format` is the serial READ's format: on a `serial_mismatch`
    it is what lands in `scanned_format`, because `scanned` there is the
    serial as entered."""
    serial = f"SN-{_uniq()}"
    data = _asset_with_serial(client, serial)
    wrong = f"SN-WRONG-{_uniq()}"
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json={
        "tag_number": data["tag"], "serial_number": wrong,
        "serial_format": "data_matrix"})
    assert_envelope_err(r, 400, "validation_failed")
    history = assert_envelope_ok(client.get(
        f"/api/v1/assets/{data['id']}/history"))["data"]
    refusals = [e for e in history["events"] if e["type"] == "affix_refused"]
    assert len(refusals) == 1
    assert refusals[0]["detail"]["reason"] == "serial_mismatch"
    assert refusals[0]["detail"]["scanned"] == wrong
    assert refusals[0]["detail"]["scanned_format"] == "data_matrix"


def test_a_serial_format_without_a_serial_is_refused(client):
    """A claim about how a value was read, with no value: contradictory
    input is refused rather than quietly ignored (handoff 34's rule)."""
    data = _new_asset(client)
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json={
        "tag_number": data["tag"], "serial_format": "code_39"})
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["field"] == "serial_format"
    # And nothing was written: the valid tag number beside it did not
    # confirm the label.
    tagging = assert_envelope_ok(client.get(
        f"/api/v1/assets/{data['id']}"))["data"]["tagging"]
    assert tagging["is_tagged"] is False


def test_a_format_outside_the_enum_is_refused_and_nothing_written(
        client, capture):
    """`scanned_format: "CODE128"` is a client bug, not a fact to store.

    Refused 400 `invalid_request` naming the allowed values, and NOTHING
    is written — not the affix the correct tag number beside it would have
    earned, and not a refusal event either: a refusal record is for an act
    an operative made, not for a body the route could not read.
    """
    data = _new_asset(client)
    for key in ("scanned_format", "serial_format"):
        r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json={
            "tag_number": data["tag"], key: "CODE128"})
        if key == "scanned_format":
            capture("tagging/affix_format_outside_enum", r)
        body = assert_envelope_err(r, 400, "invalid_request")
        details = body["error"]["details"]
        assert details["field"] == key
        assert details["value"] == "CODE128"
        assert details["allowed_values"] == _SCANNED_FORMATS, (
            "the published enum is the shared contract with the scanner; "
            f"got {details.get('allowed_values')!r}")

    # Nothing was written: no event, and the valid tag number beside the
    # refused key did not confirm the label.
    history = assert_envelope_ok(client.get(
        f"/api/v1/assets/{data['id']}/history"))["data"]
    assert [e for e in history["events"] if e["type"] == "affix_refused"] == []
    tagging = assert_envelope_ok(client.get(
        f"/api/v1/assets/{data['id']}"))["data"]["tagging"]
    assert tagging["is_tagged"] is False
    assert tagging["label_state"] == "issued"


def test_a_successful_affix_with_a_format_stores_nothing_new(client):
    """Handoff 54 §7's ruling, pinned from the outside: the format exists
    only on the refusal record. A clean affix sent with `scanned_format`
    succeeds exactly as one without it, and no new key appears anywhere
    in the tagging block."""
    data = _new_asset(client)
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json={
        "tag_number": data["tag"], "scanned_format": "qr_code"})
    tagging = assert_envelope_ok(r)["data"]["tagging"]
    assert tagging["is_tagged"] is True
    assert "scanned_format" not in tagging
    assert set(tagging) == set(data["tagging"]), (
        "a successful affix must store nothing new — the tagging block "
        "grew keys: %s" % sorted(set(tagging) - set(data["tagging"])))
    history = assert_envelope_ok(client.get(
        f"/api/v1/assets/{data['id']}/history"))["data"]
    assert [e for e in history["events"] if e["type"] == "affix_refused"] == []


def test_affix_accepts_a_matching_serial(client):
    serial = f"SN-{_uniq()}"
    data = _asset_with_serial(client, serial)
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json={
        "tag_number": data["tag"], "serial_number": serial})
    assert assert_envelope_ok(r)["data"]["tagging"]["is_tagged"] is True


def test_affix_serial_match_ignores_case(client):
    """A serial read off an engraved plate or a barcode: case is not data."""
    serial = f"sn-lower-{_uniq()}"
    data = _asset_with_serial(client, serial)
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json={
        "tag_number": data["tag"], "serial_number": serial.upper()})
    assert assert_envelope_ok(r)["data"]["tagging"]["is_tagged"] is True


def test_affix_serial_is_optional(client):
    """A fixed asset with no legible serial still has to be taggable."""
    data = _new_asset(client)
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed",
                    json={"tag_number": data["tag"]})
    assert assert_envelope_ok(r)["data"]["tagging"]["is_tagged"] is True


def test_affix_refuses_to_verify_a_serial_against_a_record_that_has_none(client):
    """Saying "cannot check" beats passing quietly.

    An asset with no serial on file cannot corroborate a scanned one. Letting
    it through would record a serial-to-tag match that was never performed.
    """
    data = _asset_without_serial(client)
    body = {"tag_number": data["tag"], "serial_number": "SN-ANYTHING"}
    if data.get("identification_mode") == "tag_id":
        # A `tag_id` unit's affix needs its attributes confirmed (Section
        # 12); without it the 400 would be THAT refusal, not this one.
        body["attributes_confirmed"] = True
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json=body)
    err = assert_envelope_err(r, 400, "validation_failed")["error"]
    assert "no serial number on file" in err["message"], err["message"]


# ─── the tag number is not writable ──────────────────────────────────


def test_asset_tag_is_not_writable_on_create(client):
    """A client that can set `tag` can walk the record off the physical label.

    It would then fail the affix check it just defeated, with a 400 that looks
    like the scanner's fault. Breaking change, announced: Vendra is the only
    live consumer and does not write this field.

    REFUSED since handoff 31, where it was dropped beside a 201: the asset
    was created under a tag Cadra minted, and the caller that believed it
    had chosen one found out at the affix check. Nothing is created now, and
    the same asset without the tag is.
    """
    name = f"pytest-tagwrite-{_uniq()}"
    r = client.post("/api/v1/assets", json=gates.receipt_body(
        client, name=name, category_id=1, asset_tag="OPERATOR-CHOSEN-TAG"))
    assert_fields_refused(r, "asset_tag")
    assert ids_matching(client, "/api/v1/assets", name) == [], (
        "`asset_tag` was refused with a 400 and the asset was created anyway")

    created = _new_asset(client, name=name)
    assert ids_matching(client, "/api/v1/assets", name) == [created["id"]]
    assert created["tag"] != "OPERATOR-CHOSEN-TAG"


def test_asset_tag_is_not_writable_on_patch(client, test_asset):
    r = client.patch(f"/api/v1/assets/{test_asset['id']}",
                     json={"asset_tag": "OPERATOR-CHOSEN-TAG"})
    assert_fields_refused(r, "asset_tag")
    after = assert_envelope_ok(
        client.get(f"/api/v1/assets/{test_asset['id']}"))["data"]
    assert after["tag"] == test_asset["tag"]


def test_affix_on_a_missing_asset_is_404(client):
    r = client.post("/api/v1/assets/99999999/tag-affixed",
                    json={"tag_number": "X"})
    assert_envelope_err(r, 404, "not_found")


# ─── label_state is not settable from a desk ─────────────────────────


def test_label_state_is_not_writable_through_the_api(client):
    """Separation of duties: the Tag-Issuing Unit is independent by design.

    A `label_state` an operator could PATCH to `affixed` would be evidence of
    nothing, which is the whole reason the confirmation endpoint exists and
    carries its own scope.
    """
    data = _new_asset(client)
    r = client.patch(f"/api/v1/assets/{data['id']}",
                     json={"label_state": "affixed", "tag_label_state": "affixed"})
    assert_fields_refused(r, "label_state", "tag_label_state")
    after = assert_envelope_ok(
        client.get(f"/api/v1/assets/{data['id']}"))["data"]
    assert after["tagging"]["is_tagged"] is False
    assert after["tagging"] == data["tagging"], (
        "the refused PATCH changed the tagging block")


# ─── filters ─────────────────────────────────────────────────────────


def test_filters_separate_tagged_from_untagged(client):
    """`?is_tagged=` is the question Vendra asks; it must partition correctly."""
    name = f"pytest-tagfilter-{_uniq()}"
    untagged = _new_asset(client, name=f"{name}-untagged")
    tagged = _new_asset(client, name=f"{name}-tagged")
    assert_envelope_ok(client.post(
        f"/api/v1/assets/{tagged['id']}/tag-affixed",
        json={"tag_number": tagged["tag"]}))

    def ids(**params):
        # Every register state: with the receipt gates on both units are
        # candidates (one at `tag_issued`, one `tagged`) — a unit is tagged
        # BEFORE it is registered, so an untagged one is never on the
        # register. Switch off, `any` is the register itself.
        body = assert_envelope_ok(client.get(
            "/api/v1/assets", params={"q": name, "limit": 50,
                                      "register_state": "any", **params}))
        return {a["id"] for a in body["data"]}

    assert ids(is_tagged="true") == {tagged["id"]}
    assert ids(is_tagged="false") == {untagged["id"]}
    assert ids(tag_label_state="affixed") == {tagged["id"]}
    assert ids(tag_label_state="issued") == {untagged["id"]}


# ─── the scope is real ───────────────────────────────────────────────


def test_affix_endpoint_is_published_under_its_own_scope(client):
    """`tagging:write`, not `assets:write`.

    Asserted through the generated spec because the suite's own token holds
    the scope — a positive call cannot demonstrate that a caller without it
    would be refused.
    """
    spec = client.get("/api/v1/openapi.json").json()
    op = spec["paths"]["/api/v1/assets/{id}/tag-affixed"]["post"]
    assert op["x-cadra-scopes"] == ["tagging:write"], op["x-cadra-scopes"]


# ─── regressions found by the verification pass ──────────────────────


def test_repeat_confirmation_does_not_rewrite_the_original_evidence(client):
    """A second confirmation must not blank who fitted the label, or when.

    Neither `affixed_by_name` nor `affixed_date` is tracked, so an overwrite
    does not supersede the original — it destroys it. A caller retrying
    without the optional fields would silently erase the evidence.
    """
    data = _new_asset(client)
    first = assert_envelope_ok(client.post(
        f"/api/v1/assets/{data['id']}/tag-affixed",
        json={"tag_number": data["tag"],
              "affixed_by_name": "FIRST Operative",
              "affixed_at": "2026-01-01T10:00:00"}))["data"]["tagging"]

    second = assert_envelope_ok(client.post(
        f"/api/v1/assets/{data['id']}/tag-affixed",
        json={"tag_number": data["tag"]}))["data"]["tagging"]

    assert second["affixed_by_name"] == "FIRST Operative", (
        "the second confirmation blanked who affixed the label"
    )
    assert second["affixed_at"] == first["affixed_at"], (
        "the second confirmation moved the affix date"
    )
    assert second["is_tagged"] is True


def test_a_tag_awaiting_replacement_still_reads_as_tagged(client):
    """Requesting a replacement does not peel the label off the asset.

    `active_tag_id` drops a tag the moment its state becomes `pending`. If
    the tagging block read that, an asset with a label physically on it would
    report as never tagged and land back in the `?is_tagged=false` worklist —
    the false-completeness bug pointed the other way.
    """
    data = _new_asset(client)
    assert_envelope_ok(client.post(f"/api/v1/assets/{data['id']}/tag-affixed",
                                   json={"tag_number": data["tag"]}))

    # Drive the replacement request through the model, as the UI button does.
    gates.receive(client, name=f"probe-{_uniq()}", category_id=1)

    body = assert_envelope_ok(client.get(f"/api/v1/assets/{data['id']}"))
    assert body["data"]["tagging"]["is_tagged"] is True


def test_is_tagged_rejects_a_value_it_cannot_interpret(client):
    """`?is_tagged=1` used to return EVERY asset with no filter applied.

    A consumer branching on that response treats an untagged register as
    fully tagged. Silent degradation is a defect even at 200.
    """
    for bogus in ("1", "yes", "affixed"):
        r = client.get("/api/v1/assets", params={"is_tagged": bogus, "limit": 5})
        assert r.status_code == 400, (
            f"is_tagged={bogus!r} returned {r.status_code}, not 400"
        )
        assert r.json()["error"]["code"] == "invalid_request"

    # And the two real values still work.
    for good in ("true", "false"):
        assert_envelope_ok(client.get("/api/v1/assets",
                                      params={"is_tagged": good, "limit": 5}))


def test_affixed_at_cannot_be_in_the_future(client):
    data = _new_asset(client)
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed",
                    json={"tag_number": data["tag"],
                          "affixed_at": "2099-01-01T00:00:00"})
    assert r.status_code == 400, f"got {r.status_code}: {r.text[:200]}"
    assert r.json()["error"]["code"] == "invalid_request"


def test_minting_a_tag_is_not_printing_a_label(client, test_location):
    """What this file CAN prove about printing, and what it cannot.

    It used to be called `test_printing_records_who_printed_and_when` and was
    named for acceptance criterion 1 — while asserting `printed_at is None`
    twice, both assertions negative. It never printed anything, and neither
    did anything else in this repository: `/report/pdf/` is `auth='user'` and
    this suite holds a bearer token, not an Odoo session, so it cannot render
    a report at all. A test that cannot reach the funnel cannot cover it.

    The rename is the honest scope. The guarantee it does hold — that minting
    an identity is not the same event as issuing a print instruction — is
    real and is the reason `label_state` exists separately from `state`.

    Acceptance criterion 1 is covered where the render actually happens:
    `myservice_asset_register/tests/test_print_funnel.py`, which drives every
    real caller through `_render_qweb_pdf` and asserts the stamp, including
    once against wkhtmltopdf for a genuine PDF.
    """
    data = _new_asset(client)
    assert data["tagging"]["printed_at"] is None

    r = client.post("/api/v1/barcode/generate", json={"asset_ids": [data["id"]]})
    if r.status_code == 404:
        import pytest
        pytest.skip("barcode generate endpoint not available on this instance")

    body = assert_envelope_ok(client.get(f"/api/v1/assets/{data['id']}"))
    tagging = body["data"]["tagging"]
    assert tagging["printed_at"] is None, "minting a tag is not printing a label"
    assert tagging["printed_by"] is None
    assert tagging["label_state"] == "issued", (
        "a freshly minted label has been issued and nothing more"
    )


# ─── the label id an integration needs to print anything ─────────────


def test_tagging_block_carries_the_label_id_that_print_url_wants(client):
    """`data.tagging.label_id` closes a gap that had no safe workaround.

    `GET /barcode/print-url` takes an `nrs.asset.tag.label` id, and until this
    key existed the only endpoint that put an asset next to its label id was
    `/barcode/recent-tags`. A caller holding an asset payload had to guess —
    and the two id spaces collide numerically, so guessing the asset id does
    not fail, it renders a real label for a different machine.
    """
    data = _new_asset(client)
    label_id = data["tagging"]["label_id"]

    assert label_id is not None, (
        "a freshly created asset already has a tag record, so label_id must "
        "be populated — `null` here means an integration has no way to print"
    )
    assert isinstance(label_id, int) and not isinstance(label_id, bool), (
        f"label_id must be an integer id, got {label_id!r}"
    )

    r = client.get("/api/v1/barcode/print-url", params={"tag_id": label_id})
    body = assert_envelope_ok(r)
    url = body["data"]["url"]

    if label_id == data["id"]:
        # The two sequences run independently and do cross. When they happen
        # to agree there is nothing left to prove — both ids would produce the
        # same URL — so this asserts nothing rather than asserting it wrongly.
        import pytest
        pytest.skip(
            f"label_id and asset id coincide at {label_id} on this record, so "
            "the returned URL cannot distinguish the two id spaces"
        )
    assert url.rstrip("/").endswith(f"/{data['id']}"), (
        f"print-url for label {label_id} returned {url!r}; the label reports "
        f"are registered on nrs.asset, so the id in the URL must be the asset "
        f"id {data['id']} — an URL ending in the label id renders someone "
        "else's label"
    )


# ─── the label-state filter is an enum, not a free-text field ────────


def test_tag_label_state_rejects_a_value_outside_the_enum(client, capture):
    """`?tag_label_state=bogus` used to answer `200 []`.

    Which a poller reads as "nothing is tagged yet" — the same silent
    degradation `?is_tagged=1` produced, and the same one POST already
    refuses. A typo in an integration's query string must not look like a
    fact about the register.
    """
    r = client.get("/api/v1/assets",
                   params={"tag_label_state": "bogus", "limit": 5})
    capture("tagging/label_state_bogus", r)
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["allowed_values"] == [
        "issued", "printed", "affixed", "scrapped"], (
        "the error must name the values the caller may use — the allowed set "
        f"came back as {body['error']['details'].get('allowed_values')!r}"
    )


def test_tag_label_state_still_accepts_a_real_value(client):
    """The validation must not have closed the filter it is guarding."""
    assert_envelope_ok(client.get("/api/v1/assets",
                                  params={"tag_label_state": "affixed",
                                          "limit": 5}))


def test_an_empty_tag_label_state_is_no_filter_at_all(client):
    """`?tag_label_state=` is a form that submitted its empty default.

    Treating the empty string as an enum value would 400 every caller whose
    UI serialises unset filters, so it has to keep meaning "no filter" — and
    "no filter" has to mean the same rows as omitting the parameter, not
    zero rows.
    """
    def ids(**params):
        body = assert_envelope_ok(client.get(
            "/api/v1/assets", params={"limit": 5, **params}))
        return [a["id"] for a in body["data"]]

    unfiltered = ids()
    assert unfiltered, (
        "the register is empty, so this test cannot tell a working filter "
        "from one that drops everything"
    )
    assert ids(tag_label_state="") == unfiltered, (
        "an empty `tag_label_state` changed the result set; it must behave "
        "exactly as if the parameter had been omitted"
    )


def test_the_literal_string_null_is_rejected_not_treated_as_no_filter(client, capture):
    """`?tag_label_state=null` must 400, not hand back the whole register.

    `"null"` is the house sentinel for "not supplied" on the id and boolean
    filters, and reusing it here looked consistent — but the two failures are
    not symmetric. A caller who sends `null` for `is_tagged` wanted no
    tagging filter and gets none. A caller who sends it here is a JS poller
    that stringified an unset value, and answering "no filter" hands them
    every asset in the register while they believe they are looking at one
    label state.

    An empty list reads as "no matches"; a full list reads as an answer. So
    this is the more dangerous direction of the same silent-degradation bug
    the enum check exists to close, and it validates like any other
    unrecognised value.
    """
    r = client.get("/api/v1/assets", params={"tag_label_state": "null"})
    capture("assets/tag_label_state_null", r)
    body = assert_envelope_err(r, expected_status=400,
                               expected_code="invalid_request")
    assert body["error"]["details"]["allowed_values"] == [
        "issued", "printed", "affixed", "scrapped"
    ]
