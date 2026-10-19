"""Handoff 65 §0a.1: the AI provider key leaves the database.

Handoff 64 kept the key for *Identify from photo* on the Turnstile secret's
road — an `ir_config_parameter` row, `myservice_api.ai_api_key`, mirrored by
bootstrap from `CADRA_AI_API_KEY` or written by `scripts/set_ai_key.sh`.
Report 64 (deviation 2) asked whether that was what "never on the
configuration record" meant; the Architect ruled that it was not: a row is
readable by any back-office system administrator and it lands in every
database backup. The server now reads `CADRA_AI_API_KEY` from its own process
environment (`ai_provider.provider_key`) and nothing reads or writes the row.

This deletes the row on every tenant the upgrade reaches, archived or empty
alike, and prints one line per tenant saying WHETHER one existed — never its
value, never its length. Raw SQL rather than `set_param(key, False)`: on 19
`set_param` with an empty value stores an empty string instead of deleting
(CLAUDE.md, the email-relay gotcha), and a leftover row is exactly what this
migration exists to remove.

A tenant that had a key placed does not lose identification by this alone:
the key it needs is the same one, now set on the server
(`CADRA_AI_API_KEY` in the local `.env`, or the `cadra-odoo` secret on the
cluster). Until it is, the route answers `503 server_misconfigured` in words
and the Settings screen says no key is present.
"""
import logging

_logger = logging.getLogger(__name__)

PARAM = 'myservice_api.ai_api_key'


def migrate(cr, version):
    cr.execute("DELETE FROM ir_config_parameter WHERE key = %s RETURNING id",
               (PARAM,))
    existed = bool(cr.fetchall())
    _logger.warning(
        "handoff 65: %s on %s — a stored AI provider key existed: %s "
        "(deleted; the server reads CADRA_AI_API_KEY from its environment)",
        PARAM, cr.dbname, existed)
