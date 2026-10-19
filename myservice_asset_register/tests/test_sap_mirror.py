"""Handoff 63, in-registry — the SAP mirror, its import, the matcher, and §0.

Every record below is INVENTED in the October export's shapes
(`sap_export_shapes.py`); no row of NRS's export is in this repository.

* the reader: columns found by header name, a missing one refused naming
  it, Excel-serial dates, an 11-digit number kept as its digits, and a read
  resumed at every batch boundary yielding exactly the rows of one pass;
* the import job: ticks that resume, the counts, placeholders stored aside,
  the office from the tag, a re-import unchanged (and `write_date` not
  moved), a record missing from a newer export marked and kept, an office
  from SAP's location extract never overwritten, the upload not kept;
* the mirror is read-only to every writer but the importer;
* the matcher's five reasons, and a linked record excluded and counted;
* the coverage report's §6 count, contested links counted apart;
* §0 ruling 2: the tags active on two assets, listed; the unique index
  created where they read zero and not where they do not;
* §0 ruling 3: a category policy save is one write per category, and a
  recompute that changes nothing moves no `write_date`.

Run with:
    odoo -d test19 -u myservice_asset_register --test-enable \\
         --test-tags /myservice_asset_register:TestSapExportReader,/myservice_asset_register:TestSapImport,/myservice_asset_register:TestSapMatcher,/myservice_asset_register:TestActiveOnTwoAssets,/myservice_asset_register:TestCategorySaveIsBatched \\
         --stop-after-init --workers=0 --http-port=8099 --gevent-port=8098
"""
import base64
import datetime
import io
import json
import uuid
from unittest.mock import patch

import psycopg2

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.myservice_nrs_base.tests.common import CadraTransactionCase

from ..models import sap_export_reader as reader
from ..models.asset_snapshot import snapshot_today
from . import sap_export_shapes as shapes


def _uid():
    return uuid.uuid4().hex[:6].upper()


def _category(env):
    """A category of the test's own: an asset needs one."""
    return env['nrs.asset.category'].sudo().create(
        {'name': 'SAP mirror probe %s' % _uid()})


@tagged('post_install', '-at_install')
class TestSapExportReader(CadraTransactionCase):

    def _export(self, rows, **kw):
        return reader.Export(io.BytesIO(shapes.build_xlsx(rows, **kw)))

    def test_columns_are_found_by_name_and_a_missing_one_is_refused(self):
        ex = self._export([shapes.record('2000000001')])
        header, _prefix, _start = ex.header()
        colmap = reader.header_map(header)
        # SAP's layout puts the description in E and its second line in CC.
        self.assertEqual(colmap['description'], 'E')
        self.assertEqual(colmap['description_2'], 'CC')
        self.assertEqual(colmap['old_tag'], 'AM')
        ex = self._export([shapes.record('2000000001')],
                          drop=('Inventory number', 'Deactivation on'))
        header, _p, _s = ex.header()
        with self.assertRaises(reader.ExportRefused) as e:
            reader.header_map(header)
        self.assertIn('"Inventory number", "Deactivation on"', str(e.exception))
        self.assertEqual(e.exception.details['missing'],
                         ['Inventory number', 'Deactivation on'])

    def test_an_optional_column_may_be_absent(self):
        ex = self._export([shapes.record('2000000001')], drop=('Vendor',))
        colmap = reader.header_map(ex.header()[0])
        self.assertNotIn('vendor', colmap)

    def test_not_a_workbook_is_refused_in_words(self):
        with self.assertRaises(reader.ExportRefused) as e:
            reader.Export(io.BytesIO(b'asset,number\n1,2\n'))
        self.assertIn('not an .XLSX workbook', str(e.exception))

    def test_values_read_as_sap_wrote_them(self):
        strings = []
        # 29999999990 is invented, and absent from SAP's October export.
        self.assertEqual(reader.text_value((None, '29999999990'), strings),
                         '29999999990')
        self.assertEqual(reader.text_value((None, '2.999999999E10'), strings),
                         '29999999990')
        self.assertEqual(reader.date_value((None, '43538'), strings, False, 'X'),
                         datetime.date(2019, 3, 14))
        self.assertEqual(reader.date_value(('inlineStr', '14.03.2019'), strings,
                                           False, 'X'),
                         datetime.date(2019, 3, 14))
        self.assertIsNone(reader.date_value(('inlineStr', '00.00.0000'),
                                            strings, False, 'X'))
        with self.assertRaises(reader.RowRefused) as e:
            reader.date_value(('inlineStr', 'yesterday'), strings, False,
                              'Capitalized on')
        self.assertEqual(e.exception.reason,
                         'an unreadable date in "Capitalized on"')

    def test_a_read_resumed_at_every_boundary_is_one_read(self):
        rows = [shapes.record('2%010d' % i, tag='FIRS/HQ%02d/%04d' % (i % 7, i))
                for i in range(120)]
        ex = self._export(rows)
        header, prefix, start = ex.header()
        colmap = reader.header_map(header)
        strings = ex.shared_strings()
        with patch.object(reader, 'FEED_BYTES', 700):
            whole, offsets = [], []
            for batch, offset, _last in ex.iter_batches(colmap, strings,
                                                        start, prefix):
                whole += batch
                offsets.append(offset)
            self.assertGreater(len(offsets), 10)
            self.assertEqual(len(whole), 120)
            # Resume from every boundary in turn: what is read from there
            # is exactly the tail of the single pass.
            seen = 0
            for offset in offsets[:-1]:
                seen = sum(len(b) for b, o, _l in ex.iter_batches(
                    colmap, strings, start, prefix) if o <= offset)
                tail = [r for b, _o, _l in ex.iter_batches(
                    colmap, strings, offset, prefix) for r in b]
                self.assertEqual(tail, whole[seen:])


