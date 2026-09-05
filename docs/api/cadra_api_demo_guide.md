# Cadra API — Demo Guide

A focused walkthrough of every endpoint exposed by the Cadra API (module
`myservice_api`), structured for a live demo. 45 endpoints across 8
groups, all under `/api/v1/*`, JWT-protected, with one envelope shape
across the board.

- **Staging base URL:** `https://staging.app.cadra.ng`
- **Local base URL:** `http://localhost:8069` (docker-compose dev stack)
- **Auth:** OAuth2 client-credentials → JWT (HS256, 1 h TTL)
- **Content type:** `application/json` (one CSV exception)
- **Self-documenting:** `GET /api/v1/openapi.json` + Swagger UI at `/api/v1/docs`

## How every response looks

Every JSON response follows one envelope (PRD §10.7):

```jsonc
// Success
{
  "data": { ... } | [ ... ],
  "meta": { "request_id": "...", "timestamp": "2026-06-08T...", "version": "v1" },
  "pagination": { "next_cursor": "...", "previous_cursor": null, "total_estimate": 1272 }  // only on lists
}

// Error
{
  "error": {
    "code": "not_found",          // machine-readable
    "message": "Asset 9999 ...",  // human-readable
    "details": { ... }            // optional, field-specific
  },
  "meta": { "request_id": "...", "timestamp": "...", "version": "v1" }
}
```

**Error codes you'll see in the demo:** `invalid_request`, `unauthorized`,
`forbidden`, `not_found`, `conflict`, `unprocessable`, `rate_limited`,
`server_misconfigured`.

**Pagination:** opaque cursors. `limit` default 50, max 200. Append
`?cursor=<next_cursor>` to step forward. Pass `?total=0` to skip the
count query on huge tables.

---

## §1 — Auth (1 endpoint)

Every other endpoint needs a Bearer token. Get one once, reuse for the
hour.

### `POST /api/v1/auth/token` — exchange client credentials for a JWT

```bash
curl -sX POST https://staging.app.cadra.ng/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"test_client","client_secret":"<from docs/api/.creds>"}'
```

```json
{
  "data": {
    "token_type": "Bearer",
    "access_token": "eyJhbGciOi...",
    "expires_in": 3600,
    "scope": "assets:read assets:write locations:read locations:write requests:read requests:write dashboards:read integrations:write"
  },
  "meta": { ... }
}
```

**For every other call:**

```bash
TOKEN=$(curl -sX POST https://staging.app.cadra.ng/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"test_client","client_secret":"…"}' | jq -r .data.access_token)
```

**Scopes (14 total):**
`assets:read`, `assets:write`, `locations:read`, `locations:write`,
`requests:read`, `requests:write`, `approvals:write`, `dashboards:read`,
`integrations:write`, `ingestion:write`, `webhooks:admin`, `identity:read`,
`tagging:write`, `admin`.

---

## §2 — Assets (7 endpoints)

Map onto `nrs.asset` (1,272 records seeded). Lifecycle states: `active`,
`in_repair`, `disposed`, `transferred`, `missing`. Custody changes go
through `mail.thread`; location moves create `nrs.asset.transfer` rows.

| Method | Path | Scope | What it does |
|---|---|---|---|
| GET    | `/api/v1/assets` | `assets:read` | List with rich filters |
| GET    | `/api/v1/assets/<id>` | `assets:read` | Single asset (`?include=transfers,pm,children`) |
| GET    | `/api/v1/assets/by-tag/<tag>` | `assets:read` | Lookup by `asset_tag` (fallback `asset_code`) |
| POST   | `/api/v1/assets` | `assets:write` | Create — `asset_code` auto-generated if omitted |
| PATCH  | `/api/v1/assets/<id>` | `assets:write` | Partial update |
| POST   | `/api/v1/assets/<id>/move` | `assets:write` | Move to a new location (records a transfer) |
| POST   | `/api/v1/assets/<id>/transfer-custody` | `assets:write` | Reassign `custodian_id` (hr.employee) |

### List with filters

```bash
curl -sH "Authorization: Bearer $TOKEN" \
  "https://staging.app.cadra.ng/api/v1/assets?q=fire&category_id=12&building_id=1&state=active&limit=20"
```

