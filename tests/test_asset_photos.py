"""Photos on an asset — handoff 61 §5, over HTTP.

`POST /api/v1/assets/<id>/photos` is the first multipart body inside the
envelope, so this file holds the envelope's rules for that shape too: a part
the route does not read is refused like an unknown JSON key, every refusal
says what it refused, and NOTHING is written on any of them — each refusal
test reads the list back to prove it.

The caps are AI-NFR-07's 300 KB per photo and the handoff's fallback of 12
per asset (the NFR names no count); the type is JPEG or PNG judged from the
bytes. The pictures are built here without Pillow (the suite's venv has
none): a PNG from `zlib` and `struct`, a JPEG as a 705-byte constant.

The evidence half runs with the receipt gates ON (`gated`, which puts the
tenant's own value back), because IAD's evidence only exists on a unit that
has been verified: a unit is walked to `vfm_verified` by the demo personas
(`tests/gates.py`), then the list is read as a reader of evidence (the
Auditor) and as a non-reader (the Store Officer, who holds `assets:write`
and `candidates:read` and not `evidence:read`).
"""
import base64
import hashlib
import struct
import time
import uuid
import zlib

import pytest
import requests

from . import gates
from .conftest import (assert_envelope_err, assert_envelope_ok,
                       assert_fields_refused)

SETTINGS_GATE = "/api/v1/settings/receipt-gate"
MAX_BYTES = 300 * 1024

#: 24 × 16, baseline, 705 bytes — made with Pillow once and kept.
JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQY"
    "GBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYa"
    "KCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAAR"
    "CAAQABgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAA"
    "AgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkK"
    "FhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWG"
    "h4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl"
    "5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREA"
    "AgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYk"
    "NOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOE"
    "hYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk"
    "5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDgqKrfYbT/AJ9YP+/Yo+w2n/PrB/37FeZy"
    "4f8Amf8A4Cv/AJI/Suat/Kvvf+RZoqt9htP+fWD/AL9iijlw/wDM/wDwFf8AyQc1b+Vfe/8A"
    "I//Z")
JPEG_SIZE = (24, 16)

PDF = (b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog>>endobj\n"
       b"trailer<</Root 1 0 R>>\n%%EOF\n")
GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9"
       b"\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02"
       b"\x02D\x01\x00;")


def _chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def png(width=8, height=6, *, total=None, seed=0):
    """A real RGB PNG. With `total`, padded to EXACTLY that many bytes by a
    private ancillary chunk (`cdRa`), which a decoder skips and checksums —
    so the file is still a valid PNG at the size the cap is about."""
    row = bytes((seed + x) % 256 for x in range(width * 3))
    raw = b"".join(b"\x00" + row for _ in range(height))
    head = (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height,
                                          8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw)))
    tail = _chunk(b"IEND", b"")
    if total is not None:
        pad = total - len(head) - len(tail) - 12
        assert pad >= 0, "cannot pad a PNG to fewer bytes than it has"
        head += _chunk(b"cdRa", b"\x00" * pad)
    out = head + tail
    assert total is None or len(out) == total
    return out


def _uniq(prefix):
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def gated(client, admin_scope):
    """The receipt gates ON for the test, the tenant's own value after."""
    was = gates.receipt_gated(client)
    assert_envelope_ok(client.patch(SETTINGS_GATE, json={"enabled": True}))
    try:
        yield
    finally:
        assert_envelope_ok(client.patch(SETTINGS_GATE, json={"enabled": was}))


@pytest.fixture
def asset(client):
    """A fresh asset, whatever the switch says (a candidate takes photos
    too, so `receive` is enough)."""
    return gates.receive(client, name=_uniq("pytest-asset-photo"))


