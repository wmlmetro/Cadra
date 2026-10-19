"""Handoff 66 §2 (R2a): the ledger of asset codes, backfilled.

`nrs.asset.code` is new in this version. Every code an asset already carries
becomes one ledger row, so there is one answer to "which codes exist":

* on the register (`register_state = 'registered'`) → `active`;
* a receipt candidate → `in_review` (R2a: a code is ACTIVE AT REGISTRATION);
* a receipt IAD rejected → `void`, with that reason — it is never reused.

`source = 'backfill'` says the row was recorded from an existing asset, not
written when its code was born. Idempotent: a code already in the ledger is
left alone, so a re-run writes nothing. Prints the per-tenant count.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        INSERT INTO nrs_asset_code
               (code, state, source, asset_id, used_at, activated_at,
                voided_at, void_reason, create_uid, write_uid, create_date,
                write_date)
        SELECT a.asset_code,
               CASE WHEN a.register_state = 'registered' THEN 'active'
                    WHEN a.register_state = 'vfm_rejected' THEN 'void'
                    ELSE 'in_review' END,
               'backfill', a.id, a.create_date,
               CASE WHEN a.register_state = 'registered'
                    THEN a.create_date END,
               CASE WHEN a.register_state = 'vfm_rejected' THEN now() END,
               CASE WHEN a.register_state = 'vfm_rejected'
                    THEN 'The receipt was rejected by IAD (recorded when the '
                         'ledger was built).' END,
               1, 1, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC'
          FROM nrs_asset a
         WHERE a.asset_code IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM nrs_asset_code c
                            WHERE c.code = a.asset_code)
    """)
    added = cr.rowcount
    cr.execute("""SELECT state, count(*) FROM nrs_asset_code
                   GROUP BY state ORDER BY state""")
    by_state = dict(cr.fetchall())
    cr.execute("SELECT count(*) FROM nrs_asset")
    assets = cr.fetchone()[0]
    message = ("asset-code ledger on %s: %d rows written now; %d assets, "
               "ledger by state %s" % (cr.dbname, added, assets, by_state))
    _logger.info(message)
    print(message)
