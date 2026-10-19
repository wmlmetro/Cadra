"""Identify from photo — handoff 64 §2 and §5.2–§5.3, over HTTP, on the fake.

Ruling R11: Cadra's server asks a vision model what a photographed item is,
and a person confirms. Every test here runs on the TEST STAND-IN provider
(`fake`), which answers from the photo's file name (`ai_provider.FakeProvider`
says how), so no photo leaves the machine and no key is involved. The
stand-in may be chosen only on a database marked `test`; the suite only
runs on one.

What is proved:

* the route, field by field — the class (a tenant class, with confidence and
  two alternatives), the attributes, the condition, the text read, the
  photo held for an asset not yet saved, the usage and the notice;
* the SAP candidates: the records, each with its reason, for a holder of
  `sap_mirror:read`; the count and nothing else for the Store Officer;
* each refusal in words — switched off, neither or both photo parts, a
  non-image, the provider timing out, failing or declining, a malformed
  answer discarded AND counted, the daily cap;
* the audit trail: a save with 4 accepted and 1 changed, the record on the
  answer, the history line, the photo claimed; and a suggestion nobody saved
  leaving nothing on any asset.

The tenant's own settings are put back after every test (`ai_on`).
"""
import base64
import struct
import time
import uuid
import zlib
import importlib.util
import pathlib

import pytest
import requests

from . import gates
from .conftest import assert_envelope_err, assert_envelope_ok

AI = "/api/v1/settings/ai-identify"
IDENTIFY = "/api/v1/ai/identify"

_SHAPES = (pathlib.Path(__file__).resolve().parent.parent
           / "myservice_asset_register" / "tests" / "sap_export_shapes.py")
_spec = importlib.util.spec_from_file_location("sap_export_shapes_64", _SHAPES)
shapes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shapes)


def _chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def png(width=40, height=30, seed=0):
    row = bytes((seed + x) % 256 for x in range(width * 3))
    raw = b"".join(b"\x00" + row for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height,
                                          8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b""))


PDF = (b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog>>endobj\n"
       b"trailer<</Root 1 0 R>>\n%%EOF\n")


def _u():
    return uuid.uuid4().hex[:6].upper()


def _settings(client):
    return assert_envelope_ok(client.get(AI))["data"]


@pytest.fixture
def ai_on(client):
    """The switch on, on the stand-in, for the test; the tenant's own
    settings after."""
    was = _settings(client)
    r = client.patch(AI, json={"provider": "fake", "enabled": True,
                               "daily_cap": 100000})
    assert_envelope_ok(r)
    try:
        yield
    finally:
        assert_envelope_ok(client.patch(AI, json={
            "enabled": False, "provider": was["provider"],
            "daily_cap": was["daily_cap"]}))
        if was["enabled"]:
            client.patch(AI, json={"enabled": True})


def _identify(client, *, data=None, filename="chair-01.png", photo_id=None,
              source="web", token=None, headers=None):
    files = {"file": (filename, data, "image/png")} if data is not None \
        else None
    fields = {}
    if photo_id is not None:
        fields["photo_id"] = str(photo_id)
    if source and data is not None:
        fields["source"] = source
    if files is None:
        # A multipart body with no file part: `requests` needs one entry
        # in `files` to send multipart at all.
        files = {k: (None, v) for k, v in fields.items()}
        fields = None
    if token is None:
        return client.post(IDENTIFY, files=files, data=fields,
                           headers=headers or {})
    return requests.post(client.base + IDENTIFY, files=files, data=fields,
                         timeout=60, headers=dict(
                             headers or {}, Authorization=f"Bearer {token}"))


def _calls_today(client):
    return _settings(client)["today"]["calls"]


def _categories(client):
    return {c["id"]: c for c in
            assert_envelope_ok(client.get("/api/v1/asset-categories"))["data"]}


# ── the switch and the settings ──────────────────────────────────────