class _ImportMixin:

    def _run(self, rows, *, cpu_budget=None, user=None, mark_absent=True,
             **kw):
        """`mark_absent` (handoff 65 §3): these tests import small invented
        files over whatever mirror the tenant holds, so they say "Yes, mark
        them absent" unless the guard is what they test."""
        raw = shapes.build_xlsx(rows, **kw)
        export = reader.Export(io.BytesIO(raw))
        header, prefix, start = export.header()
        run = self.env['nrs.sap.import.run'].sudo().create({
            'file_name': 'test.xlsx', 'file_size': len(raw),
            'sheet_size': export.zip.getinfo(export.sheet_path).file_size,
            'file_data': base64.b64encode(raw),
            'uploaded_by': (user or self.env.user).id,
            'header_map': json.dumps(reader.header_map(header)),
            'sheet_prefix': prefix.decode('utf-8'), 'resume_offset': start,
            'absent_confirmed': mark_absent})
        return run._run_to_end(cpu_budget=cpu_budget)

    def _rec(self, number):
        return self.env['nrs.sap.asset'].sudo().search(
            [('asset_number_norm', '=', number.upper())])


@tagged('post_install', '-at_install')
class TestSapImport(_ImportMixin, CadraTransactionCase):

    def setUp(self):
        super().setUp()
        self.u = _uid()

    # ── handoff 65 §3: the 5% guard ───────────────────────────────────

    def _scratch_rows(self, run):
        self.env.cr.execute(
            "SELECT count(*) FROM nrs_sap_import_seen WHERE run_id = %s",
            [run.id])
        return self.env.cr.fetchone()[0]

    def test_a_count_under_the_guard_rewinds_and_writes(self):
        """1 of 40 absent (2.5%): counted, then written from the FIRST data
        row — read over many ticks, so the count's resume and the rewind are
        both exercised (verification pass, finding 5)."""
        u = self.u
        rows = [shapes.record('2W%s%03d' % (u, i)) for i in range(40)]
        self._run(rows)
        new = shapes.record('2W%sNEW' % u)
        with patch.object(reader, 'FEED_BYTES', 400):
            run = self._run(rows[:39] + [new], mark_absent=False,
                            cpu_budget=0.0)
        self.assertEqual(run.state, 'done', run.message)
        self.assertEqual((run.phase, run.mirror_records_before,
                          run.would_mark_absent), ('write', 40, 1))
        self.assertGreater(run.ticks, 4, 'the count and the write each '
                                         'took more than one tick')
        self.assertEqual(run.rows_read, 40, 'the write pass read every row '
                                            'once, from the first')
        self.assertEqual((run.created_count, run.marked_absent_count), (1, 1))
        self.assertEqual(run.unchanged_count + run.updated_count, 39)
        self.assertFalse(run.absent_confirmed)
        self.assertEqual(self._scratch_rows(run), 0, 'the scratch is emptied')
        self.assertFalse(self._rec('2W%s039' % u).in_latest_export)

    def test_a_count_over_the_guard_holds_and_writes_nothing(self):
        u = self.u
        rows = [shapes.record('2H%s%03d' % (u, i)) for i in range(40)]
        self._run(rows)
        before = self.env['nrs.sap.asset'].search_count(
            [('in_latest_export', '=', True)])
        run = self._run(rows[:2] + [shapes.record('2H%sNEW' % u)],
                        mark_absent=False)
        self.assertEqual(run.state, 'held')
        self.assertEqual((run.would_mark_absent, run.mirror_records_before,
                          run.created_count, run.marked_absent_count),
                         (38, 40, 0, 0))
        self.assertIn('truncated', run.message)
        self.assertFalse(self._rec('2H%sNEW' % u), 'nothing was created')
        self.assertEqual(self.env['nrs.sap.asset'].search_count(
            [('in_latest_export', '=', True)]), before, 'nothing was marked')
        self.assertFalse(run._attachment(), 'the file is not kept')
        self.assertEqual(self._scratch_rows(run), 0)

    def test_an_import_reads_counts_and_drops_the_file(self):
        u = self.u
        rows = [
            shapes.record('2T%s001' % u, tag='FIRS/O%s/0001' % u,
                          serial='SN-%s-REAL' % u, description_2='BLACK',
                          vendor='V%s' % u),
            shapes.record('2T%s002' % u, tag=r'firs\o%s\0002' % u.lower(),
                          serial='XXXX'),
            shapes.record('2T%s003' % u, retired=datetime.date(2020, 1, 1)),
            shapes.record('2T%s003' % u, sub='0001'),  # a sub-number
            shapes.record('', description='NO NUMBER'),
            shapes.record('2T%s001' % u),               # twice in one file
        ]
        with patch.object(reader, 'FEED_BYTES', 400):
            run = self._run(rows, cpu_budget=0)
        self.assertEqual(run.state, 'done')
        self.assertGreater(run.ticks, 1, 'a zero budget ends every tick '
                                         'after one batch')
        self.assertLess(run.ticks, 50, 'and the run still ends')
        self.assertEqual((run.rows_read, run.created_count, run.refused_count),
                         (6, 4, 2))
        self.assertEqual(json.loads(run.refused_reasons), {
            'no asset number': 1,
            'the same asset number and sub-number twice in this file': 1})
        self.assertFalse(run._attachment(), 'the upload is not kept')
        one = self._rec('2T%s001' % u)
        self.assertEqual((one.office_code, one.office_source, one.serial_kind,
                          one.serial_number, one.description_2,
                          one.capitalized_on),
                         ('O%s' % u, 'tag', 'real', 'SN-%s-REAL' % u, 'BLACK',
                          datetime.date(2019, 3, 14)))
        two = self._rec('2T%s002' % u)
        self.assertEqual(two.old_tag_norm, 'FIRS/O%s/0002' % u)
        self.assertEqual((two.serial_kind, two.serial_number,
                          two.serial_placeholder), ('placeholder', False, 'XXXX'))
        three = self._rec('2T%s003' % u)
        self.assertEqual(len(three), 2, 'main record and sub-number 1')
        main = three.filtered(lambda r: r.sub_number_norm == '0')
        self.assertFalse(main.sap_active)
        self.assertEqual(main.office_source, 'none')

    def test_a_reimport_is_unchanged_and_a_missing_record_is_kept(self):
        u = self.u
        rows = [shapes.record('2U%s%03d' % (u, i)) for i in range(5)]
        self._run(rows)
        rec = self._rec('2U%s000' % u)
        self.env.cr.execute(
            "UPDATE nrs_sap_asset SET write_date = '2026-01-01' WHERE id = %s",
            [rec.id])
        again = self._run(rows)
        self.assertEqual((again.created_count, again.updated_count,
                          again.unchanged_count), (0, 0, 5))
        rec.invalidate_recordset()
        self.assertEqual(str(rec.write_date), '2026-01-01 00:00:00',
                         'an unchanged record does not move write_date')
        changed = [dict(rows[0], description='OFFICE CHAIR SWIVEL')] + rows[2:]
        third = self._run(changed)
        self.assertEqual((third.updated_count, third.unchanged_count), (1, 3))
        self.assertGreaterEqual(third.marked_absent_count, 1)
        gone = self._rec('2U%s001' % u)
        self.assertTrue(gone.exists())
        self.assertFalse(gone.in_latest_export)
        back = self._run(rows)
        self.assertGreaterEqual(back.updated_count, 2,
                                'the reappeared and the re-changed record')
        gone.invalidate_recordset()
        self.assertTrue(gone.in_latest_export)

    def test_an_office_from_the_location_extract_is_not_overwritten(self):
        u = self.u
        rows = [shapes.record('2L%s001' % u, tag='FIRS/A%s/1' % u)]
        self._run(rows)
        rec = self._rec('2L%s001' % u)
        rec.with_context(cadra_sap_mirror_import=True).write({
            'office_code': 'EXTRACT%s' % u,
            'office_source': 'location_extract'})
        self._run([dict(rows[0], description='OFFICE CHAIR ARMLESS')])
        rec.invalidate_recordset()
        self.assertEqual((rec.office_code, rec.office_source,
                          rec.description),
                         ('EXTRACT%s' % u, 'location_extract',
                          'OFFICE CHAIR ARMLESS'))

    def test_a_file_that_stops_making_sense_fails_the_run_in_words(self):
        run = self._run([shapes.record('2F%s001' % self.u)])
        bad = run.copy({'state': 'queued', 'file_data': base64.b64encode(
            b'not a zip')})
        bad._run_to_end()
        self.assertEqual(bad.state, 'failed')
        self.assertIn('not an .XLSX workbook', bad.message)
        self.assertFalse(bad._attachment())

    def test_the_mirror_is_read_only_to_everyone_but_the_importer(self):
        self._run([shapes.record('2R%s001' % self.u)])
        rec = self._rec('2R%s001' % self.u)
        with self.assertRaises(UserError):
            rec.write({'description': 'EDITED'})
        with self.assertRaises(UserError):
            rec.unlink()
        with self.assertRaises(UserError):
            self.env['nrs.sap.asset'].sudo().create({'sap_key': 'X|0'})

    def test_a_test_credentials_run_labels_its_rows(self):
        if 'is_test_fixture' not in self.env['nrs.sap.asset']._fields:
            self.skipTest('myservice_api (the fixture label) is not installed')
        run = self._run([shapes.record('2X%s001' % self.u)])
        self.assertEqual(self._rec('2X%s001' % self.u).is_test_fixture,
                         run.is_test_fixture)


