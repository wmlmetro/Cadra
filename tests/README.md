# Cadra REST API — pytest suite

Comprehensive end-to-end tests for the 42-endpoint Cadra API. Runs against
the local docker stack.

## Prerequisites

1. Docker stack up — **both compose files**:
   `docker compose -f docker-compose.yml -f docker-compose.19.yml up -d`
2. **Point the suite at a tenant.** Cadra routes by `Host`, so a bare
   `localhost` answers *"No database is selected"*:

   ```bash
   CADRA_API_BASE=http://jaizbankplc.localhost:8069 \
     tests/.venv/bin/python -m pytest tests/ -q
   ```

3. **Credentials for that tenant** at `docs/api/.creds.<tenant>` — e.g.
   `docs/api/.creds.jaizbankplc`. `scripts/bootstrap.sh` writes it for whichever
   database it bootstrapped — which is `POSTGRES_DB` from `.env`, not an
   argument, so bootstrapping a *different* tenant means changing `.env` first.

   The file is resolved from `CADRA_API_BASE`'s hostname, falling back to the
   lone per-tenant file when a checkout has exactly one. The shared
   `docs/api/.creds` is gone: secrets are per-database
   (one Odoo process, many databases, each with its own API clients and
   `jwt_secret`), so a single global file points at whichever tenant was
   bootstrapped last and aiming the suite anywhere else fails at the first call
   with a bare `401` that looks like a code fault.

   `docs/api/setup_api_smoke.py` can also create the client. It no longer
   rotates anything unless you ask (`CADRA_SMOKE_ROTATE=1`,
   `CADRA_SMOKE_ROTATE_JWT=1`) — it used to reset the JWT secret and delete the
   client on every run, on whichever database the shell happened to be attached
   to.

## One-time setup

```bash
python3 -m venv tests/.venv
source tests/.venv/bin/activate
pip install -r tests/requirements.txt
```

## Run the suite

```bash
source tests/.venv/bin/activate
pytest tests/ -v
```

`CADRA_API_BASE` selects both the host and, through it, the tenant and its
credentials file.

Note: ~25 admin-scoped tests skip when the tenant's client does not hold the
`admin` scope. That is expected, not a failure.

## Outputs (gitignored)

- **`docs/api/test-responses/<resource>/<name>.json`** — full response body
  for every endpoint, including the request that produced it. Inspect by
  opening the file directly. Secret-named values (`client_secret`,
  `access_token`, `refresh_token`, `password`, …) are redacted in both the
  request and the response body: CI uploads this directory as a 14-day
  artifact, and captures are evidence, not a credential store.
- **`docs/api/test-report.md`** — markdown summary table with pass/fail per
  endpoint + links to the response JSONs.

## What's tested

42 endpoints across 11 resource families:

| File | Endpoints |
|---|---|
| `test_auth.py` | POST /auth/token |
| `test_locations.py` | 7 location endpoints (list/get/create/patch/children/ancestors/descendants) |
| `test_assets.py` | 8 asset endpoints (incl. move + transfer-custody actions) |
| `test_assets_csv.py` | /assets/export.csv (non-JSON) |
| `test_custody.py` | /assets/<id>/custody + `include=custody` — the append-only chain (INT-10 §2.3) |
| `test_requests.py` | 8 service-request endpoints (incl. assign/transition/comment actions) |
| `test_dashboards.py` | 9 dashboard endpoints (operations + security + fleet + fm) |
| `test_barcode.py` | 4 barcode endpoints + /tags/lookup |
| `test_home.py` | 2 homepage endpoints |
| `test_integrations.py` | sap/employee-sync + workflow/callback |
| `test_meta.py` | /openapi.json + /docs |
| `test_negative.py` | 401, 403, 404, 400 cases |
| `test_idempotency.py` | X-Idempotency-Key cached-response behaviour |

Tests create their own resources (one location, one asset, one request per
session) and **leave them in the dev DB** — same convention as
`docs/api/smoke_test.py`. No teardown.

## Relationship to docs/api/smoke_test.py

The smoke test stays as the quick "is everything alive" check (urllib +
stdlib, ~30 endpoints, terse output). This pytest suite is the thorough
verification (42 endpoints, assertions, captured responses, report).
