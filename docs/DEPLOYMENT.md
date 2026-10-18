# Cadra Deployment Runbook

**The shape this document describes: one client, one server, one database,
one domain.** That is what a Cadra customer gets. The `prod` profile below is
the whole of it — a single VPS running Docker Compose behind Caddy.

The shared multi-tenant estate on Kubernetes, where `nrs19`, `gtb19`,
`jaizbankplc` and the rest live side by side on one Odoo registry, is the
**development and demonstration** arrangement. It is not the production
topology and never was. Nothing in this document deploys it; see
["What this document does not cover"](#what-this-document-does-not-cover).

**The runtime is Odoo 19.** Both profiles below resolve to `cadra-odoo:19.0-dev`,
built `FROM odoo:19.0`, and that is asserted rather than promised —
[`tests/test_deployment_profile.py`](../tests/test_deployment_profile.py)
fails if any compose profile resolves to another major, and the
`prod-compose-lint` job in CI checks the same fact against the real
`docker compose config`. Until handoff 20 this document named no version at
all while the `prod` profile quietly built Odoo 15.

| Profile | Compose files | Reverse proxy | TLS | Use for |
|---|---|---|---|---|
| `dev` | `docker-compose.yml` + `docker-compose.19.yml` | nginx (HTTP only) | None | Local development and CI |
| `prod` | `docker-compose.yml` + `docker-compose.prod.yml` | Caddy (auto Let's Encrypt) | Required | A client's own server |

`CADRA_PROFILE=dev19` is an accepted alias for `dev`; it is the spelling CI
uses. There used to be two dev profiles, one on each Odoo major — which is
how `prod` came to inherit 15. There is one now.

## Prerequisites

- Docker 20.10+ with Compose v2 (`docker compose`, not `docker-compose`)
- **8+ GB RAM** and 10+ GB disk. 4 GB is not enough on a developer machine:
  see [ENVIRONMENT-FACTS.md](ENVIRONMENT-FACTS.md) on Postgres crash-restarts
  under concurrent registry loads.
- **For prod only:** a public DNS A record pointing at the host, ports 80
  and 443 reachable from the internet (Let's Encrypt's HTTP-01 challenge
  needs port 80 inbound)

---

## First-time setup (dev)

```bash
git clone git@github.com:wmlmetro/Cadra.git
cd Cadra

# Copy env defaults. The dev defaults are deliberately weak and the prod
# bring-up refuses them — see "Credentials" below.
cp .env.example .env

# Bring up + install + seed + create API clients + capture credentials.
# Takes 3–5 minutes the first time (image build + module install + seeds).
scripts/bootstrap.sh
```

When it finishes you get a summary banner with URLs and a path to the
captured credentials at `docs/api/.creds.<db>`.

**Which database you reach depends on `ODOO_DBFILTER`, and nothing else.**
The committed default is `^odoo$`: one database, named by `POSTGRES_DB`,
served on every host — which is what CI wants. To run the local tenants
side by side instead, export `^%d$` before bringing the stack up, and each
host's first label selects the database of the same name:

```bash
ODOO_DBFILTER='^%d$' docker compose -f docker-compose.yml -f docker-compose.19.yml up -d
# then http://jaizbankplc.localhost:8069 , http://nrs19.localhost:8069 , …
```

With `^%d$` set, plain `http://localhost:8069` answers *"No database is
selected"*. That is correct behaviour, not a fault.

**`odoo` — the database `.env.example` names — is not one you can test
against on a developer machine that has been through the migration.** It is
an Odoo 15 leftover and a 19 worker refuses it with `operator does not exist:
character varying >> unknown` followed by `Failed to load registry`, an error
that names nothing relevant. CI is unaffected because it creates the database
fresh. Locally, name a real tenant.

**Sanity check the install**:

```bash
curl -sI http://localhost:8069/web/login          # or <db>.localhost on ^%d$

python3 -m venv tests/.venv                        # Python 3.13, one time
tests/.venv/bin/pip install -r tests/requirements.txt

CADRA_API_BASE=http://jaizbankplc.localhost:8069 \
  tests/.venv/bin/python -m pytest tests/ -q
```

`CADRA_API_BASE` is not optional on a `^%d$` stack: Cadra routes by `Host`,
so a bare `localhost` fails at the first call with a 401 that looks like a
code fault. The suite needs a tenant with a `docs/api/.creds.<db>` file.

Measured on `jaizbankplc`, 2026-09-10: **449 passed, 0 failed, 28 skipped**.

**The skip count is a function of the tenant, not a constant**, so check the
reasons (`pytest -rs`) rather than the number: 24 admin-scoped tests this
tenant's `test_client` cannot reach, 2 for Turnstile not being configured, 1
for no asset carrying a SAP asset number, 1 for no active `workflow.config`.
A tenant whose client holds the `admin` scope skips far fewer.
[ENVIRONMENT-FACTS.md](ENVIRONMENT-FACTS.md) carries the same breakdown.

There are no `xfail` markers in the suite any more; the two
delegated-controller bugs that used to need them are fixed.

**Check the denominator, not the exit code.** An Odoo test run whose database
died before the test phase reports `0 failed, 0 error(s) of 0 tests` **and
exits 0**. Grep for `of 0 tests` and for `CRITICAL` before believing a green.

---

## First-time setup (prod — a client's server)

```bash
# On the target VPS:
git clone git@github.com:wmlmetro/Cadra.git
cd Cadra

cp .env.example .env
nano .env    # set CADRA_DOMAIN and CADRA_ACME_EMAIL, and ROTATE every secret

# Generate the three that matter:
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)"
echo "ODOO_MASTER_PASSWORD=$(openssl rand -base64 32)"
echo "CADRA_JWT_SECRET=$(openssl rand -base64 48)"

CADRA_PROFILE=prod scripts/bootstrap.sh
```

On first start Caddy obtains a Let's Encrypt certificate for `$CADRA_DOMAIN`
(30–60 s, cached in the `cadra_caddy_data` volume thereafter):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f proxy
```

When the banner says `serving HTTPS on <CADRA_DOMAIN>`, you are live.

### Credentials

The three commands above are no longer advice. **The prod container refuses
to start** if `POSTGRES_PASSWORD`, `ODOO_MASTER_PASSWORD` or
`CADRA_JWT_SECRET` still holds a value this repository ships as a default
(`admin`, `odoo`, `changeme` and the rest of the list in
`docker-compose.prod.yml`). It names each offender and exits. A security
position that rests on somebody having read a runbook is the thing a rule
exists to replace.

`CADRA_JWT_SECRET` may be left **empty** — bootstrap generates one and stores
it per database in `ir.config_parameter`. What it may not be is a placeholder.

**One thing this repository does NOT set, on any tenant: the Odoo `admin`
user's password.** `bootstrap.py` adds `base.user_admin` to the groups the
API needs and never touches its password; no seed, migration or job does
either. `ODOO_MASTER_PASSWORD` is the *database manager* password, which is
a different credential. **Set the `admin` user's password by hand, in the
UI, before the server is reachable from the internet.**

### Build and ship, rather than bind-mount

The compose files mount the source tree read-only at `/mnt/extra-addons`,
which is right for development and wrong for a client server: it means the
running code is whatever is checked out, and a rollback is a `git checkout`
on a live box. For a real deployment, build a tagged image and pin it:

```bash
docker build -f Dockerfile.odoo.19.k8s -t <registry>/cadra-odoo-19:<sha> .
docker push <registry>/cadra-odoo-19:<sha>
```

Then set `image:` to that tag and drop the `./:/mnt/extra-addons:ro` mount in
a small site-local override file. `Dockerfile.odoo.19.k8s` bakes every
in-house addon; CI's `image-addons-complete` job fails if a module with a
`__manifest__.py` has no `COPY` line in it, so the image cannot silently
lose a module.

---

## What the bootstrap actually does

`scripts/bootstrap.sh` is idempotent — safe to re-run any time. The whole of
`bootstrap.py` runs in one transaction that rolls back and re-raises on
failure, so a half-provisioned tenant is never committed.

1. Resolves `CADRA_PROFILE` and fails on an unknown one; checks `docker` is
   on `PATH`; copies `.env.example` to `.env` if missing (**in every
   profile**, not just dev); **sources `.env` into its own environment**.
2. Builds the odoo image, then starts **Postgres only** — odoo and the proxy
   come up after the module install.
3. Polls `pg_isready` for 60 seconds and hard-fails if it never answers.
4. Counts installed modules. **Fresh database** → `odoo -i <modules>
   --stop-after-init --no-http`. **Existing** → skips the install entirely;
   it does not run `-u`, so picking up code changes is a separate step (see
   "Update modules" below).
5. Stops the live odoo container, runs `scripts/bootstrap.py` in a one-off
   `odoo shell`, and brings odoo back. The stop is the point: a one-off and
   a live server fight over the registry otherwise. `bootstrap.py`:
   - Sets `ir.config_parameter myservice_api.jwt_secret` **per database**,
     from `CADRA_JWT_SECRET`, else an existing value, else a fresh
     48-byte token. Values under 16 chars and the known placeholders are
     rejected.
   - Mirrors `CADRA_TURNSTILE_SECRET` into `myservice_api.turnstile_secret`,
     one-way: an empty variable leaves a stored value alone, so a job that
     loses the variable cannot strip bot protection off a live tenant.
   - Adds the admin user to `group_asset_manager` and `group_security_admin`.
   - Provisions **three** API clients, each with its own `res.users` rather
     than acting as Administrator: `test_client` (the full canonical scope
     set, derived from the code), `tag_issuing_unit` (`tagging:write` only)
     and `vendra` (`assets:read assets:write` only). The two scoped clients
     are **re-narrowed on every run** — a scope added by hand does not
     survive.
   - Configures `ir.mail_server` from `SMTP_*` if `SMTP_HOST` is set, and the
     HTTPS email relay from `CADRA_EMAIL_RELAY_URL` / `_SECRET` if set.
     The relay (`myservice_email_relay`) reads three `ir.config_parameter`
     rows, and only the first two are written by bootstrap or by
     `.github/workflows/set-email-relay.yml`:
     - `cadra.email_relay_url` and `cadra.email_relay_secret` — BOTH set,
       or the relay is off and core SMTP runs. The relay sends as its own
       account; the letter's From is not carried.
     - `cadra.email_relay_text_field` — the name of the relay's plain-text
       field. **Absent or empty, the plain-text part of every letter is
       dropped** and a reader with HTML switched off sees nothing. It is not
       set anywhere by default because nobody here has confirmed the relay
       accepts such a field, or under what name, and a relay that refuses
       an unknown key would then refuse every mail. Once whoever runs the
       relay confirms the name, set it per tenant (an `odoo shell`:
       `env['ir.config_parameter'].sudo().set_param('cadra.email_relay_text_field', '<name>')`,
       then commit) and roll odoo — `ir.config_parameter` reads are cached
       per worker.
   - Runs the seeds for `CADRA_SEED_PROFILE`.
6. Captures the sentinel-wrapped output and merges seven credential keys into
   `docs/api/.creds.<db>` (mode 600). It **merges** rather than overwrites,
   because a hashed secret cannot be re-read and bootstrap prints
   `<UNCHANGED — …>` when it preserves one; writing that placeholder straight
   to disk used to destroy a working creds file.
7. Waits up to 120 s for Odoo's healthcheck.
8. Prints the summary banner: URLs, the admin login, the creds path, and the
   tenant-aware pytest command.

**The script takes no database argument.** It bootstraps `POSTGRES_DB` from
`.env`, so provisioning a second database means editing `.env` first.

### Seed profiles

`CADRA_SEED_PROFILE` selects a seed list; `core` is the default and an empty
value runs none. An unknown profile warns and skips rather than failing.

| Profile | Contents | Rough cost |
|---|---|---|
| `core` | ITSM structure, location skeleton, 415 FIRS offices | fast |
| `fleet` | `core` + the master fleet seed (1,617 vehicles) | slow |
| `full` | 4-level office hierarchy, master seed, NRS HQ assets (1,272), HQ metadata, fleet taxonomy, location matcher | 12–15 min |
| `full-no-master` | `full` without the master seed | ~7 min less |
| `full+geo`, `full-no-master+geo` | plus geocoding | ~30 min — **exceeds the 20-minute bootstrap Job cap in cluster** |
| `gtb`, `jaiz`, `lasg` | per-tenant demo data (122 / 39 / 90 locations) | fast |

Seeds are get-or-create, so re-running picks up new entries. A seed whose
file is absent is skipped with a warning; a seed that fails is logged at
ERROR and does not abort the rest.

---

## Day-2 operations

Every command below reads `.env` values. **`scripts/bootstrap.sh` sources
`.env` internally; your shell does not.** Load it first, or the variables
below expand to nothing — `DROP DATABASE ;` being the memorable case:

```bash
set -a && . ./.env && set +a
```

Substitute `docker-compose.prod.yml` for `docker-compose.19.yml` on a client
server — **and mind the config path**. The dev overlay mounts its config at
`/etc/odoo/odoo.conf`; the prod overlay mounts it at
`/etc/odoo/odoo.conf.**template**` and `config/prod-entrypoint.sh` builds the
real one at `/tmp/odoo.conf` at start-up, because the database credentials and
the master password have to come from the environment rather than from a
committed file.

So on prod, **every command below that passes `-c` must pass
`-c /tmp/odoo.conf`**, not `-c /etc/odoo/odoo.conf`. The latter exists — it is
the base image's stub — and using it gives you an addons path with no
`crnd-19` or `oca-19` on it and no database credentials at all, which fails
with `fe_sendauth: no password supplied`. That error names nothing relevant.

### View logs

```bash
docker compose -f docker-compose.yml -f docker-compose.19.yml logs -f odoo
```

### Restart Odoo (after editing a Python file)

```bash
docker compose -f docker-compose.yml -f docker-compose.19.yml restart odoo
```

Python is bind-mounted but not hot-reloaded, so a restart is required. **An
asset-bundle, view or manifest change is not enough — it needs a module
upgrade.** And note that *editing* `config/odoo.19.conf` breaks its own
mount: it is mounted as a single file, so any editor that replaces the inode
leaves the container with no `/etc/odoo/odoo.conf` at all and every
`exec … odoo -c` fails with a confusing `psycopg2.OperationalError` about a
unix socket. Follow a config edit with
`up -d --force-recreate odoo`.

### Update modules (after pulling new code)

The running container already binds 8069, so an in-container upgrade must be
given free ports:

```bash
# dev
docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
  odoo -c /etc/odoo/odoo.conf -d "$POSTGRES_DB" -u myservice_api \
  --stop-after-init --http-port=8099 --gevent-port=8098

# prod — note the config path
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T odoo \
  odoo -c /tmp/odoo.conf -d "$POSTGRES_DB" -u myservice_api \
  --stop-after-init --http-port=8099 --gevent-port=8098

docker compose -f docker-compose.yml -f docker-compose.19.yml restart odoo
```

`--no-http` alone is **not** sufficient: Odoo still binds without an explicit
`--http-port`.

Replace `myservice_api` with the comma-separated list of modules that
changed. `-u` upgrades a module and everything that depends on it, not its
dependencies.

### Adding a stored field is a migration, not a code change

**On a client server this is ordinary and the blast radius is zero** — there
is one database, so "upgrade the schema, then ship the code" is the usual
rule and nothing else can be left behind.

**On the shared development machine and in cluster it is not.** One Odoo
process serves every database from one registry, so the moment a stored field
lands in the Python, every database that has not been upgraded is broken:
reads of that column raise `UndefinedColumn` and any serializer touching it
500s the endpoint. Upgrade **all** of them before the code ships:

```bash
for db in cadra19 nrs19 gtb19 test19 nrs lasg gtb jaizbankplc; do
  docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
    odoo -c /etc/odoo/odoo.conf -d $db -u <module> --stop-after-init \
    --http-port=8099 --gevent-port=8098
done
```

**Serialise it.** Never run two `--stop-after-init` invocations at once, on
this machine or any developer machine — a second registry load is itself the
contended resource and the Docker VM's OOM killer takes Postgres down with
it. Different databases do not help; memory is the shared thing. Build a
three-attempt retry into any fan-out, waiting for the database to come back
between attempts. Retry a crash; do not retry a code fault.
[ENVIRONMENT-FACTS.md](ENVIRONMENT-FACTS.md) carries the measurement.

### Load SAP's asset master (handoff 63)

Settings → *SAP asset master* in the app, as a system administrator: upload
SAP's asset-master export, the `.XLSX` as SAP produced it. The server checks
the header row on upload and reads the rest in the background; the page
shows the run. Two things on the path must allow it, checked against the
files on 2026-10-18:

- **The upload size.** The October export is 75 MB. Odoo's own ceiling is
  128 MB (`odoo/http.py`, `DEFAULT_MAX_CONTENT_LENGTH`) and the route's 200
  MB. `config/Caddyfile` (prod) sets no `request_body` limit; the cluster
  ingresses (`k8s/dev/60-ingress.yaml`, `62-ingress-19.yaml`) set
  `proxy-body-size: 200m`; the local `config/nginx.dev.conf` was 50m and is
  200m since handoff 63.
- **The cron.** The import runs as ticks of the *SAP mirror — read the
  queued asset-master import* scheduled action, each ≤ 25 s of CPU, so it
  fits `limit_time_cpu` whatever it is (`config/odoo.prod.conf` 600 s; the
  local `config/odoo.19.conf` leaves Odoo's 60 s default). A server whose
  cron does not run never reads the file: the run stays `queued`.

The uploaded file is deleted when the run ends. Re-uploading the same export
changes nothing (every record counted `unchanged`).

### Back up the database

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db \
    pg_dump -Fc --no-owner --no-acl -U "$POSTGRES_USER" "$POSTGRES_DB" \
    > backup-$(date +%Y%m%d-%H%M%S).dump
```

`-T` is load-bearing. Without it compose allocates a TTY and mangles the
binary `-Fc` stream.

**A database dump is not a backup of Cadra.** Attachments and compiled asset
bundles live in the filestore volume (`cadra_odoo_data`), and a database
restored without its matching filestore serves a blank `/web` and 404s every
attachment. Back up both:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    run --rm --no-deps -T --entrypoint sh odoo \
    -c 'tar czf - -C /var/lib/odoo .' \
    > filestore-$(date +%Y%m%d-%H%M%S).tar.gz
```

**Let compose attach the volume; do not name it yourself.** The volume's real
name is prefixed with the compose project, which defaults to the directory
name — `Cadra` here, `myservicenrs` on an older clone. `docker run -v
cadra_odoo_data:/data` does not fail on a wrong name: Docker CREATES an empty
volume of that name and tars nothing, and the backup looks like it worked.
`--no-deps` keeps it from starting Postgres for a filesystem read.

There is no `scripts/backup.sh` in this repository. Scheduling and off-site
rotation are per-site; a cron entry running the two commands above into
object storage is the minimum.

### Restore the database

```bash
# 0. Verify the dump is readable BEFORE destroying anything.
pg_restore -l backup-XYZ.dump | head

# 1. Take a fresh backup of what you are about to replace.

# 2. Stop everything that holds a connection — the proxy too, or a hit on
#    /web/login re-opens one mid-drop.
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop odoo proxy

# 3. Drop and recreate. `-d postgres` is required: psql with no -d connects
#    to the database named after the user, which is the one being dropped.
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db \
    psql -U "$POSTGRES_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE);" \
    -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\";"

docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db \
    pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" < backup-XYZ.dump

# 4. Restore the matching filestore, then bring the stack back.
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Rotate API client credentials

Set the secret you want in `.env` and re-run bootstrap — no deletion needed:

```bash
CADRA_TEST_CLIENT_SECRET=$(openssl rand -base64 32)   # in .env
scripts/bootstrap.sh
```

`tag_issuing_unit` and `vendra` rotate the same way through their own
variables. Rotating the JWT secret invalidates every issued token, which is
the point of doing it but is not a quiet operation.

### Stop the stack

```bash
# Keep volumes — restart is fast
docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# Also delete the database AND the filestore (destructive!)
docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v
```

---

## Rollback

**Code-only, on a bind-mounted deployment:**

```bash
git checkout <known-good-sha>
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart odoo
```

This is the weakest form of rollback and it is why the "build and ship"
section above exists: on a pinned-image deployment you roll back by changing
a tag, which is atomic and does not depend on the state of a git checkout on
the server.

Two things a code-only rollback does **not** undo:

- **An asset-bundle or view change.** Those live in the database and need a
  module upgrade to move in either direction.
- **A schema change.** Restore from the pre-deploy backup.

Always take a backup before pulling new code in prod.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `502 Bad Gateway` from Caddy | Odoo not ready yet — Caddy comes up first on purpose, to get its certificate | Wait 30–60 s; `docker compose logs odoo` |
| `No database is selected` on `localhost:8069` | `ODOO_DBFILTER=^%d$` — correct behaviour | Use `http://<db>.localhost:8069` |
| `Could not connect to Cadra API` from pytest | Stack down, or the wrong host | Check the stack; set `CADRA_API_BASE` to the tenant's host |
| Blanket `401` on every endpoint | `docs/api/.creds.<db>` belongs to a different tenant than `CADRA_API_BASE`, or the tenant was `-i`'d but never bootstrapped so it has no `jwt_secret` | Point both at the same tenant; run bootstrap. See [reading-an-auth-failure.md](api/reading-an-auth-failure.md) |
| `server_misconfigured` 500 on a correct password | Tenant has no `myservice_api.jwt_secret` | Run `bootstrap.py` against it with `CADRA_SEED_PROFILE=` empty |
| `403 forbidden`, `Missing required scope(s)`, on a **client** token | The API client's scopes do not cover the endpoint | Re-run `scripts/bootstrap.sh` — it re-syncs scopes to the canonical set |
| `403 forbidden` on a **session** token from `/auth/login` | Since handoff 05, login scopes are derived from the user's **Odoo groups**, not from any client record. Re-running bootstrap will not help | Grant the user the right group. `tagging:write` comes from exactly one group and is implied by no other; a user in none of the mapped groups gets no scopes at all |
| `module myservice_X not installed` in cluster | The module has no `COPY` line in `Dockerfile.odoo.19.k8s`, so it is not in the image | Add it; CI's `image-addons-complete` job guards this |
| Postgres `all server processes terminated; reinitializing` | The Docker VM's OOM killer, from two Odoo registry loads at once. Not something you broke | Serialise. Budget twenty minutes and one discarded run |
| `psycopg2.OperationalError` about a unix socket on `exec … odoo -c` | A config edit replaced the bind-mounted file's inode, so the container has no `/etc/odoo/odoo.conf` | `up -d --force-recreate odoo` |
| Blank `/web`, 404s on asset bundles, `odoo.define is not a function` | The filestore does not match the database — usually a rename or a restore that moved one and not the other | Restore or move `filestore/<db>/` to match |
| `cannot execute INSERT in a read-only transaction`, dozens of lines, `0 failed` | Expected noise from the in-registry suite | Ignore it. Do not chase it |
| `internal_error` from an `HttpCase` POST that works against the live server | Test mode gives a read/write route a read-only cursor and a controller-level `except Exception` defeats Odoo's retry | Let the exception through; guarded by `tests/test_source_guards.py` |
| `last_used_ip` is always the proxy's container address in dev | `ProxyFix` runs only when the request carries `X-Forwarded-Host`, which the dev nginx does not send. Caddy and ingress-nginx do | Not a dev-stack fault |

---

## What this document does not cover

Deliberately. These are the shared development and demonstration estate, not
a client deployment, and they have their own runbooks:

- **The Kubernetes cluster** — `k8s/dev/` and its three guides:
  [CLUSTER-SETUP.md](../k8s/dev/CLUSTER-SETUP.md),
  [ODOO-19-STACK.md](../k8s/dev/ODOO-19-STACK.md) and
  [MULTI-TENANT.md](../k8s/dev/MULTI-TENANT.md). Tenant onboarding, the
  database-name-equals-subdomain rule, the filestore-move rule and the
  cutover procedure are all there.
- **The public landing page at `https://cadra.ng/`** — static files in
  `landing/`, served from the same cluster by its own pod, Ingress and
  certificate (`k8s/dev/45-landing-deployment.yaml`, `46-landing-service.yaml`,
  `63-ingress-landing.yaml`) and published by `deploy-landing.yml` on any push
  to `dev` that touches them. It is the company's site, not part of what a
  client is given, and no client server runs it.
- **The 20 GitHub Actions workflows** in `.github/workflows/`, which are how
  the cluster is actually operated: `deploy-dev.yml`, `upgrade-19.yml`,
  `tenant-cutover-19.yml`, `audit-tenant.yml`, `db-query.yml`,
  `drop-db.yml` and the rest. Each carries its own header explaining what it
  does and what it destroys.
- **Machine-specific facts** that will cost you an afternoon —
  [ENVIRONMENT-FACTS.md](ENVIRONMENT-FACTS.md).
- **Why anything here is the way it is** — [DECISIONS.md](DECISIONS.md).

---

## File map

Only what a deployment touches. It is not a repository listing.

```
.
├── .env.example                 # Documented config vars (copy to .env)
├── docker-compose.yml           # Base services (db, odoo) — pins Odoo 19
├── docker-compose.19.yml        # Dev overrides: nginx, exposed ports, SPA mount
├── docker-compose.prod.yml      # Prod overrides: Caddy + TLS, credential refusal
├── Dockerfile.odoo.19.dev       # FROM odoo:19.0 — dev/CI image, bind-mounted repo
├── Dockerfile.odoo.19.k8s       # FROM odoo:19.0 — every addon baked in (build & ship)
├── config/
│   ├── nginx.dev.conf           # Dev nginx vhost: Odoo + the React SPA at /app/
│   ├── Caddyfile                # Prod Caddy config (auto Let's Encrypt)
│   ├── odoo.19.conf             # Dev/CI Odoo config (list_db=True, 19 options)
│   ├── odoo.prod.conf           # Prod Odoo TEMPLATE (list_db=False, hardened, 19)
│   └── prod-entrypoint.sh       # Prod start-up: refuses weak credentials, builds /tmp/odoo.conf
├── scripts/
│   ├── bootstrap.sh             # Host-side orchestrator (the one command)
│   └── bootstrap.py             # In-container Python (runs inside odoo shell)
├── k8s/dev/                     # The demo cluster — not a client deployment
├── tests/                       # pytest API suite (see tests/README.md)
└── docs/
    ├── DEPLOYMENT.md            # This file
    ├── ENVIRONMENT-FACTS.md     # Things true of these machines
    ├── DECISIONS.md             # Why anything is the way it is
    └── api/
        ├── .creds.<db>          # per-tenant credentials from bootstrap (gitignored)
        ├── smoke_test.py        # 30-second liveness check (stdlib only)
        └── reading-an-auth-failure.md
```
