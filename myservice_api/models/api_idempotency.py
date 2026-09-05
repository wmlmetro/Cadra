from odoo import api, fields, models, release, tools

# Odoo 19 dropped `_sql_constraints` — model_classes.py logs "Model attribute
# '_sql_constraints' is no longer supported, please define models.Constraint on
# the model" and creates nothing. Declared the old way, the uniqueness this
# cache depends on silently stopped existing. Both spellings are kept so the
# constraint is real on 19 and on the 15 stack that is still production.
_ODOO_MAJOR = release.version_info[0]


class MyserviceApiIdempotency(models.Model):
    """Cache of (X-Idempotency-Key, endpoint) -> response body.

    Populated automatically by the @cadra_endpoint(idempotent=True) decorator
    on successful write responses. Lookups on the same key + endpoint within
    the TTL return the original response without re-executing the handler.
    """
    _name = "myservice.api.idempotency"
    _description = "Cadra API Idempotency Cache"
    _order = "create_date desc"

    key = fields.Char(required=True, index=True)
    endpoint = fields.Char(required=True, index=True,
                           help="Request path (e.g. /api/v1/assets) — keys "
                                "are scoped per-endpoint so the same key on "
                                "different endpoints doesn't collide.")
    response_body = fields.Text(required=True)
    expires_at = fields.Datetime(required=True, index=True)

    if _ODOO_MAJOR >= 19:
        _key_endpoint_uniq = models.Constraint(
            "UNIQUE (key, endpoint)",
            "Idempotency key must be unique per endpoint.",
        )
    else:
        _sql_constraints = [
            ("key_endpoint_uniq",
             "UNIQUE (key, endpoint)",
             "Idempotency key must be unique per endpoint."),
        ]

    def _auto_init(self):
        """Clear duplicate (key, endpoint) rows before the constraint applies.

        Any database that ran while the constraint was absent may hold
        duplicates, and Odoo answers a failed constraint by logging a warning
        and moving on — leaving the table unprotected exactly as before. This
        is a 24h response cache, so dropping the loser of an old race costs
        nothing: the winner's row is the one replays were already resolving to
        under `search(..., limit=1)`.
        """
        if tools.sql.table_exists(self.env.cr, self._table):
            self.env.cr.execute(
                """
                DELETE FROM {table} a
                      USING {table} b
                      WHERE a.id > b.id
                        AND a.key = b.key
                        AND a.endpoint = b.endpoint
                """.format(table=self._table)
            )
        return super()._auto_init()

    @api.autovacuum
    def _gc_expired(self):
        """Garbage-collect expired entries on Odoo's standard vacuum cron."""
        expired = self.search([("expires_at", "<", fields.Datetime.now())])
        if expired:
            expired.unlink()