@tagged('post_install', '-at_install')
class TestSapMatcher(_ImportMixin, CadraTransactionCase):
    """Each answer says why it ranked (handoff 63 §2) — one test per reason."""

    def setUp(self):
        super().setUp()
        u = self.u = _uid()
        self.w = 'ZQ%s' % u   # a word no other record on the tenant carries
        self.office = 'M%s' % u
        rows = [
            shapes.record('2M%s001' % u, tag='FIRS/%s/0001' % self.office,
                          description='%s CHAIR' % self.w),
            shapes.record('2M%s002' % u, tag='FIRS/%s/0002' % self.office,
                          description='%s CHAIR' % self.w),
            shapes.record('2M%s003' % u, tag='FIRS/%s/0002' % self.office,
                          description='%s TABLE' % self.w),
            shapes.record('2M%s004' % u, serial='SN-%s-ONLY' % u,
                          description='%s DESK' % self.w),
            shapes.record('2M%s005' % u, description='%s CABINET' % self.w),
        ]
        self._run(rows)
        self.Sap = self.env['nrs.sap.asset']

    def _top(self, **query):
        answer = self.Sap._match(**query)
        top = answer['results'][0]
        return answer, top, self.Sap.browse(top['id']).asset_number

    def test_old_tag_unique(self):
        a, top, number = self._top(old_tag=' firs\\%s\\0001 ' % self.office.lower())
        self.assertEqual((top['reason_code'], top['reason'], number),
                         ('old_tag_unique', 'old tag, unique',
                          '2M%s001' % self.u))
        self.assertEqual(a['tied_at_top'], 1)

    def test_old_tag_shared_settled_by_the_description(self):
        a, top, number = self._top(old_tag='FIRS/%s/0002' % self.office,
                                   description='table')
        self.assertEqual(number, '2M%s003' % self.u)
        self.assertEqual(top['reason'], 'old tag, shared by 2; description '
                                        'matches')
        self.assertEqual(a['results'][1]['reason'],
                         'old tag, shared by 2; description does not match')

    def test_serial_unique_when_no_record_carries_the_tag(self):
        a, top, number = self._top(old_tag='FIRS/NOWHERE/1',
                                   serial='sn-%s-only' % self.u.lower())
        self.assertEqual((top['reason_code'], number),
                         ('serial_unique', '2M%s004' % self.u))
        self.assertIn('No active SAP record carries the old tag', a['notes'][0])
        a = self.Sap._match(serial='XXXX', description='nothing')
        self.assertIn('placeholder', a['notes'][0])

    def test_description_within_the_office_from_the_tag(self):
        a, top, number = self._top(old_tag='FIRS/%s/9999' % self.office,
                                   description='%s chair' % self.w)
        self.assertEqual(a['basis'], 'description')
        self.assertEqual((a['office_used'], a['office_from']),
                         (self.office, 'tag'))
        self.assertEqual(top['reason'], 'description; office %s' % self.office)
        self.assertEqual(a['tied_at_top'], 2)

    def test_description_nationwide_when_no_office_is_known(self):
        a, top, number = self._top(description='%s cabinet' % self.w,
                                   asset_class='2000')
        self.assertEqual((top['reason_code'], top['reason'], number),
                         ('description_nationwide',
                          'description and class; office unknown',
                          '2M%s005' % self.u))
        partial = self.Sap._match(description='%s cabinet steel' % self.w)
        self.assertIn('(matches 2 of 3 words)',
                      partial['results'][0]['reason'])

    def test_a_record_already_linked_is_not_offered_and_is_counted(self):
        sap = self.Sap.search([('asset_number', '=', '2M%s001' % self.u)])
        self.env['nrs.asset'].sudo().create({
            'name': 'linked probe %s' % self.u,
            'category_id': _category(self.env).id,
            'sap_asset_number': ' 2m%s001 ' % self.u.lower()})
        a = self.Sap._match(old_tag='FIRS/%s/0001' % self.office)
        self.assertEqual(a['results'], [])
        self.assertEqual(a['already_linked'], 1)
        self.assertEqual(a['already_linked_note'],
                         "1 more already on Cadra's register")
        self.assertTrue(sap._linked_assets())

    def test_reconcilable_today_counts_contested_links_apart(self):
        before = self.Sap._confident_links()
        Asset = self.env['nrs.asset'].sudo()
        cat = _category(self.env).id
        tag = 'FIRS/%s/0001' % self.office
        Asset.create({'name': 'c1 %s' % self.u, 'category_id': cat,
                      'legacy_asset_code': tag})
        Asset.create({'name': 'c2 %s' % self.u, 'category_id': cat,
                      'legacy_asset_code': tag.lower()})
        Asset.create({'name': 'c3 %s' % self.u, 'category_id': cat,
                      'serial_number': 'SN-%s-ONLY' % self.u})
        after = self.Sap._confident_links()
        self.assertEqual(after['by_unique_old_tag']
                         - before['by_unique_old_tag'], 2)
        self.assertEqual(after['by_unique_serial']
                         - before['by_unique_serial'], 1)
        self.assertEqual(after['contested_assets']
                         - before['contested_assets'], 2)
        self.assertEqual(after['uncontested'] - before['uncontested'], 1)


