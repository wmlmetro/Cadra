"""Deactivate Odoo's outbound third-party crons on every existing tenant.

Handoff 08 found that `mail.ir_cron_module_update_notification` ("Publisher:
Update Notification") POSTs weekly, per database, to services.odoo.com — the
database name and uuid, `web.base.url`, the installed application list, user
counts, and the **company name, email and phone**. Across these tenants that
is the Nigeria Revenue Service, Guaranty Trust Bank, Jaiz Bank Plc and the
Lagos State Ministry of Health. One such POST already left a developer laptop
on 2026-09-06. The local stack was neutralised in handoff 08; the cluster's
config has never set `db_name`, so its scheduler HAS been enumerating every
tenant and these have been going out weekly all along.

`digest.ir_cron_digest_scheduler_action` rides along on the same pass. It is
inert today only because no tenant has an `ir_mail_server` — it manufactured
~40 `mail_mail` rows on the first local tick and every one failed — and it
becomes real outbound email the day anyone configures SMTP.

This runs on upgrade, which is the only mechanism that reaches an existing
tenant: the cadra-upgrade Job fans `odoo -u <module>` out per database. The
matching install path is `post_init_hook` in `myservice_nrs_base/__init__.py`,
because an install runs no migration scripts.

The durable half of the telemetry fix is `publisher_warranty_url` pointing at a
closed port in both `config/odoo.19.conf` and
`k8s/dev/10-configmap-odoo-19.yaml`. That one is in the repo and covers
databases that do not exist yet; this one stops the weekly ERROR and climbing
`failure_count` that a live cron against a closed port would produce, since the
server action passes `cron_mode` falsy and therefore raises rather than
returning False.

Signature note: Odoo 19 still passes `(cr, version)`, not `(env, version)` —
`odoo/modules/migration.py::VALID_MIGRATE_PARAMS` accepts only
`('cr'|'_cr', 'version'|'_version')` and `exec_script` calls
`mod.migrate(cr, installed_version)`.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    changed = env["ir.cron"]._cadra_disable_third_party_crons()
    _logger.info(
        "myservice_nrs_base 19.0.1.1.0: %d third-party scheduled action(s) "
        "deactivated on %s", changed, cr.dbname)
