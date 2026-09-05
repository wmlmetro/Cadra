"""
Dev-only: set the JWT secret and create a smoke-test API client.

Run via `seed_dev.sh` style:
    docker compose -f docker-compose.dev.yml run --rm -T odoo bash -c \\
      "odoo shell -c /etc/odoo/odoo.conf -d odoo --no-http <<< \\
       \\"exec(open('/mnt/extra-addons/docs/api/setup_api_smoke.py').read())\\""

Writes the credentials to /mnt/extra-addons/docs/api/.creds (gitignored)
so we can read them from the host.
"""
import secrets

from odoo.addons.myservice_api.controllers.utils import ALL_SCOPES

SECRET = secrets.token_urlsafe(48)
env['ir.config_parameter'].sudo().set_param('myservice_api.jwt_secret', SECRET)

Client = env['myservice.api.client'].sudo()
existing = Client.search([('client_id', '=', 'test_client')], limit=1)
if existing:
    existing.unlink()

admin = env.ref('base.user_admin')
client = Client.create({
    'name': 'Smoke Test',
    'client_id': 'test_client',
    'user_id': admin.id,
    # Derived rather than hand-listed: this literal drifted behind ALL_SCOPES
    # once already, and conftest.py points developers at this script, so a
    # missing scope here means their suite 403s on endpoints that pass in CI.
    'scopes': ' '.join(sorted(ALL_SCOPES - {'admin'})),
    'token_ttl_seconds': 3600,
})
raw = client.rotate_secret()
env.cr.commit()

# Bind mount is :ro so we can't write a creds file from inside. Print
# the credentials so the host can capture them from the shell stdout.
print("=== SMOKE_CREDS_BEGIN ===")
print(f"JWT_SECRET={SECRET}")
print(f"CLIENT_ID=test_client")
print(f"CLIENT_SECRET={raw}")
print("=== SMOKE_CREDS_END ===")
