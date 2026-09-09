"""Provenance for a chain-of-custody link written under an API credential.

This lives in `myservice_api` and not in `myservice_asset_register`, and the
direction matters. `is_test_credential` is a column on
`myservice.api.client`, which this module owns. When the lookup lived in the
lower module, that module read a column belonging to a module it does not
depend on — so Odoo's dependency graph could not order the two, and a tenant
carrying the new Python against the older `myservice_api` schema would have
raised `UndefinedColumn` on **every** custodian write. One registry serves
every database on a shared host, which makes that a cross-tenant outage
produced by a single-module upgrade.

Here, the column and the code that reads it ship together and move together.
"""
from odoo import api, models, tools


class NRSAssetCustody(models.Model):
    _inherit = 'nrs.asset.custody'

    @api.model
    def _resolve_source(self, declared, user):
        """Relabel a link written under a test credential as `test`.

        The API test suite exercises the RECORDER — it moves a real asset's
        custodian over HTTP — because a test that does not exercise the
        recorder proves nothing about whether the chain is written at all.
        The recorder is append-only, so those links are PERMANENT in
        whichever tenant the suite ran against. That is accepted. What is not
        accepted is a reader of the chain being unable to tell them from
        history.

        Decided from the ACTING USER and never from anything the caller
        sends. A request header or body field saying "this one is a test"
        would let anybody disguise a real change of custodian as an artefact,
        in the one model whose whole value is that its contents were not
        invented.

        It OVERRIDES the declared source rather than sitting beside it. The
        reader's first question about a link is whether it happened at all,
        and `api_transfer` does not answer that. The `reason` still carries
        whatever the caller wrote.
        """
        source = super()._resolve_source(declared, user)
        if source != 'tracking_backfill' and user \
                and self._is_test_credential_user(user.id):
            return 'test'
        return source

    @api.model
    @tools.ormcache('user_id')
    def _is_test_credential_user(self, user_id):
        """Is this the Odoo user behind a credential flagged as a test one?

        Cached on the user id because `_record` is called PER RECORD from
        `nrs.asset.create` and `nrs.asset.write`, so an uncached lookup is
        one `search_count` per row — ten thousand of them on a bulk import
        with custodians, and one per asset when an employee leaves. The
        answer depends only on the user and on a field an administrator
        changes about once, so the cache is invalidated by writes to
        `myservice.api.client` rather than by time.

        `active_test=False`: an archived credential's artefacts are still
        artefacts.
        """
        Client = self.env.get('myservice.api.client')
        if Client is None or not user_id:
            return False
        return bool(Client.sudo().with_context(active_test=False).search_count([
            ('user_id', '=', user_id),
            ('is_test_credential', '=', True),
        ]))
