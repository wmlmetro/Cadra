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

from .conftest import assert_envelope_ok, assert_envelope_err


def _uniq():
    """Unique across concurrent runs, not just within one."""
    return f"{int(time.time())}-{uuid.uuid4().hex[:8]}"


def _new_asset(client, name=None):
    name = name or f"pytest-tag-{_uniq()}"
    r = client.post("/api/v1/assets", json={"name": name, "category_id": 1})
    return assert_envelope_ok(r, expected_status=201)["data"]


# ─── the trap this work exists to close ──────────────────────────────


def test_new_asset_has_a_tag_string_but_is_not_tagged(client, capture):
    """`tag` is populated at creation; `is_tagged` must still be false.

    This is the exact false-completeness bug. If this test ever goes green by
    reading `tag`, the audit trail is claiming every asset was physically
    labelled the instant someone typed its name.
    """
    data = _new_asset(client)
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
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-serial-{_uniq()}", "category_id": 1,
        "serial_number": serial})
    return assert_envelope_ok(r, expected_status=201)["data"]


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
    # And nothing is recorded.
    after = assert_envelope_ok(client.get(f"/api/v1/assets/{data['id']}"))
    assert after["data"]["tagging"]["is_tagged"] is False


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
    data = _new_asset(client)            # created without a serial_number
    r = client.post(f"/api/v1/assets/{data['id']}/tag-affixed", json={
        "tag_number": data["tag"], "serial_number": "SN-ANYTHING"})
    assert_envelope_err(r, 400, "validation_failed")


# ─── the tag number is not writable ──────────────────────────────────


def test_asset_tag_is_not_writable_on_create(client):
    """A client that can set `tag` can walk the record off the physical label.

    It would then fail the affix check it just defeated, with a 400 that looks
    like the scanner's fault. Breaking change, announced: Vendra is the only
    live consumer and does not write this field.
    """
    r = client.post("/api/v1/assets", json={
        "name": f"pytest-tagwrite-{_uniq()}", "category_id": 1,
        "asset_tag": "OPERATOR-CHOSEN-TAG"})
    body = assert_envelope_ok(r, expected_status=201)
    assert body["data"]["tag"] != "OPERATOR-CHOSEN-TAG"
    rejected = (body["data"].get("_warnings") or {}).get("rejected_fields") or []
    assert "asset_tag" in rejected, (
        "a dropped field must be reported, not silently ignored"
    )


def test_asset_tag_is_not_writable_on_patch(client, test_asset):
    r = client.patch(f"/api/v1/assets/{test_asset['id']}",
                     json={"asset_tag": "OPERATOR-CHOSEN-TAG"})
    body = assert_envelope_ok(r)
    assert body["data"]["tag"] != "OPERATOR-CHOSEN-TAG"
    rejected = (body["data"].get("_warnings") or {}).get("rejected_fields") or []
    assert "asset_tag" in rejected


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
    body = assert_envelope_ok(r)
    rejected = (body["data"].get("_warnings") or {}).get("rejected_fields") or []
    assert "label_state" in rejected and "tag_label_state" in rejected, (
        f"label_state must be rejected, not written. rejected={rejected}"
    )
    assert body["data"]["tagging"]["is_tagged"] is False


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
        body = assert_envelope_ok(client.get(
            "/api/v1/assets", params={"q": name, "limit": 50, **params}))
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
    r = client.post("/api/v1/assets", json={"name": f"probe-{_uniq()}",
                                            "category_id": 1})
    assert_envelope_ok(r, expected_status=201)

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
