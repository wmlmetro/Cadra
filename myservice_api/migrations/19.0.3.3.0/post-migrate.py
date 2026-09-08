"""Provision the clients that must never be capped.

The external record cap (`controllers/utils.py`) is a commercial control and
it stays. What changed is that it now keys off the client record rather than
off the `aud` claim, which only /auth/login stamps — so the rule in force
used to be "browsers are trusted, programs are not" when the rule intended
was "our own systems are trusted, third parties are not". Vendra holds a
machine credential; so will Audit. The paywall was pointed at our own
customer, and on a 2,363-asset tenant Vendra was told there were 100.

Setting `total_record_cap = -1` by hand on eight tenants is the failure mode
this programme has already paid for three times: state that lives in records
rather than code does not move when code moves. So it is a migration.

Deliberately NOT done here:
  * No client is created. A tenant with no Vendra integration must not grow
    a Vendra credential because a module was upgraded.
  * `max_page_limit` is left at 0. Uncapping the total is what INT-03 and
    INT-10 need; a bigger single page is a performance question, and the
    cursor still walks the whole set at 100 a time.
  * Nothing is capped that was not capped before. This migration only ever
    widens, and only on ids it recognises.
"""
import logging

_logger = logging.getLogger(__name__)

# The ids `scripts/bootstrap.py` provisions. Both are env-overridable there
# (CADRA_VENDRA_CLIENT_ID / CADRA_AUDIT_CLIENT_ID), so a tenant bootstrapped
# with an override keeps its cap and has to be widened by hand — logged
# below as a miss rather than passed over in silence.
#
# `audit_viewer` is the role name in Cadra_at_NRS_Specification_v0.1 §3 and
# in docs/integrations/INT-10-audit-access.md. No tenant has one yet; when
# INT-10 names it for real this list is the single edit.
UNCAPPED_CLIENT_IDS = ("vendra", "audit_viewer")


def migrate(cr, version):
    if not version:
        return

    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    Client = env["myservice.api.client"].sudo()

    # `active_test=False`: an archived Vendra client must not be skipped and
    # then start silently truncating the day somebody reactivates it.
    # `=ilike` because `=` on a Postgres varchar is case-sensitive and at
    # least one tenant was provisioned `Vendra`, not `vendra` — the same
    # mismatch that made /auth/token answer identically to a wrong secret.
    leaves = [("client_id", "=ilike", cid) for cid in UNCAPPED_CLIENT_IDS]
    domain = ["|"] * (len(leaves) - 1) + leaves
    clients = Client.with_context(active_test=False).search(domain)

    if not clients:
        _logger.info(
            "myservice_api: no client matching %s on this tenant — nothing to "
            "uncap", " / ".join(UNCAPPED_CLIENT_IDS))
        return

    for client in clients:
        if client.total_record_cap == -1:
            _logger.info(
                "myservice_api: client %s is already uncapped", client.client_id)
            continue
        client.write({"total_record_cap": -1})
        _logger.info(
            "myservice_api: client %s uncapped (total_record_cap 0 -> -1); it "
            "was seeing the first %d records of every resource",
            client.client_id, 100)

    found = {c.client_id.lower() for c in clients}
    for cid in UNCAPPED_CLIENT_IDS:
        if cid not in found:
            _logger.info(
                "myservice_api: no `%s` client on this tenant; if one exists "
                "under a bootstrap override it is still capped", cid)