def test_switched_off_the_route_refuses_and_writes_nothing(client):
    s = _settings(client)
    if s["enabled"]:
        pytest.skip("the tenant has identification switched on")
    before = s["today"]["calls"]
    r = _identify(client, data=png())
    body = assert_envelope_err(r, 403, "forbidden")
    assert body["error"]["details"]["reason"] == "switched_off"
    assert "switched off" in body["error"]["message"]
    assert _calls_today(client) == before
    # Every screen learns the switch from /settings, and is told nothing
    # else it could draw a button from.
    published = assert_envelope_ok(client.get("/api/v1/settings"))["data"]
    assert published["ai_identify"]["enabled"] is False


def test_the_settings_never_return_the_key_and_refuse_to_take_one(client):
    s = _settings(client)
    assert "key" not in s and "api_key" not in s
    assert isinstance(s["key_placed"], bool)
    assert s["key_command"].startswith("scripts/set_ai_key.sh ")
    r = client.patch(AI, json={"api_key": "sk-not-a-key"})
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["rejected_fields"] == ["api_key"]
    assert "owner" in body["error"]["details"]["hint"]
    assert "sk-not-a-key" not in r.text


def test_the_real_provider_cannot_be_switched_on_without_a_key(client):
    s = _settings(client)
    if s["key_placed"]:
        pytest.skip("a key is placed on this tenant")
    r = client.patch(AI, json={"provider": "anthropic", "enabled": True})
    body = assert_envelope_err(r, 400, "validation_failed")
    assert body["error"]["details"]["reason"] == "provider_not_ready"
    assert "set_ai_key.sh" in body["error"]["message"]
    assert _settings(client)["enabled"] is s["enabled"]


def test_the_patch_answers_with_what_it_wrote(client):
    """Found by the live-check dry run: the PATCH read the settings back
    with raw SQL before its own write was flushed, and answered with the
    values from BEFORE it."""
    was = _settings(client)
    target = 499 if was["daily_cap"] != 499 else 498
    try:
        got = assert_envelope_ok(client.patch(
            AI, json={"daily_cap": target, "effort": "medium"}))["data"]
        assert (got["daily_cap"], got["effort"]) == (target, "medium")
    finally:
        assert_envelope_ok(client.patch(AI, json={
            "daily_cap": was["daily_cap"], "effort": was["effort"]}))


def test_settings_values_are_checked(client):
    for body, field in (({"daily_cap": 0}, "daily_cap"),
                        ({"timeout_seconds": 600}, "timeout_seconds"),
                        ({"effort": "max"}, "effort"),
                        ({"provider": "openai"}, "provider"),
                        ({"model": "two words"}, "model"),
                        ({"enabled": "yes"}, "enabled")):
        r = client.patch(AI, json=body)
        got = assert_envelope_err(r, 400, "validation_failed")
        assert got["error"]["details"]["field"] == field, body


# ── the route, field by field ────────────────────────────────────────

def test_a_new_photo_is_identified_field_by_field(client, ai_on):
    cats = _categories(client)
    before = _calls_today(client)
    data = png(seed=1)
    r = _identify(client, data=data, filename="chair-01.png")
    s = assert_envelope_ok(r, 201)["data"]
    assert isinstance(s["suggestion_id"], int)
    assert s["provider"] == "fake" and s["model"] == "cadra-fake-1"
    assert s["prompt_version"]
    # The class is one of THIS tenant's, named, with two alternatives.
    cat = s["category"]
    assert cat["id"] in cats and cat["name"] == cats[cat["id"]]["name"]
    assert 0 <= cat["confidence"] <= 1
    assert len(cat["alternatives"]) == min(2, len(cats) - 1)
    assert all(a["id"] in cats and a["id"] != cat["id"]
               for a in cat["alternatives"])
    a = s["attributes"]
    assert a["name"] == "HIGH BACK EXECUTIVE SWIVEL CHAIR"
    assert (a["colour"], a["material"]) == ("BLACK", "LEATHER")
    # Not legible, not stated: never guessed.
    assert a["make"] is None and a["model_name"] is None
    assert a["dimensions"] is None
    assert s["condition"] == {"value": "good", "note": None}
    assert s["text_read"] == []
    # Held for an asset not yet saved.
    assert s["photo"]["kind"] == "pending" and s["photo"]["expires_at"]
    assert s["usage"]["input_tokens"] > 0
    assert s["usage"]["output_tokens"] > 0
    assert s["notice"].startswith("Photograph the item, not people.")
    assert s["is_test_fixture"] is True
    assert _calls_today(client) == before + 1


