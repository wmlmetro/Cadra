"""Handoff 60 §1.1: Vendra may see the receipt candidates it handed over.

With the receipt gates on, a receipt Vendra sends (INT-03) becomes a
CANDIDATE, and Vendra asks Cadra where each unit is with
`GET /api/v1/assets?register_state=any`, which needs `candidates:read`.
Vendra's credential held `assets:read assets:write` only, so it saw a unit
once registered and never a rejection (Vendra report 55).

Adds `candidates:read` to every existing Vendra client — the one
`scripts/bootstrap.py` provisions, found by its name `Vendra (INT-03)` or its
default client id `vendra`, archived ones included — and to nothing else.
Read only: `candidates:read` maps to Asset User in `SCOPE_GROUPS`, which
`assets:read` already grants, so the client's user gains no group. Through
the ORM, so the client's user is re-provisioned to `groups_for_scopes` as on
any scope change (CLAUDE.md rule 7) — which, on a tenant whose Vendra user
still holds the pre-handoff-47 Asset Manager group for `assets:write`, moves
it to Asset Officer, what `assets:write` grants today. Existing scopes are
kept (`nrs19`'s `locations:read` included); only the one scope is added.
Vendra's refresh family keeps the scopes it was issued with, so Vendra
calls `/auth/token` again to hold it.

The PR merge is the owner's authorisation of this grant (handoff 60 §1.1);
it is not granted by hand anywhere. Prints one line per tenant.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

SCOPE = 'candidates:read'


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Client = env['myservice.api.client'].with_context(active_test=False)
    # `=ilike` on the id, as 19.0.3.3.0 does: one tenant was once
    # provisioned as `Vendra`.
    vendra = Client.search(['|', ('name', '=', 'Vendra (INT-03)'),
                            ('client_id', '=ilike', 'vendra')])
    granted = 0
    for client in vendra:
        scopes = (client.scopes or '').split()
        if SCOPE in scopes:
            continue
        client.write({'scopes': ' '.join(scopes + [SCOPE])})
        granted += 1
    _logger.warning(
        "handoff 60: Vendra clients on %s — %d of %d given %s "
        "(%d of %d API clients are Vendra's)",
        cr.dbname, granted, len(vendra), SCOPE, len(vendra),
        Client.search_count([]))
