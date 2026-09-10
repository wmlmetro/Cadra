# Cadra — NRS Service Platform

Cadra is an API-first service platform for the Nigeria Revenue Service (NRS),
built on Odoo 15 with a versioned REST layer (`/api/v1/*`) on top of the
existing ITSM, asset register, security, and facility-management modules.

The platform is the spiritual successor of `myservicenrs`. The Odoo addons in
this repo provide the data model and admin UI; the `myservice_api` module
exposes a JWT-protected REST API that other systems (mobile app, third-party
integrations, dashboards) can consume.

> **Spec is canonical.** The PRD and NRS specification under
> [docs/](docs/) (`Cadra_Platform_PRD_v0.4.docx`,
> `Cadra_at_NRS_Specification_v0.1.docx`) are the source of truth for all
> design decisions. When this README and the spec disagree, the spec wins —
> open an issue or a PR.

---

## At a glance

|              |                                                                                     |
| ------------ | ----------------------------------------------------------------------------------- |
| **Stack**    | Odoo 15 (Python 3.10) · PostgreSQL 13 · Docker Compose · nginx (dev) / Caddy (prod) |
| **API**      | 36 REST endpoints under `/api/v1/*`, JWT-protected, OpenAPI 3.0 spec auto-generated |
| **Auth**     | OAuth2 client-credentials → JWT (HS256, 1h TTL)                                     |
| **Envelope** | PRD §10.7 — `{data, meta}` on success, `{error}` on failure                         |
| **Tests**    | 70 pytest cases (67 pass, 3 xfail) + a 30-second smoke test                         |
| **CI**       | GitHub Actions — cold bootstrap + full pytest on every push                         |
| **Deploy**   | One command: `scripts/bootstrap.sh` (dev or prod)                                   |

---

## Quick start (local dev)

Prerequisites: Docker 20.10+ with Compose v2, 4 GB RAM free, ~10 GB disk.

```bash
git clone <repo-url>
cd myservicenrs

# Copies .env.example → .env (defaults are dev-safe) and runs the full
# bootstrap: build image → install 15 modules → seed ITSM/locations/offices
# → generate JWT secret → create API client → capture creds to docs/api/.creds.
# First run takes 3–5 min; subsequent runs are seconds.
scripts/bootstrap.sh
```

When it finishes you'll see:

```
═══════════════════════════════════════════════════════════════════
  Bootstrap complete ✓
═══════════════════════════════════════════════════════════════════
  Web UI:      http://localhost:8069
  API docs:    http://localhost:8069/api/v1/docs
  OpenAPI:     http://localhost:8069/api/v1/openapi.json
  Admin login: admin / admin
  API client:  see docs/api/.creds.<db>  (one file per tenant)
```

**Verify**:

```bash
# 30-second alive check
python3 docs/api/smoke_test.py

# Full pytest suite (one-time venv setup)
python3 -m venv tests/.venv
source tests/.venv/bin/activate
pip install -r tests/requirements.txt
pytest tests/ -v          # expect: 67 passed, 3 xfailed
```

---

## Repository layout

