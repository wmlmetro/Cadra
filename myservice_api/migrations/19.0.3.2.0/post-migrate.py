"""Give every API client its own Odoo user instead of Administrator.

Both provisioning sites in `scripts/bootstrap.py` created clients with
`user_id = base.user_admin`, so every record the API has ever written carries
`create_uid = 2` and every tag affix carries `affixed_by = 2`. The scope
separation those clients exist to enforce held perfectly — Vendra is refused
`tagging:write` and cannot certify an asset it created — but the answer that
separation exists to produce, *who confirmed this label*, is "Administrator"
for the Tag-Issuing Unit and for Vendra alike. A control whose result cannot
name the actor has proved something about the credential and nothing about
the act.

Two things this deliberately does NOT do:

* **Historic rows are not rewritten.** There is no evidence in the database
  saying which uid-2 affix came from the tagging client and which from a
  console session, and inventing one would be fabricating an audit trail —
  strictly worse than an honestly useless value. The handoff report carries
  the count instead.

* **Refresh-token families are not revoked.** `verify_and_rotate` now resolves
  a client family's user from the client record rather than replaying the one
  stored at mint time (api_refresh_token.py), so families in flight pick the
  new user up on their next rotation without logging any integration out. The
  stored `user_id` is repointed here as well so that a row read directly —
  `/auth/me`, the token list view — agrees with the token it describes.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    admin = env.ref("base.user_admin")
    Client = env["myservice.api.client"].sudo()
    Token = env["myservice.api.refresh_token"].sudo()

    # `active_test=False`: an archived client must not be skipped and then
    # start minting the wrong uid the day somebody reactivates it.
    clients = Client.with_context(active_test=False).search(
        [("user_id", "=", admin.id)])
    if not clients:
        _logger.info("myservice_api: no API client is still running as admin")
        return


    for client in clients:
        user = client._provision_client_user(
            client.client_id, client.name, client.scopes)
        # NO `base.group_system`, whatever the scopes (handoff 44). This
        # migration used to grant it to a client holding `admin` or `*`, so
        # that "the few controller reads that do not sudo()" kept working —
        # they had all sudo()'d since handoff 09, and handoff 44 drove an
        # `admin` credential without the group through the whole HTTP suite
        # and every integration leg with nothing failing (report 44 §A). It
        # is also the grant that made `test_client` a system administrator
        # on exactly the three local tenants whose credential held `admin`
        # on 2026-09-07. A database upgraded across this version later — a
        # 15-era client cut over to 19 — would otherwise mint root again.
        # What a credential is entitled to: `docs/DECISIONS.md` 2026-10-02.
        client.user_id = user

        families = Token.search([
            ("client_id", "=", client.id),
            ("user_id", "=", admin.id),
            ("revoked", "=", False),
        ])
        families.write({"user_id": user.id})
        _logger.info(
            "myservice_api: client %s now runs as %s (uid %s -> %s); "
            "repointed %d live refresh token family/families",
            client.client_id, user.login, admin.id, user.id, len(families))
