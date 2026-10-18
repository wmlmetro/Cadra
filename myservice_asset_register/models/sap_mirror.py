# -*- coding: utf-8 -*-
"""What SAP holds, in Cadra — the SAP mirror (handoff 63).

`nrs.sap.asset` is a READ-ONLY REFERENCE TABLE of SAP's fixed-asset master
for NRS, loaded from SAP's own export. It is **not** `nrs.asset`: it is not
on the register, in a count, a report of assets or an export of assets.
Nothing about it touches `nrs.asset`'s search — no row of it is an asset.

Why it exists (`docs/AI-CAPTURE-EVALUATION.md` §1, §3): SAP already holds
NRS's register — 161,647 active assets in the October 2026 export, 80,370
of them furniture. A chair an audit team finds in a room is almost certainly
one of them. Before Cadra can say *"this chair is SAP asset 2NNNNNNNNNN"*
it has to know what SAP holds, which is this table; and before any audit
team goes into a room it already answers the first question NRS will ask —
how much of SAP's register Cadra holds (`GET /reports/sap-coverage`).

THE IMPORT IS A JOB, NOT A REQUEST
---------------------------------
The System Administrator uploads the `.XLSX` as SAP produced it. The upload
route reads the header row only (a missing column is refused there and
then, naming it) and records an `nrs.sap.import.run`; the cron below reads
the rest in TICKS of at most `TICK_CPU_SECONDS` of CPU, each committing what
it read and the decompressed offset it reached, so a cron worker killed by
`limit_time_cpu` (60 s locally, 600 s on the cluster) loses one tick, never
the run. A tick that leaves work triggers the cron again; the cron's own
five-minute interval picks up a tick that was killed. The parser is
`sap_export_reader` (streamed; 148 MB peak over the 655 MB sheet).

Why not the thread the employee import uses (`nrs.employee.import.job`):
a thread inside an HTTP worker shares that process's RLIMIT_CPU, which Odoo
resets per request to `limit_time_cpu` — a 50-second parse in a thread
gets the WORKER killed, with whatever request it is serving.

* **Upsert on (asset number, sub-number)** — both normalised: the number
  stripped and upper-cased (handoff 59's rule for SAP numbers), the
  sub-number with leading zeros dropped (`0`, `00`, blank are the main
  record). A record missing from a new export is marked
  `in_latest_export = False`, **never deleted** — the table refuses
  `unlink` outright.
* **Unchanged is unchanged**: a row whose values hash to what is stored is
  counted `unchanged` and its `write_date` is NOT moved, so
  `GET /sap-assets?updated_since=` hands an offline phone only what changed.
* **The uploaded file is not kept.** It is NRS's register; the table holds
  what the mirror needs. The attachment is deleted when the run ends, done
  or failed.
* **Placeholder serials** (handoff 59's tenant list, `cadra.serial_placeholders`)
  are stored as `serial_kind = 'placeholder'` with the value aside — never
  as a serial, so the matcher can never match one.
* **The office** is parsed from a `FIRS/<office>/…` old tag
  (`office_source = 'tag'`). SAP's export carries no cost centre or
  location (report 61 §12); the owner has asked SAP's team for the
  location extract (ANLZ), and when it arrives a later import fills the
  office with `office_source = 'location_extract'`, which an export import
  then never overwrites. An untagged record's office is `none`.

Rows are written with SQL in batches (`execute_values`), not one ORM
`create` per row: 211,699 ORM creates is an hour. Nothing watches these
rows — no recorder, no gate — and the ORM `create`/`write` are refused to
every other writer, so the importer is the only writer there is.

THE LINK TO THE REGISTER — computed, not stored
-----------------------------------------------
A Cadra asset whose `sap_asset_number` matches a mirror record (stripped,
upper-cased — handoff 59's rule — the sub-numbers compared the same way,
and the company code compared when the asset carries one) is LINKED to it.
**Computed at read time** by one join (`LINKED_CTE`), never stored:
`sap_asset_number` has many writers (the legacy importer, INT-07, the
Register Maker's gate, the back office), and a stored link refreshed "on
every SAP-number write" is a link that goes stale on the writer somebody
forgets. The join is driven from the assets that carry a number (2 of
11,959 on `nrs19` today) through an index on the mirror's normalised
number, so it costs milliseconds whichever side is large.
"""
import hashlib
import io
import json
import logging
import re
import resource
import time

from psycopg2.extras import execute_values

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules import module as odoo_module

from . import sap_export_reader as reader
from . import serial_placeholders

_logger = logging.getLogger(__name__)

#: CPU a tick may spend reading before it commits and hands over to the
#: next. Under the local `limit_time_cpu` (60 s) with room for the shared
#: strings (1.1 s), the skip to the offset (≤ 0.8 s) and the writes.
TICK_CPU_SECONDS = 25.0
#: Wall time likewise — a tick waiting on the database is still a tick.
TICK_WALL_SECONDS = 90.0
#: Rows per batched write.
FLUSH_ROWS = 2000
#: A sheet larger than this (decompressed) is refused at upload: the offset
#: is an `int4`, and nothing SAP exports for one company code is near it.
MAX_SHEET_BYTES = 2_000_000_000

OFFICE_SOURCES = [
    ('tag', 'From the old FIRS tag'),
    ('location_extract', "From SAP's location extract"),
    ('none', 'No office'),
]
SERIAL_KINDS = [
    ('none', 'No serial'),
    ('real', 'Serial'),
    ('placeholder', 'Placeholder'),
]
RUN_STATES = [
    ('queued', 'Queued'),
    ('running', 'Running'),
    ('done', 'Done'),
    ('failed', 'Failed'),
]

_OFFICE_FROM_TAG = re.compile(r'^FIRS/([A-Z0-9]+)/')
_WORDS = re.compile(r'[A-Z0-9]+')

