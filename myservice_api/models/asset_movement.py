"""Provenance for a movement record written under an API credential.

The same module, the same direction and the same reason as
`asset_custody.py` next door: `is_test_credential` is a column on
`myservice.api.client`, which this module owns, so the code that reads it
ships here and not in `myservice_asset_register`.
"""
from odoo import api, models


class NRSAssetMovement(models.Model):
    _inherit = 'nrs.asset.movement'

    @api.model
    def _resolve_source(self, declared, user):
        """Relabel a movement written under a test credential as `test`.

        The API test suite moves real assets, because a test that does not
        exercise the recorder proves nothing about whether a move is recorded
        at all — and the record is append-only, so those rows are PERMANENT in
        whichever tenant the suite ran against. That is accepted. A reader
        being unable to tell them from history is not.

        Decided from the ACTING USER, never from anything the caller sends,
        and it OVERRIDES the declared source rather than sitting beside it —
        both for the reasons `nrs.asset.custody._resolve_source` gives. One
        derivation, read from the model that owns the column: a second copy
        of a safety rule is how the two answers start to disagree.
        """
        source = super()._resolve_source(declared, user)
        if source == 'tracking_backfill' or not user:
            return source
        Client = self.env.get('myservice.api.client')
        if Client is not None and Client._is_test_credential_user(user.id):
            return 'test'
        return source
