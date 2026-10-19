# -*- coding: utf-8 -*-
"""Reading SAP's asset-master export (`.XLSX`) without loading it — handoff 63 §1.

The October 2026 export (`docs/reference/sap-asset-master-2026-10.md`) is a
75 MB zip whose one worksheet is **655 MB of XML**: 211,699 rows of 93
columns. Loaded whole (openpyxl, or `etree.parse`) it is several gigabytes
of Python objects; the cluster's worker is killed at 1.5 GB. So this module
STREAMS it:

* the worksheet is decompressed a megabyte at a time and fed to lxml's
  pull parser, and every row is cleared as soon as it has been read — the
  parser holds one row at a time (measured: 39 MB peak over the whole file);
* text cells point into `xl/sharedStrings.xml` (380,748 strings, 10.8 MB),
  which IS read whole, because a cell can name any of them;
* columns are found **by header name**, never by position — SAP's own
  export orders them by the layout the user picked, and a missing column
  refuses the file in words, naming it (`ExportRefused`).

**Resumable at a row boundary.** A full pass costs ~70 s of CPU, and an Odoo
cron worker is killed after `limit_time_cpu` (60 s locally by default,
600 s on the cluster) — so the import runs as several short ticks. Each
batch this reader yields carries the decompressed byte offset at which the
NEXT row begins; a later tick skips that many bytes (decompression alone is
0.8 s for the whole sheet) and feeds the parser the sheet's own opening
(`<worksheet …><sheetData>`, captured on the first pass) before carrying on,
so the parser sees a well-formed document whose first rows are the ones not
yet read. `tests/test_sap_mirror.py` proves a resumed read yields exactly
the rows a single pass does.

Nothing here touches the database or imports Odoo, so it is exercised on its
own and the import job (`sap_mirror.py`) holds no parsing logic.
"""
import datetime
import re
import zipfile
from decimal import Decimal, InvalidOperation

from lxml import etree

MAIN_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG_REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
_ROW = '{%s}row' % MAIN_NS
_C = '{%s}c' % MAIN_NS
_V = '{%s}v' % MAIN_NS
_IS = '{%s}is' % MAIN_NS
_T = '{%s}t' % MAIN_NS
_SI = '{%s}si' % MAIN_NS
_RPH = '{%s}rPh' % MAIN_NS

#: How much decompressed XML is fed to the parser at once. A row of the
#: October export is ~3 KB, so a feed is ~300 rows — the granularity of a
#: checkpoint.
FEED_BYTES = 1 << 20

#: `(field, header, required)`. The header is SAP's column title as its
#: export writes it, compared case-insensitively with runs of whitespace
#: collapsed. `Asset description` appears TWICE in SAP's layout (the
#: description and its second line); the first is `description`, the second
#: `description_2`.
#:
#: Required: what the mirror cannot do its job without — the key, the class,
#: the description, the old tag, the serial, and the two dates that say when
#: it was capitalised and whether it is still active. Optional: what an
#: export with a narrower layout may leave out, stored empty when absent.
COLUMNS = (
    ('company_code', 'Company Code', True),
    ('asset_number', 'Asset', True),
    ('sub_number', 'Sub-number', True),
    ('asset_class', 'Asset Class', True),
    ('description', 'Asset description', True),
    ('description_2', 'Asset description', False),
    ('old_tag', 'Inventory number', True),
    ('serial', 'Serial number', True),
    ('capitalized_on', 'Capitalized on', True),
    ('first_acquired_on', 'First acquisition on', False),
    ('sap_created_on', 'Created On', False),
    ('deactivated_on', 'Deactivation on', True),
    ('vendor', 'Vendor', False),
)
DATE_FIELDS = ('capitalized_on', 'first_acquired_on', 'sap_created_on',
               'deactivated_on')

_SPACES = re.compile(r'\s+')
_ROW_START = re.compile(rb'<(?:[A-Za-z_][\w.-]*:)?row[\s>/]')
_ROW_END = re.compile(rb'</(?:[A-Za-z_][\w.-]*:)?row\s*>')
_LETTERS = re.compile(r'^([A-Z]+)')


