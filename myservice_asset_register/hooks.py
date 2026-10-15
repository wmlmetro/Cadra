"""Install-time hooks for `myservice_asset_register`."""
from odoo import fields

TRACKING_BEGAN_PARAM = 'cadra.provenance_tracked_from'


def stamp_tracking_began(env):
    """Write down when this database began tracking the handoff-28 fields.

    A migration script runs on UPGRADE and never on a fresh install, so
    `migrations/19.0.1.15.0/post-migrate.py` alone left every new database
    unstamped — and the register snapshot read an absent stamp as "tracked
    since the first asset". That is false for a database built new and then
    LOADED: the 15 to 19 cutover does exactly that, by ETL, preserving each
    asset's original `create_date`, and the snapshot would have rolled a GRN
    reference back across years it has no record of.

    So a fresh install stamps too, and absence never has to mean anything.
    Written once: never moved by a later call.
    """
    Param = env['ir.config_parameter'].sudo()
    if not Param.get_param(TRACKING_BEGAN_PARAM):
        Param.set_param(
            TRACKING_BEGAN_PARAM,
            fields.Datetime.to_string(fields.Datetime.now()))
    fill_location_codes(env)


def fill_location_codes(env):
    """Handoff 61 §7: every location has a room code from the start.

    The fresh-install twin of `migrations/19.0.1.30.0/post-migrate.py`, for
    the reason the docstring above gives — a migration never runs on a
    fresh install. Locations created after the module is installed get
    their code in `generic.location.create`; this covers the ones that
    existed before it (a database built from `generic_location` first, or
    loaded by ETL). Idempotent. Called from `stamp_tracking_began`, which
    is the manifest's one `post_init_hook` and keeps its name so the
    manifest does not change.
    """
    env['generic.location']._fill_location_codes()
