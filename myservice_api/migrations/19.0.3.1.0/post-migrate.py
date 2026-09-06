"""Narrow the wildcard scopes on refresh tokens issued by `/auth/login`.

Until 19.0.3.1.0 a session login minted `scopes = "*"`, and
`verify_and_rotate` replays the stored string verbatim on every refresh
rather than re-deriving it. So fixing `login()` alone would not have closed
the hole: every session already in flight would have gone on minting
wildcard access tokens — including `tagging:write` — for up to the full
30-day sliding window, refreshing indefinitely while the browser stayed
open.

Live rows are re-derived rather than revoked. The scopes a user's groups
justify are exactly what a fresh login would hand them, so re-deriving is
the same answer without logging the whole estate out on deploy. A user who
holds no mapped group lands on an empty string, which means no permissions.

Client-credential rows (`client_id` set) are untouched: their scopes come
from the client record and were never a wildcard by this route.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    from odoo import SUPERUSER_ID, api
    from odoo.addons.myservice_api.controllers.utils import scopes_for_user

    env = api.Environment(cr, SUPERUSER_ID, {})
    Token = env["myservice.api.refresh_token"].sudo()

    stale = Token.search([
        ("client_id", "=", False),
        ("scopes", "in", ["*", "* "]),
        ("revoked", "=", False),
    ])
    if not stale:
        _logger.info("myservice_api: no wildcard session refresh tokens to narrow")
        return

    # One `has_group` resolution per distinct user, not per token — a busy
    # tenant carries many live families per person.
    by_user = {}
    for token in stale:
        by_user.setdefault(token.user_id, Token.browse())
        by_user[token.user_id] |= token

    for user, tokens in by_user.items():
        scopes = " ".join(scopes_for_user(user))
        tokens.write({"scopes": scopes})
        _logger.info(
            "myservice_api: narrowed %d refresh token(s) for %s from '*' to %r",
            len(tokens), user.login, scopes,
        )