class ExportRefused(ValueError):
    """The FILE cannot be imported — said in words, with `details`."""

    def __init__(self, message, **details):
        super().__init__(message)
        self.details = details


class RowRefused(ValueError):
    """One ROW cannot be imported. `reason` is a short sentence; the run
    counts rows per reason, and never stores the row's values."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def header_key(text):
    """The form a header is compared in."""
    return _SPACES.sub(' ', (text or '').strip()).lower()


def column_letter(index):
    """1 → 'A', 27 → 'AA'."""
    out = ''
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


class Export:
    """One uploaded export: the zip, its first worksheet, its date system."""

    def __init__(self, fileobj):
        try:
            self.zip = zipfile.ZipFile(fileobj)
        except (zipfile.BadZipFile, OSError, ValueError):
            raise ExportRefused(
                'This file is not an .XLSX workbook (it is not a zip '
                'archive). Upload the export as SAP produced it.')
        names = set(self.zip.namelist())
        if 'xl/workbook.xml' not in names:
            raise ExportRefused(
                'This zip has no xl/workbook.xml, so it is not an Excel '
                'workbook. Upload the .XLSX as SAP produced it.')
        self.sheet_path, self.date1904 = self._first_sheet(names)
        self.has_shared_strings = 'xl/sharedStrings.xml' in names

    def _first_sheet(self, names):
        wb = etree.fromstring(self.zip.read('xl/workbook.xml'))
        pr = wb.find('{%s}workbookPr' % MAIN_NS)
        date1904 = pr is not None and pr.get('date1904') in ('1', 'true')
        sheet = wb.find('{%s}sheets/{%s}sheet' % (MAIN_NS, MAIN_NS))
        target = None
        if sheet is not None and 'xl/_rels/workbook.xml.rels' in names:
            rid = sheet.get('{%s}id' % REL_NS)
            rels = etree.fromstring(self.zip.read('xl/_rels/workbook.xml.rels'))
            for rel in rels.iter('{%s}Relationship' % PKG_REL_NS):
                if rel.get('Id') == rid:
                    target = rel.get('Target')
        if target:
            target = target.lstrip('/')
            path = target if target.startswith('xl/') else 'xl/' + target
        else:
            path = 'xl/worksheets/sheet1.xml'
        if path not in names:
            raise ExportRefused(
                'The workbook names its first sheet as %s, which is not in '
                'the file. Upload the .XLSX as SAP produced it.' % path)
        return path, date1904

    # ── shared strings ────────────────────────────────────────────────

    def shared_strings(self, upto=None):
        """The shared-string table as a list, streamed. `upto` stops once
        index `upto` is read (the header row needs only its own)."""
        out = []
        if not self.has_shared_strings:
            return out
        with self.zip.open('xl/sharedStrings.xml') as f:
            for _ev, si in etree.iterparse(f, events=('end',), tag=_SI):
                # Phonetic runs (`rPh`) are a reading aid, not the text.
                out.append(''.join(
                    t.text or '' for t in si.iter(_T)
                    if t.getparent() is None or t.getparent().tag != _RPH))
                si.clear()
                if upto is not None and len(out) > upto:
                    break
        return out

    # ── the sheet ─────────────────────────────────────────────────────

    def _opening(self):
        """`(prefix, offset)`: the sheet's bytes before its first row, and
        that row's offset. The prefix is what a resumed parse is fed first."""
        buf = b''
        with self.zip.open(self.sheet_path) as f:
            while True:
                chunk = f.read(65536)
                buf += chunk
                m = _ROW_START.search(buf)
                if m:
                    return buf[:m.start()], m.start()
                if not chunk:
                    raise ExportRefused('The first sheet has no rows.')
                if len(buf) > 16 << 20:
                    raise ExportRefused(
                        'The first sheet has no row in its first 16 MB.')

    def header(self):
        """`{letter: header text}` of the first row, the sheet's opening,
        and the offset of the second row. Reads only as far as it needs."""
        prefix, start = self._opening()
        parser = etree.XMLPullParser(events=('end',), tag=_ROW)
        parser.feed(prefix)
        with self.zip.open(self.sheet_path) as f:
            _skip(f, start)
            buf, fed = b'', start
            while True:
                chunk = f.read(65536)
                buf += chunk
                m = _ROW_END.search(buf)
                if m:
                    parser.feed(buf[:m.end()])
                    fed += m.end()
                    break
                if not chunk:
                    raise ExportRefused('The first sheet has no header row.')
        row = next(el for _ev, el in parser.read_events())
        cells = list(_raw_cells(row))
        needed = [int(v) for _l, t, v in cells if t == 's' and v is not None]
        strings = self.shared_strings(upto=max(needed) if needed else None)
        header = {}
        for letter, t, v in cells:
            text = _cell_text(t, v, strings)
            if text is not None and text.strip():
                header[letter] = text.strip()
        return header, prefix, fed

    def iter_batches(self, colmap, strings, start, prefix):
        """Yield `(rows, next_offset, last)` from `start` to the end of the
        sheet.

        `rows` is a list of `(excel_row_number, {field: raw value})`;
        `next_offset` is where the row after the batch begins, the value a
        later tick resumes from; `last` is True on the final batch — the one
        that read to the end of the sheet, whose `next_offset` there is
        nothing after. `colmap` is `header_map`'s answer."""
        wanted = {letter: field for field, letter in colmap.items()}
        parser = etree.XMLPullParser(events=('end',), tag=_ROW)
        parser.feed(prefix)
        with self.zip.open(self.sheet_path) as f:
            _skip(f, start)
            buf, offset = b'', start
            while True:
                chunk = f.read(FEED_BYTES)
                buf += chunk
                if chunk:
                    end = _last_row_end(buf)
                    if end is None:
                        continue
                    piece, buf = buf[:end], buf[end:]
                else:
                    piece, buf = buf, b''
                parser.feed(piece)
                offset += len(piece)
                rows = []
                for _ev, el in parser.read_events():
                    rows.append(_read_row(el, wanted))
                    # One row at a time: clear it and drop the siblings the
                    # tree kept, or the parsed sheet grows to gigabytes.
                    el.clear()
                    parent = el.getparent()
                    while parent is not None and el.getprevious() is not None:
                        del parent[0]
                if rows or not chunk:
                    yield rows, offset, not chunk
                if not chunk:
                    return


