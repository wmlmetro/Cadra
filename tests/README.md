# Cadra REST API — pytest suite

Comprehensive end-to-end tests for the 42-endpoint Cadra API. Runs against
the local docker stack at `http://localhost:8069`.

## Prerequisites

1. Docker stack up: `docker compose -f docker-compose.dev.yml up -d`
2. API credentials at `docs/api/.creds` (run `docs/api/setup_api_smoke.py`
   once to create them — see [docs/api/setup_api_smoke.py](../docs/api/setup_api_smoke.py))

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

Override the API base URL with `CADRA_API_BASE=http://other-host:8069 pytest tests/`.

## Outputs (gitignored)

- **`docs/api/test-responses/<resource>/<name>.json`** — full response body
  for every endpoint, including the request that produced it. Inspect by
  opening the file directly.
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