def _post(client, asset_id, data, *, filename="photo.png",
          content_type="image/png", token=None, headers=None, **fields):
    fields.setdefault("source", "web")
    url = f"/api/v1/assets/{asset_id}/photos"
    files = {"file": (filename, data, content_type)}
    if token is None:
        return client.post(url, files=files, data=fields,
                           headers=headers or {})
    return requests.post(
        client.base + url, files=files, data=fields, timeout=30,
        headers=dict(headers or {}, Authorization=f"Bearer {token}"))


def _list(client, asset_id, token=None):
    url = f"/api/v1/assets/{asset_id}/photos"
    if token is None:
        r = client.get(url)
    else:
        r = requests.get(client.base + url, timeout=30,
                         headers={"Authorization": f"Bearer {token}"})
    return assert_envelope_ok(r)["data"]


def _photos(client, asset_id):
    return [i for i in _list(client, asset_id)["items"]
            if i["kind"] == "photo"]


# ── up and back ─────────────────────────────────────────────────────────

def test_a_photo_goes_up_and_comes_back_byte_for_byte(client, asset):
    r = _post(client, asset["id"], JPEG, filename="tag-in-frame.jpg",
              content_type="image/jpeg", caption="Tag in frame",
              source="web")
    photo = assert_envelope_ok(r, 201)["data"]
    assert photo["kind"] == "photo"
    assert photo["asset_id"] == asset["id"]
    assert photo["mimetype"] == "image/jpeg"
    assert (photo["width"], photo["height"]) == JPEG_SIZE
    assert photo["size"] == len(JPEG)
    assert photo["sha256"] == hashlib.sha256(JPEG).hexdigest()
    assert photo["caption"] == "Tag in frame"
    assert photo["source"] == "web"
    assert photo["filename"] == "tag-in-frame.jpg"
    assert photo["superseded"] is None
    assert photo["uploaded_by"] and photo["uploaded_by"]["id"]
    assert photo["uploaded_at"]
    # The suite's credential is a test credential: the label is derived.
    assert photo["is_test_fixture"] is True
    assert photo["url"] == (f"/api/v1/assets/{asset['id']}/photos/"
                            f"{photo['id']}")

    got = client.get(photo["url"])
    assert got.status_code == 200, got.text[:300]
    assert got.content == JPEG, "the bytes came back changed"
    assert hashlib.sha256(got.content).hexdigest() == photo["sha256"]
    assert got.headers["Content-Type"].startswith("image/jpeg")
    assert got.headers.get("ETag") == f'"{photo["sha256"]}"'
    assert got.headers.get("X-Content-Type-Options") == "nosniff"

    listed = _list(client, asset["id"])
    assert [i["id"] for i in listed["items"] if i["kind"] == "photo"] \
        == [photo["id"]]
    assert listed["photos"]["count"] == 1
    assert listed["photos"]["standing"] == 1
    assert listed["photos"]["max_standing"] == 12
    assert listed["photos"]["max_bytes"] == MAX_BYTES


def test_the_type_is_read_from_the_bytes_not_from_the_label(client, asset):
    """A PNG sent as `photo.gif`, `image/gif` is a PNG."""
    data = png(9, 7)
    r = _post(client, asset["id"], data, filename="photo.gif",
              content_type="image/gif")
    photo = assert_envelope_ok(r, 201)["data"]
    assert photo["mimetype"] == "image/png"
    assert (photo["width"], photo["height"]) == (9, 7)
    got = client.get(photo["url"])
    assert got.content == data
    assert got.headers["Content-Type"].startswith("image/png")


def test_a_retry_under_the_same_key_stores_one_photo(client, asset):
    key = str(uuid.uuid4())
    first = assert_envelope_ok(_post(
        client, asset["id"], png(), headers={"X-Idempotency-Key": key}),
        201)["data"]
    again = assert_envelope_ok(_post(
        client, asset["id"], png(), headers={"X-Idempotency-Key": key}),
        201)["data"]
    assert again["id"] == first["id"]
    assert len(_photos(client, asset["id"])) == 1


