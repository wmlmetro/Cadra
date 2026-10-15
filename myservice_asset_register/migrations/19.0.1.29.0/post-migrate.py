"""Handoff 60 §2a: when each candidate entered its present register state.

`register_state_since` is new: the Candidates list is read oldest first by
it. Filled here on every unit not yet on the register, from the same facts
`gates.state_since` is published from — its last `gate_fired` event, else
its creation. A registered asset is left empty: it is never sorted by it,
and inventing an instant for 16,000 records that never waited on anybody
would be a claim the record cannot back. New records get it at creation.

Also measures `identification_mode` (handoff 60 §1.2): new assets carry
their class's mode from now on, gates on or off; existing rows are not
touched, and the line says how many have none.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE nrs_asset a
           SET register_state_since = COALESCE(
                 (SELECT max(e.occurred_at) FROM nrs_asset_event e
                   WHERE e.asset_id = a.id AND e.event_type = 'gate_fired'),
                 a.create_date)
         WHERE a.register_state <> 'registered'
           AND a.register_state_since IS NULL""")
    filled = cr.rowcount
    cr.execute("SELECT count(*) FROM nrs_asset "
               "WHERE register_state <> 'registered'")
    candidates = cr.fetchone()[0]
    cr.execute("SELECT count(*), count(*) FILTER "
               "(WHERE identification_mode IS NULL) FROM nrs_asset")
    assets, no_mode = cr.fetchone()
    _logger.warning(
        "handoff 60: %s — register_state_since filled on %d of %d "
        "candidates; %d of %d assets carry no identification_mode (created "
        "with the gates off before handoff 60; left as they are)",
        cr.dbname, filled, candidates, no_mode, assets)
