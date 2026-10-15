# Handoff 61 §7 — room codes. Written by the location-code agent.
"""`generic.location.location_code`: the code a room label carries (R8).

A room is scanned at the station before anything in it is (the audit-capture
path, `docs/AI-CAPTURE-EVALUATION.md` §3 step 1), so every location needs a
code a scanner can read and nothing else in the register can be read as.

THE FORMAT
----------
``LOC-`` followed by the zone codes of the location's ancestors and itself,
root first, each cleaned to ``[A-Z0-9]`` exactly as `nrs.asset._tag_prefix`
cleans them (so the room segment on a room label reads the same as on the
asset tags printed for things in that room), joined by ``-``. A level with
no zone code is skipped. A location with NO zone code of its own ends in its
database id, because nothing else in the hierarchy names it:

    NRS Headquarters / 10th Floor / Open Office North   (HQ / F10 / OFC-N)
        -> LOC-HQ-F10-OFCN
    Orlu MSTO (no zone code anywhere above it)          -> LOC-1133
    a room with no zone code under HQ / F10             -> LOC-HQ-F10-<id>

Measured before choosing (all eight local tenants, 2026-10-15): 4,869
locations, of which only 538 carry a zone code (all of them `nrs19`/`nrs`'s
headquarters tree, and 30 `test19` fixtures). A format built from zone codes
alone would have left 4,331 locations with nothing to derive from — so the id
is the honest last segment, not an invented abbreviation of a name like
"Port Harcourt SC & DMEO".

WHY THE PREFIX. A scan must never be ambiguous. An asset code is
``NRS-AST-######`` and a tag number is ``<zone codes or brand>-<class>-NNN``
(`asset_tag._tag_prefix`); neither begins ``LOC-`` on any local tenant
(0 tags, 0 asset codes, 0 serials, 0 zone codes equal to ``LOC``; brand short
names NRS, GTB, Jaiz, LASG Health). Every code, generated or typed, must
begin ``LOC-``, and a typed one is ALSO refused if it equals an existing tag
number (any state) or asset code. The scan resolver tries a location code
LAST, after tag, asset code and serial, so even a future tag minted under a
building whose zone code is ``LOC`` would still resolve as the tag it is.

COLLISIONS ARE IMPOSSIBLE BY CONSTRUCTION. The derived code is tried first;
if another location (archived ones included) holds it, ``-<id>`` is appended;
then ``LOC-<id>``; then ``LOC-<id>-2``, ``-3``… The id is unique, so the
sequence always ends on a free code, and the database's own UNIQUE constraint
stands behind it. Measured: the only derived collision on any tenant is 29
`test19` fixtures sharing zone code ``E2E-01`` — the oldest keeps
``LOC-E2E01``-shaped code and the other 28 take the ``-<id>`` suffix; 0
collisions remain on any tenant.

A CODE DOES NOT FOLLOW THE HIERARCHY. It is generated once, when empty, and
stored. Moving a room or editing a zone code does NOT change it — a printed
label must go on scanning. To re-derive it, clear it: an EMPTY value written
to `location_code` regenerates it from the hierarchy as it is now.
"""
import base64
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

#: Every room code begins with this. See the module docstring.
LOCATION_CODE_PREFIX = 'LOC-'

#: Long enough for every derived code measured (15 characters at most, 20
#: with an id suffix) and short enough to stay readable as Code 128 on the
#: medium label, where every character costs 11 modules of 46 mm.
LOCATION_CODE_MAX_LENGTH = 24

#: Printable verbatim as Code 128 and QR: upper-case letters, digits and
#: single hyphens between non-empty segments, the prefix first.
_CODE_SHAPE = re.compile(r'^LOC(-[A-Z0-9]+)+$')

_CLEAN = re.compile(r'[^A-Z0-9]')


def _clean_segment(value):
    """A zone code as `nrs.asset._tag_prefix` cleans it: [A-Z0-9] only."""
    return _CLEAN.sub('', (value or '').upper())


def normalize_location_code(value):
    """Trimmed and upper-cased. Nothing else is changed: an inner space or a
    character a label cannot carry is REFUSED by `_location_code_refusal`,
    not silently removed, so the code a person typed is the code they get or
    a sentence saying why not."""
    if value is None or value is False:
        return ''
    return str(value).strip().upper()