def test_unserviceable_is_poor_with_a_note_and_text_is_read(client, ai_on):
    r = _identify(client, data=png(seed=2),
                  filename="printer-brand-sn-cn12345-unserviceable.png")
    s = assert_envelope_ok(r, 201)["data"]
    assert s["condition"] == {"value": "poor", "note": "unserviceable"}
    kinds = {(t["text"], t["looks_like"]) for t in s["text_read"]}
    assert ("CN12345", "serial_like") in kinds
    assert ("HP", "brand") in kinds and ("LASERJET M404", "model") in kinds
    # Legible, so proposed.
    assert (s["attributes"]["make"], s["attributes"]["model_name"]) == (
        "HP", "LASERJET M404")


def test_a_stored_photo_is_identified_by_its_id(client, ai_on):
    asset = gates.receive(client, name=f"pytest-ai-photo-{_u()}")
    up = client.post(f"/api/v1/assets/{asset['id']}/photos",
                     files={"file": ("desk-02.png", png(seed=3),
                                     "image/png")},
                     data={"source": "web"})
    photo = assert_envelope_ok(up, 201)["data"]
    r = _identify(client, photo_id=photo["id"])
    s = assert_envelope_ok(r, 201)["data"]
    assert s["photo"] == {"kind": "asset_photo", "id": photo["id"],
                          "asset_id": asset["id"]}


# ── SAP candidates: the records for a reader, the count for the rest ──

@pytest.fixture(scope="module")
def sap_tag(client):
    """One SAP record carrying an old tag, imported as the administrator."""
    from .test_sap_mirror import _import
    u = _u()
    office = f"Q{u}"
    run = _import(client, [shapes.record(
        f"2A{u}001", tag=f"FIRS/{office}/0001",
        description="HIGH BACK EXECUTIVE SWIVEL CHAIR")])
    assert run["state"] == "done", run
    return office


def test_sap_candidates_for_a_reader_and_the_count_for_others(
        client, ai_on, sap_tag):
    name = f"chair-firs-{sap_tag.lower()}-0001.png"
    r = _identify(client, data=png(seed=4), filename=name)
    s = assert_envelope_ok(r, 201)["data"]
    assert {"text": f"FIRS/{sap_tag}/0001",
            "looks_like": "firs_tag_like"} in s["text_read"]
    sap = s["sap_candidates"]
    assert sap["basis"] == "old_tag"
    assert sap["query"]["old_tag"] == f"FIRS/{sap_tag}/0001"
    assert sap["count"] >= 1 and sap["items"]
    top = sap["items"][0]
    assert top["old_tag"] == f"FIRS/{sap_tag}/0001"
    assert top["reason_code"].startswith("old_tag") and top["reason"]
    assert len(sap["items"]) <= 5

    # The Store Officer may write assets and may not read the mirror.
    token = gates._token(client, "storekeeper")
    r = _identify(client, data=png(seed=5), filename=name, token=token)
    s = assert_envelope_ok(r, 201)["data"]
    assert s["sap_candidates"]["items"] is None
    assert s["sap_candidates"]["count"] >= 1
    assert "sap_mirror:read" in s["sap_candidates"]["note"]


# ── the refusals ─────────────────────────────────────────────────────

def test_neither_or_both_photo_parts_is_refused(client, ai_on):
    before = _calls_today(client)
    r = _identify(client)
    assert_envelope_err(r, 400, "invalid_request")
    r = client.post(IDENTIFY, files={"file": ("a.png", png(), "image/png")},
                    data={"source": "web", "photo_id": "1"})
    assert_envelope_err(r, 400, "invalid_request")
    assert _calls_today(client) == before


def test_a_non_image_is_refused_before_the_provider_is_asked(client, ai_on):
    before = _calls_today(client)
    r = _identify(client, data=PDF, filename="chair.jpg")
    body = assert_envelope_err(r, 415, "validation_failed")
    assert body["error"]["details"]["detected"] == "application/pdf"
    assert _calls_today(client) == before