@tagged('post_install', '-at_install')
class TestActiveOnTwoAssets(CadraTransactionCase):
    """§0 ruling 2: listed for a person, and the index only where it fits."""

    def test_the_filter_lists_them_and_the_index_waits_for_zero(self):
        Tag = self.env['nrs.asset.tag.label'].sudo()
        cr = self.env.cr
        cr.execute('DROP INDEX IF EXISTS %s' % Tag.ACTIVE_NUMBER_INDEX)
        Asset = self.env['nrs.asset'].sudo()
        cat = _category(self.env).id
        a1 = Asset.create({'name': 'dup probe 1', 'category_id': cat})
        a2 = Asset.create({'name': 'dup probe 2', 'category_id': cat})
        number = 'DUP-%s' % _uid()
        t1 = Tag.create({'name': number, 'asset_id': a1.id})
        self.env.flush_all()
        # The ORM refuses a second active label with the number; the data
        # this ruling is about got there some other way, so it is made the
        # same way here.
        t2 = Tag.create({'name': number + '-B', 'asset_id': a2.id})
        self.env.flush_all()
        cr.execute("UPDATE nrs_asset_tag_label SET name = %s WHERE id = %s",
                   [number, t2.id])
        t2.invalidate_recordset()
        listed = Tag.search([('active_number_shared', '=', True)])
        self.assertIn(t1, listed)
        self.assertIn(t2, listed)
        self.assertTrue(t2.active_number_shared)
        numbers, labels = Tag._active_number_duplicates()
        self.assertGreaterEqual((numbers, labels), (1, 2))
        with mute_logger('odoo.addons.myservice_asset_register.models.asset_tag'):
            Tag.init()
        cr.execute('SELECT 1 FROM pg_indexes WHERE indexname = %s',
                   [Tag.ACTIVE_NUMBER_INDEX])
        self.assertFalse(cr.fetchone(), 'not created while any number is '
                                        'active twice')
        # Resolve every duplicate on the tenant inside this transaction (it
        # is rolled back), then the next upgrade creates the index.
        cr.execute("""UPDATE nrs_asset_tag_label t SET state = 'scrapped'
                       WHERE t.state = 'active' AND EXISTS (
                         SELECT 1 FROM nrs_asset_tag_label o
                          WHERE o.state = 'active' AND o.name = t.name
                            AND o.id < t.id)""")
        Tag.init()
        cr.execute('SELECT 1 FROM pg_indexes WHERE indexname = %s',
                   [Tag.ACTIVE_NUMBER_INDEX])
        self.assertTrue(cr.fetchone())
        with self.assertRaises(psycopg2.errors.UniqueViolation), \
                mute_logger('odoo.sql_db'), cr.savepoint():
            cr.execute("UPDATE nrs_asset_tag_label SET state = 'active' "
                       "WHERE id = %s", [t2.id])


