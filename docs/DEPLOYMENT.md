# Cadra Deployment Runbook

Two deployment profiles, same codebase. Both use Docker Compose; both run
through `scripts/bootstrap.sh`. The only difference is which compose
override is active.

| Profile | Compose files | Reverse proxy | TLS | Use for |
|---|---|---|---|---|
| `dev` | `docker-compose.yml` + `docker-compose.dev.yml` | nginx (HTTP only) | None | Local development on any docker host |
| `prod` | `docker-compose.yml` + `docker-compose.prod.yml` | Caddy (auto Let's Encrypt) | Required | A single VPS with a public domain |

## Prerequisites

- Docker 20.10+ with Compose v2 (`docker compose`, not `docker-compose`)
- 4+ GB RAM, 10+ GB disk
- **For prod only:** a public DNS A record pointing at the host, ports 80
  and 443 reachable from the internet (Let's Encrypt's HTTP-01 challenge
  needs port 80 inbound)

---

## First-time setup (dev)

```bash
# Clone the repo
git clone https://github.com/<your-org>/myservicenrs.git
cd myservicenrs

# Copy env defaults (the dev defaults are safe — admin/admin/odoo locally)
cp .env.example .env

# Bring up + install + seed + create API client + capture credentials.
# Takes 3–5 minutes the first time (image build + module install + seeds).
scripts/bootstrap.sh
```

When it finishes you'll see a summary banner with URLs and a path to the
captured credentials at `docs/api/.creds.<db>`.

**Sanity check the install**:

```bash
# Quick alive check
curl -sI http://localhost:8069/web/login

# Full pytest suite (one-time venv setup, then runs in seconds)
python3 -m venv tests/.venv
source tests/.venv/bin/activate
pip install -r tests/requirements.txt
pytest tests/ -v
```

You should see `67 passed, 3 xfailed` — the xfailed tests are documented
upstream bugs in delegated controllers, not API regressions. See
[tests/README.md](../tests/README.md) for what each test covers.

---

## First-time setup (prod)

```bash
# On the target VPS:
git clone https://github.com/<your-org>/myservicenrs.git
cd myservicenrs

# Create your .env from the example, then EDIT every secret
cp .env.example .env
nano .env   # set CADRA_DOMAIN, CADRA_ACME_EMAIL, and ROTATE every secret

# Generate strong secrets for the three values you must set:
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)"
echo "ODOO_MASTER_PASSWORD=$(openssl rand -base64 32)"
echo "CADRA_JWT_SECRET=$(openssl rand -base64 48)"

# Bring up — uses docker-compose.prod.yml (Caddy + TLS + restart policies)
CADRA_PROFILE=prod scripts/bootstrap.sh
```

On first start, Caddy will obtain a Let's Encrypt cert for `$CADRA_DOMAIN`
(takes 30–60 s the first time, cached in the `cadra_caddy_data` volume
thereafter). Watch the proxy logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f proxy
```

When the banner says `serving HTTPS on <CADRA_DOMAIN>`, you're live.

---

## What the bootstrap actually does

`scripts/bootstrap.sh` is idempotent — safe to re-run any time:

1. Verifies `.env` exists (copies from `.env.example` if missing in dev).
2. Brings the stack up: `docker compose up -d`.
3. Waits for the Postgres healthcheck.
4. Detects whether the Odoo DB is initialised:
   - **Fresh DB**: runs `odoo -i <modules>` to install the canonical
     in-house module set + `web_responsive`.
   - **Existing DB**: skips install — assumes you handled module updates
     out-of-band (or run `scripts/upgrade.sh` if/when we add one).
5. Runs `scripts/bootstrap.py` inside an `odoo shell`:
   - Sets `ir.config_parameter myservice_api.jwt_secret` from
     `CADRA_JWT_SECRET` env (or generates one if blank).
   - Adds the admin user to `group_asset_manager` and
     `group_security_admin` (required for the API to read every model).
   - Creates (or rotates) the smoke-test API client.
   - Runs the seed scripts per `CADRA_SEED_PROFILE` (`core` by default:
     ITSM structure, location skeleton, 415 FIRS offices).
6. Captures the bootstrap output (sentinel-wrapped) and writes
   credentials to `docs/api/.creds.<db>`.
7. Waits for Odoo's healthcheck to go green post-restart.

Re-running the script after a code change is the supported way to refresh
the bootstrap state. If you want to also re-run the seed scripts and pick
up any new entries, that just works — the seeds use get-or-create
internally.

---

## Day-2 operations

### View logs

```bash
# All services
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f

# Just Odoo
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f odoo
```

### Restart Odoo (e.g. after editing a Python file)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml restart odoo
```

### Update modules (after pulling new code)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml stop odoo
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm odoo \
    odoo -c /etc/odoo/odoo.conf -d $POSTGRES_DB -u myservice_api --stop-after-init --no-http
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d odoo
```

Replace `myservice_api` with the comma-separated list of modules that changed.

### Back up the DB

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec db \
    pg_dump -Fc -U $POSTGRES_USER $POSTGRES_DB > backup-$(date +%Y%m%d-%H%M%S).dump
```

For prod, schedule this via cron + rotate to S3 / NAS:

```bash
0 3 * * * /opt/cadra/scripts/backup.sh   # (write this script per your storage)
```

### Restore the DB

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml stop odoo
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec db \
    psql -U $POSTGRES_USER -c "DROP DATABASE $POSTGRES_DB; CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER;"
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T db \
    pg_restore -U $POSTGRES_USER -d $POSTGRES_DB < backup-XYZ.dump
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d odoo
```

### Rotate API client credentials

```bash
# Delete the existing client and re-bootstrap → fresh credentials
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm -T odoo bash -c \
  "odoo shell -c /etc/odoo/odoo.conf -d $POSTGRES_DB --no-http <<< \"
env['myservice.api.client'].sudo().search([('client_id','=','test_client')]).unlink()
env.cr.commit()\""

scripts/bootstrap.sh    # creates a fresh client, new secret in docs/api/.creds.<db>
```

### Stop the stack

```bash
# Keep volumes — restart is fast
docker compose -f docker-compose.yml -f docker-compose.dev.yml down

# Also delete data (destructive!)
docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v
```

---

## Rollback

Strategy: pin to a known-good image tag, or to a known-good commit.

```bash
# Roll the code back
git checkout <known-good-sha>

# Restart Odoo (no DB changes — code-only rollback)
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart odoo
```

For DB rollback after a bad migration: restore from the pre-deploy backup
(see "Restore the DB" above). Always take a backup before pulling new
code in prod.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `502 Bad Gateway` from Caddy | Odoo not ready yet | Wait 30–60 s after startup; check `docker compose logs odoo` |
| `Could not connect to Cadra API` from pytest | Stack isn't up | `docker compose -f ... -f ... up -d` |
| `ConnectionRefusedError` on postgres | Healthcheck failing | `docker compose logs db` — usually a permissions issue on the volume |
| `module myservice_X not installed` errors at API call time | Bootstrap didn't run the install step | `scripts/bootstrap.sh` again (idempotent) |
| `401 unauthorized` on every endpoint | JWT secret rotated; old tokens expired | Mint a fresh token via POST /api/v1/auth/token |
| `403 forbidden` with `Missing required scope(s)` | API client's scopes don't cover the endpoint | Re-run `scripts/bootstrap.sh` (it re-syncs scopes to the canonical set) |
| Caddy stuck issuing cert | DNS not pointing at host, or port 80 blocked | Check `dig $CADRA_DOMAIN` resolves to the host; check firewall |
| `internal_error` from a barcode/home endpoint | Pre-existing upstream bug in a delegated module | See [tests/README.md](../tests/README.md) "xfailed" — not a deployment regression |

---

## File map

```
.
├── .env.example               # Documented config vars (copy to .env)
├── docker-compose.yml         # Base services (db, odoo) — always loaded
├── docker-compose.dev.yml     # Dev overrides: nginx, exposed ports, list_db=True
├── docker-compose.prod.yml    # Prod overrides: Caddy + TLS, restart policies
├── Dockerfile.odoo.dev        # Odoo image (FROM odoo:15.0 + html2text)
├── config/
│   ├── nginx.dev.conf         # Dev nginx vhost (HTTP only)
│   ├── Caddyfile              # Prod Caddy config (auto Let's Encrypt)
│   ├── odoo.dev.conf          # Dev Odoo config (list_db=True etc.)
│   └── odoo.prod.conf         # Prod Odoo config (list_db=False, hardened)
├── scripts/
│   ├── bootstrap.sh           # Host-side orchestrator (the one command)
│   └── bootstrap.py           # In-container Python (runs inside odoo shell)
├── tests/                     # pytest API test suite (see tests/README.md)
└── docs/
    ├── DEPLOYMENT.md          # This file
    └── api/
        ├── .creds.<db>        # per-tenant API credentials from bootstrap (gitignored)
        ├── smoke_test.py      # Quick alive-check (stdlib only)
        └── test-responses/    # pytest captured responses (gitignored)
```
