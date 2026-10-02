"""The reminder cron, on tenants already at 19.0.3.17.0.

`align_signup_rows` grew its third statement — switching off Odoo's
*unregistered users* reminder cron (report 43 §F.8) — after the 17.0
migration had already run on all 8 local tenants, and a migration does
not run twice. Idempotent; a tenant coming from 16 or earlier runs both
and the second changes nothing.
"""
from odoo.addons.myservice_api.models.invitation import align_signup_rows


def migrate(cr, version):
    if not version:
        return
    align_signup_rows(cr)
