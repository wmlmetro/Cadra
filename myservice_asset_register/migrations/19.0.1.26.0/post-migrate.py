"""Handoff 57 (SCAFFOLDING, replaced by handoff 58): every existing asset is
REGISTERED.

`nrs.asset.register_state` arrives with this version. Anything but
`registered` is a receipt candidate, hidden from the register — so a row
that came out of the column add as anything else would vanish from every
list, count and report overnight. The field's default fills the column on
add; this makes it explicit, and prints the count per tenant, which the
handoff asks for (§4, "print the count per tenant").
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("UPDATE nrs_asset SET register_state = 'registered' "
               "WHERE register_state IS NULL OR register_state = ''")
    fixed = cr.rowcount
    cr.execute("SELECT count(*), "
               "count(*) FILTER (WHERE register_state = 'registered') "
               "FROM nrs_asset")
    total, registered = cr.fetchone()
    _logger.warning(
        "handoff 57: register_state on %s — %s of %s assets registered "
        "(%s filled by this migration)", cr.dbname, registered, total, fixed)
