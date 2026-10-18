"""Invented SAP asset-master exports, in the October export's SHAPES (handoff 63).

No row of NRS's export enters this repository (handoff 59's rule, 63 §4).
What the tests need is a file that looks like SAP's to the reader: a zip
with `xl/workbook.xml`, a first sheet whose header row names SAP's columns
(93 of them, `Asset description` twice), text in `xl/sharedStrings.xml`
and dates as Excel serial numbers — every value below invented.

Standard library only, so the same file serves the in-registry tests (imported
as a module) and the HTTP suite (`tests/test_sap_mirror.py` loads it by
path; its virtualenv has no openpyxl).
"""
import datetime
import io
import zipfile
from xml.sax.saxutils import escape

#: The October export's header row, in its order (column titles only).
SAP_HEADERS = (
    'Company Code', 'Asset', 'Sub-number', 'Language Key',
    'Asset description', 'Asset Class', 'Created By', 'Created On',
    'Changed by', 'Changed on', 'Mark for Deletion', 'Locked to acquis.',
    'Screen layout rule', 'Acct determination', 'Line item settlement',
    'Asset category', 'Acquisition year', 'First acquis.period',
    'First acquisition on', 'Capitalized on', 'Last retirement',
    'Deactivation on', 'Sort key', 'Manage historically', 'Compl.ind.',
    'Vendor', 'Original value', 'In-house prod.perc.', 'not in use',
    'Investment Order', 'Base Unit of Measure', 'Quantity', 'Type name',
    'Investment reason', 'Inventory Ind.', 'Man.net wrth val.',
    'Assessed val', 'Area', 'Inventory number', 'Lease length',
    'Lease in periods', 'Payment cycle', 'Lease payment',
    'Base value as new', 'Leas.purch.price', 'Monthly int. rate',
    'Annual interest rate', 'Last posting date', 'Posted payments',
    'Interest posted', 'Long-term liability', 'No. lease payments',
    'Agreement number', 'Supplementary text', 'Capitalize fixed asset',
    'Change type', 'Last document number', 'Maintain date View0',
    'View0 changed by', 'Maintain date V1', 'V1 changed by',
    'Maintain date V2', 'View2 changed by', 'Maintain date V3',
    'View3 changed by', 'Maintain date View4', 'View4 changed by',
    'Maintain date V5', 'View5 changed by', 'Maintain date V6',
    'View6 changed by', 'Connection to SAP real estate managment',
    'Object number', 'L.Typ', 'Advance payments', 'Evaluation Group 5',
    'WBS element', 'Do not take memo value into account', 'Purchased used',
    'Group asset', 'Asset description', 'Investment Measure',
    'Serial number', 'Envir. investment', 'Last reval. on',
    'Change asset master record from equipmen',
    'Time-Dependent Parameters Exist', 'Reorganization Date',
    'Internal code', 'Approval document number', 'Approval version',
    'investment program asset number', 'Asset version',
)

#: Row keys → the header they fill (the second `Asset description` is
#: `description_2`).
_FIELD_HEADER = {
    'company_code': 'Company Code', 'asset_number': 'Asset',
    'sub_number': 'Sub-number', 'description': 'Asset description',
    'asset_class': 'Asset Class', 'sap_created_on': 'Created On',
    'first_acquired_on': 'First acquisition on',
    'capitalized_on': 'Capitalized on', 'deactivated_on': 'Deactivation on',
    'vendor': 'Vendor', 'old_tag': 'Inventory number',
    'serial': 'Serial number',
}
_DATE_KEYS = ('sap_created_on', 'first_acquired_on', 'capitalized_on',
              'deactivated_on')
_EPOCH = datetime.date(1899, 12, 30)


def _letter(index):
    out = ''
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def build_xlsx(rows, *, drop=(), headers=SAP_HEADERS):
    """`rows`: dicts keyed like `_FIELD_HEADER` plus `description_2`.
    Dates are `datetime.date`. `drop` removes header titles (every
    occurrence) — a file "with a header removed"."""
    headers = [h for h in headers if h not in set(drop)]
    strings, index = [], {}

    def sst(text):
        if text not in index:
            index[text] = len(strings)
            strings.append(text)
        return index[text]

    def cell(ref, value):
        if value is None or value == '':
            return ''
        if isinstance(value, datetime.date):
            return '<c r="%s" s="2"><v>%d</v></c>' % (
                ref, (value - _EPOCH).days)
        return '<c r="%s" t="s"><v>%d</v></c>' % (ref, sst(str(value)))

    columns = []  # (letter, header)
    for i, h in enumerate(headers, 1):
        columns.append((_letter(i), h))
    desc_seen = 0
    col_field = {}
    for letter, h in columns:
        if h == 'Asset description':
            col_field[letter] = 'description' if desc_seen == 0 \
                else 'description_2'
            desc_seen += 1
        else:
            for k, title in _FIELD_HEADER.items():
                if title == h and k != 'description':
                    col_field[letter] = k
    lines = ['<row r="1">%s</row>' % ''.join(
        cell('%s1' % letter, h) for letter, h in columns)]
    for n, row in enumerate(rows, 2):
        cells = []
        for letter, _h in columns:
            field = col_field.get(letter)
            if field is None:
                continue
            cells.append(cell('%s%d' % (letter, n), row.get(field)))
        lines.append('<row r="%d">%s</row>' % (n, ''.join(cells)))
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
             '<worksheet xmlns="%s"><dimension ref="A1"/><sheetData>%s'
             '</sheetData></worksheet>' % (ns, ''.join(lines)))
    sst_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<sst xmlns="%s" count="%d" uniqueCount="%d">%s</sst>' % (
                   ns, len(strings), len(strings),
                   ''.join('<si><t>%s</t></si>' % escape(s) for s in strings)))
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="%s" xmlns:r="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships"><sheets><sheet name="Sheet1" '
        'sheetId="1" r:id="rId1"/></sheets></workbook>' % ns)
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types/>')
        z.writestr('xl/workbook.xml', workbook)
        z.writestr('xl/_rels/workbook.xml.rels', rels)
        z.writestr('xl/worksheets/sheet1.xml', sheet)
        z.writestr('xl/sharedStrings.xml', sst_xml)
    return buf.getvalue()


def record(number, *, cls='2000', description='OFFICE CHAIR', tag=None,
           serial=None, sub='0', retired=None, description_2=None,
           vendor=None, company='FIRS'):
    """One invented record in SAP's shapes."""
    return {
        'company_code': company, 'asset_number': number, 'sub_number': sub,
        'asset_class': cls, 'description': description,
        'description_2': description_2, 'old_tag': tag, 'serial': serial,
        'capitalized_on': datetime.date(2019, 3, 14),
        'first_acquired_on': datetime.date(2019, 3, 14),
        'sap_created_on': datetime.date(2019, 3, 1),
        'deactivated_on': retired, 'vendor': vendor,
    }