# ── the caps, each refused, nothing written ─────────────────────────────

def test_301_kb_is_refused_and_300_kb_is_not(client, asset):
    r = _post(client, asset["id"], png(total=301 * 1024))
    body = assert_envelope_err(r, 413, "validation_failed")
    details = body["error"]["details"]
    assert details["reason"] == "too_large"
    assert details["max_bytes"] == MAX_BYTES
    assert details["received_bytes"] == 301 * 1024
    assert "300 KB" in body["error"]["message"]
    assert "308,224 bytes (301 KB)" in body["error"]["message"]
    assert "Nothing was written" in body["error"]["message"]
    assert _photos(client, asset["id"]) == []

    at_the_cap = png(total=MAX_BYTES)
    photo = assert_envelope_ok(
        _post(client, asset["id"], at_the_cap), 201)["data"]
    assert photo["size"] == MAX_BYTES
    assert client.get(photo["url"]).content == at_the_cap


def test_the_thirteenth_photo_is_refused_until_one_is_superseded(
        client, asset):
    ids = [assert_envelope_ok(_post(client, asset["id"], png(seed=i)),
                              201)["data"]["id"] for i in range(12)]
    r = _post(client, asset["id"], png(seed=99))
    body = assert_envelope_err(r, 409, "conflict")
    details = body["error"]["details"]
    assert (details["reason"], details["photos"], details["max_photos"]) \
        == ("photo_limit", 12, 12)
    assert "already has 12 photos" in body["error"]["message"]
    assert len(_photos(client, asset["id"])) == 12

    assert_envelope_ok(client.post(
        f"/api/v1/assets/{asset['id']}/photos/{ids[0]}/supersede",
        json={"reason": "Duplicate of the next one"}))
    assert_envelope_ok(_post(client, asset["id"], png(seed=99)), 201)
    listed = _list(client, asset["id"])
    assert (listed["photos"]["count"], listed["photos"]["standing"],
            listed["photos"]["superseded"]) == (13, 12, 1)


def test_a_pdf_renamed_jpg_is_refused(client, asset):
    r = _post(client, asset["id"], PDF, filename="receipt.jpg",
              content_type="image/jpeg")
    body = assert_envelope_err(r, 415, "validation_failed")
    details = body["error"]["details"]
    assert details["reason"] == "unsupported_type"
    assert details["detected"] == "application/pdf"
    assert details["allowed"] == ["image/jpeg", "image/png"]
    # What the client SAID, kept for the reader and never believed.
    assert details["filename"] == "receipt.jpg"
    assert details["declared_type"] == "image/jpeg"
    assert "application/pdf" in body["error"]["message"]
    assert _photos(client, asset["id"]) == []


def test_a_gif_is_refused(client, asset):
    r = _post(client, asset["id"], GIF, filename="photo.gif",
              content_type="image/gif")
    body = assert_envelope_err(r, 415, "validation_failed")
    assert body["error"]["details"]["detected"] == "image/gif"
    assert _photos(client, asset["id"]) == []


def test_a_truncated_jpeg_is_refused(client, asset):
    r = _post(client, asset["id"], JPEG[:300], filename="cut.jpg",
              content_type="image/jpeg")
    body = assert_envelope_err(r, 400, "validation_failed")
    assert body["error"]["details"]["reason"] == "unreadable_image"
    assert _photos(client, asset["id"]) == []


# ── the body, refused the way a JSON body is ────────────────────────────

def test_an_unknown_form_field_is_refused_and_nothing_is_written(
        client, asset):
    r = _post(client, asset["id"], png(), colour="red")
    details = assert_fields_refused(r, "colour")
    assert details["writable"] == ["caption", "file", "source"]
    assert _photos(client, asset["id"]) == [], (
        "the refused body's photo was stored anyway")