#: The register's side of the link. Driven from the assets that carry an
#: SAP number, through `nrs_sap_asset_number_norm_idx`. Every nrs_asset row
#: counts — a receipt candidate whose maker typed the number and an
#: archived asset claim it too (the same rows handoff 59's uniqueness check
#: compares), so offering that SAP record to somebody else would make a
#: second claim on it.
#: How an asset `a` and a mirror record `s` are linked.
_LINK_COND = """
    a.sap_asset_number IS NOT NULL
    AND upper(btrim(a.sap_asset_number)) = s.asset_number_norm
    AND coalesce(nullif(ltrim(btrim(a.sap_asset_subnumber), '0'), ''), '0')
        = s.sub_number_norm
    AND (coalesce(btrim(a.sap_company_code), '') = ''
         OR upper(btrim(a.sap_company_code)) = s.company_code)"""

#: The whole table's links, computed ONCE per statement (`MATERIALIZED`)
#: and driven from the assets that carry a number, each looking its record
#: up by index. Written this way because the obvious join was planned as a
#: hash of the whole mirror on every query: Postgres estimated 6,999 assets
#: with an SAP number on `nrs19`, which has 2, and each matcher call took
#: 370 ms (measured, handoff 63). For the coverage report and §6.
LINKED_CTE = """
    linked AS MATERIALIZED (
        SELECT DISTINCT ON (s.id) s.id AS sap_id, a.id AS asset_id,
               a.register_state AS asset_register_state
          FROM nrs_asset a
          CROSS JOIN LATERAL (
                SELECT s.id FROM nrs_sap_asset s WHERE %s) s
         WHERE a.sap_asset_number IS NOT NULL
           AND btrim(a.sap_asset_number) <> ''
         ORDER BY s.id, a.id
    )""" % _LINK_COND

#: One record's link, for a pool of candidates: an index probe per row
#: (`nrs_asset_sap_number_norm_idx`), so the matcher costs what its pool
#: costs, not what the whole register costs.
LINKED_EXISTS = "EXISTS (SELECT 1 FROM nrs_asset a WHERE %s)" % _LINK_COND


def _under_test():
    return bool(odoo_module.current_test)


def norm_number(value):
    return (value or '').strip().upper()


def norm_sub(value):
    return (value or '').strip().lstrip('0') or '0'


def norm_tag(value):
    """Old FIRS tag as compared: trimmed, upper-case, `\\` → `/`, inner
    whitespace removed (a tag is one token; 61 §12 measured the looser form
    moving the shares by under 0.4 points)."""
    return re.sub(r'\s+', '', (value or '').strip().upper().replace('\\', '/'))


def office_from_tag(tag_norm):
    m = _OFFICE_FROM_TAG.match(tag_norm or '')
    return m.group(1) if m else None


def desc_words(*texts):
    """Both descriptions as ` WORD WORD ` — upper-case, every run of
    non-alphanumerics one space, padded — so `LIKE '% CHAIR %'` is a
    whole-word, case-insensitive test."""
    words = []
    for t in texts:
        words += _WORDS.findall((t or '').upper())
    return (' %s ' % ' '.join(words)) if words else ''


def query_words(text):
    """The distinct words of a description someone typed, in order."""
    return list(dict.fromkeys(_WORDS.findall((text or '').upper())))