Filters: `q`, `category_id`, `location_id`, `building_id`, `custodian_id`,
`state`, `condition`, `domain`, `is_verified`, `limit`, `cursor`.

### Get one, with embedded transfer history

```bash
curl -sH "Authorization: Bearer $TOKEN" \
  "https://staging.app.cadra.ng/api/v1/assets/1?include=transfers,pm,children"
```

### Create

```bash
curl -sX POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{
    "name": "Generator 100kVA — Bldg A",
    "category_id": 3,
    "subcategory_id": 12,
    "asset_type_id": 45,
    "location_id": 891,
    "condition": "good"
  }' \
  https://staging.app.cadra.ng/api/v1/assets
```

Returns `201 Created` with the full serialized asset.

### Move + custody (the demo-friendly side-effects)

```bash
# Move asset 1 to location 905 — creates an nrs.asset.transfer row
curl -sX POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"to_location_id": 905, "reason": "Building reshuffle"}' \
  https://staging.app.cadra.ng/api/v1/assets/1/move

# Reassign custody to employee 42
curl -sX POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"custodian_id": 42, "note": "Handover at quarter-end"}' \
  https://staging.app.cadra.ng/api/v1/assets/1/transfer-custody
```

---

## §3 — Locations (7 endpoints)

`generic.location` — 1,166 nodes seeded (zones → states → cities → 415
FIRS offices → HQ floors/rooms). Tree-shaped; every node knows its
ancestors and descendants.

| Method | Path | Scope | What it does |
|---|---|---|---|
| GET   | `/api/v1/locations` | `locations:read` | List + filters + cursor |
| GET   | `/api/v1/locations/<id>` | `locations:read` | Single (`?include=children,ancestors`) |
| POST  | `/api/v1/locations` | `locations:write` | Create |
| PATCH | `/api/v1/locations/<id>` | `locations:write` | Partial update |
| GET   | `/api/v1/locations/<id>/children` | `locations:read` | Direct children |
| GET   | `/api/v1/locations/<id>/ancestors` | `locations:read` | Root → parent chain |
| GET   | `/api/v1/locations/<id>/descendants` | `locations:read` | All descendants, paginated |

```bash
# List FIRS offices in FCT with coordinates
curl -sH "Authorization: Bearer $TOKEN" \
  "https://staging.app.cadra.ng/api/v1/locations?state_id=15&location_type=office&has_coordinates=true&limit=50"

# Drill into a state's offices
curl -sH "Authorization: Bearer $TOKEN" \
  "https://staging.app.cadra.ng/api/v1/locations/15/descendants?limit=100"
```

Filter knobs: `q`, `type_id`, `parent_id`, `country_id`, `state_id`,
`location_type`, `active`, `has_coordinates`, `limit`, `cursor`.

---

## §4 — Requests (8 endpoints)

The ITSM heart of the platform. `request.request` — service desk
tickets, incidents, change requests, etc. References follow
`KIND-MMYYYY-SEQUENCE` (e.g. `INCIDENT-052026-0000002`).

| Method | Path | Scope | What it does |
|---|---|---|---|
| GET   | `/api/v1/requests` | `requests:read` | List + filters |
| GET   | `/api/v1/requests/<id>` | `requests:read` | Single (`?include=routes,events,messages`) |
| GET   | `/api/v1/requests/by-reference/<ref>` | `requests:read` | Lookup by human-readable reference |
| POST  | `/api/v1/requests` | `requests:write` | Create — auto-names + auto-stages |
| PATCH | `/api/v1/requests/<id>` | `requests:write` | Partial update (stage changes go through `/transition`) |
| POST  | `/api/v1/requests/<id>/assign` | `requests:write` | Set assignee (`{user_id: int|null}`) |
| POST  | `/api/v1/requests/<id>/transition` | `requests:write` | Move along a stage route (`{route_id}` or `{to_stage_id}`) |
| POST  | `/api/v1/requests/<id>/comment` | `requests:write` | Post a message via mail.thread |

### Create + assign + advance + comment — the full lifecycle in 4 calls

