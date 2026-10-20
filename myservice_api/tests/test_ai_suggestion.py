"""Identify from photo — handoff 64, in-registry.

What the HTTP suite (`tests/test_what_the_photo_says.py`) cannot see:

1. **the append-only guard** on `nrs.ai.suggestion` — edit, delete and a
   hand-written row refused under sudo in its own words; another model's
   flag does not open it; the guard is the mixin's, not a copy;
2. **what is sent** — the prompt carries the tenant's classes and each
   mapped SAP class's commonest descriptions, and NO asset id, person,
   location or SAP number, even when the mirror holds a record carrying all
   of them;
3. **the validator** — a class the tenant does not have, a condition off the
   enum, three alternatives, a repeated class: discarded; a make, a model or
   dimensions the provider did not read: removed and SAID;
4. **the outcomes** — accepted (case-folded), changed (from → to), ignored
   (dismissed, or not sent and not what the asset holds), a field the asset
   ALREADY holds as suggested accepted with `already_held` (handoff 65), and
   a held photo claimed by the save;
5. **the arithmetic** — image tokens and cost at the published prices;
6. **the daily cap's day is Lagos's** (handoff 65) — a frozen clock either
   side of Lagos midnight, which is 23:00 UTC, so a cap counted by the UTC
   day would fail it.

Run with:
    odoo -d test19f -u myservice_api --test-enable \\
         --test-tags /myservice_api:TestAiSuggestion --stop-after-init \\
         --workers=0 --http-port=8099 --gevent-port=8098
"""
import io
import json
from datetime import date, datetime

from PIL import Image

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import freeze_time
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase
from odoo.addons.myservice_asset_register.models import ai_suggestion as S
from odoo.addons.myservice_api.controllers import ai_provider as ai
from odoo.addons.myservice_api.controllers import v1_ai

SUGGESTION = "nrs.ai.suggestion"
_GUARD_METHODS = ("create", "write", "unlink", "_resolve_source")


def _png(width=40, height=30, colour=(10, 120, 200)):
    out = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(out, "PNG")
    return out.getvalue()