class NRSSapAsset(models.Model):
    _name = 'nrs.sap.asset'
    _description = "SAP asset master (mirror, read-only)"
    _order = 'asset_number_norm, sub_number_norm'
    _rec_name = 'asset_number'

    sap_key = fields.Char(
        'Key', required=True, readonly=True, index=True,
        help='Normalised asset number and sub-number, `NUMBER|SUB`. What an '
             'import upserts on.')
    company_code = fields.Char('Company Code', readonly=True)
    asset_number = fields.Char('SAP Asset Number', readonly=True,
                               help='As SAP wrote it.')
    asset_number_norm = fields.Char(readonly=True, index=True)
    sub_number = fields.Char('Sub-number', readonly=True)
    sub_number_norm = fields.Char(readonly=True)
    asset_class = fields.Char('SAP Asset Class', readonly=True, index=True)
    description = fields.Char('Description', readonly=True)
    description_2 = fields.Char('Description (second line)', readonly=True)
    desc_words = fields.Char(readonly=True,
                             help='Both descriptions, whole words, for the '
                                  'matcher. Not published.')
    old_tag = fields.Char('Old FIRS Tag', readonly=True,
                          help="SAP's Inventory number, as SAP wrote it. "
                               'Not unique: 12,061 numbers are shared in the '
                               'October export.')
    old_tag_norm = fields.Char(readonly=True, index=True)
    office_code = fields.Char('Office Code', readonly=True, index=True)
    office_source = fields.Selection(OFFICE_SOURCES, 'Office From',
                                     readonly=True, default='none')
    serial_number = fields.Char('Serial Number', readonly=True,
                                help='A real-looking serial only.')
    serial_norm = fields.Char(readonly=True, index=True)
    serial_kind = fields.Selection(SERIAL_KINDS, 'Serial', readonly=True,
                                   default='none')
    serial_placeholder = fields.Char(
        'Placeholder Serial', readonly=True,
        help='What was typed where a serial should be (`0`, `XXXX`, …), kept '
             'aside so it is never matched as a serial.')
    capitalized_on = fields.Date('Capitalised On', readonly=True)
    first_acquired_on = fields.Date('First Acquisition On', readonly=True)
    sap_created_on = fields.Date('Created in SAP On', readonly=True)
    deactivated_on = fields.Date('Deactivated On', readonly=True)
    sap_active = fields.Boolean(
        'Active in SAP', compute='_compute_sap_active', store=True,
        index=True, readonly=True,
        help='No deactivation date. Computed — the importer writes the same '
             'rule.')
    vendor = fields.Char('Vendor', readonly=True)
    in_latest_export = fields.Boolean(
        'In the Latest Export', readonly=True, default=True, index=True,
        help='False once an import ran without this record. It is kept, '
             'never deleted.')
    first_import_id = fields.Many2one('nrs.sap.import.run', readonly=True,
                                      ondelete='restrict')
    last_import_id = fields.Many2one('nrs.sap.import.run', readonly=True,
                                     ondelete='restrict', index=True)
    row_hash = fields.Char(readonly=True)

    _sap_key_unique = models.Constraint(
        'UNIQUE (sap_key)',
        'The SAP mirror holds one record per asset number and sub-number.',
    )

    @api.depends('deactivated_on')
    def _compute_sap_active(self):
        for r in self:
            r.sap_active = not r.deactivated_on

    def init(self):
        # The register's side of the link (`LINKED_CTE`): an expression
        # index so the join from an asset's typed number is an index probe.
        self.env.cr.execute(
            "CREATE INDEX IF NOT EXISTS nrs_asset_sap_number_norm_idx "
            "ON nrs_asset (upper(btrim(sap_asset_number))) "
            "WHERE sap_asset_number IS NOT NULL")
        self.env.cr.execute(
            "CREATE INDEX IF NOT EXISTS nrs_sap_asset_number_norm_sub_idx "
            "ON nrs_sap_asset (asset_number_norm, sub_number_norm)")

    # ── read-only ─────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('cadra_sap_mirror_import'):
            raise UserError(_(
                "The SAP mirror is SAP's register, read-only in Cadra. Records "
                "arrive only by importing SAP's asset-master export (Settings "
                "→ SAP asset master)."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('cadra_sap_mirror_import'):
            raise UserError(_(
                "The SAP mirror is SAP's register, read-only in Cadra. A record "
                "changes only when a newer export of SAP's asset master is "
                "imported."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_(
            'A record of the SAP mirror is never deleted. One missing from a '
            'newer export is marked "not in the latest export" and kept.'))

    # ── the link ──────────────────────────────────────────────────────

    def _linked_assets(self):
        """`{sap_id: {'asset_id', 'register_state'}}` for these records —
        driven from THESE records, an index probe each."""
        if not self.ids:
            return {}
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT DISTINCT ON (s.id) s.id, a.id, a.register_state "
            "  FROM nrs_sap_asset s JOIN nrs_asset a ON %s "
            " WHERE s.id = ANY(%%s) ORDER BY s.id, a.id" % _LINK_COND,
            [self.ids])
        return {sap_id: {'asset_id': asset_id, 'register_state': state}
                for sap_id, asset_id, state in self.env.cr.fetchall()}

    @api.model
    def _for_asset(self, asset):
        """The mirror record a Cadra asset is linked to, or an empty set."""
        number = norm_number(asset.sap_asset_number)
        if not number:
            return self.browse()
        self.env.flush_all()
        sub = norm_sub(asset.sap_asset_subnumber)
        company = norm_number(asset.sap_company_code)
        self.env.cr.execute(
            "SELECT id FROM nrs_sap_asset WHERE asset_number_norm = %s "
            "AND sub_number_norm = %s AND (%s = '' OR company_code = %s) "
            "ORDER BY id LIMIT 1", [number, sub, company, company])
        row = self.env.cr.fetchone()
        return self.browse(row[0]) if row else self.browse()

    # ── the first reconciliation (handoff 63 §3) ──────────────────────

    @api.model
    def _coverage(self):
        """How much of SAP's register Cadra holds, by class and by office.

        SAP's side counts records ACTIVE in SAP and IN THE LATEST EXPORT.
        Cadra's side counts assets ON THE REGISTER (`register_state =
        'registered'`; an asset has no archive); a Cadra asset's class is its
        category's `sap_asset_class` (handoff 59), and it has no office —
        Cadra's locations carry no SAP office code, so the Cadra columns of
        the by-office table are null and say why.

        `confident` is §6's question: of the Cadra assets with no SAP
        number, how many the matcher would rank FIRST by a unique old tag
        (the asset's `legacy_asset_code`, normalised as the matcher does)
        or a unique real serial — one active, unlinked SAP record carries
        it. Two Cadra assets pointing at the same SAP record are counted
        apart (`contested_*`): `uncontested` is the number a reconciliation
        could link without a person choosing between two of Cadra's own
        assets."""
        cr = self.env.cr
        self.env.flush_all()
        cr.execute("""
            WITH %s
            SELECT s.asset_class,
                   count(*) FILTER (WHERE s.sap_active),
                   count(*) FILTER (WHERE s.sap_active AND l.sap_id IS NOT NULL),
                   count(*) FILTER (WHERE s.sap_active AND l.sap_id IS NOT NULL
                                    AND l.asset_register_state <> 'registered'),
                   count(*) FILTER (WHERE NOT s.sap_active)
              FROM nrs_sap_asset s LEFT JOIN linked l ON l.sap_id = s.id
             WHERE s.in_latest_export GROUP BY 1 ORDER BY 1 NULLS LAST
        """ % LINKED_CTE)
        sap_class = {r[0]: r[1:] for r in cr.fetchall()}
        cr.execute("""
            WITH %s
            SELECT s.office_code,
                   count(*) FILTER (WHERE s.sap_active),
                   count(*) FILTER (WHERE s.sap_active AND l.sap_id IS NOT NULL)
              FROM nrs_sap_asset s LEFT JOIN linked l ON l.sap_id = s.id
             WHERE s.in_latest_export GROUP BY 1
             ORDER BY 2 DESC, 1 NULLS LAST
        """ % LINKED_CTE)
        sap_office = cr.fetchall()
        cr.execute("""
            SELECT count(*), count(*) FILTER (WHERE in_latest_export),
                   count(*) FILTER (WHERE NOT in_latest_export),
                   count(*) FILTER (WHERE in_latest_export AND sap_active)
              FROM nrs_sap_asset""")
        all_rows, latest, absent, active = cr.fetchone()
        # Cadra's side, per SAP class of the asset's category.
        cr.execute("""
            WITH cadra AS (
                SELECT a.id, nullif(btrim(c.sap_asset_class), '') AS cls,
                       upper(btrim(a.sap_asset_number)) AS num,
                       coalesce(nullif(ltrim(btrim(a.sap_asset_subnumber),
                                             '0'), ''), '0') AS sub,
                       upper(coalesce(btrim(a.sap_company_code), '')) AS cc
                  FROM nrs_asset a
                  LEFT JOIN nrs_asset_category c ON c.id = a.category_id
                 WHERE a.register_state = 'registered')
            SELECT cls, count(*),
                   count(*) FILTER (WHERE coalesce(num, '') <> ''),
                   count(*) FILTER (WHERE coalesce(num, '') <> '' AND NOT EXISTS (
                       SELECT 1 FROM nrs_sap_asset s
                        WHERE s.asset_number_norm = cadra.num
                          AND s.sub_number_norm = cadra.sub
                          AND (cadra.cc = '' OR s.company_code = cadra.cc))),
                   count(*) FILTER (WHERE coalesce(num, '') = '')
              FROM cadra GROUP BY 1 ORDER BY 1 NULLS LAST""")
        cadra_class = {r[0]: r[1:] for r in cr.fetchall()}
        confident = self._confident_links()
        return {
            'sap': {'records': all_rows, 'in_latest_export': latest,
                    'not_in_latest_export': absent, 'active': active},
            'sap_by_class': sap_class,
            'sap_by_office': sap_office,
            'cadra_by_class': cadra_class,
            'confident': confident,
        }

    @api.model
    def _confident_links(self):
        """§6: Cadra assets with no SAP number that the matcher would rank
        first by a unique old tag or a unique real serial. The same rules
        as `SapMatcher._by_tag` / `_by_serial` when `total == 1` and that
        one record is unlinked, written as one query over the register."""
        cr = self.env.cr
        is_ph = serial_placeholders.matcher(serial_placeholders.load(self.env))
        cr.execute("""
            SELECT a.id, a.legacy_asset_code, a.serial_number
              FROM nrs_asset a
             WHERE a.register_state = 'registered'
               AND coalesce(btrim(a.sap_asset_number), '') = ''""")
        assets = cr.fetchall()
        tags = {}
        serials = {}
        for aid, legacy, serial in assets:
            t = norm_tag(legacy)
            if t:
                tags.setdefault(t, []).append(aid)
            s = serial_placeholders.normalise(serial) if serial else ''
            if s and not is_ph(s):
                serials.setdefault(s, []).append(aid)
        unique_tag, unique_serial, found_tags = {}, {}, set()
        if tags:
            cr.execute("""
                WITH %s
                SELECT s.old_tag_norm, min(s.id), count(*),
                       bool_or(l.sap_id IS NOT NULL)
                  FROM nrs_sap_asset s LEFT JOIN linked l ON l.sap_id = s.id
                 WHERE s.sap_active AND s.in_latest_export
                   AND s.old_tag_norm = ANY(%%s)
                 GROUP BY 1""" % LINKED_CTE, [list(tags)])
            groups = cr.fetchall()
            found_tags = {t for t, _sid, _n, _l in groups}
            unique_tag = {t: sid for t, sid, n, linked in groups
                          if n == 1 and not linked}
        if serials:
            cr.execute("""
                WITH %s
                SELECT s.serial_norm, min(s.id), count(*),
                       bool_or(l.sap_id IS NOT NULL)
                  FROM nrs_sap_asset s LEFT JOIN linked l ON l.sap_id = s.id
                 WHERE s.sap_active AND s.in_latest_export
                   AND s.serial_kind = 'real' AND s.serial_norm = ANY(%%s)
                 GROUP BY 1""" % LINKED_CTE, [list(serials)])
            unique_serial = {v: sid for v, sid, n, linked in cr.fetchall()
                             if n == 1 and not linked}
        by_tag, by_serial_only, target = set(), set(), {}
        tagged = 0
        for aid, legacy, serial in assets:
            t = norm_tag(legacy)
            if t:
                tagged += 1
            if t and t in unique_tag:
                by_tag.add(aid)
                target[aid] = unique_tag[t]
                continue
            s = serial_placeholders.normalise(serial) if serial else ''
            # The matcher tries the serial only when no active record
            # carries the tag at all.
            if s in unique_serial and t not in found_tags:
                by_serial_only.add(aid)
                target[aid] = unique_serial[s]
        # A SAP record two Cadra assets would each be linked to is not a
        # confident link for either: one of the two is the wrong asset (or
        # Cadra holds the item twice). Counted apart, never resolved here.
        claims = {}
        for aid, sid in target.items():
            claims.setdefault(sid, []).append(aid)
        contested = {sid for sid, aids in claims.items() if len(aids) > 1}
        contested_assets = sum(len(claims[sid]) for sid in contested)
        return {
            'assets_without_sap_number': len(assets),
            'with_an_old_tag': tagged,
            'by_unique_old_tag': len(by_tag),
            'by_unique_serial': len(by_serial_only),
            'total': len(by_tag) + len(by_serial_only),
            'sap_records': len(claims),
            'contested_sap_records': len(contested),
            'contested_assets': contested_assets,
            'uncontested': len(target) - contested_assets,
        }

    # ── the matcher (handoff 63 §2) ───────────────────────────────────

    @api.model
    def _match(self, old_tag=None, description=None, asset_class=None,
               office=None, serial=None, limit=5):
        """Up to `limit` ACTIVE, UNLINKED SAP records for an item someone
        found, each with the reason it ranked. See `SapMatcher`."""
        return SapMatcher(self.env).match(
            old_tag=old_tag, description=description,
            asset_class=asset_class, office=office, serial=serial,
            limit=limit)


class SapMatcher:
    """The ranking rules, in one place (handoff 63 §2):

    1. an exact old tag (normalised: trimmed, upper-case, `\\` → `/`);
    2. among records sharing that tag, the description;
    3. without a tag, class and description within the office — the office
       given, or the one inside the tag — and nationwide only when the
       office is unknown.

    A serial, when one is given and no record carries the tag, is tried
    before 3: an exact real serial is as good as a unique tag when it is
    unique, and placeholders are never stored as serials, so `XXXX` matches
    nothing.

    Description matching is whole-word and case-insensitive over both
    description columns, scored by how many of the typed words a record
    carries; ties are broken by the shorter description (fewer words the
    item did not mention), then the asset number. No fuzzy matching: 61 §12
    measured that the tag and the description settle three items in four,
    and the rest are a choice for the operator, not a guess for Cadra.

    Records already linked to a Cadra asset are never offered; how many were
    passed over is counted on the answer.
    """

    def __init__(self, env):
        self.env = env
        self.cr = env.cr

    def match(self, old_tag=None, description=None, asset_class=None,
              office=None, serial=None, limit=5):
        self.env.flush_all()
        tag = norm_tag(old_tag)
        words = query_words(description)
        cls = (asset_class or '').strip() or None
        office_in = (office or '').strip().upper() or None
        office_used, office_from = office_in, ('param' if office_in else None)
        if not office_used and office_from_tag(tag):
            office_used, office_from = office_from_tag(tag), 'tag'
        ser = serial_placeholders.normalise(serial) if serial else ''
        notes = []
        answer = None
        if tag:
            answer = self._by_tag(tag, words, limit)
            if answer is None:
                notes.append("No active SAP record carries the old tag %s."
                             % tag)
        if answer is None and ser:
            if serial_placeholders.is_placeholder(self.env, ser):
                notes.append('The serial %s is a placeholder, not a serial; '
                             'it was not matched.' % ser)
            else:
                answer = self._by_serial(ser, words, limit)
                if answer is None:
                    notes.append('No active SAP record carries the serial %s.'
                                 % ser)
        if answer is None and (words or cls):
            answer = self._by_description(words, cls, office_used, limit)
        if answer is None:
            answer = {'basis': None, 'pool': 0, 'tied_at_top': 0,
                      'already_linked': 0, 'results': []}
        answer.update({
            'query': {'old_tag': tag or None, 'description_words': words,
                      'class': cls, 'office': office_in,
                      'serial': ser or None},
            'office_used': office_used if answer.get('basis') == 'description'
            else None,
            'office_from': office_from if answer.get('basis') == 'description'
            else None,
            'notes': notes,
        })
        n = answer['already_linked']
        answer['already_linked_note'] = (
            '%d more already on Cadra\'s register' % n if n else None)
        return answer

    # ── the three tiers ───────────────────────────────────────────────

    def _score_sql(self, words):
        if not words:
            return '0', []
        return (' + '.join(["(s.desc_words LIKE %s)::int"] * len(words)),
                ['%% %s %%' % w for w in words])

    def _ranked(self, where, params, words, limit):
        """The deciding pool, ranked IN SQL — a nationwide "office chair"
        pool is thousands of rows, and only the top `limit` leave the
        database. `(top, free, linked, best, tied, total)`: the best
        unlinked rows as `(id, score)`, how many unlinked and linked records
        the pool holds, the best score, how many unlinked records share it,
        and the pool's size."""
        score, sparams = self._score_sql(words)
        pool = ("WITH pool AS MATERIALIZED ("
                " SELECT s.id, %s AS score, "
                "        coalesce(length(s.desc_words), 0) AS dl, "
                "        s.asset_number_norm AS num, %s AS linked "
                "   FROM nrs_sap_asset s "
                "  WHERE s.sap_active AND s.in_latest_export AND %s) "
                % (score, LINKED_EXISTS, where))
        # ONE statement: the pool is read once, whatever its size.
        self.cr.execute(
            pool + ", agg AS (SELECT count(*) AS total, "
                   "  count(*) FILTER (WHERE linked) AS linked, "
                   "  max(score) FILTER (WHERE NOT linked) AS best FROM pool) "
                   "SELECT agg.total, agg.linked, agg.best, "
                   "  (SELECT count(*) FROM pool "
                   "    WHERE NOT linked AND score = agg.best), "
                   "  ARRAY(SELECT ARRAY[id, score] FROM pool WHERE NOT linked "
                   "        ORDER BY score DESC, dl, num LIMIT %s) "
                   "FROM agg", sparams + params + [limit])
        total, linked, best, tied, top = self.cr.fetchone()
        free = total - linked
        if not free:
            return [], 0, linked, 0, 0, total
        return [tuple(t) for t in top], free, linked, best, tied, total

    def _by_tag(self, tag, words, limit):
        top, free, linked, best, tied, total = self._ranked(
            "s.old_tag_norm = %s", [tag], words, limit)
        if not total:
            return None
        results = []
        for rank, row in enumerate(top, 1):
            if total == 1:
                code, reason = 'old_tag_unique', 'old tag, unique'
            else:
                code, reason = self._shared_reason(
                    'old_tag', 'old tag, shared by %d' % total, row[1], words)
            results.append(self._result(row[0], rank, code, reason))
        return {'basis': 'old_tag', 'pool': free, 'tied_at_top': tied,
                'already_linked': linked, 'shared_by': total,
                'results': results}

    def _by_serial(self, ser, words, limit):
        top, free, linked, best, tied, total = self._ranked(
            "s.serial_norm = %s AND s.serial_kind = 'real'", [ser], words,
            limit)
        if not total:
            return None
        results = []
        for rank, row in enumerate(top, 1):
            if total == 1:
                code, reason = 'serial_unique', 'serial, unique'
            else:
                code, reason = self._shared_reason(
                    'serial', 'serial, shared by %d' % total, row[1], words)
            results.append(self._result(row[0], rank, code, reason))
        return {'basis': 'serial', 'pool': free, 'tied_at_top': tied,
                'already_linked': linked, 'shared_by': total,
                'results': results}

    def _by_description(self, words, cls, office, limit):
        clauses, params = [], []
        if cls:
            clauses.append('s.asset_class = %s')
            params.append(cls)
        if office:
            clauses.append('s.office_code = %s')
            params.append(office)
        if words:
            score, sparams = self._score_sql(words)
            clauses.append('(%s) > 0' % score)
            params += sparams
        top, free, linked, best, tied, total = self._ranked(
            ' AND '.join(clauses) or 'TRUE', params, words, limit)
        parts = []
        if words:
            parts.append('description')
        if cls:
            parts.append('class')
        what = ' and '.join(parts)
        where = 'office %s' % office if office else 'office unknown'
        results = []
        for rank, row in enumerate(top, 1):
            reason = '%s; %s' % (what, where)
            if words and row[1] < len(words):
                reason += ' (matches %d of %d words)' % (row[1], len(words))
            code = 'description_office' if office else 'description_nationwide'
            results.append(self._result(row[0], rank, code, reason))
        return {'basis': 'description', 'pool': free, 'tied_at_top': tied,
                'already_linked': linked, 'results': results}

    @staticmethod
    def _shared_reason(prefix, head, score, words):
        if not words:
            return '%s_shared' % prefix, head + '; no description given'
        if score == len(words):
            return ('%s_shared_description' % prefix,
                    head + '; description matches')
        if score:
            return ('%s_shared_description' % prefix,
                    head + '; description matches %d of %d words'
                    % (score, len(words)))
        return '%s_shared' % prefix, head + '; description does not match'

    @staticmethod
    def _result(sap_id, rank, code, reason):
        return {'id': sap_id, 'rank': rank, 'reason_code': code,
                'reason': reason}


class NRSSapImportRun(models.Model):
    _name = 'nrs.sap.import.run'
    _description = "Import of SAP's asset-master export"
    _order = 'id desc'

    state = fields.Selection(RUN_STATES, required=True, default='queued',
                             readonly=True, index=True)
    file_name = fields.Char(readonly=True)
    file_size = fields.Integer('File Size (bytes)', readonly=True)
    sheet_size = fields.Integer('Sheet Size (bytes, uncompressed)',
                                readonly=True)
    file_data = fields.Binary(
        'Upload', attachment=True, readonly=True,
        help='The uploaded export, kept only while the run reads it. Deleted '
             'when the run ends, done or failed.')
    uploaded_by = fields.Many2one('res.users', readonly=True,
                                  ondelete='restrict')
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    duration_seconds = fields.Float(
        readonly=True, digits=(12, 1),
        help='From the first tick to the end, waits between ticks included.')
    cpu_seconds = fields.Float(readonly=True, digits=(12, 1))
    ticks = fields.Integer(readonly=True)
    peak_rss_mb = fields.Float(
        'Peak Memory (MB)', readonly=True, digits=(12, 0),
        help='The highest resident size of a worker process while it ran '
             'this import (`ru_maxrss`).')
    rows_read = fields.Integer(readonly=True)
    created_count = fields.Integer('Created', readonly=True)
    updated_count = fields.Integer('Updated', readonly=True)
    unchanged_count = fields.Integer('Unchanged', readonly=True)
    refused_count = fields.Integer('Refused', readonly=True)
    refused_reasons = fields.Text(readonly=True,
                                  help='JSON: reason → rows. Never the rows.')
    marked_absent_count = fields.Integer(
        'Marked Not in Latest Export', readonly=True)
    message = fields.Text(readonly=True)
    header_map = fields.Text(readonly=True)
    sheet_prefix = fields.Text(readonly=True)
    resume_offset = fields.Integer(readonly=True)

    # ── the job ───────────────────────────────────────────────────────

    def _commit(self):
        """Commit a tick's progress — except under the test runner, whose
        cursor is one transaction for the whole test. (Odoo 19 has no
        `registry.in_test_mode()`; a running test is
        `odoo.modules.module.current_test`.)"""
        if not _under_test():
            self.env.cr.commit()

    @api.model
    def _cron_process_imports(self):
        """One tick of the oldest run still to do."""
        run = self.sudo().search([('state', 'in', ('queued', 'running'))],
                                 order='id', limit=1)
        if run:
            more = run._tick()
            if more and not _under_test():
                self.env.ref('myservice_asset_register.cron_sap_mirror_import'
                             )._trigger()

    def _run_to_end(self, cpu_budget=None):
        """Every tick, back to back — for a shell and for tests."""
        self.ensure_one()
        while self._tick(cpu_budget=cpu_budget):
            pass
        return self

    def _attachment(self):
        return self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name), ('res_field', '=', 'file_data'),
            ('res_id', '=', self.id)], limit=1)

    def _open_upload(self):
        att = self._attachment()
        if not att:
            raise reader.ExportRefused(
                'The uploaded file is no longer stored, so this run cannot '
                'continue. Upload the export again.')
        if att.store_fname:
            return open(att._full_path(att.store_fname), 'rb')
        return io.BytesIO(att.raw or b'')

    def _tick(self, cpu_budget=None):
        """Read for up to `cpu_budget` CPU seconds, write what was read,
        commit. True when the run has more to do."""
        self.ensure_one()
        budget = TICK_CPU_SECONDS if cpu_budget is None else cpu_budget
        cpu0, wall0 = time.process_time(), time.monotonic()
        if self.state not in ('queued', 'running'):
            return False
        if self.state == 'queued':
            self.write({'state': 'running',
                        'started_at': fields.Datetime.now()})
            self._commit()
        fh = None
        try:
            fh = self._open_upload()
            export = reader.Export(fh)
            if not self.header_map:
                header, prefix, start = export.header()
                colmap = reader.header_map(header)
                self.write({'header_map': json.dumps(colmap),
                            'sheet_prefix': prefix.decode('utf-8'),
                            'resume_offset': start})
            colmap = json.loads(self.header_map)
            prefix = self.sheet_prefix.encode('utf-8')
            strings = export.shared_strings()
            writer = _Writer(self, strings, export.date1904)
            pending, offset, more = [], self.resume_offset, False
            for rows, next_offset, last in export.iter_batches(
                    colmap, strings, self.resume_offset, prefix):
                pending += rows
                offset = next_offset
                if last:
                    # The end of the sheet: finish here, whatever the
                    # budget says — a tick that stopped now would resume AT
                    # the end, read nothing, and stop again, for ever.
                    break
                over = (time.process_time() - cpu0 > budget
                        or time.monotonic() - wall0 > TICK_WALL_SECONDS)
                if len(pending) >= FLUSH_ROWS or over:
                    writer.flush(pending, offset)
                    pending = []
                if over:
                    more = True
                    break
            if not more:
                writer.flush(pending, offset)
                writer.finish()
        except reader.ExportRefused as e:
            self._fail(str(e))
            more = False
        except Exception as e:
            # catch-all: reported — a tick reads a file an operator uploaded
            # through zipfile, lxml and the database; whatever escapes is
            # logged with its traceback and the run is marked failed with
            # the type and text, so the screen stops saying "running".
            _logger.exception('SAP mirror import %s failed', self.id)
            self.env.cr.rollback()
            self._fail('%s: %s' % (type(e).__name__, e))
            more = False
        finally:
            if fh is not None:
                fh.close()
        self._account(cpu0, wall0)
        self._commit()
        return more

    def _account(self, cpu0, wall0):
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
        vals = {'cpu_seconds': (self.cpu_seconds or 0)
                + time.process_time() - cpu0,
                'ticks': (self.ticks or 0) + 1,
                'peak_rss_mb': max(self.peak_rss_mb or 0, rss)}
        if self.state in ('done', 'failed') and self.started_at:
            vals['duration_seconds'] = (
                fields.Datetime.now() - self.started_at).total_seconds()
        self.write(vals)

    def _fail(self, message):
        self.write({'state': 'failed', 'message': message,
                    'finished_at': fields.Datetime.now()})
        self._drop_upload()

    def _drop_upload(self):
        """The export is NRS's register and is not kept (§1)."""
        att = self._attachment()
        if att:
            att.unlink()

    # ── published shape ───────────────────────────────────────────────

    def _reasons(self):
        try:
            return json.loads(self.refused_reasons or '{}')
        except ValueError:
            return {'(the stored list of reasons could not be read)':
                    self.refused_count}