class LocationCodeRefused(ValidationError):
    """A room code that cannot be saved, with the reason in words.

    `kind` is ``format`` (not a code a label can carry), ``taken`` (another
    location holds it) or ``shadows`` (a tag number or asset code already
    reads the same, so a scan of it would be ambiguous). The API maps
    ``format`` to 400 and the other two to 409; any other caller (the back
    office, a shell) gets the sentence as a `ValidationError`.
    """

    def __init__(self, message, kind, details=None):
        super().__init__(message)
        self.kind = kind
        self.details = details or {}


class GenericLocation(models.Model):
    _inherit = 'generic.location'

    location_code = fields.Char(
        string='Room Code', index=True, copy=False,
        help="The code a room label carries, as a QR and a Code 128, "
             "verbatim. Begins LOC-. Generated from the hierarchy's zone "
             "codes when empty and stored — it does not change when the "
             "location moves, so a printed label goes on scanning. Clear it "
             "to generate it again.")

    # Unique per tenant, archived locations included (a constraint sees every
    # row). Odoo 19 removed `_sql_constraints`; this is the only spelling
    # that creates anything. No `_ODOO_MAJOR` guard: the 15 stack is retired
    # (handoff 20) and `myservice_asset_register` loads on 19 only. NULL is
    # never equal to NULL, so a location not yet given a code does not
    # collide with another.
    _location_code_unique = models.Constraint(
        'UNIQUE (location_code)',
        'Another location already carries this room code.',
    )

    # ── the refusal, in words, before the database says it ────────────

    @api.model
    def _location_code_refusal(self, code, exclude_ids=()):
        """None when `code` (already normalised) may be saved, else a
        `LocationCodeRefused` to raise. A read: nothing is written."""
        if not _CODE_SHAPE.match(code) or len(code) > LOCATION_CODE_MAX_LENGTH:
            return LocationCodeRefused(_(
                "Room code %(code)s cannot be printed as a room label. A room "
                "code begins LOC-, uses only the letters A-Z, the digits 0-9 "
                "and single hyphens between them, and is at most %(max)s "
                "characters long — so a scan can never be mistaken for a tag "
                "number or an asset code.",
                code=code, max=LOCATION_CODE_MAX_LENGTH),
                'format', {'location_code': code,
                           'max_length': LOCATION_CODE_MAX_LENGTH,
                           'prefix': LOCATION_CODE_PREFIX})
        holder = self.sudo().with_context(active_test=False).search(
            [('location_code', '=', code), ('id', 'not in', list(exclude_ids))],
            limit=1)
        if holder:
            return LocationCodeRefused(_(
                "Room code %(code)s is already the code of %(name)s "
                "(location %(id)s%(archived)s). Each location's code is "
                "unique, archived locations included. Choose another code, "
                "or leave it empty to have one generated.",
                code=code, name=holder.name, id=holder.id,
                archived=_(', archived') if not holder.active else ''),
                'taken', {'location_code': code,
                          'held_by_location_id': holder.id})
        Tag = self.env.get('nrs.asset.tag.label')
        if Tag is not None and Tag.sudo().with_context(
                active_test=False).search_count([('name', '=', code)], limit=1):
            return LocationCodeRefused(_(
                "Room code %(code)s reads the same as a tag number already "
                "issued, so a scan of it could not tell the room from the "
                "asset. Choose another code.", code=code),
                'shadows', {'location_code': code, 'shadows': 'tag_number'})
        Asset = self.env.get('nrs.asset')
        if Asset is not None and Asset.sudo().with_context(
                active_test=False, cadra_candidates=True).search_count(
                    [('asset_code', '=', code)], limit=1):
            return LocationCodeRefused(_(
                "Room code %(code)s reads the same as an asset code, so a "
                "scan of it could not tell the room from the asset. Choose "
                "another code.", code=code),
                'shadows', {'location_code': code, 'shadows': 'asset_code'})
        return None

    # ── generation ────────────────────────────────────────────────────

    def _derived_location_code(self):
        """The code this location's hierarchy gives it, before any collision
        is considered. Walks `parent_id` rather than reading `parent_path`,
        which a record created in this transaction may not have in cache."""
        self.ensure_one()
        chain, seen, loc = [], set(), self
        while loc and loc.id not in seen:
            seen.add(loc.id)
            chain.append(loc)
            loc = loc.parent_id
        chain.reverse()
        segments = [s for s in (_clean_segment(l.zone_code) for l in chain) if s]
        if not _clean_segment(self.zone_code):
            segments.append(str(self.id))
        code = LOCATION_CODE_PREFIX + '-'.join(segments)
        if len(code) > LOCATION_CODE_MAX_LENGTH:
            # A deep tree of long zone codes: the id alone is still unique
            # and still the shortest thing that names this location.
            code = '%s%d' % (LOCATION_CODE_PREFIX, self.id)
        return code

    def _candidate_location_codes(self):
        self.ensure_one()
        derived = self._derived_location_code()
        yield derived
        suffixed = '%s-%d' % (derived, self.id)
        if len(suffixed) <= LOCATION_CODE_MAX_LENGTH and not derived.endswith(
                '-%d' % self.id):
            yield suffixed
        yield '%s%d' % (LOCATION_CODE_PREFIX, self.id)
        n = 2
        while True:
            yield '%s%d-%d' % (LOCATION_CODE_PREFIX, self.id, n)
            n += 1

    def _next_free_location_code(self):
        """The first candidate nobody else holds. Ends: the id is unique."""
        self.ensure_one()
        for code in self._candidate_location_codes():
            if self._location_code_refusal(code, exclude_ids=self.ids) is None:
                return code
        return None  # unreachable — the generator above never ends

    def _assign_generated_location_codes(self):
        """Give every record in `self` its generated code, oldest first, so
        the oldest location keeps the derived code when two derive the same.
        Through `super().write` of THIS class: the value is generated, so it
        needs no refusal check of its own."""
        for loc in self.sorted('id'):
            code = loc._next_free_location_code()
            super(GenericLocation, loc).write({'location_code': code})

    @api.model
    def _fill_location_codes(self):
        """Fill every EMPTY code on the tenant, archived locations included.

        Idempotent: a location that has a code is never touched, so a second
        run writes nothing. Called by `migrations/19.0.1.30.0/post-migrate.py`
        on an upgrade and by the install hook on a fresh database. Touches
        `generic_location` only — no asset's code, serial, class or number.
        Returns `(filled, total)`.
        """
        Location = self.sudo().with_context(active_test=False)
        empty = Location.search([('location_code', '=', False)], order='id')
        empty._assign_generated_location_codes()
        return len(empty), Location.search_count([])

    # ── every writer ──────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        given = []
        for vals in vals_list:
            if 'location_code' in vals:
                code = normalize_location_code(vals['location_code'])
                vals['location_code'] = code or False
                if code:
                    if code in given:
                        raise LocationCodeRefused(_(
                            "Room code %(code)s was given to two of the "
                            "locations being created together. Each "
                            "location's code is unique.", code=code),
                            'taken', {'location_code': code})
                    refusal = self._location_code_refusal(code)
                    if refusal:
                        raise refusal
                    given.append(code)
        records = super().create(vals_list)
        records.filtered(lambda l: not l.location_code) \
            ._assign_generated_location_codes()
        return records

    def write(self, vals):
        if 'location_code' not in vals:
            return super().write(vals)
        vals = dict(vals)
        code = normalize_location_code(vals['location_code'])
        if not code:
            # EMPTY MEANS REGENERATE, from the hierarchy as it is after this
            # same write (a new parent or zone code in the same body counts).
            vals.pop('location_code')
            result = super().write(vals) if vals else True
            self._assign_generated_location_codes()
            return result
        if len(self) > 1:
            raise LocationCodeRefused(_(
                "Room code %(code)s cannot be given to %(count)s locations at "
                "once: each location's code is unique.",
                code=code, count=len(self)),
                'taken', {'location_code': code})
        vals['location_code'] = code
        # A write that NAMES the code a location already has is allowed —
        # an edit form re-sends every field on every save.
        if self and self.location_code != code:
            refusal = self._location_code_refusal(code, exclude_ids=self.ids)
            if refusal:
                raise refusal
        return super().write(vals)

    # ── the room label ────────────────────────────────────────────────

    def get_location_path(self):
        """Root-first names, `NRS Headquarters / 10th Floor / Store`.
        Public because the room label template reads it."""
        self.ensure_one()
        chain, seen, loc = [], set(), self
        while loc and loc.id not in seen:
            seen.add(loc.id)
            chain.append(loc.name or '')
            loc = loc.parent_id
        return ' / '.join(reversed(chain))

    def get_room_label_barcode(self, barcode_type, value, **kwargs):
        """A PNG barcode as base64, for the room label templates
        (`data/location_label_report.xml`; public because a template calls
        it, like `nrs.asset.get_barcode_base64`). The value is passed
        VERBATIM: handoff 55 §3 — no URL, no prefix inside the encoded
        value."""
        if not value:
            return ''
        png = self.env['ir.actions.report'].barcode(
            barcode_type, value, **kwargs)
        return base64.b64encode(png).decode()