```
.
├── myservice_api/              ← THE API LAYER (this is the new code)
│   ├── controllers/
│   │   ├── utils.py            ← envelope helpers, JWT, scope constants
│   │   ├── v1.py               ← cadra_route decorator, auth, dashboards, etc
│   │   ├── v1_locations.py     ← /api/v1/locations/*
│   │   ├── v1_assets.py        ← /api/v1/assets/*
│   │   └── v1_requests.py      ← /api/v1/requests/*
│   ├── http_patch.py           ← forces HttpRequest for /api/v1/* (bypasses
│   │                              Odoo's Content-Type-based JsonRequest auto-select)
│   ├── models/api_client.py    ← API client + scopes (admin UI)
│   └── openapi.yaml            ← seed spec (live spec is auto-generated at /api/v1/openapi.json)
│
├── myservice_*/                ← Existing Odoo modules (asset register, security,
│                                 fleet, dashboards, NRS theme, workflow, etc.)
├── dist/                       ← CRND/Bureaucrat vendored addons (do not edit)
│
├── tests/                      ← Pytest API suite — 12 files, 70 tests
│   ├── conftest.py             ← session fixtures (token, client, test_*)
│   ├── test_auth.py, test_locations.py, test_assets.py, …
│   └── README.md
│
├── scripts/
│   ├── bootstrap.sh            ← host-side orchestrator (dev or prod)
│   ├── bootstrap.py            ← runs inside odoo shell: JWT, groups, client, seeds
│   └── nrs_hq_seed_v4.py       ← master fleet/vehicle seed (slow — opt in via CADRA_SEED_PROFILE=fleet)
│
├── config/
│   ├── odoo.19.conf            ← dev/CI: list_db=True, admin_passwd=admin, 2 workers
│   ├── odoo.prod.conf          ← prod: list_db=False, no demo, proxy_mode=True
│   ├── nginx.dev.conf          ← dev reverse proxy
│   └── Caddyfile               ← prod reverse proxy + Let's Encrypt
│
├── docs/
│   ├── Cadra_Platform_PRD_v0.4.docx       ← THE SPEC
│   ├── Cadra_at_NRS_Specification_v0.1.docx
│   ├── DEPLOYMENT.md           ← ops runbook (first-time, day-2, rollback)
│   ├── cadra-api-docs.html
│   └── api/
│       ├── smoke_test.py       ← 30-second alive check
│       ├── setup_api_smoke.py  ← creates API client + saves creds
│       ├── test-report.md      ← generated by pytest hook
│       └── test-responses/     ← captured response JSON per endpoint (gitignored)
│
├── docker-compose.yml          ← base — db + odoo + healthchecks, pins Odoo 19
├── docker-compose.19.yml       ← dev overrides (exposed ports, nginx, SPA, no TLS)
├── docker-compose.prod.yml     ← prod overrides (Caddy TLS, no exposed ports)
├── Dockerfile.odoo.19.dev      ← Odoo 19 image + this repo at /mnt/extra-addons
├── Dockerfile.odoo.19.k8s      ← Odoo 19 image with every addon baked in
├── .env.example                ← every configurable knob, documented
└── .github/workflows/ci.yml    ← cold bootstrap + pytest on every push
```

---

## The API

### Base URL

| Environment | Base                                            |
| ----------- | ----------------------------------------------- |
| Local dev   | `http://localhost:8069`                         |
| Production  | `https://<CADRA_DOMAIN>` (Caddy terminates TLS) |

### Documentation

- **Live Swagger UI** — `GET /api/v1/docs`
- **OpenAPI 3.0 spec** — `GET /api/v1/openapi.json` (auto-generated from
  `@cadra_route` decorators at runtime, so it is always in sync with the code)

### Authentication

```bash
# 1. Mint a token (no auth required)
curl -X POST http://localhost:8069/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"client_id": "test_client", "client_secret": "<secret>"}'

# Response:
# { "data": { "access_token": "eyJ…", "token_type": "Bearer", "expires_in": 3600,
#             "scopes": ["assets:read", "assets:write", …] },
#   "meta": { … } }

# 2. Use the token on every other call
curl http://localhost:8069/api/v1/locations \
  -H 'Authorization: Bearer eyJ…'
```

Tokens are JWT (HS256), TTL 1 hour, signed with `CADRA_JWT_SECRET`. The dev
client's credentials are auto-generated by `scripts/bootstrap.py` and saved to
`docs/api/.creds.<db>` — one per tenant, gitignored. The shared `docs/api/.creds` was removed in handoff 05; secrets belong to a database, and one global file authenticates whichever tenant was bootstrapped last.

### Response envelope (PRD §10.7)

**Success:**

```json
{
  "data": { ... },
  "meta": {
    "request_id": "uuid",
    "timestamp": "2026-05-24T18:42:00Z",
    "pagination": { "cursor": null, "next_cursor": "...", "limit": 50 }
  }
}
```

