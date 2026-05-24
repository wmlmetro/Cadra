from odoo import api, fields, models


class MyserviceApiIdempotency(models.Model):
    """Cache of (Idempotency-Key, endpoint) -> response body.

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

    _sql_constraints = [
        ("key_endpoint_uniq",
         "UNIQUE (key, endpoint)",
         "Idempotency key must be unique per endpoint."),
    ]

    @api.autovacuum
    def _gc_expired(self):
        """Garbage-collect expired entries on Odoo's standard vacuum cron."""
        expired = self.search([("expires_at", "<", fields.Datetime.now())])
        if expired:
            expired.unlink()
