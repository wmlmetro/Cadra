"""Handoff 69b: a refused sync row counts its repeats.

`count` (default 1) and `last_refused_at` are new on
`nrs.audit.capture.refusal`. A row written by 19.0.1.37.0 was refused once,
so its last refusal is its first; `GET /audit/refusals?since=` reads
`last_refused_at`, and without this an old row would fall out of every
window. Idempotent: only rows with no `last_refused_at` are touched.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE nrs_audit_capture_refusal
           SET last_refused_at = refused_at
         WHERE last_refused_at IS NULL
    """)
    _logger.info("refused syncs: last_refused_at set on %d row(s)",
                 cr.rowcount)
