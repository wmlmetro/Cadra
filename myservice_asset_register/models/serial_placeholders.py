# -*- coding: utf-8 -*-
"""Placeholder serials — a value typed where a serial should be (handoff 59 §3).

SAP's own register for NRS (October 2026 export,
`docs/reference/sap-asset-master-2026-10.md`) holds 33,096 active assets
whose "serial" is a placeholder: `0` on 22,217 rows, `XXXX`, `XXX`,
`4A12345FD` on 5,762. *No serial, no receipt* (Addendum A) means a
placeholder is NOT a serial: a gated receipt refuses one as what it is,
rather than accepting it and then refusing the next unit that carries the
same placeholder as a "duplicate".

The list is the TENANT's: one `ir.config_parameter`, `cadra.serial_placeholders`,
JSON `{"exact": [...], "patterns": [...]}` — so every change is a row on the
configuration record with its writer, the way the class settings are. Seeded
by `data/serial_placeholders.xml` (noupdate); ABSENT means the seed below, so
a tenant whose row was never created still refuses `XXXX`.

A value is compared stripped, upper-cased and with internal runs of
whitespace collapsed to one space (`normalise`); exact values are stored in
that form, patterns are matched against it, case-insensitively.

Nothing here rewrites a stored serial. Cleaning the legacy register is NRS's
decision (GO-LIVE §29 item 8); `measure` only counts.
"""
import json
import re

PARAM = 'cadra.serial_placeholders'

DEFAULT_PATTERNS = ('^X+$', '^0+$')
DEFAULT_EXACT = ('4A12345FD', '5D12345M', '12345AB', '12345ABC', '12345HFD',
                 '123456', 'N/A', 'NA', 'NIL', 'NONE', 'NO SERIAL')

_SPACES = re.compile(r'\s+')
#: Invented serials in real shapes; a pattern matching one is refused.
_REAL_LOOKING = ('5CD1234ABC', 'C02XK1ABJGH5', 'SN-20431977', 'R9PQ7Z')


def normalise(value):
    """The form a serial is compared in: stripped, upper-case, one space."""
    return _SPACES.sub(' ', (value or '').strip()).upper()


def validate(exact, patterns):
    """`(exact, patterns)` normalised, or raise ValueError with the sentence."""
    for name, items in (('exact', exact), ('patterns', patterns)):
        if not isinstance(items, list) or not all(
                isinstance(v, str) and v.strip() for v in items):
            raise ValueError(
                '`%s` must be a list of non-empty strings.' % name)
    if not exact and not patterns:
        # An empty list accepts every placeholder — the failure this exists
        # to prevent — so it is not a list a tenant can save.
        raise ValueError('The list cannot be empty: with nothing on it, every '
                         'placeholder would be accepted as a serial.')
    for p in patterns:
        try:
            compiled = re.compile(p, re.IGNORECASE)
        except re.error as e:
            raise ValueError('Pattern %r is not a valid regular expression '
                             '(%s).' % (p, e))
        hit = next((s for s in _REAL_LOOKING if compiled.search(s)), None)
        if hit:
            # `.*` would refuse every serial at every gated receipt.
            raise ValueError('Pattern %r matches a real-looking serial (%s), '
                             'so it would refuse real serials too. Anchor it '
                             'to the placeholder (for example ^X+$).' % (p, hit))
    clean_exact = sorted({normalise(v) for v in exact})
    clean_patterns = list(dict.fromkeys(p.strip() for p in patterns))
    return clean_exact, clean_patterns


def load(env):
    """`{'exact': [...], 'patterns': [...], 'configured': bool}`.

    Raw SQL, like the receipt switch, so no cache answers for the row. A row
    that cannot be read as the list (somebody wrote it by hand) falls back to
    the seed rather than to no list at all: an empty list would quietly
    accept every placeholder, which is the failure this exists to prevent.
    """
    env.cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s",
                   (PARAM,))
    row = env.cr.fetchone()
    if row:
        try:
            data = json.loads(row[0] or '')
            exact, patterns = validate(list(data['exact']),
                                       list(data['patterns']))
            return {'exact': exact, 'patterns': patterns, 'configured': True}
        except (ValueError, TypeError, KeyError):
            pass
    # Unreadable or absent: the seed, and NOT configured — the screen must
    # not present the seed as what somebody saved.
    return {'exact': sorted(DEFAULT_EXACT), 'patterns': list(DEFAULT_PATTERNS),
            'configured': False}


def matcher(lists):
    """A function `value -> bool` for one list, compiled once."""
    exact = set(lists['exact'])
    compiled = [re.compile(p, re.IGNORECASE) for p in lists['patterns']]

    def is_placeholder(value):
        norm = normalise(value)
        if not norm:
            return False
        return norm in exact or any(c.search(norm) for c in compiled)
    return is_placeholder


def is_placeholder(env, value):
    return matcher(load(env))(value)


def store(env, exact, patterns):
    """Write the list (validated). The configuration record is the row."""
    exact, patterns = validate(exact, patterns)
    env['ir.config_parameter'].sudo().set_param(
        PARAM, json.dumps({'exact': exact, 'patterns': patterns}))
    return {'exact': exact, 'patterns': patterns}


def measure(env, top=8):
    """How many assets on this tenant carry a placeholder serial, and which.

    Every `nrs_asset` row, candidates and archived ones included (raw SQL —
    the register filter does not apply), grouped by the normalised value so
    the list is read once per distinct serial, not once per asset.
    """
    is_ph = matcher(load(env))
    env.cr.execute("SELECT count(*) FROM nrs_asset")
    assets = env.cr.fetchone()[0]
    env.cr.execute(
        "SELECT upper(regexp_replace(btrim(serial_number), '\\s+', ' ', 'g')),"
        "       count(*) "
        "FROM nrs_asset WHERE serial_number IS NOT NULL "
        "AND btrim(serial_number) <> '' GROUP BY 1")
    rows = env.cr.fetchall()
    with_serial = sum(n for _v, n in rows)
    hits = sorted(((v, n) for v, n in rows if is_ph(v)),
                  key=lambda r: (-r[1], r[0]))
    return {
        'assets': assets,
        'with_serial': with_serial,
        'placeholders': sum(n for _v, n in hits),
        'top': [{'value': v, 'count': n} for v, n in hits[:top]],
    }
