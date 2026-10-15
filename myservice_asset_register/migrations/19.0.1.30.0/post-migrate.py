"""Handoff 61 §7 (R8): every location gets a room code.

`generic.location.location_code` is new in this version. After the registry
has created the column (and its UNIQUE constraint, which empty rows satisfy),
every location with no code is given the one its hierarchy derives
(`models/location_code.py` says the format), oldest first so the oldest of
two locations deriving the same code keeps it.

Idempotent: a location that already has a code is never touched, so a re-run
writes nothing. The fresh-install twin is `hooks.stamp_tracking_began`.

Writes `generic_location.location_code` and nothing else: no asset's code,
serial, class or number is read for writing here (handoff 61 §10).
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    filled, total = env['generic.location']._fill_location_codes()
    # The ORM writes above may still be in the cache; the count below reads
    # the table, so it must read what was written.
    env.flush_all()
    cr.execute("""SELECT count(*) FILTER (WHERE location_code IS NULL),
                         count(location_code) - count(DISTINCT location_code)
                    FROM generic_location""")
    empty, duplicates = cr.fetchone()
    _logger.warning(
        "handoff 61: %s — location_code filled on %d of %d locations; "
        "%d of %d still empty; %d duplicate codes",
        cr.dbname, filled, total, empty, total, duplicates)