def header_map(header):
    """`{field: letter}` from `Export.header()`'s map, or `ExportRefused`
    naming every required column that is missing."""
    by_key = {}
    for letter in sorted(header, key=lambda l: (len(l), l)):
        by_key.setdefault(header_key(header[letter]), []).append(letter)
    colmap, missing, used = {}, [], {}
    for field, title, required in COLUMNS:
        key = header_key(title)
        letters = by_key.get(key, [])
        nth = used.get(key, 0)
        if nth < len(letters):
            colmap[field] = letters[nth]
            used[key] = nth + 1
        elif required:
            missing.append(title)
    if missing:
        raise ExportRefused(
            'The file has no %s column%s, so it cannot be imported. Columns '
            'are found by their header in the first row; export SAP\'s asset '
            'master with %s included. Nothing was imported.' % (
                ', '.join('"%s"' % m for m in missing),
                '' if len(missing) == 1 else 's',
                'it' if len(missing) == 1 else 'them'),
            missing=missing,
            required=[t for _f, t, r in COLUMNS if r])
    return colmap


# ── row values ────────────────────────────────────────────────────────

def _skip(f, n):
    while n > 0:
        got = f.read(min(n, FEED_BYTES))
        if not got:
            raise ExportRefused(
                'The sheet is shorter than the point this import had reached; '
                'the stored upload is not the file this run started with.')
        n -= len(got)


def _last_row_end(buf):
    """End of the last complete `</row>` in `buf`, or None."""
    window = 4096
    while True:
        lo = max(0, len(buf) - window)
        last = None
        for m in _ROW_END.finditer(buf, lo):
            last = m
        if last is not None:
            return last.end()
        if lo == 0:
            return None
        window *= 4


