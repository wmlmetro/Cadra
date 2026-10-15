# Handoff 61 — written by the location-code work.
"""Room codes, in the registry. Handoff 61 §7, ruling R8.

`generic.location.location_code` (`myservice_asset_register/models/
location_code.py`): the format generated from the hierarchy, the two
uniqueness checks (the model's sentence BEFORE the database, and the
database's UNIQUE constraint behind it), the fill the migration and the
install hook call, the scan resolver's last step, and the room label PDF.

The HTTP half — the routes, the 409 with nothing written, the PDF over a
bearer token — is `tests/test_location_code.py`.
"""
import re
import uuid
from unittest.mock import patch

import psycopg2

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.myservice_asset_register.models.location_code import (
    LOCATION_CODE_MAX_LENGTH, LocationCodeRefused)
from odoo.addons.myservice_barcode_station.controllers.main import (
    _resolve_lookup)
from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

SHAPE = re.compile(r'^LOC(-[A-Z0-9]+)+$')


@tagged('post_install', '-at_install')
class TestLocationCode(CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.Location = self.env['generic.location']
        self.tag = uuid.uuid4().hex[:6].upper()

    def _loc(self, name, **vals):
        return self.Location.create(dict({'name': name}, **vals))

    # ── the format ────────────────────────────────────────────────────

    def test_a_coded_hierarchy_gives_its_zone_codes(self):
        b = self._loc('B %s' % self.tag, zone_code='Z%s' % self.tag,
                      location_type='building')
        f = self._loc('F', parent_id=b.id, zone_code='f1',
                      location_type='floor')
        r = self._loc('R', parent_id=f.id, zone_code='mtg-1',
                      location_type='room')
        # Cleaned exactly as `_tag_prefix` cleans a zone code: upper-cased,
        # anything but A-Z/0-9 removed — `mtg-1` is the segment `MTG1`.
        self.assertEqual(b.location_code, 'LOC-Z%s' % self.tag)
        self.assertEqual(f.location_code, 'LOC-Z%s-F1' % self.tag)
        self.assertEqual(r.location_code, 'LOC-Z%s-F1-MTG1' % self.tag)

    def test_a_location_with_no_zone_code_ends_in_its_id(self):
        root = self._loc('Uncoded root %s' % self.tag)
        self.assertEqual(root.location_code, 'LOC-%d' % root.id)
        b = self._loc('B %s' % self.tag, zone_code='Y%s' % self.tag)
        child = self._loc('Uncoded child', parent_id=b.id)
        self.assertEqual(child.location_code,
                         'LOC-Y%s-%d' % (self.tag, child.id))

    def test_every_generated_code_is_printable_verbatim(self):
        for loc in (self._loc('A %s' % self.tag),
                    self._loc('B', zone_code='weird code!/é')):
            self.assertRegex(loc.location_code, SHAPE)
            self.assertLessEqual(len(loc.location_code),
                                 LOCATION_CODE_MAX_LENGTH)

    def test_a_code_too_long_for_the_label_falls_back_to_the_id(self):
        top = self._loc('Deep', zone_code='A' * 12)
        mid = self._loc('Deeper', parent_id=top.id, zone_code='B' * 12)
        self.assertEqual(mid.location_code, 'LOC-%d' % mid.id)

    def test_two_locations_deriving_one_code_never_collide(self):
        """The `test19` case: 29 fixtures share zone code `E2E-01`."""
        a = self._loc('Twin A', zone_code='T%s' % self.tag)
        b = self._loc('Twin B', zone_code='T%s' % self.tag)
        self.assertEqual(a.location_code, 'LOC-T%s' % self.tag)
        self.assertEqual(b.location_code, 'LOC-T%s-%d' % (self.tag, b.id))

    def test_the_code_does_not_follow_a_move(self):
        """A printed label must go on scanning."""
        b = self._loc('Mover B', zone_code='M%s' % self.tag)
        room = self._loc('Mover R', zone_code='R1')
        before = room.location_code
        room.write({'parent_id': b.id})
        self.assertEqual(room.location_code, before)

    def test_an_empty_code_regenerates_it_from_the_hierarchy_now(self):
        b = self._loc('Regen B', zone_code='G%s' % self.tag)
        room = self._loc('Regen R', zone_code='R2')
        room.write({'parent_id': b.id, 'location_code': ''})
        self.assertEqual(room.location_code, 'LOC-G%s-R2' % self.tag)

    def test_a_copy_gets_its_own_code(self):
        a = self._loc('Copied %s' % self.tag, zone_code='C%s' % self.tag)
        b = a.copy()
        self.assertTrue(b.location_code)
        self.assertNotEqual(a.location_code, b.location_code)

    # ── a typed code ──────────────────────────────────────────────────

    def test_a_typed_code_is_trimmed_and_upper_cased(self):
        loc = self._loc('Typed %s' % self.tag,
                        location_code='  loc-typed-%s ' % self.tag.lower())
        self.assertEqual(loc.location_code, 'LOC-TYPED-%s' % self.tag)

    def test_a_code_without_the_prefix_is_refused_in_words(self):
        loc = self._loc('Prefix %s' % self.tag)
        before = loc.location_code
        for bad in ('HQ-F10-%s' % self.tag, 'LOC-HAS SPACE', 'LOC--X',
                    'LOC-%s' % ('X' * 30)):
            with self.assertRaises(LocationCodeRefused) as caught:
                loc.write({'location_code': bad})
            self.assertEqual(caught.exception.kind, 'format')
            self.assertIn('begins LOC-', str(caught.exception))
        self.assertEqual(loc.location_code, before)

    def test_a_taken_code_is_refused_before_the_database_is_asked(self):
        a = self._loc('Holder %s' % self.tag)
        b = self._loc('Other %s' % self.tag)
        before = b.location_code
        with self.assertRaises(LocationCodeRefused) as caught:
            b.write({'location_code': a.location_code, 'name': 'Renamed'})
        self.assertEqual(caught.exception.kind, 'taken')
        self.assertEqual(caught.exception.details['held_by_location_id'], a.id)
        self.assertIn(a.name, str(caught.exception))
        b.invalidate_recordset()
        self.assertEqual(b.location_code, before)
        self.assertEqual(b.name, 'Other %s' % self.tag,
                         'nothing of the refused body is written')

    def test_an_archived_location_still_holds_its_code(self):
        a = self._loc('Archived %s' % self.tag)
        a.active = False
        with self.assertRaises(LocationCodeRefused) as caught:
            self._loc('New', location_code=a.location_code)
        self.assertEqual(caught.exception.kind, 'taken')
        self.assertIn('archived', str(caught.exception))

    def test_a_code_reading_as_a_tag_number_is_refused(self):
        """Ambiguity at the scan box is impossible, not merely unlikely."""
        category = self.env['nrs.asset.category'].create(
            {'name': 'Loc code cat %s' % self.tag, 'code': 'LCC'})
        asset = self.env['nrs.asset'].create(
            {'name': 'Loc code asset', 'category_id': category.id})
        tag = asset.active_tag_id
        self.assertTrue(tag)
        # A tag never begins LOC- on a real tenant; force the shape to prove
        # the check, in this transaction only. Raw SQL because the label
        # model guards its own number.
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE nrs_asset_tag_label SET name = %s WHERE id = %s",
            ('LOC-SHADOW-%s' % self.tag, tag.id))
        tag.invalidate_recordset(['name'])
        loc = self._loc('Shadow %s' % self.tag)
        with self.assertRaises(LocationCodeRefused) as caught:
            loc.write({'location_code': 'LOC-SHADOW-%s' % self.tag})
        self.assertEqual(caught.exception.kind, 'shadows')

    def test_naming_the_code_a_location_already_has_is_not_a_change(self):
        loc = self._loc('Resend %s' % self.tag)
        loc.write({'location_code': loc.location_code, 'description': 'x'})
        self.assertEqual(loc.description, 'x')

    def test_the_database_refuses_a_duplicate_the_model_did_not_see(self):
        """The second check: a writer that goes round the model (raw SQL)
        still meets the UNIQUE constraint — `models.Constraint`, because
        Odoo 19 creates nothing from `_sql_constraints`."""
        a = self._loc('SQL A %s' % self.tag)
        b = self._loc('SQL B %s' % self.tag)
        self.env.flush_all()
        with mute_logger('odoo.sql_db'), self.assertRaises(
                psycopg2.errors.UniqueViolation), self.env.cr.savepoint():
            self.env.cr.execute(
                "UPDATE generic_location SET location_code = %s WHERE id = %s",
                (a.location_code, b.id))
        self.env.cr.execute(
            "SELECT 1 FROM pg_constraint "
            "WHERE conname = 'generic_location_location_code_unique'")
        self.assertTrue(self.env.cr.fetchone(),
                        'the UNIQUE constraint exists under its Odoo 19 name')

    # ── the fill ──────────────────────────────────────────────────────

    def test_the_fill_gives_every_empty_location_a_code_and_is_idempotent(self):
        a = self._loc('Fill A %s' % self.tag, zone_code='F%s' % self.tag)
        b = self._loc('Fill B %s' % self.tag)
        self.env.flush_all()
        # The state before the migration: no code at all.
        self.env.cr.execute(
            "UPDATE generic_location SET location_code = NULL "
            "WHERE id IN %s", (tuple((a | b).ids),))
        (a | b).invalidate_recordset(['location_code'])
        filled, total = self.Location._fill_location_codes()
        self.assertGreaterEqual(filled, 2)
        self.assertEqual(a.location_code, 'LOC-F%s' % self.tag)
        self.assertEqual(b.location_code, 'LOC-%d' % b.id)
        codes_before = dict(self.Location.with_context(
            active_test=False).search([]).mapped(
                lambda l: (l.id, l.location_code)))
        self.assertEqual(self.Location._fill_location_codes(), (0, total),
                         'a second run writes nothing')
        codes_after = dict(self.Location.with_context(
            active_test=False).search([]).mapped(
                lambda l: (l.id, l.location_code)))
        self.assertEqual(codes_before, codes_after)

    def _asset_fingerprint(self):
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT count(*), md5(coalesce(string_agg(concat_ws('|', id, "
            "asset_code, serial_number, category_id, sap_asset_number, "
            "write_date), ',' ORDER BY id), '')) FROM nrs_asset")
        return self.env.cr.fetchone()

    def test_the_whole_tenant_from_nothing_one_code_each_none_collide(self):
        """The migration's own case, on this tenant's real rows: every code
        taken away (in this transaction), then the fill. Every location gets
        one, no two share one — and §10: no asset's code, serial, class or
        number moves, nor its write date."""
        assets_before = self._asset_fingerprint()
        self.env.cr.execute("UPDATE generic_location SET location_code = NULL")
        self.Location.invalidate_model(['location_code'])
        filled, total = self.Location._fill_location_codes()
        self.assertEqual(filled, total)
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT count(*), count(location_code), "
            "count(DISTINCT location_code), "
            "count(*) FILTER (WHERE location_code !~ '^LOC(-[A-Z0-9]+)+$') "
            "FROM generic_location")
        total_rows, coded, distinct, misshapen = self.env.cr.fetchone()
        self.assertEqual(coded, total_rows, '%d of %d locations have a code'
                         % (coded, total_rows))
        self.assertEqual(distinct, coded, '%d codes for %d locations'
                         % (distinct, coded))
        self.assertEqual(misshapen, 0)
        self.assertEqual(self._asset_fingerprint(), assets_before)

    # ── the scan ──────────────────────────────────────────────────────

    def test_a_room_code_resolves_last_and_names_no_asset(self):
        loc = self._loc('Scan room %s' % self.tag, zone_code='S%s' % self.tag)
        hit = _resolve_lookup(self.env, ' %s ' % loc.location_code.lower(),
                              rooms=True)
        self.assertTrue(hit['found'])
        self.assertEqual(hit['matched_by'], 'location')
        self.assertEqual(hit['location'], loc)
        self.assertNotIn('asset', hit)

    def test_the_public_portal_does_not_resolve_rooms(self):
        loc = self._loc('Portal room %s' % self.tag)
        hit = _resolve_lookup(self.env, loc.location_code)
        self.assertFalse(hit['found'])

    def test_an_archived_room_still_resolves(self):
        loc = self._loc('Archived room %s' % self.tag)
        loc.active = False
        hit = _resolve_lookup(self.env, loc.location_code, rooms=True)
        self.assertEqual(hit.get('location'), loc)

    def test_a_tag_still_beats_a_room(self):
        category = self.env['nrs.asset.category'].create(
            {'name': 'Loc scan cat %s' % self.tag, 'code': 'LSC'})
        asset = self.env['nrs.asset'].create(
            {'name': 'Loc scan asset', 'category_id': category.id})
        hit = _resolve_lookup(self.env, asset.active_tag_id.name, rooms=True)
        self.assertEqual(hit['matched_by'], 'tag_number')
        hit = _resolve_lookup(self.env, asset.asset_code, rooms=True)
        self.assertIn(hit['matched_by'], ('asset_code', 'tag_number'))
        self.assertEqual(hit['asset'], asset)

    # ── the label ─────────────────────────────────────────────────────

    def test_the_room_label_renders_a_pdf_at_both_sizes(self):
        loc = self._loc('Label room %s' % self.tag, zone_code='L%s' % self.tag)
        Report = self.env['ir.actions.report'].with_context(
            force_report_rendering=True)
        for name in ('myservice_asset_register.report_location_label_medium',
                     'myservice_asset_register.report_location_label_large'):
            content, kind = Report._render_qweb_pdf(name, [loc.id])
            self.assertEqual(kind, 'pdf', name)
            self.assertTrue(content.startswith(b'%PDF'), name)

    def test_the_room_label_encodes_the_code_verbatim(self):
        """Handoff 55 §3: no URL, no prefix inside the encoded value. Read
        at the one place the template hands a value to the encoder."""
        loc = self._loc('Verbatim room %s' % self.tag)
        encoded = []
        real = type(loc).get_room_label_barcode

        def recording(this, barcode_type, value, **kwargs):
            encoded.append((barcode_type, value))
            return real(this, barcode_type, value, **kwargs)

        for size in ('medium', 'large'):
            encoded.clear()
            with patch.object(type(loc), 'get_room_label_barcode', recording):
                html, _kind = self.env['ir.actions.report']._render_qweb_html(
                    'myservice_asset_register.report_location_label_%s'
                    % size, [loc.id])
            self.assertEqual(sorted(encoded),
                             [('Code128', loc.location_code),
                              ('QR', loc.location_code)], size)
            html = html.decode() if isinstance(html, bytes) else html
            self.assertIn(loc.location_code, html)

    def test_a_room_label_records_no_tag_print(self):
        """The print funnel stamps ASSET tag reports only."""
        loc = self._loc('No funnel %s' % self.tag)
        Label = self.env['nrs.asset.tag.label']
        printed_before = Label.search_count([('printed_date', '!=', False)])
        self.env['ir.actions.report'].with_context(
            force_report_rendering=True)._render_qweb_pdf(
                'myservice_asset_register.report_location_label_medium',
                [loc.id])
        self.assertEqual(
            Label.search_count([('printed_date', '!=', False)]),
            printed_before)