def test_source_is_required_and_is_web_or_mobile(client, asset):
    url = f"/api/v1/assets/{asset['id']}/photos"
    r = client.post(url, files={"file": ("p.png", png(), "image/png")})
    body = assert_envelope_err(r, 400, "validation_failed")
    assert body["error"]["details"]["missing"] == ["source"]
    for source in ("gate_evidence", "camera"):
        r = _post(client, asset["id"], png(), source=source)
        body = assert_envelope_err(r, 400, "validation_failed")
        assert body["error"]["details"]["allowed_values"] == ["web",
                                                              "mobile"]
    assert assert_envelope_ok(_post(client, asset["id"], png(),
                                    source="mobile"), 201)["data"][
        "source"] == "mobile"
    assert len(_photos(client, asset["id"])) == 1


def test_a_json_body_and_a_missing_file_are_refused(client, asset):
    url = f"/api/v1/assets/{asset['id']}/photos"
    r = client.post(url, json={"file": "aGVsbG8=", "source": "web"})
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["expected_content_type"] \
        == "multipart/form-data"
    r = client.post(url, files={"source": (None, "web")})
    body = assert_envelope_err(r, 400, "validation_failed")
    assert body["error"]["details"]["missing"] == ["file"]
    r = client.post(url, files=[("file", ("a.png", png(), "image/png")),
                                ("file", ("b.png", png(seed=3),
                                          "image/png"))],
                    data={"source": "web"})
    body = assert_envelope_err(r, 400, "invalid_request")
    assert body["error"]["details"]["count"] == 2
    assert _photos(client, asset["id"]) == []


def test_a_reader_cannot_add_a_photo(client, asset):
    """The Auditor holds `assets:read` and not `assets:write`."""
    r = _post(client, asset["id"], png(),
              token=gates._token(client, "auditor"))
    assert_envelope_err(r, 403, "forbidden")
    assert _photos(client, asset["id"]) == []


# ── superseding ─────────────────────────────────────────────────────────

def test_a_supersede_keeps_the_photo_marks_it_and_happens_once(
        client, asset):
    photo = assert_envelope_ok(_post(client, asset["id"], JPEG,
                                     filename="blurred.jpg",
                                     content_type="image/jpeg"),
                               201)["data"]
    url = f"/api/v1/assets/{asset['id']}/photos/{photo['id']}/supersede"

    r = client.post(url, json={})
    body = assert_envelope_err(r, 400, "validation_failed")
    assert body["error"]["details"]["field"] == "reason"
    assert_fields_refused(client.post(url, json={"reason": "x",
                                                 "by": "someone"}), "by")
    assert _photos(client, asset["id"])[0]["superseded"] is None

    done = assert_envelope_ok(client.post(
        url, json={"reason": "Blurred; retaken with the tag in frame"}))
    marked = done["data"]["superseded"]
    assert marked["reason"] == "Blurred; retaken with the tag in frame"
    assert marked["by"] and marked["by"]["id"] == photo["uploaded_by"]["id"]
    assert marked["at"] and marked["event_id"]

    # Kept: still listed, still served byte for byte, now marked.
    listed = _photos(client, asset["id"])
    assert [p["id"] for p in listed] == [photo["id"]]
    assert listed[0]["superseded"]["event_id"] == marked["event_id"]
    assert client.get(photo["url"]).content == JPEG

    again = client.post(url, json={"reason": "Again"})
    body = assert_envelope_err(again, 409, "conflict")
    assert body["error"]["details"]["reason"] == "already_superseded"
    assert body["error"]["details"]["superseded"]["event_id"] \
        == marked["event_id"]
    assert "already superseded" in body["error"]["message"]
    assert "Blurred; retaken with the tag in frame" \
        in body["error"]["message"]