```bash
# 1. Create a new electrical incident at location 480 against asset 1
curl -sX POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{
    "type_id": 1,
    "category_id": 5,
    "priority": "3",
    "request_text": "<p>UPS in Bldg A failed overnight</p>",
    "location_id": 480,
    "nrs_asset_id": 1
  }' \
  https://staging.app.cadra.ng/api/v1/requests
# → 201, returns {data: {id: 3, reference: "INCIDENT-062026-0000003", stage: "New", ...}}

# 2. Assign to user 7 (a facility lead)
curl -sX POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"user_id": 7}' \
  https://staging.app.cadra.ng/api/v1/requests/3/assign

# 3. Move to next stage (Assigned → In Progress)
curl -sX POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"route_id": 23}' \
  https://staging.app.cadra.ng/api/v1/requests/3/transition

# 4. Add a public comment
curl -sX POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"body": "Engineer dispatched — ETA 30 min", "internal": false}' \
  https://staging.app.cadra.ng/api/v1/requests/3/comment
```

### Lookup by human-readable reference (for support handoffs)

```bash
curl -sH "Authorization: Bearer $TOKEN" \
  https://staging.app.cadra.ng/api/v1/requests/by-reference/INCIDENT-062026-0000003
```

Filters on `GET /requests`: `q`, `type_id`, `category_id`, `stage_id`,
`user_id`, `priority`, `closed`, `location_id`, `asset_id`, `limit`, `cursor`.

---

## §5 — Dashboards (8 endpoints, all GET, scope `dashboards:read`)

Pre-aggregated payloads consumed by the Odoo webclient AND any external
BI tool. Each is a thin pass-through to the model that already feeds the
Odoo widgets — so curl returns exactly what the chart on `/web` shows.

| Path | What it returns |
|---|---|
| `/api/v1/dashboard/kpis` | Top-of-page KPI strip (open / overdue / SLA / etc.) |
| `/api/v1/dashboard/map` | Geo points for the map widget |
| `/api/v1/dashboard/fleet-command` | Fleet command tab payload (vehicle status grid) |
| `/api/v1/security/kpis` | Security incident KPIs |
| `/api/v1/security/map-data` | Security map markers |
| `/api/v1/security/trend` | Incident trend time-series |
| `/api/v1/security/recent` | Recent security incidents |
| `/api/v1/fleet/dashboard` | Fleet maintenance KPIs + SLA |
| `/api/v1/fm/dashboard` | FM operations dashboard (the home page) |

```bash
# The same payload that powers the FM Operations Dashboard
curl -sH "Authorization: Bearer $TOKEN" \
  https://staging.app.cadra.ng/api/v1/fm/dashboard | jq '.data.kpis'
```

Demo angle: **the API + the Odoo UI are literally reading the same
function — no separate "API layer" to drift out of sync.**

---

## §6 — Barcode + tag lookup (7 endpoints)

For the handheld barcode-station workflow. Same data the on-device JS
queries, surfaced as proper JSON.

| Method | Path | Scope | Purpose |
|---|---|---|---|
| GET | `/api/v1/barcode/lookup?query=…` | `assets:read` | Find an asset by tag or partial code |
| GET | `/api/v1/barcode/kpis` | `assets:read` | Scan-station KPIs |
| GET | `/api/v1/barcode/recent-tags?domain_filter=&limit=` | `assets:read` | Recently scanned/printed tags |
| GET | `/api/v1/barcode/print-url?tag_id=&size=` | `assets:read` | Generate a Zebra print URL |
| GET | `/api/v1/barcode/untagged?q=&limit=` | `assets:read` | Assets with an asset code but no barcode |
| POST | `/api/v1/barcode/generate` | `assets:write` | Mint barcodes for the given assets |
| GET | `/api/v1/tags/lookup?query=…` | `assets:read` | Portal-style lookup (JWT, not anonymous) |

```bash
curl -sH "Authorization: Bearer $TOKEN" \
  "https://staging.app.cadra.ng/api/v1/barcode/lookup?query=HQ-GF-MR"

curl -sH "Authorization: Bearer $TOKEN" \
  "https://staging.app.cadra.ng/api/v1/barcode/print-url?tag_id=1234&size=large"

curl -sX POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"asset_ids": [412, 413]}' \
  "https://staging.app.cadra.ng/api/v1/barcode/generate"
```

---

## §7 — Bulk export (2 endpoints)

