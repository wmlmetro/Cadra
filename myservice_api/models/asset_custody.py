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
from odoo import api, models


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
    def _is_test_credential_user(self, user_id):
        """Delegate to the model that owns the column.

        The implementation moved to `myservice.api.client` in handoff 26,
        which gave the derivation a SECOND consumer — `cadra.test.fixture.
        mixin`, which stamps the same fact onto every other model the API can
        create. Two copies of a safety derivation is how the two answers
        start disagreeing, and this one is load-bearing for a chain that
        refuses correction by design.

        The name stays here because `scripts/mark_test_fixtures.py`, the
        docs and three reports cite it, and because the caching, the
        `active_test=False` and the invalidation all live on the other side
        unchanged. This is a forwarder, not a second opinion.
        """
        Client = self.env.get('myservice.api.client')
        if Client is None:
            return False
        return Client._is_test_credential_user(user_id)
