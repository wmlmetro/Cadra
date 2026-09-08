"""Delete two ir.cron rows whose methods are not in the code that runs them.

`nrs19` and `jaizbankplc` carry:

    cron_asset_pm_refresh_overdue    -> nrs.asset.pm._cron_refresh_overdue()
    cron_asset_refresh_verification  -> nrs.asset._cron_refresh_verification()

Both methods DO exist — in commit `c673ed1`, on `feat/rfp-phase1-authorisation`,
which is not an ancestor of `dev`. That commit added the two crons, their data
file and their (batched, documented) implementations together, and it was
never merged. These two databases were upgraded from that branch; the rows
survived, the code did not. So on `dev` the xmlid claims this module owns a
cron that this module does not define, and `getattr` on the model finds
nothing.

They were harmless only because Odoo's scheduler was pinned to a single
database and never ran anything. The first tick after that is fixed would
raise `AttributeError` on both, on every affected tenant, every day.

Deleted rather than deactivated: a scheduled job that cannot run is not a
placeholder for one that will, and leaving it disabled preserves the
appearance of a guarantee while removing the only thing that would have made
its absence audible.

**What is NOT fixed here.** The crons were a correct response to a real
defect. `nrs.asset.is_verified` and `nrs.asset.pm.is_overdue` are both
`store=True` computes whose `@api.depends` can never fire, because what
changes them is the calendar and the calendar is not an ORM dependency — so
`is_verified` never expires after 365 days and `is_overdue` is False on every
PM row, which is why the "Overdue PM" menu is permanently empty.
**`c673ed1` is where the fix already lives** and is the place to start, not a
blank page. It is not cherry-picked here because `is_verified` is published
API surface (serialised and filterable), so correcting it changes what Vendra
sees and is a decision rather than a cleanup. See docs/handoffs/08-REPORT.md.
"""
import logging

_logger = logging.getLogger(__name__)

# xmlid -> (model, method it schedules). The method is checked at run time
# rather than assumed absent: from 19.0.1.11.0 both of these are real crons
# with real implementations, and a database jumping straight from a version
# below 1.10.0 to 1.11.0 or later loads the 1.11.0 data file BEFORE this
# script runs. Deleting unconditionally would then remove the crons the same
# upgrade had just installed, and leave the tenant back where handoff 08 found
# it — silently, on exactly the databases nobody was watching.
# As of 19.0.1.11.0 both methods ship, so `hasattr` is true on every version
# path and THIS SCRIPT CAN NO LONGER DELETE ANYTHING. That is the intended
# end state, not an oversight: the script's whole remaining job is to be
# inert while still guarding the one ordering that would otherwise bite —
# Odoo loads a module's data files BEFORE running its post-migrate scripts,
# so a tenant jumping from below 1.10.0 straight to 1.11.0 loads the two cron
# records and then runs this. Unconditional deletion would remove the crons
# the same upgrade had just installed.
ORPHANS = {
    "cron_asset_pm_refresh_overdue": ("nrs.asset.pm", "_cron_refresh_overdue"),
    "cron_asset_refresh_verification": ("nrs.asset", "_cron_refresh_verification"),
}


def migrate(cr, version):
    if not version:
        return

    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    Data = env["ir.model.data"].sudo()

    for name, (model_name, method) in ORPHANS.items():
        if model_name in env and hasattr(env[model_name], method):
            _logger.info(
                "myservice_asset_register: keeping cron %s — %s.%s() exists in "
                "this registry, so it is not an orphan.",
                name, model_name, method)
            continue

        entries = Data.search([
            ("module", "=", "myservice_asset_register"),
            ("model", "=", "ir.cron"),
            ("name", "=", name),
        ])
        if not entries:
            continue
        crons = env["ir.cron"].sudo().with_context(active_test=False).browse(
            entries.mapped("res_id")).exists()
        _logger.warning(
            "myservice_asset_register: removing orphan cron %s (%s) — it "
            "schedules a method that does not exist",
            name, ", ".join(crons.mapped("cron_name")) or "no record")
        # The server action goes with it; ir.cron._inherits it, so unlinking
        # the cron takes the ir.actions.server row too.
        crons.unlink()
        entries.unlink()
