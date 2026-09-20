"""Stamp the instant the provenance fields began to be tracked — once.

Handoff 28 put `tracking=True` on `grn_reference`, `purchase_order_reference`,
`purchase_vendor`, `import_source`, `import_date` and `import_ref`. From the
moment this upgrade lands, a change to any of them leaves a chatter line.
Before it, a change left nothing at all.

The register snapshot (`asset_snapshot.py`) rolls tracked fields back to a
requested date and says of them that *no recorded change since the date means
the current value IS the value at the date*. For these six that is true only
back to NOW, on THIS database. So the instant is written down here, where it
is a measurement, rather than typed into the source, where it would be a
claim — and a wrong one on every server upgraded on a later day.

Written ONCE. A re-run, or a later upgrade of this module, must not move it
forward: that would un-flag a period in which changes genuinely were being
recorded, which is harmless, but it would also be a history that edits
itself, which is not.

Nothing here touches an asset. There is no backfill: a value these fields
held before today is not recoverable from anything, and the snapshot says so
per row rather than this script inventing one.
"""
import logging

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)

PARAM = 'cadra.provenance_tracked_from'


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Param = env['ir.config_parameter'].sudo()
    existing = Param.get_param(PARAM)
    if existing:
        _logger.info(
            "%s already stamped at %s on %s; left as it is.",
            PARAM, existing, cr.dbname)
        return
    if not version:
        # A fresh install: every asset this database will ever hold is
        # created with the fields already tracked. No stamp means "from the
        # first asset", which is what the snapshot reads an absent one as.
        return
    now = fields.Datetime.to_string(fields.Datetime.now())
    Param.set_param(PARAM, now)
    _logger.info(
        "Provenance fields on nrs.asset are tracked from %s on %s. The "
        "register snapshot names them as today's value for any earlier date.",
        now, cr.dbname)