class _Writer:
    """Writes one run's rows: normalise, hash, upsert in batches."""

    #: Stored columns in the order every INSERT and UPDATE writes them.
    COLS = ('sap_key', 'company_code', 'asset_number', 'asset_number_norm',
            'sub_number', 'sub_number_norm', 'asset_class', 'description',
            'description_2', 'desc_words', 'old_tag', 'old_tag_norm',
            'office_code', 'office_source', 'serial_number', 'serial_norm',
            'serial_kind', 'serial_placeholder', 'capitalized_on',
            'first_acquired_on', 'sap_created_on', 'deactivated_on',
            'sap_active', 'vendor', 'row_hash')
    _CASTS = {'capitalized_on': '::date', 'first_acquired_on': '::date',
              'sap_created_on': '::date', 'deactivated_on': '::date',
              'sap_active': '::boolean'}

    def __init__(self, run, strings, date1904):
        self.run = run
        self.env = run.env
        self.cr = run.env.cr
        self.strings = strings
        self.date1904 = date1904
        self.is_placeholder = serial_placeholders.matcher(
            serial_placeholders.load(run.env))
        self.titles = {f: t for f, t, _r in reader.COLUMNS}
        self.uid = run.uploaded_by.id or run.env.uid
        self.fixture = bool(getattr(run, 'is_test_fixture', False))

    def _row(self, raw):
        def text(field):
            return reader.text_value(raw.get(field), self.strings)

        def date(field):
            return reader.date_value(raw.get(field), self.strings,
                                     self.date1904, self.titles[field])

        number = text('asset_number')
        if not number:
            raise reader.RowRefused('no asset number')
        sub = text('sub_number')
        tag = text('old_tag')
        tag_norm = norm_tag(tag)
        office = office_from_tag(tag_norm)
        serial = text('serial')
        if not serial:
            kind, real, ph = 'none', None, None
        elif self.is_placeholder(serial):
            kind, real, ph = 'placeholder', None, serial
        else:
            kind, real, ph = 'real', serial, None
        d1, d2 = text('description'), text('description_2')
        vals = {
            'sap_key': '%s|%s' % (norm_number(number), norm_sub(sub)),
            'company_code': norm_number(text('company_code')) or None,
            'asset_number': number,
            'asset_number_norm': norm_number(number),
            'sub_number': sub or None,
            'sub_number_norm': norm_sub(sub),
            'asset_class': text('asset_class') or None,
            'description': d1 or None,
            'description_2': d2 or None,
            'desc_words': desc_words(d1, d2) or None,
            'old_tag': tag or None,
            'old_tag_norm': tag_norm or None,
            'office_code': office,
            'office_source': 'tag' if office else 'none',
            'serial_number': real,
            'serial_norm': serial_placeholders.normalise(real) if real else None,
            'serial_kind': kind,
            'serial_placeholder': ph,
            'capitalized_on': date('capitalized_on'),
            'first_acquired_on': date('first_acquired_on'),
            'sap_created_on': date('sap_created_on'),
            'deactivated_on': date('deactivated_on'),
            'vendor': text('vendor') or None,
        }
        vals['sap_active'] = vals['deactivated_on'] is None
        vals['row_hash'] = hashlib.sha1(json.dumps(
            [vals[c] for c in self.COLS[:-1] if c not in (
                'office_code', 'office_source')],
            default=str).encode('utf-8')).hexdigest()
        return vals

    def flush(self, rows, offset):
        """Write `rows` and record that the run has read up to `offset`."""
        run = self.run
        refused = run._reasons()
        good = {}
        dup = 'the same asset number and sub-number twice in this file'
        for _num, raw in rows:
            try:
                vals = self._row(raw)
            except reader.RowRefused as e:
                refused[e.reason] = refused.get(e.reason, 0) + 1
                continue
            if vals['sap_key'] in good:
                refused[dup] = refused.get(dup, 0) + 1
                continue
            good[vals['sap_key']] = vals
        created = updated = unchanged = 0
        if good:
            self.cr.execute(
                "SELECT sap_key, id, row_hash, in_latest_export, "
                "       last_import_id, office_source, office_code "
                "FROM nrs_sap_asset WHERE sap_key = ANY(%s)", [list(good)])
            existing = {r[0]: r[1:] for r in self.cr.fetchall()}
            inserts, updates, same = [], [], []
            for key, vals in good.items():
                row = existing.get(key)
                if row is None:
                    inserts.append(vals)
                    continue
                sid, old_hash, latest, last_run, src, office = row
                if last_run == run.id:
                    refused[dup] = refused.get(dup, 0) + 1
                    continue
                if src == 'location_extract':
                    # SAP's location extract filled this office; an asset
                    # export, which carries none, never overwrites it.
                    vals = dict(vals, office_code=office,
                                office_source='location_extract')
                if old_hash == vals['row_hash'] and latest:
                    same.append(sid)
                else:
                    updates.append((sid, vals))
            created, updated, unchanged = self._store(inserts, updates, same)
        refused_n = sum(refused.values())
        run.write({
            'rows_read': run.rows_read + len(rows),
            'created_count': run.created_count + created,
            'updated_count': run.updated_count + updated,
            'unchanged_count': run.unchanged_count + unchanged,
            'refused_count': refused_n,
            'refused_reasons': json.dumps(refused, sort_keys=True),
            'resume_offset': offset,
        })
        run._commit()

    def _store(self, inserts, updates, same):
        run_id = self.run.id
        now = fields.Datetime.now()
        if inserts:
            cols = self.COLS + ('in_latest_export', 'first_import_id',
                                'last_import_id', 'create_uid', 'write_uid',
                                'create_date', 'write_date')
            extra = (True, run_id, run_id, self.uid, self.uid, now, now)
            # The test-fixture label (`cadra.test.fixture.mixin`, added by
            # `myservice_api`): a record imported under a test credential
            # says so, as the run does. Stamped here because these rows do
            # not go through the mixin's `create`.
            if 'is_test_fixture' in self.env['nrs.sap.asset']._fields:
                cols += ('is_test_fixture',)
                extra += (self.fixture,)
            template = '(%s)' % ', '.join(
                '%%s%s' % self._CASTS.get(c, '') for c in cols)
            execute_values(
                self.cr,
                'INSERT INTO nrs_sap_asset (%s) VALUES %%s' % ', '.join(cols),
                [tuple(v[c] for c in self.COLS) + extra for v in inserts],
                template=template, page_size=1000)
        if updates:
            cols = ('id',) + self.COLS
            template = '(%s)' % ', '.join(
                '%%s%s' % self._CASTS.get(c, '') for c in cols)
            sets = ', '.join('%s = v.%s' % (c, c) for c in self.COLS)
            # `execute_values` allows ONE placeholder (the VALUES), so the
            # run, the writer and the instant are literals.
            execute_values(
                self.cr,
                "UPDATE nrs_sap_asset s SET %s, in_latest_export = TRUE, "
                "last_import_id = %d, write_uid = %d, "
                "write_date = (now() AT TIME ZONE 'UTC') "
                "FROM (VALUES %%s) AS v (%s) WHERE s.id = v.id"
                % (sets, run_id, self.uid, ', '.join(cols)),
                [(sid,) + tuple(v[c] for c in self.COLS)
                 for sid, v in updates],
                template=template, page_size=1000)
        if same:
            # Unchanged: only which import last saw it. `write_date` does
            # NOT move, so a sync is handed only what changed.
            self.cr.execute(
                "UPDATE nrs_sap_asset SET last_import_id = %s "
                "WHERE id = ANY(%s)", [run_id, same])
        self.env['nrs.sap.asset'].invalidate_model()
        return len(inserts), len(updates), len(same)

    def finish(self):
        """Mark what this export did not carry, drop the upload, close."""
        run = self.run
        self.cr.execute(
            "UPDATE nrs_sap_asset SET in_latest_export = FALSE, "
            "       write_date = %s, write_uid = %s "
            " WHERE in_latest_export "
            "   AND last_import_id IS DISTINCT FROM %s",
            [fields.Datetime.now(), self.uid, run.id])
        absent = self.cr.rowcount
        self.env['nrs.sap.asset'].invalidate_model()
        # Up to 211,699 rows just arrived; the planner's statistics are
        # what keep the matcher on its indexes.
        self.cr.execute("ANALYZE nrs_sap_asset")
        run.write({'state': 'done', 'finished_at': fields.Datetime.now(),
                   'marked_absent_count': absent})
        run._drop_upload()
        _logger.info(
            'SAP mirror import %s on %s: %d rows read, %d created, %d updated, '
            '%d unchanged, %d refused, %d marked not in the latest export',
            run.id, self.cr.dbname, run.rows_read, run.created_count,
            run.updated_count, run.unchanged_count, run.refused_count, absent)
