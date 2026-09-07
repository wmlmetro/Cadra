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
    system_group = env.ref("base.group_system")
    Client = env["myservice.api.client"].sudo()
    Token = env["myservice.api.refresh_token"].sudo()

    # `active_test=False`: an archived client must not be skipped and then
    # start minting the wrong uid the day somebody reactivates it.
    clients = Client.with_context(active_test=False).search(
        [("user_id", "=", admin.id)])
    if not clients:
        _logger.info("myservice_api: no API client is still running as admin")
        return

    groups_field = ("group_ids" if "group_ids" in env["res.users"]._fields
                    else "groups_id")

    for client in clients:
        user = client._provision_client_user(
            client.client_id, client.name, client.scopes)
        # A client holding the `admin` wildcard keeps the access it already
        # had — the few controller reads that do not sudo() would otherwise
        # start failing on a client whose token still says `admin`. This
        # grants nothing new; it stops the change from being a silent
        # narrowing dressed up as an audit fix.
        # Token match, not substring: `scopes` is a space-separated list and
        # `"*" in "assets:read"` is the kind of check that quietly grants a
        # wildcard to something that merely contains the character.
        scopes = (client.scopes or "").split()
        if "admin" in scopes or "*" in scopes:
            user.write({groups_field: [(4, system_group.id)]})
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