@pytest.mark.parametrize("hint,reason,status", [
    ("timeout", "provider_timeout", 503),
    ("error", "provider_error", 503),
    ("refuse", "provider_declined", 503),
    ("malformed", "answer_discarded", 502),
])
def test_a_failed_call_is_refused_in_words_and_counted(
        client, ai_on, hint, reason, status):
    before = _calls_today(client)
    r = _identify(client, data=png(seed=6), filename=f"chair-{hint}.png")
    body = assert_envelope_err(r, status, "internal_error")
    assert body["error"]["message"] == (
        "The photo could not be identified just now; fill the details by "
        "hand.")
    assert body["error"]["details"]["reason"] == reason
    # A call was made: it counts, and its record exists — but nothing of a
    # malformed answer is shown.
    assert isinstance(body["error"]["details"]["suggestion_id"], int)
    assert _calls_today(client) == before + 1
    assert "category" not in r.text


def test_the_daily_cap_refuses_in_words(client, ai_on):
    calls = _calls_today(client)
    assert_envelope_ok(client.patch(AI, json={"daily_cap": max(1, calls)}))
    if calls == 0:
        assert_envelope_ok(_identify(client, data=png(seed=7)), 201)
    r = _identify(client, data=png(seed=8))
    body = assert_envelope_err(r, 429, "rate_limited")
    cap = max(1, calls)
    assert body["error"]["message"] == (
        f"Today's {cap} identifications are used; fill the details by hand.")
    assert body["error"]["details"]["reason"] == "daily_cap"


# ── the audit trail ──────────────────────────────────────────────────

def _history(client, asset_id):
    return assert_envelope_ok(
        client.get(f"/api/v1/assets/{asset_id}/history"))["data"]


def _suggested_lines(client, asset_id):
    return [e for e in _history(client, asset_id)["events"]
            if e["type"] == "details_suggested"]


def test_a_save_records_four_accepted_and_one_changed(client, ai_on):
    data = png(seed=9)
    s = assert_envelope_ok(_identify(client, data=data,
                                     filename="chair-03.png"), 201)["data"]
    a = s["attributes"]
    # The person keeps the class, the name (retyped in lower case — still
    # accepted), the colour and the material, and corrects the condition.
    body = gates.receipt_body(
        client, category_id=s["category"]["id"], name=a["name"].lower(),
        colour=a["colour"], material=a["material"], condition="fair",
        ai_suggestion={"id": s["suggestion_id"]})
    r = client.post("/api/v1/assets", json=body)
    saved = assert_envelope_ok(r, 201)["data"]
    applied = saved["ai_suggestion"]
    assert applied["id"] == s["suggestion_id"]
    assert applied["counts"] == {"accepted": 4, "changed": 1, "ignored": 0}
    assert applied["fields"]["condition"] == {
        "outcome": "changed", "from": "good", "to": "fair"}
    for f in ("category_id", "name", "colour", "material"):
        assert applied["fields"][f]["outcome"] == "accepted", f

    # The photo it came from is now the asset's first photo.
    photos = assert_envelope_ok(client.get(
        f"/api/v1/assets/{saved['id']}/photos"))["data"]["items"]
    assert [p["filename"] for p in photos if p["kind"] == "photo"] == [
        "chair-03.png"]

    # The history says it in one line.
    lines = _suggested_lines(client, saved["id"])
    assert len(lines) == 1
    assert lines[0]["summary"] == (
        "Details suggested from a photo; 4 accepted, 1 changed.")
    assert lines[0]["detail"]["ai_suggestion_id"] == s["suggestion_id"]
    assert lines[0]["detail"]["counts"]["changed"] == 1

    # A suggestion is applied once.
    again = gates.receipt_body(client, name=f"pytest-ai-again-{_u()}",
                               ai_suggestion={"id": s["suggestion_id"]})
    r = client.post("/api/v1/assets", json=again)
    body = assert_envelope_err(r, 409, "conflict")
    assert body["error"]["details"]["reason"] == "already_applied"