def _raw_cells(row):
    """`(letter, type, value)` per cell; `r` absent means positional."""
    pos = 0
    for c in row:
        if c.tag != _C:
            continue
        pos += 1
        ref = c.get('r')
        if ref:
            m = _LETTERS.match(ref)
            letter = m.group(1) if m else column_letter(pos)
            if m:
                pos = _letter_index(letter)
        else:
            letter = column_letter(pos)
        t = c.get('t')
        if t == 'inlineStr':
            node = c.find(_IS)
            value = (''.join(x.text or '' for x in node.iter(_T))
                     if node is not None else None)
        else:
            v = c.find(_V)
            value = v.text if v is not None else None
        yield letter, t, value


def _letter_index(letter):
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch) - 64)
    return n


def _cell_text(t, value, strings):
    if value is None:
        return None
    if t == 's':
        try:
            return strings[int(value)]
        except (ValueError, IndexError):
            raise RowRefused('a text cell points outside the shared strings')
    return value


def _read_row(row, wanted):
    """`(excel row number, {field: (type, raw value)})` for the WANTED
    columns only. The other eighty-odd cells of a row are skipped on their
    reference alone — decoding all 93 cost 100 s of CPU over the October
    file, a third more than reading only these."""
    try:
        number = int(row.get('r') or 0)
    except ValueError:
        number = 0
    values = {}
    pos = 0
    for c in row:
        if c.tag != _C:
            continue
        pos += 1
        ref = c.get('r')
        if ref:
            letter = ref.rstrip('0123456789')
            pos = _letter_index(letter) if letter else pos
        else:
            letter = column_letter(pos)
        field = wanted.get(letter)
        if field is None:
            continue
        t = c.get('t')
        if t == 'inlineStr':
            node = c.find(_IS)
            value = (''.join(x.text or '' for x in node.iter(_T))
                     if node is not None else None)
        else:
            v = c.find(_V)
            value = v.text if v is not None else None
        if value is not None:
            values[field] = (t, value)
    return number, values


def text_value(cell, strings):
    """A cell as text: shared and inline strings verbatim, a number as the
    digits SAP stored (an 11-digit asset number held as a NUMBER is still
    `29999999990`, never `2.999999999E10`)."""
    if cell is None:
        return ''
    t, value = cell
    if t in ('s', 'inlineStr', 'str'):
        text = _cell_text('s' if t == 's' else None, value, strings)
        return (text or '').strip()
    if t in ('b', 'e'):
        return (value or '').strip()
    raw = (value or '').strip()
    try:
        d = Decimal(raw)
    except InvalidOperation:
        return raw
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), 'f')


_DATE_FORMATS = ('%Y-%m-%d', '%d.%m.%Y', '%Y%m%d')
_EMPTY_DATES = ('00.00.0000', '0000-00-00', '00000000', '0')


def date_value(cell, strings, date1904, column):
    """A cell as a date, or None when empty. An Excel serial (how SAP's
    export writes its dates) or text in ISO, `dd.mm.yyyy` or `yyyymmdd`;
    anything else refuses the ROW, naming the column."""
    if cell is None:
        return None
    t, value = cell
    if t in ('s', 'inlineStr', 'str'):
        text = (_cell_text('s' if t == 's' else None, value, strings) or '').strip()
        if not text or text in _EMPTY_DATES:
            return None
        for fmt in _DATE_FORMATS:
            try:
                return datetime.datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise RowRefused('an unreadable date in "%s"' % column)
    raw = (value or '').strip()
    if not raw:
        return None
    try:
        serial = float(raw)
    except ValueError:
        raise RowRefused('an unreadable date in "%s"' % column)
    if serial <= 0:
        return None
    base = datetime.date(1904, 1, 1) if date1904 else datetime.date(1899, 12, 30)
    try:
        return base + datetime.timedelta(days=int(serial))
    except OverflowError:
        raise RowRefused('an unreadable date in "%s"' % column)
