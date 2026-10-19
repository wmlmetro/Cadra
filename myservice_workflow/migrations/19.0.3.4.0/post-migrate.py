"""Handoff 63, ruling 8: the delivery retry budget covers a day.

The old default — 8 attempts, 60 s doubling to a 3,600 s cap — gives up
after 2 h 3 min (report 62 §5), so a receiver down for a working day had
every event dead-lettered. The new default is 32 attempts at the same base
and cap: 1, 2, 4, 8, 16 and 32 minutes, then hourly — 26 h 3 min of trying.

Every target still carrying the OLD default is moved to the new one; a
target somebody customised (any of the three values different) is left
alone and LISTED. One line per database says what changed. Rows already
queued keep the budget they were queued with (`workflow.dispatch.log`
snapshots it); only new events get the new one.
"""
import logging

_logger = logging.getLogger(__name__)

OLD = (8, 60, 3600)
NEW_ATTEMPTS = 32


def migrate(cr, version):
    cr.execute("""
        SELECT id, name, retry_max_attempts, retry_base_seconds,
               retry_cap_seconds
          FROM workflow_config ORDER BY id""")
    rows = cr.fetchall()
    moved = [r for r in rows if tuple(r[2:]) == OLD]
    kept = [r for r in rows if tuple(r[2:]) != OLD]
    if moved:
        cr.execute("UPDATE workflow_config SET retry_max_attempts = %s "
                   "WHERE id = ANY(%s)", [NEW_ATTEMPTS, [r[0] for r in moved]])
    _logger.info(
        "retry budget on %s: %d of %d target(s) moved from 8 to %d attempts "
        "(%s); %d customised, left alone (%s)",
        cr.dbname, len(moved), len(rows), NEW_ATTEMPTS,
        ", ".join("#%d %s" % (r[0], r[1]) for r in moved) or "none",
        len(kept),
        # `%s`, not `%d`: a hand-edited row may hold a NULL.
        ", ".join("#%s %s: %s/%ss/%ss" % r for r in kept) or "none")