| Method | Path | Scope | Format |
|---|---|---|---|
| GET | `/api/v1/assets/export` | `assets:read` | JSON array of all assets |
| GET | `/api/v1/assets/export.csv` | `assets:read` | CSV (the one endpoint that bypasses the envelope) |

```bash
# CSV with all 1,272 HQ assets — pipe straight to a file
curl -sH "Authorization: Bearer $TOKEN" \
  https://staging.app.cadra.ng/api/v1/assets/export.csv > assets.csv

# JSON, structured, friendly for ETL
curl -sH "Authorization: Bearer $TOKEN" \
  https://staging.app.cadra.ng/api/v1/assets/export | jq '.assets | length'
```

CSV is intentionally outside the envelope so it streams cleanly into
Excel / Power BI.

---

## §8 — Homepage helpers (2 endpoints)

Drives the public-facing service-request form on the marketing site.

| Method | Path | Scope | Purpose |
|---|---|---|---|
| GET  | `/api/v1/home/form-data` | `requests:read` | Dropdowns (types, categories, locations) |
| POST | `/api/v1/home/quick-submit` | `requests:write` | One-shot request submission from a public form (idempotent on `X-Idempotency-Key`) |

```bash
# Fetch the form's dropdowns
curl -sH "Authorization: Bearer $TOKEN" \
  https://staging.app.cadra.ng/api/v1/home/form-data

# Submit with idempotency — same key → same response, no duplicate request
curl -sX POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -H 'X-Idempotency-Key: demo-abc-123' \
  -d '{"name":"Adamu","email":"a@firs.gov.ng","message":"AC not working","location_name":"HQ Floor 4"}' \
  https://staging.app.cadra.ng/api/v1/home/quick-submit
```

---

## §9 — Integrations (2 endpoints, scope `integrations:write`)

Inbound webhooks for upstream systems.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/integrations/sap/employee-sync` | Receive SAP SuccessFactors employee events (hire, move, terminate) — keeps `hr.employee` in sync |
| POST | `/api/v1/integrations/workflow/callback` | External workflow engine (e.g. Camunda) tells Cadra a decision was made → request transitions accordingly |

```bash
# SAP pushing a new hire
curl -sX POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{
    "event": "hire",
    "employee_id": "12345",
    "name": "Adaobi Eze",
    "email": "adaobi.eze@firs.gov.ng",
    "department": "ICT",
    "office": "HQ"
  }' \
  https://staging.app.cadra.ng/api/v1/integrations/sap/employee-sync

# External workflow approving a request
curl -sX POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"request_id": 3, "decision": "approve", "route_id": 24, "actor": "workflow@firs"}' \
  https://staging.app.cadra.ng/api/v1/integrations/workflow/callback
```

---

## §10 — Self-documenting (2 endpoints)

The kicker for any demo audience:

| Path | Returns |
|---|---|
| `GET /api/v1/openapi.json` | OpenAPI 3.0 spec auto-generated from the live route registry — never out of date |
| `GET /api/v1/docs` | Swagger UI rendered inline, no separate hosting |

```bash
curl -s https://staging.app.cadra.ng/api/v1/openapi.json | jq '.paths | keys | length'
# → 45
```

Open `https://staging.app.cadra.ng/api/v1/docs` in a browser — click
"Authorize", paste the JWT, every endpoint is testable from the page.

---

## Suggested 12-minute demo flight plan

### Minute 0–1 — Set the stage
> "Single API spec, 45 endpoints, three core resources (Assets, Locations,
> Requests) and the dashboards/integrations layered on top. Every
> response wears the same envelope, every list paginates with cursors,
> every action is JWT-scoped."

### Minute 1–2 — Auth
- Hit `POST /api/v1/auth/token` live, copy the JWT.
- Show the `scope` field — explain that the test client has every scope;
  in real life each integration gets only what it needs.

### Minute 2–5 — Requests (the lifecycle story)
- `POST /api/v1/requests` → show the auto-generated reference
  `INCIDENT-062026-…`
- `POST /api/v1/requests/<id>/assign` — show the assignee landing in
  the response
- `POST /api/v1/requests/<id>/transition` — show stage moving
- `POST /api/v1/requests/<id>/comment` — note that `mail.thread` is the
  underlying transport, so an Odoo notification fires too