@tagged('post_install', '-at_install')
class TestCategorySaveIsBatched(CadraTransactionCase):
    """§0 ruling 3: report 61 measured 162,072 writes for one category save
    on a class of 18,008 — nine per asset. One per category now."""

    def setUp(self):
        super().setUp()
        if 'use_category_policy' not in self.env['nrs.asset']._fields:
            self.skipTest('myservice_asset_depreciation is not installed')
        self.cat = self.env['nrs.asset.category'].sudo().create({
            'name': 'Batch probe %s' % _uid(), 'depreciation_method':
            'straight_line', 'useful_life_months': 60})
        self.assets = self.env['nrs.asset'].sudo().create([{
            'name': 'batch %d' % i, 'category_id': self.cat.id,
            'acquisition_cost': 1000.0 * (i + 1),
            'acquisition_date': datetime.date(2022, 1, 1)}
            for i in range(30)])

    def test_the_policy_reaches_every_asset_in_one_write(self):
        Asset = type(self.env['nrs.asset'])
        calls = []
        real = Asset.write

        def counting(records, vals):
            calls.append((len(records), tuple(sorted(vals))))
            return real(records, vals)

        self.cat.write({'useful_life_months': 36})
        with patch.object(Asset, 'write', counting):
            self.assets._sync_policy_from_category()
            self.assets._apply_depreciation()
        policy = [c for c in calls if 'useful_life_months' in c[1]]
        self.assertEqual(policy, [(30, ('declining_rate',
                                        'depreciation_method',
                                        'salvage_rate',
                                        'useful_life_months'))])
        self.assertEqual(len(calls), 1, 'the figures are not ORM writes')
        self.assertEqual(set(self.assets.mapped('useful_life_months')), {36})
        # The figures stored by SQL are the engine's, asset by asset.
        from odoo.addons.myservice_asset_depreciation.models import (
            depreciation_engine as engine)
        today = snapshot_today()
        for a in self.assets:
            acc, bv, state = engine.value_at(today, **a._depreciation_policy())
            self.assertEqual((a.accumulated_depreciation,
                              a.current_book_value, a.depreciation_state),
                             (acc, bv, state))

    def test_a_recompute_that_changes_nothing_moves_no_write_date(self):
        # Assets with NO schedule too (method none, no cost) — the engine's
        # `None` end date against the cache's `False` made every one of them
        # "changed" on every recompute (the verification pass): 19,453 of
        # 22,042 on `test19`. And a cost that does not round evenly.
        none_cat = self.env['nrs.asset.category'].sudo().create({
            'name': 'No schedule %s' % _uid(), 'depreciation_method': 'none'})
        self.assets |= self.env['nrs.asset'].sudo().create([
            {'name': 'no schedule', 'category_id': none_cat.id},
            {'name': 'no cost', 'category_id': self.cat.id},
            {'name': 'odd cost', 'category_id': self.cat.id,
             'acquisition_cost': 1000.0 / 3,
             'acquisition_date': datetime.date(2021, 7, 13)}])
        self.assets._apply_depreciation()
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE nrs_asset SET write_date = '2026-01-01' WHERE id = ANY(%s)",
            [self.assets.ids])
        self.assets.invalidate_recordset()
        self.assets._apply_depreciation()
        self.env.flush_all()
        self.assets.invalidate_recordset()
        self.assertEqual({str(d) for d in self.assets.mapped('write_date')},
                         {'2026-01-01 00:00:00'})