**Error:**

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "name is required",
    "details": { ... }
  },
  "meta": { "request_id": "uuid", "timestamp": "..." }
}
```

### Endpoint coverage (36 paths)

| Family                                                               | Verbs            | Notes                                                               |
| -------------------------------------------------------------------- | ---------------- | ------------------------------------------------------------------- |
| `/auth/token`                                                        | POST             | Issues JWT                                                          |
| `/locations/*`                                                       | GET, POST, PATCH | CRUD + `/children`, `/ancestors`, `/descendants`                    |
| `/assets/*`                                                          | GET, POST, PATCH | CRUD + `/by-tag/<tag>`, `/move`, `/transfer-custody`, `/export.csv` |
| `/requests/*`                                                        | GET, POST, PATCH | CRUD + `/by-ref/<ref>`, `/assign`, `/transition`, `/comment`        |
| `/dashboard/*`, `/security/*`, `/fleet/*`, `/fm/*`                   | GET              | 9 read-only dashboard endpoints                                     |
| `/barcode/*`, `/tags/lookup`                                         | GET              | KPIs, recent tags, label print URL                                  |
| `/home/*`                                                            | GET, POST        | Quick-submit homepage form                                          |
| `/integrations/sap/employee-sync`, `/integrations/workflow/callback` | POST             | Inbound webhooks                                                    |
| `/openapi.json`, `/docs`                                             | GET              | Spec + Swagger UI (non-envelope responses)                          |

### Idempotency

Write endpoints (POST/PATCH) respect `X-Idempotency-Key`: a second call with
the same key returns the cached first response, byte-for-byte. Keys are
scoped per client and live for 24 hours.

### Scopes

Read and write are separate scopes per resource family
(`locations:read`, `locations:write`, `assets:read`, …). Insufficient scope
returns 403. See [myservice_api/controllers/utils.py](myservice_api/controllers/utils.py)
for the full `SCOPE_*` constants.

---

## Deployment

Two profiles, same codebase. Both use `scripts/bootstrap.sh` — the only
difference is which compose override the script picks up.

| Profile | Compose                          | Proxy                 | TLS  | Bring up                                  |
| ------- | -------------------------------- | --------------------- | ---- | ----------------------------------------- |
| `dev`   | `docker-compose.yml + .dev.yml`  | nginx (HTTP only)     | None | `scripts/bootstrap.sh`                    |
| `prod`  | `docker-compose.yml + .prod.yml` | Caddy (Let's Encrypt) | Auto | `CADRA_PROFILE=prod scripts/bootstrap.sh` |

### Prod prerequisites

1. A public domain pointing at the host (A record).
2. Ports 80 and 443 open (Let's Encrypt HTTP-01 challenge needs port 80).
3. Edit `.env`:
   ```bash
   CADRA_DOMAIN=cadra.example.com
   CADRA_ACME_EMAIL=ops@example.com
   ODOO_MASTER_PASSWORD=$(openssl rand -base64 32)
   POSTGRES_PASSWORD=$(openssl rand -base64 32)
   ```
4. `CADRA_PROFILE=prod scripts/bootstrap.sh`

Caddy will obtain a Let's Encrypt cert on first request to your domain.

### Detailed runbook

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — first-time setup, day-2 ops
(logs, restart, module update, backups, restores, credential rotation),
rollback strategy, and a troubleshooting table.

---

## Configuration

Every configurable value lives in `.env`. See [.env.example](.env.example) for
the documented list. Key knobs:

| Variable                  | Default        | Purpose                                         |
| ------------------------- | -------------- | ----------------------------------------------- |
| `POSTGRES_PASSWORD`       | `odoo`         | DB password — **change for prod**               |
| `ODOO_MASTER_PASSWORD`    | `admin`        | DB manager auth — **change for prod**           |
| `ODOO_WORKERS`            | `2`            | Worker processes (prod: `2 * cpu + 1`)          |
| `CADRA_JWT_SECRET`        | _(auto-gen)_   | JWT signing key, ≥16 chars (prod: ≥48)          |
| `CADRA_BOOTSTRAP_MODULES` | _(15 modules)_ | Comma-list installed on first run               |
| `CADRA_SEED_PROFILE`      | `core`         | `core` (fast) or `fleet` (adds vehicle seed)    |
| `CADRA_DOMAIN`            | —              | **prod-only:** public hostname for TLS cert     |
| `CADRA_ACME_EMAIL`        | —              | **prod-only:** Let's Encrypt registration email |

---

## Testing

Two layers of testing, both runnable against any reachable Cadra instance.

### Smoke test (30 seconds, no install)

```bash
python3 docs/api/smoke_test.py
```

Exits 0 if the API is alive and returning the right envelope.

### Pytest suite (3-4 seconds after warm-up)

```bash
python3 -m venv tests/.venv
source tests/.venv/bin/activate
pip install -r tests/requirements.txt
pytest tests/ -v
```

What it does:

- Mints a JWT, then hits every endpoint with the correct verb, body, and scopes
- Asserts HTTP status + PRD envelope shape
- Captures the full response of each call to `docs/api/test-responses/<resource>/<name>.json`
- Writes a summary markdown report to `docs/api/test-report.md`
- Negative tests: 401 (no token), 403 (wrong scope), 404 (no such id), 400 (bad body)
- Idempotency tests: writes with the same `X-Idempotency-Key` return identical responses

Coverage by file:

| File                   | Tests | What it covers                                      |
| ---------------------- | ----- | --------------------------------------------------- |
| `test_auth.py`         | 3     | Token mint success + 2 failure modes                |
| `test_locations.py`    | 11    | All 7 location endpoints + pagination + filters     |
| `test_assets.py`       | 10    | All 8 asset endpoints                               |
| `test_assets_csv.py`   | 2     | CSV export (non-JSON response)                      |
| `test_requests.py`     | 11    | All 8 request endpoints + assign/transition/comment |
| `test_dashboards.py`   | 9     | Every dashboard GET                                 |
| `test_barcode.py`      | 6     | Barcode + tag lookups                               |
| `test_home.py`         | 2     | Quick-submit form                                   |
| `test_integrations.py` | 4     | SAP sync + workflow callback                        |
| `test_meta.py`         | 3     | OpenAPI spec + Swagger HTML                         |
| `test_negative.py`     | 6     | 401/403/404/400 envelope correctness                |
| `test_idempotency.py`  | 3     | X-Idempotency-Key cache                             |

### CI

Every push to any branch runs [.github/workflows/ci.yml](.github/workflows/ci.yml):

1. **`bootstrap-and-test`** — full cold start in a clean GitHub runner. Brings
   up the stack, runs `scripts/bootstrap.sh` (build, install, seed, mint
   creds), then runs pytest. Test report + per-endpoint captures uploaded as
   workflow artifacts on every run.
2. **`prod-compose-lint`** — syntactic validation of `docker-compose.prod.yml`
   (no real domain needed).

---

## Development workflow

### Hot-reload addon changes

The repo is bind-mounted at `/mnt/extra-addons` in the odoo container, so
Python file changes are picked up on restart:

```bash
docker compose -f docker-compose.yml -f docker-compose.19.yml restart odoo
```

For changes to module manifests, views, or data files, run the upgrade
inside the container:

```bash
docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
  odoo -c /etc/odoo/odoo.conf -d <db> -u myservice_api --stop-after-init \
  --http-port=8099 --gevent-port=8098
```

### Adding a new endpoint

1. Add a `@cadra_route(path, method=…, scopes=…)` controller method in the
   appropriate `myservice_api/controllers/v1_*.py` file.
2. Return either `ok(data, …)` or `err(code, message)` from
   [myservice_api/controllers/utils.py](myservice_api/controllers/utils.py) —
   never raw dicts, so the envelope is consistent.
3. Add a test in `tests/test_<resource>.py` following the existing pattern.
4. Run `pytest tests/test_<resource>.py -v` — the OpenAPI coverage check in
   `tests/test_meta.py` will fail if the endpoint isn't listed in the spec
   (it auto-discovers from the `_ROUTE_REGISTRY`, so no manual spec edit).

### Inspecting the live DB

```bash
docker compose -f docker-compose.yml -f docker-compose.19.yml exec db \
  psql -U odoo -d <db>
```

Postgres is exposed on `localhost:5432` in dev (user/pw: `odoo`/`odoo`).

---

## Known limitations

- **`/api/v1/barcode/lookup`** (GET with `?q=…`) — pre-existing upstream bug
  in `myservice_barcode_station`. Marked `xfail` in tests; tracked for
  later.
- **`/api/v1/home/quick-submit`** — pre-existing upstream bug in
  `myservice_request_fields` form validation. Marked `xfail`; tracked.
- **Webhook delivery (PRD §10.6)** — not yet implemented. Outbound events
  are next on the roadmap once deployment is shipped.
- **Odoo 15 lock-in** — upgrading to Odoo 18 was scoped and rejected: the
  CRND/Bureaucrat dist addons are auth-gated and would need to be replaced.
  Cadra v0.2 will revisit the platform layer.

---

## CRND assembly metadata (legacy)

This repo was originally a CRND assembly. The addon manifest it was built
from is still here — [`odoo-packager.yml`](./odoo-packager.yml), which this
section named as `odoo_packager.yml` and linked to nothing — and it lists the
vendored `dist/` addons. Cadra's own modules are **not** maintained that way;
they live directly in the repo root.

**The pipeline that ran the packager is gone.** `.gitlab-ci.yml` was deleted
in handoff 21: it pinned `SERIES_BRANCH: '15.0'`, targeted a GitLab that is
not a remote of this repository, and had not been touched since an assembly
bot wrote it in March 2023. `dist/` is the Odoo 15 vendor tree and is off
every Odoo 19 addons path, so nothing in it is refreshed any more —
`crnd-19/` hand-ports what the 19 stack needs.

For the packager docs, should anyone ever need them, see the
[upstream packager README](https://gitlab.crnd.pro/crnd/docker/odoo-apps-packager/blob/d/README.md).

---

## License & ownership

Internal Westmetro / NRS project. Vendored addons under `dist/` retain
their upstream LGPLv3 license.

gh workflow run deploy-dev.yml --ref dev -f run_bootstrap=true
