"""Provenance for an append-only asset record written under an API credential.

The same module, the same direction and the same reason as `asset_custody.py`
and `asset_movement.py` next door: `is_test_credential` is a column on
`myservice.api.client`, which this module owns, so the code that reads it
ships here and not in `myservice_asset_register`.

**On the MIXIN, not on `nrs.asset.event`.** Custody and movement each carry
their own copy of this override, and the two copies are not the same code —
one goes through a forwarder method and the other inlines the lookup. That is
harmless today and it is how two answers start to disagree. Extending the
abstract model means every model that adopts the guard gets this derivation
with it, once, and a fourth append-only record cannot be written without it.
"""
from odoo import api, models


class NRSAssetAppendOnlyMixin(models.AbstractModel):
    _inherit = 'nrs.asset.append.only.mixin'

    @api.model
    def _resolve_source(self, declared, user):
        """Relabel a row written under a test credential as `test`.

        The API test suite verifies, condemns and marks missing real assets,
        because a test that does not exercise the recorder proves nothing
        about whether anything is recorded — and the record is append-only,
        so those rows are PERMANENT in whichever tenant the suite ran
        against. That is accepted. A reader being unable to tell them from
        history is not.

        Decided from the ACTING USER, never from anything the caller sends,
        and it OVERRIDES the declared source rather than sitting beside it —
        both for the reasons `nrs.asset.custody._resolve_source` gives.
        """
        source = super()._resolve_source(declared, user)
        if not user:
            return source
        Client = self.env.get('myservice.api.client')
        if Client is not None and Client._is_test_credential_user(user.id):
            return 'test'
        return source