@tagged("post_install", "-at_install")
class TestAiSuggestion(CadraTransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Category = cls.env["nrs.asset.category"]
        cls.chair = Category.create({"name": "AI probe chairs",
                                     "sap_asset_class": "2000"})
        cls.laptop = Category.create({"name": "AI probe laptops"})

    def setUp(self):
        super().setUp()
        self.Suggestion = self.env[SUGGESTION]

    def _pending(self, filename="chair-01.png"):
        return self.env["nrs.ai.pending.photo"]._hold(
            _png(), source="web", filename=filename)

    def _suggestion(self, data, pending=None):
        return self.Suggestion._record(
            pending=pending or self._pending(), provider="fake",
            model="cadra-fake-1", prompt_version=ai.PROMPT_VERSION,
            result="ok", suggestion=data, latency_ms=3,
            usage={"input_tokens": 10, "output_tokens": 5})

    def _published(self, **attrs):
        base = {"name": "HIGH BACK EXECUTIVE SWIVEL CHAIR", "colour": "BLACK",
                "material": "LEATHER", "make": None, "model_name": None,
                "dimensions": None}
        base.update(attrs)
        return {"category": {"id": self.chair.id, "confidence": 0.9,
                             "alternatives": []},
                "attributes": base,
                "condition": {"value": "good", "note": None},
                "text_read": [], "sap_candidates": {"count": 0, "items": []},
                "notes": []}

    # ── 1 · the guard ────────────────────────────────────────────────

    def test_an_edit_and_a_delete_are_refused_under_sudo(self):
        row = self._suggestion(self._published())
        with self.assertRaises(UserError) as raised:
            row.sudo().write({"result": "invalid"})
        self.assertIn("suggestion from a photo is append-only",
                      str(raised.exception))
        with self.assertRaises(UserError):
            row.sudo().unlink()
        self.assertEqual(row.result, "ok")

    def test_a_hand_written_row_is_refused_and_no_other_flag_opens_it(self):
        vals = {"photo_sha256": "0" * 64, "actor_id": self.env.user.id,
                "provider": "fake", "prompt_version": "x", "result": "ok"}
        with self.assertRaises(UserError) as raised:
            self.Suggestion.sudo().create(vals)
        self.assertIn("cannot be created directly", str(raised.exception))
        with self.assertRaises(UserError):
            self.Suggestion.sudo().with_context(
                cadra_photo_append=True, cadra_event_append=True,
                cadra_custody_append=True).create(vals)

    def test_the_guard_is_the_mixins_and_not_a_copy(self):
        module = "odoo.addons.myservice_asset_register.models.ai_suggestion"
        mro = type(self.env[SUGGESTION]).__mro__
        own = [k for k in mro if k.__module__ == module]
        self.assertEqual(len(own), 1)
        for method in _GUARD_METHODS:
            with self.subTest(method=method):
                self.assertNotIn(method, vars(own[0]))
                first = next(k for k in mro if method in vars(k))
                self.assertTrue(first.__module__.endswith(
                    ".models.append_only"), first.__module__)

    # ── 2 · what is sent ─────────────────────────────────────────────

    def test_the_prompt_carries_classes_and_words_and_nothing_else(self):
        # A mirror record carrying a number, a tag, an office, a serial and
        # a vendor — none of which may leave the server.
        self.env.cr.execute("""
            INSERT INTO nrs_sap_asset (sap_key, asset_number, asset_number_norm,
                asset_class, description, old_tag, old_tag_norm, office_code,
                serial_number, vendor, sap_active, in_latest_export,
                create_date, write_date)
            VALUES ('AIPROBE-1', '200099887766', '200099887766', '2000',
                    'AI PROBE SWIVEL CHAIR', 'FIRS/ZZQ/0099', 'FIRS/ZZQ/0099',
                    'ZZQ', 'SNPROBE998877', 'Probe Vendor Ltd', true, true,
                    now(), now())""")
        rows, examples = ai.catalogue(self.env)
        system = ai.build_system(rows, examples)
        self.assertIn("id %d: AI probe chairs" % self.chair.id, system)
        self.assertIn("SAP class 2000", system)
        self.assertIn("AI PROBE SWIVEL CHAIR (1)", system)
        for secret in ("200099887766", "FIRS/ZZQ/0099", "ZZQ",
                       "SNPROBE998877", "Probe Vendor"):
            self.assertNotIn(secret, system, secret)
        asset = self.env["nrs.asset"].create(
            {"name": "AI probe asset", "category_id": self.chair.id})
        self.assertNotIn(asset.asset_code or "NO-CODE", system)
        self.assertNotIn(self.env.user.name, system)

    def test_the_schema_offers_only_the_tenants_classes(self):
        ids = [self.chair.id, self.laptop.id]
        schema = ai.answer_schema(ids)
        self.assertEqual(
            schema["properties"]["category"]["properties"]["id"]["enum"], ids)
        self.assertEqual(
            schema["properties"]["condition"]["properties"]["value"]["enum"],
            list(ai.CONDITIONS))

    # ── 3 · the validator ────────────────────────────────────────────

    def _answer(self, **over):
        data = {
            "category": {"id": self.chair.id, "confidence": 0.8},
            "alternatives": [{"id": self.laptop.id, "confidence": 0.1}],
            "attributes": {"name": "CHAIR", "colour": "BLACK",
                           "material": None, "make": None,
                           "model_name": None, "dimensions": None},
            "condition": {"value": "good", "note": None},
            "size_band": "medium",
            "text_read": [],
        }
        data.update(over)
        return data

    def test_an_answer_outside_the_tenant_or_the_enum_is_discarded(self):
        ids = [self.chair.id, self.laptop.id]
        bad = (
            self._answer(category={"id": 999999999, "confidence": 0.9}),
            self._answer(category={"id": self.chair.id, "confidence": 1.4}),
            self._answer(condition={"value": "unserviceable", "note": None}),
            self._answer(alternatives=[{"id": self.laptop.id,
                                        "confidence": 0.1}] * 3),
            self._answer(alternatives=[{"id": self.chair.id,
                                        "confidence": 0.1}]),
            self._answer(text_read=[{"text": "X", "looks_like": "barcode"}]),
            self._answer(size_band="huge"),
            self._answer(size_band=None),
            {"category": "a chair"},
            None,
        )
        for data in bad:
            with self.subTest(data=data):
                with self.assertRaises(ai.InvalidAnswer):
                    ai.validate_answer(data, ids)

    def test_the_size_band_is_words_and_unknown_is_none(self):
        """Handoff 67 §3 (AI-FR-03): a band from the schema's enum, `unknown`
        published as None, and the words each band means in the prompt."""
        ids = [self.chair.id, self.laptop.id]
        schema = ai.answer_schema(ids)
        self.assertEqual(schema["properties"]["size_band"]["enum"],
                         ["small", "medium", "large", "unknown"])
        self.assertIn("size_band", schema["required"])
        clean, _n = ai.validate_answer(self._answer(), ids)
        self.assertEqual(clean["size_band"], "medium")
        clean, _n = ai.validate_answer(self._answer(size_band="unknown"), ids)
        self.assertIsNone(clean["size_band"])
        system = ai.build_system([], {})
        for band, words in ai.SIZE_BAND_WORDS.items():
            self.assertIn(words, system)
        block = v1_ai.size_band_block(None)
        self.assertTrue(block["approximate"])
        self.assertIsNone(block["value"])
        self.assertEqual(set(block["definitions"]), set(ai.SIZE_BANDS))

    def test_the_acceptance_counts_a_seeded_set(self):
        """Handoff 67 §3 (AI-NFR-08), against a seeded set under a model id
        nothing else uses: four calls — one discarded, three identified;
        of those, one saved unchanged, one saved with a field changed, one
        never used. The model's row is exactly that."""
        model = "cadra-test-67"
        asset = self.env["nrs.asset"].create(
            {"name": "AI probe acceptance", "category_id": self.chair.id})

        def call(result="ok"):
            return self.Suggestion._record(
                pending=self._pending(), provider="fake", model=model,
                prompt_version=ai.PROMPT_VERSION, result=result,
                suggestion=self._published() if result == "ok" else None)
        call("invalid")
        kept, changed, _unused = call(), call(), call()
        for row, counts in ((kept, {"accepted": 5, "changed": 0,
                                    "ignored": 0}),
                            (changed, {"accepted": 4, "changed": 1,
                                       "ignored": 0})):
            self.env["nrs.asset.event"]._record(
                asset, "ai_suggestion_applied", source="api_write",
                actor=self.env.user, ai_suggestion_id=row.id,
                notes=json.dumps({"counts": counts, "fields": {}}))
        out = self.Suggestion._acceptance(30)
        row = next(r for r in out["by_model"] if r["key"] == model)
        self.assertEqual(
            {k: row[k] for k in ("made", "identified", "used",
                                 "accepted_unchanged",
                                 "share_accepted_unchanged")},
            {"made": 4, "identified": 3, "used": 2, "accepted_unchanged": 1,
             "share_accepted_unchanged": 0.5})
        cat = next(r for r in out["by_category"]
                   if r["key"] == str(self.chair.id))
        self.assertEqual(cat["label"], "AI probe chairs")
        self.assertEqual((cat["made"], cat["used"]), (3, 2))
        self.assertEqual(set(out["definitions"]), set(S.ACCEPTANCE_WORDS))
        self.assertEqual(out["window"]["days"], 30)

    def test_what_was_not_read_is_removed_and_said(self):
        ids = [self.chair.id, self.laptop.id]
        data = self._answer(attributes={
            "name": "LAPTOP", "colour": None, "material": None,
            "make": "Dell", "model_name": "Latitude 5420",
            "dimensions": "120 x 60 cm"},
            text_read=[{"text": "DELL", "looks_like": "brand"}])
        clean, notes = ai.validate_answer(data, ids)
        self.assertEqual(clean["attributes"]["make"], "Dell")
        self.assertIsNone(clean["attributes"]["model_name"])
        self.assertIsNone(clean["attributes"]["dimensions"])
        self.assertEqual(len(notes), 2)
        self.assertTrue(any("Latitude 5420" in n for n in notes))
        self.assertTrue(any("120 x 60 cm" in n for n in notes))

    # ── 4 · the outcomes ─────────────────────────────────────────────

    def test_accepted_changed_and_ignored(self):
        row = self._suggestion(self._published())
        written = {"category_id": self.chair.id,
                   "name": "high back executive swivel chair ",
                   "colour": "BLACK", "condition": "fair"}
        out = row._outcomes(written, ignored=("colour",))
        self.assertEqual(out["category_id"]["outcome"], "accepted")
        self.assertEqual(out["name"]["outcome"], "accepted")
        self.assertEqual(out["colour"]["outcome"], "ignored")
        self.assertEqual(out["material"]["outcome"], "ignored")
        self.assertEqual(out["condition"],
                         {"outcome": "changed", "from": "good", "to": "fair"})
        self.assertNotIn("make", out)   # not proposed, not counted

    def test_a_save_claims_the_held_photo_and_writes_one_event(self):
        pending = self._pending("chair-07.png")
        row = self._suggestion(self._published(), pending=pending)
        asset = self.env["nrs.asset"].create(
            {"name": "AI probe saved", "category_id": self.chair.id})
        row._check_applicable(None)
        event, outcomes, counts = row._apply(
            asset, {"category_id": self.chair.id, "condition": "good"})
        self.assertEqual(counts, {"accepted": 2, "changed": 0, "ignored": 3})
        self.assertEqual(event.event_type, "ai_suggestion_applied")
        self.assertEqual(event.ai_suggestion_id, row)
        self.assertEqual(json.loads(event.notes)["counts"], counts)
        photo = self.env["nrs.asset.photo"].sudo().search(
            [("asset_id", "=", asset.id)])
        self.assertEqual(len(photo), 1)
        self.assertEqual(photo.sha256, row.photo_sha256)
        self.assertEqual(event.photo_id, photo)
        self.assertFalse(pending.exists(), "the held photo was not released")
        self.assertFalse(row.pending_photo_id)
        with self.assertRaises(S.SuggestionRefused) as raised:
            row._check_applicable(None)
        self.assertEqual(raised.exception.details["reason"],
                         "already_applied")

    def test_an_expired_held_photo_is_purged_and_the_hash_kept(self):
        pending = self._pending()
        row = self._suggestion(self._published(), pending=pending)
        self.env.cr.execute(
            "UPDATE nrs_ai_pending_photo SET expires_at = now() - "
            "interval '1 hour' WHERE id = %s", (pending.id,))
        self.env.invalidate_all()
        self.assertGreaterEqual(
            self.env["nrs.ai.pending.photo"]._cron_purge_expired(), 1)
        self.env.invalidate_all()
        self.assertFalse(pending.exists())
        self.assertFalse(row.pending_photo_id)
        self.assertEqual(len(row.photo_sha256), 64)
        with self.assertRaises(S.SuggestionRefused) as raised:
            row._check_applicable(None)
        self.assertEqual(raised.exception.details["reason"], "photo_expired")

    def test_the_provider_gets_no_gps_and_the_stored_photo_is_untouched(self):
        """§1 sends no locations: a camera JPEG's EXIF (where a phone keeps
        its GPS position) is stripped from what goes to the provider — at
        the byte level, the picture not re-encoded."""
        img = Image.new("RGB", (32, 24), (90, 10, 10))
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"             # Make
        exif[0x8825] = {2: (6.0, 27.0, 0.0)}    # GPSInfo: latitude
        out = io.BytesIO()
        img.save(out, "JPEG", exif=exif.tobytes())
        data = out.getvalue()
        self.assertIn(b"Exif", data)
        sent = ai.strip_metadata(data, "image/jpeg")
        self.assertNotIn(b"Exif", sent)
        self.assertNotIn(b"PhoneMaker", sent)
        self.assertEqual(Image.open(io.BytesIO(sent)).size, (32, 24))
        self.assertEqual(sent[-2:], b"\xff\xd9")
        png = io.BytesIO()
        from PIL import PngImagePlugin
        info = PngImagePlugin.PngInfo()
        info.add_text("Location", "6.45N 3.39E")
        Image.new("RGB", (8, 8)).save(png, "PNG", pnginfo=info)
        sent = ai.strip_metadata(png.getvalue(), "image/png")
        self.assertNotIn(b"Location", sent)
        self.assertEqual(Image.open(io.BytesIO(sent)).size, (8, 8))

    def test_only_the_asker_and_only_within_the_hold(self):
        row = self._suggestion(self._published())
        other = self.env["res.users"].create(
            {"name": "AI probe other", "login": "ai-probe-other@example.com"})
        with self.assertRaises(S.SuggestionRefused) as raised:
            row._check_applicable(None, actor=other)
        self.assertEqual(raised.exception.details["reason"], "not_yours")
        self.env.cr.execute(
            "UPDATE nrs_ai_pending_photo SET expires_at = now() - "
            "interval '1 minute' WHERE id = %s", (row.pending_photo_id.id,))
        self.env.invalidate_all()
        with self.assertRaises(S.SuggestionRefused) as raised:
            row._check_applicable(None)
        self.assertEqual(raised.exception.details["reason"], "photo_expired")

    def test_a_field_the_asset_already_holds_is_accepted_not_ignored(self):
        """Report 64's nit (handoff 65 §0a.3). The Photos tab shows a field
        the asset already holds as suggested as *Same*, with no button, and
        the save does not send it. It was recorded *ignored* — a suggestion
        the register bore out, counted as one the person turned down. It is
        `accepted`, marked `already_held`, because nothing was written for
        it. A field the asset holds DIFFERENTLY and the save did not send is
        still ignored, and one the person named is ignored whatever the
        asset holds."""
        row = self._suggestion(self._published(material="LEATHER"))
        asset = self.env["nrs.asset"].create({
            "name": "AI probe already holds", "category_id": self.chair.id,
            "colour": "Black ", "material": "FABRIC"})
        # The Photos tab's save: the name chosen, nothing else sent; the
        # category and colour shown Same (left out of `ignored`), the
        # material shown different and not chosen (named), the condition
        # (`good`, the asset's default) shown Same.
        asset.write({"name": "HIGH BACK EXECUTIVE SWIVEL CHAIR"})
        out = row._outcomes(
            {"name": "HIGH BACK EXECUTIVE SWIVEL CHAIR"},
            ignored=("material",), asset=asset)
        self.assertEqual(out["name"], {"outcome": "accepted",
                                       "suggested": "HIGH BACK EXECUTIVE "
                                                    "SWIVEL CHAIR"})
        for field in ("category_id", "colour", "condition"):
            with self.subTest(field=field):
                self.assertEqual(out[field]["outcome"], "accepted")
                self.assertIs(out[field]["already_held"], True)
        self.assertEqual(out["material"], {"outcome": "ignored",
                                           "suggested": "LEATHER"})
        # Named as ignored, though the asset holds it: the person's word.
        named = row._outcomes({}, ignored=("colour",), asset=asset)
        self.assertEqual(named["colour"]["outcome"], "ignored")
        # Not sent, and the asset holds something else: ignored, as before.
        asset.write({"colour": "RED"})
        self.assertEqual(row._outcomes({}, asset=asset)["colour"],
                         {"outcome": "ignored", "suggested": "BLACK"})
        # Without an asset to read, nothing can be said to be held.
        self.assertEqual(row._outcomes({})["category_id"]["outcome"],
                         "ignored")

    def test_the_save_records_an_already_held_field_on_the_event(self):
        """Through `_apply`, the one writer of the event: the counts carry
        the held field as accepted and the event's notes say it was held."""
        row = self._suggestion(self._published())
        asset = self.env["nrs.asset"].create({
            "name": "AI probe held on save", "category_id": self.chair.id,
            "colour": "BLACK"})
        row._check_applicable(None)
        event, outcomes, counts = row._apply(
            asset, {"material": "LEATHER"}, ignored=("name",))
        # category, colour, condition held; material written as suggested;
        # name named ignored.
        self.assertEqual(counts, {"accepted": 4, "changed": 0, "ignored": 1})
        notes = json.loads(event.notes)
        self.assertEqual(notes["counts"], counts)
        self.assertIs(notes["fields"]["colour"]["already_held"], True)
        self.assertNotIn("already_held", notes["fields"]["material"])

    # ── 5 · the arithmetic ───────────────────────────────────────────

    def test_image_tokens_and_cost(self):
        self.assertEqual(ai.image_tokens(1000, 750), 1000)
        # A phone's 4032 × 3024 comes down to 2576 on the long edge, capped.
        self.assertEqual(ai.image_tokens(4032, 3024), 4784)
        self.assertEqual(ai.cost_usd("claude-opus-5-5", {
            "input_tokens": 1_000_000, "output_tokens": 0}), 4.0)
        self.assertEqual(ai.cost_usd("claude-opus-5-5", {
            "input_tokens": 0, "output_tokens": 1000,
            "cache_read_tokens": 1_000_000}), 0.22)
        self.assertIsNone(ai.cost_usd("an-unpriced-model", {
            "input_tokens": 5}))

    # ── 6 · the daily cap's day ──────────────────────────────────────

    def test_the_daily_cap_turns_over_at_lagos_midnight(self):
        """The cap counts calls by the LAGOS day (handoff 65 §0a.3; report
        64 left it unpinned). Lagos is UTC+1 all year, so its midnight is
        23:00 UTC — and a call at 23:30 UTC belongs to the NEXT Lagos day.

        Two calls an hour apart, 22:30 and 23:30 UTC on 10 May 2031: one UTC
        day, two Lagos days. Counted by the UTC day the cap would see both
        at once (asserted below, so this test is not true of either rule);
        counted by the Lagos day, each day holds one. A year no fixture
        reaches, so nothing else on the tenant is in either day."""
        self.env["ir.config_parameter"].sudo().set_param(
            ai.PARAM_DAILY_CAP, "1")
        with freeze_time("2031-05-10 22:30:00"):          # 23:30 in Lagos
            self.assertEqual(S.lagos_today(), date(2031, 5, 10))
            first = self._suggestion(self._published())
            self.assertEqual(self.Suggestion._calls_today(), 1)
            block = v1_ai._settings_block(self.env)
            self.assertEqual(block["today"],
                             {"day": "2031-05-10", "calls": 1,
                              "remaining": 0})
        with freeze_time("2031-05-10 22:59:59"):          # 23:59:59 in Lagos
            self.assertEqual(v1_ai._settings_block(self.env)["today"]
                             ["remaining"], 0, "the day ended early")
        with freeze_time("2031-05-10 23:00:00"):          # midnight in Lagos
            self.assertEqual(S.lagos_today(), date(2031, 5, 11))
            self.assertEqual(self.Suggestion._calls_today(), 0)
            self.assertEqual(v1_ai._settings_block(self.env)["today"],
                             {"day": "2031-05-11", "calls": 0,
                              "remaining": 1})
        with freeze_time("2031-05-10 23:30:00"):          # 00:30 in Lagos
            second = self._suggestion(self._published())
            self.assertEqual(self.Suggestion._calls_today(), 1)
            self.assertEqual(v1_ai._settings_block(self.env)["today"]
                             ["remaining"], 0)
        self.assertEqual(
            (first.requested_at, second.requested_at),
            (datetime(2031, 5, 10, 22, 30), datetime(2031, 5, 10, 23, 30)))
        # What a UTC-day count would have said at 23:30 UTC: both calls,
        # one day — the cap already spent twice over. The Lagos count above
        # is the only one that says 1.
        self.env.cr.execute(
            "SELECT count(*) FROM nrs_ai_suggestion "
            "WHERE requested_at >= '2031-05-10' AND requested_at < '2031-05-11'")
        self.assertEqual(self.env.cr.fetchone()[0], 2)
