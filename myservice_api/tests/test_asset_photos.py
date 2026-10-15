"""Photos on an asset — handoff 61 §5, in-registry.

What the HTTP suite (`tests/test_asset_photos.py`) cannot reach cheaply:

1. **the sniff** — a JPEG and a PNG read for what they are, from their
   bytes alone; a PDF, a GIF, a truncated JPEG and a header claiming too
   many pixels each refused in words, with the status and details the API
   publishes;
2. **the bytes come back as sent** — including a picture wider than
   `base.image_autoresize_max_px`, which `ir.attachment` would otherwise
   have resized and re-encoded;
3. **the append-only guard** — edit, delete and a hand-written row refused
   in the model's own words, under sudo; another model's flag does not open
   it; the guard each method runs is the mixin's, not a copy;
4. **superseding** — one `photo_superseded` event with the photo, the reason
   and the actor; a second refused 409 naming the first; no reason refused;
   a superseded photo frees its slot under the cap;
5. **the caps** — 300 KB and the twelfth photo, refused before anything is
   written;
6. **the pin** — an asset with a photo cannot be deleted;
7. **the label** — `is_test_fixture` derived from the acting user, both
   ways.

Run with:
    odoo -d test19 -u myservice_api --test-enable \\
         --test-tags /myservice_api:TestAssetPhotos --stop-after-init \\
         --workers=0 --http-port=8099 --gevent-port=8098
"""
import base64
import hashlib
import io
import struct
import zlib

from PIL import Image

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase
from odoo.addons.myservice_asset_register.models import asset_photo as P
from odoo.addons.myservice_asset_register.models.asset_event import (
    EVENT_PHOTO_SUPERSEDED,
)

PHOTO = "nrs.asset.photo"
_GUARD_METHODS = ("create", "write", "unlink", "_resolve_source")


def _jpeg(width=16, height=12, colour=(200, 30, 30)):
    out = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(out, "JPEG", quality=85)
    return out.getvalue()


def _png(width=20, height=10, colour=(10, 120, 200)):
    out = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(out, "PNG")
    return out.getvalue()


def _png_header(width, height):
    """A PNG whose header declares `width` × `height` and whose (valid,
    checksummed) image data is a few bytes — what a decompression bomb
    looks like before anybody decodes it."""
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height,
                                         8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00" * 64))
            + chunk(b"IEND", b""))


_PDF = (b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF\n")
_GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9"
        b"\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02"
        b"\x02D\x01\x00;")


