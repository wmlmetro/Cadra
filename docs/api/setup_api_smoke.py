"""
Dev-only: ensure a smoke-test API client exists on ONE tenant database.

Run it as:
    docker compose -f docker-compose.yml -f docker-compose.19.yml run --rm -T odoo \\
      bash -c "odoo shell -c /etc/odoo/odoo.conf -d <db> --no-http <<< \\
        \"exec(open('/mnt/extra-addons/docs/api/setup_api_smoke.py').read())\""

── Why this script is now boring by default ─────────────────────────────

It used to regenerate the tenant's JWT secret, delete the existing client and
mint a new secret on EVERY run. That is per-database state, and one Odoo
process serves every tenant, so running it to set up tenant B silently
invalidated tenant A's credentials — including the ones the test suite was
pointed at. Nothing said so; the suite just started returning 401 and looked
like a code fault.

So: it preserves what it finds and only fills in what is missing. Ask for
rotation explicitly when you actually want it:

    CADRA_SMOKE_ROTATE=1     rotate the client secret (prints the new one)
    CADRA_SMOKE_ROTATE_JWT=1 regenerate the tenant's JWT secret — this
                             invalidates EVERY access token already issued
                             for this database, including other integrations'

The bind mount is read-only, so the credentials are printed between sentinels
rather than written. `scripts/bootstrap.sh` is the supported path and captures
them to docs/api/.creds.<db> for you.
"""
import os
import secrets

from odoo.addons.myservice_api.controllers.utils import ALL_SCOPES

_ROTATE_SECRET = os.environ.get('CADRA_SMOKE_ROTATE') == '1'
_ROTATE_JWT = os.environ.get('CADRA_SMOKE_ROTATE_JWT') == '1'

_db = env.cr.dbname
_param = env['ir.config_parameter'].sudo()

# ── JWT secret: preserve unless explicitly told otherwise ────────────
_existing_jwt = _param.get_param('myservice_api.jwt_secret')
if _existing_jwt and not _ROTATE_JWT:
    SECRET = '<UNCHANGED — existing JWT secret preserved>'
    print(f"[smoke:{_db}] JWT secret already set — preserved")
else:
    SECRET = secrets.token_urlsafe(48)
    _param.set_param('myservice_api.jwt_secret', SECRET)
    _what = ('ROTATED — every access token already issued for this database '
             'is now invalid') if _existing_jwt else 'generated'
    print(f"[smoke:{_db}] JWT secret {_what}")

# ── The client: updated in place, never deleted ──────────────────────
Client = env['myservice.api.client'].sudo()
client = Client.search([('client_id', '=', 'test_client')], limit=1)

# Derived rather than hand-listed: this literal drifted behind ALL_SCOPES
# once already, and conftest.py points developers at this script, so a
# missing scope here means their suite 403s on endpoints that pass in CI.
#
# `admin` is excluded on a client this script CREATES, because a smoke client
# does not need a wildcard over the whole API. An existing client keeps
# whatever it has — see below.
_scopes = ' '.join(sorted(ALL_SCOPES - {'admin'}))

if client:
    # Reactivated but NOT re-scoped. `scripts/bootstrap.py` provisions this
    # same client with the full set INCLUDING `admin`; this script's set
    # excludes it. Re-syncing here means whichever script ran last silently
    # decides whether `test_client` holds `admin` — so running bootstrap and
    # then this would quietly strip a scope the tenant was relying on, with
    # nothing to show for it but a 403 later.
    client.write({'active': True})
    print(f"[smoke:{_db}] client 'test_client' found — preserved as-is "
          f"(scopes: {client.scopes!r})")
else:
    client = Client.create({
        'name': 'Smoke Test',
        'client_id': 'test_client',
        'user_id': env.ref('base.user_admin').id,
        'scopes': _scopes,
        'token_ttl_seconds': 3600,
    })
    print(f"[smoke:{_db}] client 'test_client' created")

if _ROTATE_SECRET or not client.client_secret_hash:
    _had = bool(client.client_secret_hash)
    raw = client.rotate_secret()
    print(f"[smoke:{_db}] client secret "
          + ("rotated" if _had else "generated"))
else:
    raw = '<UNCHANGED — existing client secret preserved>'

env.cr.commit()

print("=== SMOKE_CREDS_BEGIN ===")
print(f"DB={_db}")
print(f"JWT_SECRET={SECRET}")
print("CLIENT_ID=test_client")
print(f"CLIENT_SECRET={raw}")
print("=== SMOKE_CREDS_END ===")
print(f"[smoke:{_db}] save these as docs/api/.creds.{_db} — the test suite "
      f"resolves the file from CADRA_API_BASE's hostname")
