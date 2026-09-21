"""Provenance for an append-only asset record written under an API credential.

**ONE derivation, on the mixin, for all three records** — `nrs.asset.custody`,
`nrs.asset.movement` and `nrs.asset.event` (handoff 31).

Until then there were three files here, one per model, that were supposed to
be the same rule and were not the same code: custody's went through a
forwarder method (`_is_test_credential_user`) and preserved
`tracking_backfill` with one spelling of the test; movement's inlined the
lookup and preserved it with another; the event record's had no such
exception at all. Each was correct. That is how three answers to one
question start, and the lower module had already shown where it ends: custody
carried a claimable `source` for twelve days after movement, copied from it,
was written without one.

It lives in `myservice_api` and not in `myservice_asset_register`, and the
direction matters. `is_test_credential` is a column on `myservice.api.client`,
which this module owns. When the lookup lived in the lower module, that module
read a column belonging to a module it does not depend on — so Odoo's
dependency graph could not order the two, and a tenant carrying the new Python
against the older `myservice_api` schema would have raised `UndefinedColumn`
on **every** custodian write. One registry serves every database on a shared
host, which makes that a cross-tenant outage produced by a single-module
upgrade. Here, the column and the code that reads it ship together.
"""
from odoo import api, models


class NRSAssetAppendOnlyMixin(models.AbstractModel):
    _inherit = 'nrs.asset.append.only.mixin'

    @api.model
    def _resolve_source(self, declared, user):
        """Relabel a row written under a test credential as `test`.

        The API test suite exercises the RECORDERS — it changes a real
        asset's custodian, moves it, verifies it, condemns it, marks it
        missing — because a test that does not exercise a recorder proves
        nothing about whether anything is recorded at all. The records are
        append-only, so those rows are PERMANENT in whichever tenant the
        suite ran against. That is accepted. What is not accepted is a reader
        being unable to tell them from history.

        Decided from the ACTING USER and never from anything the caller
        sends. A request header or body field saying "this one is a test"
        would let anybody disguise a real change as an artefact, in the
        models whose whole value is that their contents were not invented.

        It OVERRIDES the declared source rather than sitting beside it. The
        reader's first question about a row is whether it happened at all,
        and `api_transfer` does not answer that. The `reason` still carries
        whatever the caller wrote.

        A RECONSTRUCTION stays a reconstruction (`_never_relabelled`): that
        is the more important thing to say about such a row, whoever was
        acting when it was written.
        """
        source = super()._resolve_source(declared, user)
        if source in self._never_relabelled or not user:
            return source
        Client = self.env.get('myservice.api.client')
        if Client is not None and Client._is_test_credential_user(user.id):
            return 'test'
        return source
