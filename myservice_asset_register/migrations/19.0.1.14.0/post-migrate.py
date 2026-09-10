"""Recover the date of every disposal that was never given one — and nothing else.

`action_condemn` wrote a condition and a state. It did not write a date, and
`disposal_date` was not tracked, so a historic disposal in Cadra has:

  * a `state` of `disposed`, which IS tracked, so the transition carries an
    actor and a timestamp in the chatter; and
  * very often no `disposal_date` at all.

A disposal with no date falls out of every period report, in both directions:
it is invisible to the auditor asking about Q1 and it is invisible to the one
asking about Q2. That silent hole is what this script closes, using the only
evidence in the database that says when it happened — the tracked
`state → disposed` transition.

**Every recovered date is marked as recovered.** `disposal_date_reconstructed`
is set on every row this script fills and on no other row. A reconstructed
value written into the same column as a recorded one is indistinguishable
from it, which is precisely the defect `nrs.asset.custody.source =
'tracking_backfill'` exists to prevent: an auditor told where the
reconstruction begins can work with it; one who discovers it later cannot
trust any of it, including the part that was recorded properly.

**Nothing else is recovered, and in particular no approver is invented.**
`disposal_approved_by` and `disposal_approved_date` are left null on every
historic row. There was no field to record an approver in, so nothing in the
database says who authorised these disposals, and the acting user on the
state change is the person who pressed a button — not the authority who
approved it. Handoff 08 left 289 affix records carrying `Administrator`
untouched on this reasoning and it holds unchanged here: a visible gap is the
correct output, and a fabricated audit trail is not a stronger one.

`disposal_method`, `disposal_reference`, `disposal_proceeds` and
`disposal_reason` are left null for the same reason. Every disposal this
script touches will therefore appear in the period report carrying
`no_approver`, `no_authorising_reference` and `no_disposal_method`. **That is
the finding**, not a defect in the recovery.
"""
import logging

_logger = logging.getLogger(__name__)

# How many assets to write at a time. Small enough that a tenant with a large
# disposed population does not hold one transaction open across the whole
# register, large enough that the fan-out across eight tenants is not
# dominated by round trips.
_BATCH = 500


def migrate(cr, version):
    if not version:
        return

    from odoo import SUPERUSER_ID, api
    from odoo.addons.myservice_asset_register.models.asset_disposal import (
        _DISPOSED_TRACKING_SQL,
    )

    env = api.Environment(cr, SUPERUSER_ID, {})
    Asset = env["nrs.asset"].sudo()

    # The domain IS the idempotency: once a row has a date it is out of
    # scope, so a second run finds nothing to do. A migration script runs
    # once per version per database, but a tenant restored from a backup
    # taken mid-run would otherwise be re-processed, and re-processing must
    # not move a date that has since been corrected by hand.
    undated = Asset.search([
        ("state", "=", "disposed"),
        ("disposal_date", "=", False),
    ])
    if not undated:
        _logger.info(
            "myservice_asset_register: no undated disposals on %s — nothing "
            "to recover.", cr.dbname)
        return

    # Read-only. The precondition the query depends on is satisfied by the
    # domain above: every asset passed here is currently `disposed`, so its
    # most recent `state` tracking row is by definition the change INTO
    # `disposed` and the translated Selection label never has to be parsed.
    cr.execute(_DISPOSED_TRACKING_SQL, (undated.ids,))
    changed_at_by_asset = {
        row["asset_id"]: row["changed_at"]
        for row in cr.dictfetchall()
        if row["changed_at"]
    }

    recovered = 0
    for index in range(0, len(undated), _BATCH):
        for asset in undated[index:index + _BATCH]:
            changed_at = changed_at_by_asset.get(asset.id)
            if not changed_at:
                continue
            # `mail_message.date` is naive UTC and the date is taken in UTC.
            # Converting through a timezone would invent a precision the
            # source does not have, and could move a disposal across a
            # financial year boundary on the strength of a session setting.
            #
            # `tracking_disable`: the field is tracked from this version
            # forward, and a tracking row here would read as somebody having
            # changed the date during the upgrade. Nobody did — the value was
            # recovered — and `disposal_date_reconstructed` is the honest
            # place for that fact to live. Suppressing the tracking row is
            # what keeps the chatter a record of what people did.
            asset.with_context(tracking_disable=True).write({
                "disposal_date": changed_at.date(),
                "disposal_date_reconstructed": True,
            })
            recovered += 1

    _logger.info(
        "myservice_asset_register: disposal date recovery on %s — %d undated "
        "disposal(s) found, %d recovered from the tracked state change, %d "
        "left with no date because nothing in the database says when they "
        "happened. No approver, reference or method was inferred for any of "
        "them.",
        cr.dbname, len(undated), recovered, len(undated) - recovered)