@tagged("post_install", "-at_install")
class TestAssetPhotos(CadraTransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.flagged = cls.create_api_client({
            "name": "photo probe (flagged)", "scopes": "assets:write"})
        cls.unflagged = cls.create_api_client({
            "name": "photo probe (unflagged)", "scopes": "assets:write"})
        cls.unflagged.write({"is_test_credential": False})
        Category = cls.env["nrs.asset.category"]
        cls.category = Category.create({"name": "Photo probe category"})

    def setUp(self):
        super().setUp()
        self.Photo = self.env[PHOTO]
        self.asset = self._asset("Photo probe asset")

    def _asset(self, name):
        # Created nowhere and unassigned, so nothing pins it but a photo.
        return self.env["nrs.asset"].create(
            {"name": name, "category_id": self.category.id})

    def _upload(self, data=None, asset=None, user=None, **kw):
        kw.setdefault("source", "web")
        Photo = self.Photo.with_user(user) if user else self.Photo
        return Photo._upload(asset or self.asset,
                             _jpeg() if data is None else data, **kw)

    def _rows(self, asset=None):
        return self.Photo.sudo().search(
            [("asset_id", "=", (asset or self.asset).id)])

    # ── 1 · the sniff ────────────────────────────────────────────────

    def test_a_jpeg_and_a_png_are_read_for_what_they_are(self):
        self.assertEqual(P.sniff_photo(_jpeg(16, 12)), (P.JPEG, 16, 12))
        self.assertEqual(P.sniff_photo(_png(20, 10)), (P.PNG, 20, 10))

    def test_a_pdf_named_jpg_is_refused_as_what_it_is(self):
        """The name and the declared type never reach the sniff: it is
        given the bytes and nothing else, so `.jpg` cannot help a PDF."""
        with self.assertRaises(P.PhotoRefused) as raised:
            self._upload(_PDF, filename="receipt.jpg")
        e = raised.exception
        self.assertEqual((e.status, e.details["reason"],
                          e.details["detected"]),
                         (415, "unsupported_type", "application/pdf"))
        self.assertIn("must be a JPEG or a PNG", str(e))
        self.assertIn("application/pdf", str(e))
        self.assertFalse(self._rows())

    def test_a_gif_is_refused(self):
        with self.assertRaises(P.PhotoRefused) as raised:
            self._upload(_GIF, filename="photo.png")
        self.assertEqual(raised.exception.details["detected"], "image/gif")
        self.assertEqual(raised.exception.status, 415)
        self.assertFalse(self._rows())

    def test_a_jpeg_header_on_garbage_is_refused(self):
        jpeg = _jpeg(64, 64)
        for name, data in (("truncated", jpeg[:len(jpeg) // 2]),
                           ("garbage", b"\xff\xd8\xff" + b"\x00" * 400)):
            with self.subTest(case=name):
                with self.assertRaises(P.PhotoRefused) as raised:
                    self._upload(data)
                self.assertEqual(raised.exception.details["reason"],
                                 "unreadable_image")
        self.assertFalse(self._rows())

    def test_an_empty_file_is_refused(self):
        with self.assertRaises(P.PhotoRefused) as raised:
            self._upload(b"")
        self.assertEqual(raised.exception.details["reason"], "empty")

    def test_a_header_declaring_too_many_pixels_is_refused_undecoded(self):
        # 8000 × 7000 = 56 MP, declared by a valid header in under 100
        # bytes. Built by hand rather than by Pillow so the test does not
        # allocate the 56 MB it is about refusing to allocate.
        big = _png_header(8000, 7000)
        self.assertLess(len(big), 200)
        with self.assertRaises(P.PhotoRefused) as raised:
            self._upload(big)
        self.assertEqual(raised.exception.details["reason"],
                         "too_many_pixels")
        self.assertEqual((raised.exception.details["width"],
                          raised.exception.details["height"]), (8000, 7000))

    def test_source_is_web_or_mobile_and_never_gate_evidence(self):
        for source in ("gate_evidence", "camera", ""):
            with self.subTest(source=source):
                with self.assertRaises(P.PhotoRefused) as raised:
                    self._upload(source=source)
                self.assertEqual(raised.exception.details["field"], "source")
        self.assertFalse(self._rows())

    # ── 2 · the bytes come back as sent ──────────────────────────────

    def test_the_row_describes_the_bytes_and_returns_them_unchanged(self):
        data = _png(33, 21)
        photo = self._upload(data, source="mobile", caption="  Tag in "
                             "frame  ", filename="IMG_0001.PNG")
        self.assertEqual(photo.mimetype, P.PNG)
        self.assertEqual((photo.width, photo.height), (33, 21))
        self.assertEqual(photo.size, len(data))
        self.assertEqual(photo.sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(photo.caption, "Tag in frame")
        self.assertEqual(photo.source, "mobile")
        self.assertEqual(photo.uploaded_by_id, self.env.user)
        self.assertEqual(photo.uploaded_by_name, self.env.user.display_name)
        stored, intact = photo._bytes()
        self.assertEqual(stored, data)
        self.assertTrue(intact)

    def test_a_wide_picture_is_not_resized_by_the_attachment(self):
        """`ir.attachment._postprocess_contents` resizes any image above
        `base.image_autoresize_max_px` (1920×1920 unless configured) and
        re-encodes it. A photo is evidence: it must come back as sent."""
        self.env["ir.config_parameter"].sudo().set_param(
            "base.image_autoresize_max_px", "1920x1920")
        data = _jpeg(2400, 40)
        photo = self._upload(data)
        stored, intact = photo._bytes()
        self.assertEqual(stored, data)
        self.assertTrue(intact)
        self.assertEqual(Image.open(io.BytesIO(stored)).size, (2400, 40))

    def test_the_row_is_the_attachment_and_evidence_does_not_see_it(self):
        """The bytes live in the field's own attachment (`res_field`
        set), not in a plain attachment on the asset that IAD's evidence
        list could mistake for a verification file."""
        photo = self._upload()
        held = self.env["ir.attachment"].sudo().search(
            [("res_model", "=", PHOTO), ("res_id", "=", photo.id),
             ("res_field", "=", "image")])
        self.assertEqual(len(held), 1)
        self.assertEqual(held.checksum,
                         hashlib.sha1(photo._bytes()[0]).hexdigest())
        self.assertEqual(self.asset._gate_evidence(), [])

    # ── 3 · append-only, through THE mixin ───────────────────────────

    def test_an_edit_is_refused_under_sudo_in_its_own_words(self):
        photo = self._upload(caption="as sent")
        for vals in ({"caption": "rewritten"},
                     {"image": base64.b64encode(_png())},
                     {"asset_id": self._asset("elsewhere").id}):
            with self.subTest(vals=list(vals)):
                with self.assertRaises(UserError) as raised:
                    photo.sudo().write(vals)
                self.assertIn("photo of an asset is append-only",
                              str(raised.exception))
                self.assertIn("sudo", str(raised.exception))
        self.assertEqual(photo.caption, "as sent")

    def test_a_delete_is_refused_under_sudo_in_its_own_words(self):
        photo = self._upload()
        with self.assertRaises(UserError) as raised:
            photo.sudo().unlink()
        self.assertIn("photo of an asset is append-only",
                      str(raised.exception))
        self.assertTrue(photo.exists())

    def test_a_hand_written_row_is_refused(self):
        data = _jpeg()
        with self.assertRaises(UserError) as raised:
            self.Photo.sudo().create({
                "asset_id": self.asset.id,
                "image": base64.b64encode(data),
                "mimetype": P.JPEG, "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "width": 16, "height": 12, "source": "web",
                "uploaded_by_id": self.env.user.id,
            })
        self.assertIn("cannot be created directly", str(raised.exception))
        self.assertFalse(self._rows())

    def test_another_models_flag_does_not_open_this_one(self):
        others = {"cadra_custody_append": True,
                  "cadra_movement_append": True,
                  "cadra_event_append": True,
                  "cadra_renomination_append": True}
        data = _jpeg()
        with self.assertRaises(UserError):
            self.Photo.sudo().with_context(**others).create({
                "asset_id": self.asset.id,
                "image": base64.b64encode(data),
                "mimetype": P.JPEG, "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "width": 16, "height": 12, "source": "web",
                "uploaded_by_id": self.env.user.id,
            })
        self.assertFalse(self._rows())

    def test_the_guard_is_the_mixins_and_not_a_copy(self):
        """A new append-only record inherits the mixin; it does not copy it
        (`CLAUDE.md`). Asked off the MRO, as `test_append_only_mixin` asks
        it of custody, movement and the event record — and the fixture
        label's mixin, which this model also carries, must not stand in
        front of it."""
        module = "odoo.addons.myservice_asset_register.models.asset_photo"
        mro = type(self.env[PHOTO]).__mro__
        own = [klass for klass in mro if klass.__module__ == module]
        self.assertEqual(len(own), 1)
        for method in _GUARD_METHODS:
            with self.subTest(method=method):
                self.assertNotIn(method, vars(own[0]))
                first = next(klass for klass in mro if method in vars(klass))
                self.assertTrue(
                    first.__module__.endswith(".models.append_only"),
                    "%s resolves to %s" % (method, first.__module__))

    # ── 4 · superseding ──────────────────────────────────────────────

    def test_a_supersede_is_one_event_and_the_photo_is_untouched(self):
        photo = self._upload(caption="blurred")
        before = (photo.sha256, photo.caption, photo.write_date)
        event = photo.action_supersede("  Blurred; retaken.  ")
        self.assertEqual(event.event_type, EVENT_PHOTO_SUPERSEDED)
        self.assertEqual(event.photo_id, photo)
        self.assertEqual(event.asset_id, self.asset)
        self.assertEqual(event.reason, "Blurred; retaken.")
        self.assertEqual(event.actor_id, self.env.user)
        self.assertEqual((photo.sha256, photo.caption, photo.write_date),
                         before)
        photo.invalidate_recordset(["superseded_event_id"])
        self.assertEqual(photo.superseded_event_id, event)
        # The event is append-only too.
        with self.assertRaises(UserError):
            event.sudo().write({"reason": "something kinder"})

    def test_a_second_supersede_is_refused_naming_the_first(self):
        photo = self._upload()
        first = photo.action_supersede("Wrong asset in frame")
        with self.assertRaises(P.PhotoRefused) as raised:
            photo.action_supersede("Again")
        e = raised.exception
        self.assertEqual((e.status, e.code, e.details["reason"]),
                         (409, "conflict", "already_superseded"))
        self.assertEqual(e.details["superseded"]["event_id"], first.id)
        self.assertIn("already superseded", str(e))
        self.assertIn(first.actor_name, str(e))
        self.assertIn("Wrong asset in frame", str(e))
        self.assertEqual(len(self.env["nrs.asset.event"].sudo().search([
            ("event_type", "=", EVENT_PHOTO_SUPERSEDED),
            ("photo_id", "=", photo.id)])), 1)

    def test_a_supersede_without_a_reason_is_refused(self):
        photo = self._upload()
        for reason in (None, "", "   "):
            with self.subTest(reason=reason):
                with self.assertRaises(P.PhotoRefused) as raised:
                    photo.action_supersede(reason)
                self.assertEqual(raised.exception.details["field"], "reason")
        self.assertFalse(photo._supersede_events())

    # ── 5 · the caps ─────────────────────────────────────────────────

    def test_over_300_kb_is_refused_before_anything_is_written(self):
        with self.assertRaises(P.PhotoRefused) as raised:
            P.check_photo_size(301 * 1024)
        e = raised.exception
        self.assertEqual((e.status, e.details["max_bytes"],
                          e.details["received_bytes"]),
                         (413, 307200, 308224))
        self.assertIn("at most 300 KB (307,200 bytes)", str(e))
        self.assertIn("308,224 bytes (301 KB)", str(e))
        # And through `_upload`, with real bytes: the check is the same one.
        with self.assertRaises(P.PhotoRefused):
            self._upload(_jpeg() + b"\x00" * (301 * 1024))
        self.assertFalse(self._rows())
        P.check_photo_size(P.MAX_PHOTO_BYTES)   # the cap itself is allowed

    def test_the_thirteenth_is_refused_and_a_superseded_photo_frees_a_slot(
            self):
        photos = [self._upload(_png(10 + i, 10)) for i in range(12)]
        with self.assertRaises(P.PhotoRefused) as raised:
            self._upload()
        e = raised.exception
        self.assertEqual((e.status, e.code, e.details["reason"],
                          e.details["photos"], e.details["max_photos"]),
                         (409, "conflict", "photo_limit", 12, 12))
        self.assertIn("already has 12 photos", str(e))
        self.assertEqual(len(self._rows()), 12)
        photos[0].action_supersede("Duplicate of the second")
        self._upload()
        self.assertEqual(len(self._rows()), 13)
        self.assertEqual(self.Photo._standing_count(self.asset), 12)

    def test_the_cap_is_per_asset(self):
        other = self._asset("Photo probe other")
        for _i in range(12):
            self._upload()
        self._upload(asset=other)
        self.assertEqual(len(self._rows(other)), 1)

    # ── 6 · the pin ──────────────────────────────────────────────────

    def test_an_asset_with_a_photo_cannot_be_deleted(self):
        bare = self._asset("Photo probe deletable")
        pinned = self._asset("Photo probe pinned")
        self._upload(asset=pinned)
        self.env.flush_all()
        with self.env.cr.savepoint():
            bare.unlink()       # control: nothing else pins these fixtures
            self.env.flush_all()
        self.assertFalse(bare.exists())
        with self.assertRaises(Exception), mute_logger("odoo.sql_db"), \
                self.env.cr.savepoint():
            pinned.unlink()
            self.env.flush_all()
        self.assertTrue(pinned.exists())

    # ── 7 · the label ────────────────────────────────────────────────

    def test_the_label_is_derived_from_the_acting_user_both_ways(self):
        flagged = self._upload(user=self.flagged.user_id)
        unflagged = self._upload(user=self.unflagged.user_id)
        self.assertTrue(flagged.is_test_fixture)
        self.assertFalse(unflagged.is_test_fixture)
        self.assertEqual(flagged.uploaded_by_id, self.flagged.user_id)
        # And the supersede event's source says `test` for the flagged one.
        event = flagged.with_user(self.flagged.user_id).action_supersede(
            "probe")
        self.assertEqual(event.source, "test")
        event = unflagged.with_user(self.unflagged.user_id) \
            .action_supersede("probe")
        self.assertEqual(event.source, "api_photo")