### Minute 5–7 — Assets (the inventory story)
- `GET /api/v1/assets?building_id=1&limit=5` — quick filter
- `GET /api/v1/assets/1?include=transfers,pm,children` — show how
  `include` fans out
- `POST /api/v1/assets/1/move` — explain that this **created an
  nrs.asset.transfer row** in the DB; not just a field write

### Minute 7–8 — Locations (the tree story)
- `GET /api/v1/locations?state_id=15&location_type=office` — show 415
  FIRS offices addressable
- `GET /api/v1/locations/15/descendants` — show the cursor pagination
  with `total_estimate`

### Minute 8–10 — Dashboards
- Open the FM dashboard in the Odoo UI in one tab
- In another tab, `GET /api/v1/fm/dashboard` — point out the JSON is
  **the exact payload powering the chart on the left**

### Minute 10–11 — Integrations
- Show `POST /api/v1/integrations/sap/employee-sync` payload, explain
  the inbound-from-SAP story
- Mention `POST /api/v1/integrations/workflow/callback` as the
  Camunda/Flowable hook

### Minute 11–12 — Self-documenting
- Open `/api/v1/docs` in the browser
- Click "Authorize", paste the JWT
- Click `GET /assets`, hit "Try it out", run it — the same JSON appears
- Close with: **"every endpoint we just saw is auto-listed there. The
  spec is generated from the code, so it can't drift."**

---

## Cheat sheet for the demo machine

```bash
# 0. Set base URL
API=https://staging.app.cadra.ng

# 1. Get token (paste your client_secret)
TOKEN=$(curl -sX POST $API/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"test_client","client_secret":"'$CLIENT_SECRET'"}' \
  | jq -r .data.access_token)
echo "Token: ${TOKEN:0:32}..."

# 2. Helper: authenticated curl
acurl() { curl -sH "Authorization: Bearer $TOKEN" "$@"; }

# 3. Smoke-test
acurl $API/api/v1/assets?limit=1 | jq '.data[0].asset_code'
acurl $API/api/v1/locations?limit=1 | jq '.data[0].name'
acurl $API/api/v1/requests?limit=1 | jq '.data[0].reference'
acurl $API/api/v1/fm/dashboard | jq '.data.kpis'
```

---

## Endpoint index (all 45)

```
POST   /api/v1/auth/token

GET    /api/v1/openapi.json
GET    /api/v1/docs

GET    /api/v1/assets
GET    /api/v1/assets/<id>
GET    /api/v1/assets/by-tag/<tag>
POST   /api/v1/assets
PATCH  /api/v1/assets/<id>
POST   /api/v1/assets/<id>/move
POST   /api/v1/assets/<id>/transfer-custody
GET    /api/v1/assets/export
GET    /api/v1/assets/export.csv

GET    /api/v1/locations
GET    /api/v1/locations/<id>
POST   /api/v1/locations
PATCH  /api/v1/locations/<id>
GET    /api/v1/locations/<id>/children
GET    /api/v1/locations/<id>/ancestors
GET    /api/v1/locations/<id>/descendants

GET    /api/v1/requests
GET    /api/v1/requests/<id>
GET    /api/v1/requests/by-reference/<reference>
POST   /api/v1/requests
PATCH  /api/v1/requests/<id>
POST   /api/v1/requests/<id>/assign
POST   /api/v1/requests/<id>/transition
POST   /api/v1/requests/<id>/comment

GET    /api/v1/dashboard/kpis
GET    /api/v1/dashboard/map
GET    /api/v1/dashboard/fleet-command
GET    /api/v1/security/kpis
GET    /api/v1/security/map-data
GET    /api/v1/security/trend
GET    /api/v1/security/recent
GET    /api/v1/fleet/dashboard
GET    /api/v1/fm/dashboard

GET    /api/v1/barcode/lookup
GET    /api/v1/barcode/kpis
GET    /api/v1/barcode/recent-tags
GET    /api/v1/barcode/print-url
GET    /api/v1/barcode/untagged
POST   /api/v1/barcode/generate
GET    /api/v1/tags/lookup

GET    /api/v1/home/form-data
POST   /api/v1/home/quick-submit

POST   /api/v1/integrations/sap/employee-sync
POST   /api/v1/integrations/workflow/callback
```
