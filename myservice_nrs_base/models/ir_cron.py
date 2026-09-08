"""Deactivate third-party scheduled actions we did not choose to run.

Odoo ships scheduled actions that are active on every fresh database. Two of
them send something outward on behalf of a tenant, and nobody at NRS, GTB,
Jaiz Bank or the Lagos State Ministry of Health ever agreed to either.

This module cannot delete them — they belong to `mail` and `digest`, and an
upgrade of those modules would recreate the rows anyway. Deactivating is the
correct verb: the row stays visible in Settings → Technical → Scheduled
Actions, so an administrator who *does* want one can see it and turn it on,
rather than wondering why a documented Odoo feature is missing.

**Honest limitation.** This runs at install of this module and on its upgrade.
If someone installs `digest` (or `mail`) *afterwards*, the freshly created cron
row is active again and nothing here notices. For the telemetry cron that is
survivable because it is only the second of two layers: `publisher_warranty_url`
in the server config points at a closed port, which is in the repo, applies to
every database including ones that do not exist yet, and holds regardless of
what any ir_cron row says. This layer exists to stop the *noise* — the server
action calls `update_notification(None)`, i.e. `cron_mode` falsy, so it raises
on a refused connection instead of returning False, and a live cron against a
closed port means a weekly ERROR and a climbing `failure_count` on every
tenant. For `digest` there is no second layer; if it is ever installed fresh,
re-run this (an upgrade of this module is enough).
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# (xmlid, why it is off). Kept as data rather than a sequence of env.ref calls
# so the list reads as the decision it is.
THIRD_PARTY_CRONS = (
    (
        "mail.ir_cron_module_update_notification",
        "Publisher: Update Notification — POSTs the tenant company's name, "
        "email and phone, the database name and uuid and the installed app "
        "list to services.odoo.com weekly. Client identity for a national "
        "revenue service, two banks and a state ministry is not ours to "
        "disclose to a third party.",
    ),
    (
        "digest.ir_cron_digest_scheduler_action",
        "Digest Email — manufactures periodic KPI emails to every subscriber. "
        "Inert today only because no tenant has an ir_mail_server; it becomes "
        "real outbound mail the day anyone configures SMTP, and nobody has "
        "decided those subscribers should receive one.",
    ),
)


class IrCron(models.Model):
    _inherit = "ir.cron"

    @api.model
    def _cadra_disable_third_party_crons(self):
        """Deactivate the crons in THIRD_PARTY_CRONS. Returns how many changed.

        Idempotent by construction: a cron already inactive is not written to,
        so a repeated upgrade produces no write, no `write_date` churn and no
        log line claiming work that did not happen. A cron whose module is not
        installed on this tenant is simply absent — `raise_if_not_found=False`
        — and that is the normal case, not an error.
        """
        disabled = []
        already = []
        absent = []

        for xmlid, reason in THIRD_PARTY_CRONS:
            cron = self.env.ref(xmlid, raise_if_not_found=False)
            if not cron:
                absent.append(xmlid)
                continue
            # env.ref browses by id and confirms with exists(), neither of
            # which filters on `active` — so an already-deactivated cron comes
            # back as a normal record. Truthiness therefore says nothing about
            # the switch; read the field.
            cron = cron.sudo()
            if not cron.active:
                already.append(xmlid)
                continue
            cron.write({"active": False})
            disabled.append(xmlid)
            _logger.info(
                "myservice_nrs_base: deactivated scheduled action %s (%s) — %s",
                xmlid, cron.cron_name, reason)

        if already:
            _logger.info(
                "myservice_nrs_base: already inactive, left alone: %s",
                ", ".join(already))
        if absent:
            _logger.info(
                "myservice_nrs_base: not present on this database (module not "
                "installed), nothing to do: %s", ", ".join(absent))

        return len(disabled)