def test_ignored_fields_are_recorded_as_ignored(client, ai_on):
    asset = gates.receive(client, name=f"pytest-ai-patch-{_u()}")
    up = client.post(f"/api/v1/assets/{asset['id']}/photos",
                     files={"file": ("chair-04.png", png(seed=10),
                                     "image/png")},
                     data={"source": "web"})
    photo = assert_envelope_ok(up, 201)["data"]
    s = assert_envelope_ok(_identify(client, photo_id=photo["id"]),
                           201)["data"]
    # Use this: the colour only. The name is shown and dismissed.
    r = client.patch(f"/api/v1/assets/{asset['id']}", json={
        "colour": s["attributes"]["colour"],
        "ai_suggestion": {"id": s["suggestion_id"], "ignored": ["name"]}})
    applied = assert_envelope_ok(r)["data"]["ai_suggestion"]
    assert applied["fields"]["colour"]["outcome"] == "accepted"
    assert applied["fields"]["name"]["outcome"] == "ignored"
    assert applied["counts"]["accepted"] == 1
    assert applied["counts"]["changed"] == 0


def test_an_unsaved_suggestion_leaves_nothing_on_any_asset(client, ai_on):
    asset = gates.receive(client, name=f"pytest-ai-unsaved-{_u()}")
    up = client.post(f"/api/v1/assets/{asset['id']}/photos",
                     files={"file": ("chair-05.png", png(seed=11),
                                     "image/png")},
                     data={"source": "web"})
    photo = assert_envelope_ok(up, 201)["data"]
    before = assert_envelope_ok(client.get(
        f"/api/v1/assets/{asset['id']}"))["data"]
    assert_envelope_ok(_identify(client, photo_id=photo["id"]), 201)
    after = assert_envelope_ok(client.get(
        f"/api/v1/assets/{asset['id']}"))["data"]
    for f in ("name", "category_id", "colour", "material", "condition",
              "make", "model_name", "dimensions"):
        assert after.get(f) == before.get(f), f
    assert _suggested_lines(client, asset["id"]) == []


def test_a_suggestion_cannot_be_saved_onto_another_asset(client, ai_on):
    one = gates.receive(client, name=f"pytest-ai-one-{_u()}")
    two = gates.receive(client, name=f"pytest-ai-two-{_u()}")
    up = client.post(f"/api/v1/assets/{one['id']}/photos",
                     files={"file": ("chair-06.png", png(seed=12),
                                     "image/png")},
                     data={"source": "web"})
    photo = assert_envelope_ok(up, 201)["data"]
    s = assert_envelope_ok(_identify(client, photo_id=photo["id"]),
                           201)["data"]
    before = assert_envelope_ok(client.get(
        f"/api/v1/assets/{two['id']}"))["data"]["colour"]
    r = client.patch(f"/api/v1/assets/{two['id']}", json={
        "colour": "MAGENTA", "ai_suggestion": {"id": s["suggestion_id"]}})
    body = assert_envelope_err(r, 400, "validation_failed")
    assert body["error"]["details"]["reason"] == "other_asset"
    assert assert_envelope_ok(client.get(
        f"/api/v1/assets/{two['id']}"))["data"]["colour"] == before


def test_a_bad_ai_suggestion_block_writes_nothing(client, ai_on):
    asset = gates.receive(client, name=f"pytest-ai-bad-{_u()}")
    for block, status, code in (
            ({"id": "x"}, 400, "validation_failed"),
            ({"id": 1, "fields": {}}, 400, "validation_failed"),
            ({"id": 1, "ignored": ["sap_asset_number"]}, 400,
             "validation_failed"),
            ({"id": 2_000_000_000}, 404, "not_found")):
        r = client.patch(f"/api/v1/assets/{asset['id']}", json={
            "colour": "MAGENTA", "ai_suggestion": block})
        assert_envelope_err(r, status, code)
    got = assert_envelope_ok(client.get(
        f"/api/v1/assets/{asset['id']}"))["data"]
    assert got.get("colour") != "MAGENTA"