def test_another_assets_photo_is_a_404(client, asset):
    photo = assert_envelope_ok(_post(client, asset["id"], png()),
                               201)["data"]
    other = gates.receive(client, name=_uniq("pytest-asset-photo-other"))
    wrong = f"/api/v1/assets/{other['id']}/photos/{photo['id']}"
    assert_envelope_err(client.get(wrong), 404, "not_found")
    assert_envelope_err(client.post(wrong + "/supersede",
                                    json={"reason": "walked"}),
                        404, "not_found")
    assert_envelope_err(client.get(f"/api/v1/assets/{asset['id']}/photos/"
                                   "999999999"), 404, "not_found")


# ── candidates, and IAD's evidence beside the photos ────────────────────

def test_a_candidate_accepts_a_photo(client, gated):
    unit = gates.receive(client, name=_uniq("pytest-asset-photo-candidate"))
    assert unit["register_state"] == "captured"
    photo = assert_envelope_ok(_post(client, unit["id"], png()),
                               201)["data"]
    assert photo["asset_id"] == unit["id"]
    assert client.get(photo["url"]).content == png()


def test_the_list_shows_iad_evidence_beside_a_photo_and_obeys_the_guard(
        client, gated):
    unit = gates.receive(client, name=_uniq("pytest-asset-photo-iad"))
    unit = gates._walk(client, unit, "vfm_verified")
    assert unit["register_state"] == "vfm_verified"

    # The Store Officer adds a photo: `assets:write`, no `evidence:read`.
    store = gates._token(client, "storekeeper")
    photo = assert_envelope_ok(_post(client, unit["id"], JPEG,
                                     content_type="image/jpeg",
                                     filename="on-receipt.jpg",
                                     source="mobile", token=store),
                               201)["data"]

    # A reader of evidence: one list, both kinds, each labelled.
    auditor = gates._token(client, "auditor")
    seen = _list(client, unit["id"], token=auditor)
    kinds = {(i["kind"], i["source"]) for i in seen["items"]}
    assert ("photo", "mobile") in kinds
    assert ("iad_evidence", "gate_evidence") in kinds
    assert seen["iad_evidence"] == {"readable": True, "count": 1}
    evidence = [i for i in seen["items"] if i["kind"] == "iad_evidence"]
    assert len(evidence) == 1
    item = evidence[0]
    # What the walk attached at `verify` (`tests/gates.py`): a text file.
    assert item["filename"] == "sighted.txt"
    assert item["uploaded_by_name"]          # the IAD officer
    assert item["verification_event_id"]
    assert item["superseded"] is None
    assert item["url"].startswith(f"/api/v1/assets/{unit['id']}/evidence/")
    got = requests.get(client.base + item["url"], timeout=30,
                       headers={"Authorization": f"Bearer {auditor}"})
    assert got.status_code == 200, got.text[:300]
    assert got.content == b"sighted"

    # A non-reader: the photo, and IAD's evidence as a count in words.
    blind = _list(client, unit["id"], token=store)
    assert [i["kind"] for i in blind["items"]] == ["photo"]
    assert blind["items"][0]["id"] == photo["id"]
    assert blind["iad_evidence"] == {
        "readable": False, "count": 1, "summary": "IAD evidence: 1 item",
        "requires_scope": "evidence:read"}
    refused = requests.get(client.base + item["url"], timeout=30,
                           headers={"Authorization": f"Bearer {store}"})
    assert_envelope_err(refused, 403, "forbidden")


def test_the_spec_declares_what_the_upload_can_answer(client):
    """413 and 415 are outside the five every route can answer, and a
    status the generated spec omits is one a generated client handles in
    its generic error branch (handoff 18)."""
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    upload = paths["/api/v1/assets/{id}/photos"]["post"]
    for status in ("201", "400", "401", "403", "404", "409", "413", "415"):
        assert status in upload["responses"], (status, sorted(upload["responses"]))
    assert "get" in paths["/api/v1/assets/{id}/photos"]
    assert "409" in paths[
        "/api/v1/assets/{id}/photos/{photo_id}/supersede"]["post"]["responses"]
