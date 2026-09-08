from . import models


def post_init_hook(env):
    """Turn off the third-party crons on a FRESH tenant, at install.

    Odoo 19 calls the hook with a single argument, an `odoo.api.Environment`
    (`odoo/modules/loading.py`: ``getattr(py_module, post_init)(env)``) — not
    the `(cr, registry)` pair of the 15-era signature.

    Two entry points are needed and neither substitutes for the other: this one
    covers a database created after the change lands, and
    ``migrations/19.0.1.1.0/post-migrate.py`` covers the tenants that already
    exist, via the per-tenant ``odoo -u`` fan-out the cadra-upgrade Job runs.
    An install runs no migration scripts, and an upgrade runs no post_init_hook.
    """
    env["ir.cron"]._cadra_disable_third_party_crons()
