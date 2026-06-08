# Cadra API — Endpoint Reference

Every endpoint, with a copy-paste-runnable request, a success response,
and at least one error response. Response bodies are real (captured by
the pytest smoke suite into `docs/api/test-responses/`); long bodies
are trimmed with `…` for readability but the shape and field names are
exact.

## Conventions used in this document

```bash
# Pick your environment
API=https://staging.app.cadra.ng    # staging (k8s)
# API=http://localhost:8069         # local dev (docker-compose)

# Get a JWT once and reuse for the hour
TOKEN=$(curl -sX POST $API/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"test_client","client_secret":"'"$CLIENT_SECRET"'"}' \
  | jq -r .data.access_token)

# Authenticated curl wrapper used in every example below
acurl() { curl -sS -H "Authorization: Bearer $TOKEN" "$@"; }
```

Every authenticated call uses the `acurl` helper above. Unauthenticated
calls use plain `curl`.

**Envelope.** Every JSON response is one of:

```jsonc
{ "data": …, "meta": {...}, "pagination": {...}? }
{ "error": { "code": "...", "message": "...", "request_id": "...", "details": {...} } }
```

**Error codes.** `invalid_request` (400), `unauthorized` (401),
`forbidden` (403), `not_found` (404), `conflict` (409),
`unprocessable` (422), `rate_limited` (429), `internal_error` (500),
`server_misconfigured` (500).

---

# §1 — Auth

## 1.1 POST `/api/v1/auth/token` — exchange client credentials for a JWT

Auth: **none** (this is the auth bootstrap).
Success: **200**.

### Request

```bash
curl -sX POST $API/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{
    "client_id": "test_client",
    "client_secret": "wvHr54kAlQeGtoOOaiNLy_7uzAl0Ey1WNac4K3X0HivaxwHctqSKnw"
  }'
```

### Success — `200 OK`

```json
{
  "data": {
    "token_type": "Bearer",
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJteXNlcnZpY2VfYXBpIiwic3ViIjoidGVzdF9jbGllbnQiLCJ1aWQiOjIs…",
    "expires_in": 3600,
    "scope": "dashboards:read assets:read assets:write locations:read locations:write requests:read requests:write integrations:write"
  },
  "meta": { "request_id": "bff6ef80…", "timestamp": "2026-06-08T10:00:00", "version": "v1" }
}
```

### Error — `400 invalid_request` (missing field)

```bash
curl -sX POST $API/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"client_secret":"anything"}'
```

```json
{
  "error": {
    "code": "invalid_request",
    "message": "`client_id` and `client_secret` are required",
    "request_id": "8a72c65e…",
    "details": { "http_status": 400 }
  }
}
```

### Error — `401 unauthorized` (wrong secret)

```bash
curl -sX POST $API/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"test_client","client_secret":"completely-wrong-secret"}'
```

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Invalid client credentials",
    "request_id": "4c97774c…",
    "details": { "http_status": 401 }
  }
}
```

---

# §2 — Self-documenting (no auth)

## 2.1 GET `/api/v1/openapi.json` — auto-generated OpenAPI 3.0 spec

Auth: **none**. Success: **200**.

### Request

```bash
curl -s $API/api/v1/openapi.json | jq '.paths | keys | length'
```

### Success — `200 OK`

```json
{
  "openapi": "3.0.3",
  "info": { "title": "Cadra API", "version": "v1", "description": "Cadra REST API …" },
  "servers": [{ "url": "/" }],
  "components": { "securitySchemes": { "bearerAuth": { "type": "http", "scheme": "bearer", "bearerFormat": "JWT" } } },
  "paths": { "/api/v1/auth/token": { … }, "/api/v1/assets": { … }, … 43 more entries … }
}
```

### Error

There's no error path on this endpoint — it's generated in-process from the
route registry and has no external dependencies. Will only fail if the
Odoo worker itself is unreachable (transport-level 502/504 from nginx).

## 2.2 GET `/api/v1/docs` — Swagger UI

Auth: **none**. Success: **200** (HTML). Open in a browser:

```
$API/api/v1/docs
```

Click **Authorize**, paste the raw JWT (NOT prefixed with `Bearer `),
then try any endpoint inline.

### Error

Same as above — pure static HTML, no failure modes worth documenting.

---

# §3 — Assets

`nrs.asset` — 1,272 records seeded. Lifecycle states:
`active | in_repair | disposed | transferred | missing`.

## 3.1 GET `/api/v1/assets` — list assets

Scope: `assets:read`. Success: **200**.

Filters: `q`, `category_id`, `location_id`, `building_id`, `custodian_id`,
`state`, `condition`, `domain`, `is_verified`, `limit` (default 50,
max 200), `cursor`.

### Request

```bash
acurl "$API/api/v1/assets?q=Fire&category_id=6&state=active&limit=5"
```

### Success — `200 OK`

```json
{
  "data": [
    {
      "id": 124,
      "asset_code": "NRS-EV-FAL-FAP-00001",
      "tag": "HQ-GF-MR-EV-001",
      "name": "Fire Alarm Panel",
      "category": { "id": 6, "name": "ELV Systems" },
      "subcategory": { "id": 18, "name": "Fire Alarm" },
      "asset_type": { "id": 92, "name": "Fire Alarm Panel" },
      "current_location": { "id": 891, "name": "HQ - GF - Mail Room" },
      "location_hierarchy": { "building": { "id": 890, "name": "NRS HQ" }, "floor": null, "room": { "id": 891, "name": "GF Mail Room" } },
      "current_custodian": null,
      "condition": "good",
      "state": "active",
      "created_at": "2026-06-01T17:05:14.213000",
      "updated_at": "2026-06-01T17:05:14.213000"
    }
    /* 4 more … */
  ],
  "meta": { "request_id": "d15ed80c…", "timestamp": "2026-06-08T10:00:00", "version": "v1" },
  "pagination": { "next_cursor": "eyJsYXN0X2lkIjoxMjh9", "previous_cursor": null, "total_estimate": 1272 }
}
```

### Error — `401 unauthorized` (no token)

```bash
curl -s "$API/api/v1/assets?limit=5"
```

```json
{ "error": { "code": "unauthorized", "message": "Missing bearer token", "request_id": "8d87b830…", "details": { "http_status": 401 } } }
```

## 3.2 GET `/api/v1/assets/<id>` — get single asset

Scope: `assets:read`. Success: **200**.
Optional: `?include=transfers,pm,children`.

### Request

```bash
acurl "$API/api/v1/assets/124?include=transfers,pm,children"
```

### Success — `200 OK`

```json
{
  "data": {
    "id": 124,
    "asset_code": "NRS-EV-FAL-FAP-00001",
    "tag": "HQ-GF-MR-EV-001",
    "name": "Fire Alarm Panel",
    "category": { "id": 6, "name": "ELV Systems" },
    "subcategory": { "id": 18, "name": "Fire Alarm" },
    "asset_type": { "id": 92, "name": "Fire Alarm Panel" },
    "asset_level": "asset",
    "domain": "elv",
    "current_location": { "id": 891, "name": "HQ - GF - Mail Room" },
    "location_hierarchy": { "building": { "id": 890, "name": "NRS HQ" }, "floor": null, "room": { "id": 891, "name": "GF Mail Room" } },
    "current_custodian": null,
    "condition": "good",
    "state": "active",
    "financial": { "currency": { "id": 121, "name": "NGN" }, "purchase_value": null, "replacement_cost": null, "acquisition_cost": null, "current_value": null },
    "dates": { "purchase_date": null, "warranty_expiry": null, "acquisition_date": null, "disposal_date": null, "last_verified_date": null, "next_service_date": null },
    "is_verified": false,
    "pm_count": 0,
    "request_count": 0,
    "transfers": [],
    "pm": [],
    "children": [],
    "created_at": "2026-06-01T17:05:14.213000",
    "updated_at": "2026-06-01T17:05:14.213000"
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `404 not_found`

```bash
acurl "$API/api/v1/assets/99999999"
```

```json
{ "error": { "code": "not_found", "message": "Asset 99999999 not found", "request_id": "…", "details": { "http_status": 404 } } }
```

## 3.3 GET `/api/v1/assets/by-tag/<tag>` — lookup by asset_tag

Scope: `assets:read`. Success: **200**. Falls back to `asset_code` if
no match on `asset_tag`.

### Request

```bash
acurl "$API/api/v1/assets/by-tag/HQ-GF-MR-EV-001"
```

### Success — `200 OK`

Same shape as `GET /api/v1/assets/<id>` (full asset record).

### Error — `404 not_found`

```bash
acurl "$API/api/v1/assets/by-tag/NO-SUCH-TAG-12345"
```

```json
{ "error": { "code": "not_found", "message": "No asset with tag or code 'NO-SUCH-TAG-12345'", "request_id": "42785af0…", "details": { "http_status": 404 } } }
```

## 3.4 POST `/api/v1/assets` — create asset

Scope: `assets:write`. Success: **201**.
Idempotent via `Idempotency-Key` header — same key → same record.
`asset_code` auto-generated from category if omitted.

### Request

```bash
acurl -X POST $API/api/v1/assets \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-create-asset-001' \
  -d '{
    "name": "Generator 100kVA — Bldg A",
    "category_id": 3,
    "subcategory_id": 12,
    "asset_type_id": 45,
    "location_id": 891,
    "condition": "new",
    "state": "active"
  }'
```

### Success — `201 Created`

```json
{
  "data": {
    "id": 1273,
    "asset_code": "NRS-AST-001273",
    "tag": null,
    "name": "Generator 100kVA — Bldg A",
    "category": { "id": 3, "name": "Plant & Machinery" },
    "subcategory": { "id": 12, "name": "Generators" },
    "asset_type": { "id": 45, "name": "Diesel Generator 100kVA" },
    "current_location": { "id": 891, "name": "HQ - GF - Mail Room" },
    "condition": "new",
    "state": "active",
    "created_at": "2026-06-08T10:00:01.234567",
    "updated_at": "2026-06-08T10:00:01.234567"
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

Re-running the same `Idempotency-Key` with **different** body returns the
**original** record (the second body is ignored).

### Error — `400 invalid_request` (missing required field)

```bash
acurl -X POST $API/api/v1/assets -H 'Content-Type: application/json' \
  -d '{"category_id": 3}'
```

```json
{ "error": { "code": "invalid_request", "message": "`name` is required", "request_id": "…", "details": { "http_status": 400 } } }
```

## 3.5 PATCH `/api/v1/assets/<id>` — partial update

Scope: `assets:write`. Success: **200**.

### Request

```bash
acurl -X PATCH $API/api/v1/assets/124 \
  -H 'Content-Type: application/json' \
  -d '{
    "condition": "in_repair",
    "notes": "UPS battery flagged during May inspection"
  }'
```

### Success — `200 OK`

Returns the **full updated asset record** (same shape as
`GET /api/v1/assets/<id>` without `include` expansions).

### Error — `404 not_found`

```bash
acurl -X PATCH $API/api/v1/assets/99999999 \
  -H 'Content-Type: application/json' -d '{"condition":"good"}'
```

```json
{ "error": { "code": "not_found", "message": "Asset 99999999 not found", "request_id": "…", "details": { "http_status": 404 } } }
```

## 3.6 POST `/api/v1/assets/<id>/move` — move to a new location

Scope: `assets:write`. Success: **200**. Creates an
`nrs.asset.transfer` row (audit trail) as a side-effect.

### Request

```bash
acurl -X POST $API/api/v1/assets/124/move \
  -H 'Content-Type: application/json' \
  -d '{
    "to_location_id": 905,
    "reason": "Reshuffle after Q2 audit"
  }'
```

### Success — `200 OK`

```json
{
  "data": {
    "asset": { "id": 124, "asset_code": "NRS-EV-FAL-FAP-00001", "current_location": { "id": 905, "name": "HQ - 1F - Server Room" }, "condition": "good", "state": "active", "...": "full asset record" },
    "transfer": { "id": 17, "from_location": { "id": 891, "name": "HQ - GF - Mail Room" }, "to_location": { "id": 905, "name": "HQ - 1F - Server Room" }, "reason": "Reshuffle after Q2 audit", "created_at": "2026-06-08T10:00:02" }
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `422 unprocessable` (same-location move forbidden)

```bash
# Asset 124 is already at location 891 — move-to-self rejected
acurl -X POST $API/api/v1/assets/124/move \
  -H 'Content-Type: application/json' \
  -d '{"to_location_id": 891, "reason": "no-op"}'
```

```json
{ "error": { "code": "unprocessable", "message": "Asset is already at this location", "request_id": "…", "details": { "http_status": 422 } } }
```

## 3.7 POST `/api/v1/assets/<id>/transfer-custody` — reassign custodian

Scope: `assets:write`. Success: **200**. Posts a chatter note via
`mail.thread` for the audit trail.

### Request

```bash
acurl -X POST $API/api/v1/assets/124/transfer-custody \
  -H 'Content-Type: application/json' \
  -d '{
    "to_custodian_id": 42,
    "reason": "Custodian handover at quarter-end"
  }'
```

### Success — `200 OK`

```json
{
  "data": {
    "asset": { "id": 124, "current_custodian": { "id": 42, "name": "Adaobi Eze" }, "...": "full asset record" },
    "custody_log": { "message_id": 8123, "from_custodian": null, "to_custodian": { "id": 42, "name": "Adaobi Eze" }, "reason": "Custodian handover at quarter-end" }
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `400 invalid_request` (missing custodian)

```bash
acurl -X POST $API/api/v1/assets/124/transfer-custody \
  -H 'Content-Type: application/json' -d '{}'
```

```json
{ "error": { "code": "invalid_request", "message": "`to_custodian_id` is required", "request_id": "…", "details": { "http_status": 400 } } }
```

## 3.8 GET `/api/v1/assets/export` — bulk JSON export

Scope: `assets:read`. Success: **200**. Returns every asset; no pagination.
Cheaper than fanning out individual GETs for ETL into a data warehouse.

### Request

```bash
acurl $API/api/v1/assets/export | jq '.data.count'
```

### Success — `200 OK`

```json
{
  "data": {
    "count": 1272,
    "assets": [
      {
        "asset_code": "NRS-EV-FAL-FAP-00001",
        "name": "Fire Alarm Panel",
        "category": "ELV Systems",
        "condition": "good",
        "state": "active",
        "location": "HQ - GF - Mail Room",
        "assigned_to": null,
        "assigned_ir": null,
        "assigned_dept": null,
        "assignment_date": null,
        "retrieval_flag": false,
        "serial_number": null
      }
      /* 1,271 more */
    ],
    "exported_at": "2026-06-08 10:00:03"
  },
  "meta": { "request_id": "3e91a561…", "timestamp": "2026-06-08T10:00:03", "version": "v1" }
}
```

### Error — `401 unauthorized`

```bash
curl -s $API/api/v1/assets/export
```

```json
{ "error": { "code": "unauthorized", "message": "Missing bearer token", "request_id": "…", "details": { "http_status": 401 } } }
```

## 3.9 GET `/api/v1/assets/export.csv` — bulk CSV export

Scope: `assets:read`. Success: **200** (`text/csv`).
This is the **one** endpoint that bypasses the JSON envelope — useful for
Excel/Power BI import.

### Request

```bash
acurl -o assets.csv $API/api/v1/assets/export.csv
head -3 assets.csv
```

### Success — `200 OK` (response body)

```
Asset Code,Name,Category,Condition,State,Location,Assigned To,IR Number,Department,Assignment Date,Retrieval Flag,Serial Number
NRS-EV-FAL-FAP-00001,Fire Alarm Panel,ELV Systems,good,active,HQ - GF - Mail Room,,,,,NO,
NRS-EV-FAL-RAP-00001,Fire Alarm Repeater Panel,ELV Systems,good,active,HQ - GF - Mail Room,,,,,NO,
```

### Error — `401 unauthorized`

```bash
curl -s $API/api/v1/assets/export.csv
```

```json
{ "error": { "code": "unauthorized", "message": "Missing bearer token", "request_id": "7671de38…", "details": { "http_status": 401 } } }
```

---

# §4 — Locations

`generic.location` — 1,166 nodes (zones → states → cities → 415 FIRS
offices → HQ floors/rooms).

## 4.1 GET `/api/v1/locations` — list locations

Scope: `locations:read`. Success: **200**.

Filters: `q`, `type_id`, `parent_id`, `country_id`, `state_id`,
`location_type`, `active`, `has_coordinates`, `limit`, `cursor`.

### Request

```bash
acurl "$API/api/v1/locations?q=Lagos&limit=5"
```

### Success — `200 OK`

```json
{
  "data": [
    {
      "id": 138,
      "name": "Lagos",
      "type": null,
      "location_type": null,
      "description": null,
      "parent_id": 133,
      "parent_path": "133/138/",
      "active": true,
      "address": { "street": null, "street2": null, "zip": null, "city": null, "state": null, "country": null },
      "coordinates": { "latitude": 6.5244, "longitude": 3.3792 },
      "extras": { "zone_code": null, "floor_number": null, "building_id": null },
      "partner_id": null,
      "child_count": 83,
      "child_all_count": 83,
      "created_at": "2026-05-24T18:40:03.837991",
      "updated_at": "2026-05-24T18:40:03.837991",
      "created_by": { "id": 1, "name": "OdooBot" },
      "updated_by": { "id": 1, "name": "OdooBot" }
    }
    /* 4 more */
  ],
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" },
  "pagination": { "next_cursor": "eyJsYXN0X2lkIjoxNDJ9", "previous_cursor": null, "total_estimate": 17 }
}
```

### Cursor pagination

```bash
# Page 1
acurl "$API/api/v1/locations?limit=3"
# → "next_cursor": "eyJsYXN0X2lkIjozfQ"

# Page 2 — use the returned cursor
acurl "$API/api/v1/locations?limit=3&cursor=eyJsYXN0X2lkIjozfQ"
```

### Error — `401 unauthorized` (bad token)

```bash
curl -s -H 'Authorization: Bearer not-a-real-token' "$API/api/v1/locations"
```

```json
{ "error": { "code": "unauthorized", "message": "Invalid token", "request_id": "d37ce508…", "details": { "http_status": 401 } } }
```

## 4.2 GET `/api/v1/locations/<id>` — get single location

Scope: `locations:read`. Success: **200**.
Optional: `?include=children,ancestors`.

### Request

```bash
acurl "$API/api/v1/locations/1?include=children,ancestors"
```

### Success — `200 OK`

```json
{
  "data": {
    "id": 1,
    "name": "North Central",
    "parent_id": null,
    "parent_path": "1/",
    "active": true,
    "child_count": 8,
    "child_all_count": 108,
    "children": [
      { "id": 2, "name": "Benue" },
      { "id": 162, "name": "FCT" },
      { "id": 6, "name": "FCT Abuja" },
      { "id": 13, "name": "Kogi" }
      /* … */
    ],
    "ancestors": [],
    "created_at": "2026-05-24T18:40:03.837991",
    "updated_at": "2026-05-24T18:40:03.837991"
  },
  "meta": { "request_id": "950014913a9d4e60…", "timestamp": "…", "version": "v1" }
}
```

### Error — `404 not_found`

```bash
acurl "$API/api/v1/locations/99999999"
```

```json
{ "error": { "code": "not_found", "message": "Location 99999999 not found", "request_id": "6cd57290…", "details": { "http_status": 404 } } }
```

## 4.3 POST `/api/v1/locations` — create location

Scope: `locations:write`. Success: **201**.
Idempotent via `Idempotency-Key`.

### Request

```bash
acurl -X POST $API/api/v1/locations \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-create-loc-001' \
  -d '{
    "name": "HQ - 2F - Boardroom",
    "parent_id": 890,
    "description": "Executive boardroom, NRS HQ floor 2",
    "latitude": 9.0579,
    "longitude": 7.4951
  }'
```

### Success — `201 Created`

```json
{
  "data": {
    "id": 1167,
    "name": "HQ - 2F - Boardroom",
    "type": null,
    "location_type": null,
    "description": "Executive boardroom, NRS HQ floor 2",
    "parent_id": 890,
    "parent_path": "890/1167/",
    "active": true,
    "address": { "street": null, "street2": null, "zip": null, "city": null, "state": null, "country": null },
    "coordinates": { "latitude": 9.0579, "longitude": 7.4951 },
    "extras": { "zone_code": null, "floor_number": null, "building_id": null },
    "partner_id": null,
    "child_count": 0,
    "child_all_count": 0,
    "created_at": "2026-06-08T10:00:04.123456",
    "updated_at": "2026-06-08T10:00:04.123456",
    "created_by": { "id": 2, "name": "Administrator" },
    "updated_by": { "id": 2, "name": "Administrator" }
  },
  "meta": { "request_id": "1088e0d2…", "timestamp": "…", "version": "v1" }
}
```

### Error — `400 invalid_request` (missing name)

```bash
acurl -X POST $API/api/v1/locations \
  -H 'Content-Type: application/json' \
  -d '{"description":"no name"}'
```

```json
{ "error": { "code": "invalid_request", "message": "`name` is required", "request_id": "af2f61fa…", "details": { "http_status": 400 } } }
```

## 4.4 PATCH `/api/v1/locations/<id>` — partial update

Scope: `locations:write`. Success: **200**.

### Request

```bash
acurl -X PATCH $API/api/v1/locations/480 \
  -H 'Content-Type: application/json' \
  -d '{
    "description": "Updated description after refurb",
    "active": true
  }'
```

### Success — `200 OK`

```json
{
  "data": {
    "id": 480,
    "name": "pytest-loc-1779648617",
    "description": "Updated description after refurb",
    "parent_id": null,
    "active": true,
    "created_at": "2026-05-24T18:50:17.413779",
    "updated_at": "2026-06-08T10:00:05.000000",
    "created_by": { "id": 2, "name": "Administrator" },
    "updated_by": { "id": 2, "name": "Administrator" }
  },
  "meta": { "request_id": "9a103fdc…", "timestamp": "…", "version": "v1" }
}
```

### Error — `404 not_found`

```bash
acurl -X PATCH $API/api/v1/locations/99999999 \
  -H 'Content-Type: application/json' -d '{"description":"x"}'
```

```json
{ "error": { "code": "not_found", "message": "Location 99999999 not found", "request_id": "…", "details": { "http_status": 404 } } }
```

## 4.5 GET `/api/v1/locations/<id>/children` — direct children

Scope: `locations:read`. Success: **200**. Not paginated (assumes
fan-out < 200).

### Request

```bash
acurl "$API/api/v1/locations/1/children"
```

### Success — `200 OK`

```json
{
  "data": [
    { "id": 2, "name": "Benue", "parent_id": 1, "parent_path": "1/2/", "child_count": 8, "child_all_count": 8, "active": true /* …all standard location fields */ },
    { "id": 162, "name": "FCT", "parent_id": 1, "parent_path": "1/162/", "child_count": 46, "child_all_count": 46, "active": true /* … */ },
    { "id": 6, "name": "FCT Abuja", "parent_id": 1, "parent_path": "1/6/", "child_count": 5, "child_all_count": 5, "active": true /* … */ }
    /* … */
  ],
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `404 not_found`

```bash
acurl "$API/api/v1/locations/99999999/children"
```

```json
{ "error": { "code": "not_found", "message": "Location 99999999 not found", "request_id": "…", "details": { "http_status": 404 } } }
```

## 4.6 GET `/api/v1/locations/<id>/ancestors` — root → parent chain

Scope: `locations:read`. Success: **200**.

### Request

```bash
acurl "$API/api/v1/locations/3/ancestors"
```

### Success — `200 OK`

```json
{
  "data": [
    { "id": 1, "name": "North Central", "parent_id": null, "parent_path": "1/", "child_count": 8, "child_all_count": 108, "active": true /* … */ },
    { "id": 2, "name": "Benue", "parent_id": 1, "parent_path": "1/2/", "child_count": 8, "child_all_count": 8, "active": true /* … */ }
  ],
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `404 not_found`

```bash
acurl "$API/api/v1/locations/99999999/ancestors"
```

```json
{ "error": { "code": "not_found", "message": "Location 99999999 not found", "request_id": "…", "details": { "http_status": 404 } } }
```

## 4.7 GET `/api/v1/locations/<id>/descendants` — full subtree (paginated)

Scope: `locations:read`. Success: **200**.

### Request

```bash
acurl "$API/api/v1/locations/1/descendants?limit=5"
```

### Success — `200 OK`

```json
{
  "data": [
    { "id": 2, "name": "Benue", "parent_id": 1, "parent_path": "1/2/", "child_count": 8, "child_all_count": 8 /* … */ },
    { "id": 3, "name": "Makurdi", "parent_id": 2, "parent_path": "1/2/3/", "child_count": 0 /* … */ },
    { "id": 4, "name": "Gboko", "parent_id": 2, "parent_path": "1/2/4/", "child_count": 0 /* … */ },
    { "id": 5, "name": "Otukpo", "parent_id": 2, "parent_path": "1/2/5/", "child_count": 0 /* … */ },
    { "id": 6, "name": "FCT Abuja", "parent_id": 1, "parent_path": "1/6/", "child_count": 5 /* … */ }
  ],
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" },
  "pagination": { "next_cursor": "eyJsYXN0X2lkIjo2fQ", "previous_cursor": null, "total_estimate": 108 }
}
```

### Error — `404 not_found`

```bash
acurl "$API/api/v1/locations/99999999/descendants"
```

```json
{ "error": { "code": "not_found", "message": "Location 99999999 not found", "request_id": "…", "details": { "http_status": 404 } } }
```

---

# §5 — Requests (Service Desk / ITSM)

`request.request` — the ITSM ticket model. References are
`KIND-MMYYYY-SEQUENCE` (e.g. `INCIDENT-062026-0000003`).

## 5.1 GET `/api/v1/requests` — list requests

Scope: `requests:read`. Success: **200**.

Filters: `q`, `type_id`, `category_id`, `stage_id`, `user_id`, `priority`,
`closed`, `location_id`, `asset_id`, `limit`, `cursor`.

### Request

```bash
acurl "$API/api/v1/requests?category_id=5&priority=3&closed=false&limit=5"
```

### Success — `200 OK`

```json
{
  "data": [
    {
      "id": 1,
      "reference": "INCIDENT-052026-0000001",
      "type": { "id": 1, "name": "Incident" },
      "category": { "id": 5, "name": "Electrical" },
      "stage": { "id": 1, "name": "Draft", "code": "draft", "type_code": null, "closed": false },
      "kanban_state": "normal",
      "priority": "3",
      "impact": false,
      "urgency": false,
      "active": true,
      "subject": "<p>UPS in Bldg A failed overnight</p>",
      "request_text": "<p>UPS in Bldg A failed overnight</p>",
      "response_text": null,
      "author": { "id": 3, "name": "Administrator" },
      "assignee": null,
      "partner": null,
      "service": null,
      "parent_id": null,
      "tags": [],
      "deadline_date": null,
      "dates": { "created": "2026-06-08T09:55:01", "assigned": null, "moved": null, "closed": null },
      "location": null,
      "vehicle": null,
      "asset": { "id": 1, "name": "pytest-asset-1779648617" },
      "created_at": "2026-06-08T09:55:01",
      "updated_at": "2026-06-08T09:55:01"
    }
    /* 4 more */
  ],
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" },
  "pagination": { "next_cursor": "eyJsYXN0X2lkIjo2fQ", "previous_cursor": null, "total_estimate": 4 }
}
```

### Error — `401 unauthorized`

```bash
curl -s "$API/api/v1/requests"
```

```json
{ "error": { "code": "unauthorized", "message": "Missing bearer token", "request_id": "…", "details": { "http_status": 401 } } }
```

## 5.2 GET `/api/v1/requests/<id>` — get single request

Scope: `requests:read`. Success: **200**.
Optional: `?include=routes,events,messages`.

### Request

```bash
acurl "$API/api/v1/requests/2?include=routes"
```

### Success — `200 OK`

```json
{
  "data": {
    "id": 2,
    "reference": "INCIDENT-052026-0000002",
    "type": { "id": 1, "name": "Incident" },
    "category": { "id": 5, "name": "Electrical" },
    "stage": { "id": 1, "name": "Draft", "code": "draft", "type_code": null, "closed": false },
    "kanban_state": "normal",
    "priority": "2",
    "subject": "<p>pytest fixture request created at 2026-05-24T18:50:19.183310+00:00Z</p>",
    "request_text": "<p>pytest fixture request created at 2026-05-24T18:50:19.183310+00:00Z</p>",
    "author": { "id": 3, "name": "Administrator" },
    "assignee": null,
    "asset": { "id": 1, "name": "pytest-asset-1779648617" },
    "available_routes": [
      { "id": 1, "name": "New", "from_stage": { "id": 1, "name": "Draft" }, "to_stage": { "id": 2, "name": "New" } }
    ],
    "created_at": "2026-05-24T18:50:19.180004",
    "updated_at": "2026-05-24T18:50:19.245677"
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `404 not_found`

```bash
acurl "$API/api/v1/requests/99999999"
```

```json
{ "error": { "code": "not_found", "message": "Request 99999999 not found", "request_id": "…", "details": { "http_status": 404 } } }
```

## 5.3 GET `/api/v1/requests/by-reference/<reference>` — lookup by reference

Scope: `requests:read`. Success: **200**. Useful for support handoffs
("ticket INCIDENT-052026-0000002").

### Request

```bash
acurl "$API/api/v1/requests/by-reference/INCIDENT-052026-0000002"
```

### Success — `200 OK`

Same shape as `GET /api/v1/requests/<id>`.

### Error — `404 not_found`

```bash
acurl "$API/api/v1/requests/by-reference/NO-SUCH-REF"
```

```json
{ "error": { "code": "not_found", "message": "No request with reference 'NO-SUCH-REF'", "request_id": "633b8f83…", "details": { "http_status": 404 } } }
```

## 5.4 POST `/api/v1/requests` — create request

Scope: `requests:write`. Success: **201**. Idempotent via
`Idempotency-Key`. Auto-generates `reference`, picks the initial stage
from the request type.

### Request

```bash
acurl -X POST $API/api/v1/requests \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-create-req-001' \
  -d '{
    "type_id": 1,
    "category_id": 5,
    "priority": "3",
    "request_text": "<p>UPS in Bldg A failed overnight</p>",
    "location_id": 891,
    "nrs_asset_id": 124
  }'
```

### Success — `201 Created`

```json
{
  "data": {
    "id": 5,
    "reference": "INCIDENT-062026-0000005",
    "type": { "id": 1, "name": "Incident" },
    "category": { "id": 5, "name": "Electrical" },
    "stage": { "id": 1, "name": "Draft", "code": "draft", "type_code": null, "closed": false },
    "kanban_state": "normal",
    "priority": "3",
    "subject": "<p>UPS in Bldg A failed overnight</p>",
    "request_text": "<p>UPS in Bldg A failed overnight</p>",
    "author": { "id": 3, "name": "Administrator" },
    "asset": { "id": 124, "name": "Fire Alarm Panel" },
    "available_routes": [
      { "id": 1, "name": "New", "from_stage": { "id": 1, "name": "Draft" }, "to_stage": { "id": 2, "name": "New" } }
    ],
    "_warnings": { "rejected_fields": ["location_id"] },
    "created_at": "2026-06-08T10:00:06",
    "updated_at": "2026-06-08T10:00:06"
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

> **Note on `_warnings.rejected_fields`** — the API accepted the
> request but silently dropped `location_id` because that field isn't on
> `request.request` in this schema version. The response tells you which
> input keys were ignored so you can fix your client.

### Error — `400 invalid_request` (missing required type_id)

```bash
acurl -X POST $API/api/v1/requests \
  -H 'Content-Type: application/json' \
  -d '{"category_id": 5, "request_text": "<p>x</p>"}'
```

```json
{ "error": { "code": "invalid_request", "message": "`type_id` is required", "request_id": "…", "details": { "http_status": 400 } } }
```

## 5.5 PATCH `/api/v1/requests/<id>` — partial update

Scope: `requests:write`. Success: **200**.
**Stage changes are rejected** here — use `/transition` for those.

### Request

```bash
acurl -X PATCH $API/api/v1/requests/2 \
  -H 'Content-Type: application/json' \
  -d '{
    "response_text": "<p>Engineer dispatched — ETA 30 min</p>",
    "priority": "4"
  }'
```

### Success — `200 OK`

Same shape as `GET /api/v1/requests/<id>`, with updated fields.

### Error — `400 invalid_request` (attempted stage change)

```bash
acurl -X PATCH $API/api/v1/requests/2 \
  -H 'Content-Type: application/json' \
  -d '{"stage_id": 4}'
```

```json
{
  "error": {
    "code": "invalid_request",
    "message": "Stage changes must go through POST /api/v1/requests/<id>/transition",
    "request_id": "…",
    "details": { "http_status": 400 }
  }
}
```

## 5.6 POST `/api/v1/requests/<id>/assign` — assign to a user

Scope: `requests:write`. Success: **200**. `user_id: null` unassigns.

### Request

```bash
acurl -X POST $API/api/v1/requests/2/assign \
  -H 'Content-Type: application/json' \
  -d '{"user_id": 2}'
```

### Success — `200 OK`

```json
{
  "data": {
    "assignee": { "id": 2, "name": "Administrator" },
    "request": {
      "id": 2,
      "reference": "INCIDENT-052026-0000002",
      "stage": { "id": 1, "name": "Draft", "code": "draft", "closed": false },
      "priority": "4",
      "assignee": { "id": 2, "name": "Administrator" },
      "dates": { "created": "2026-05-24T18:50:19", "assigned": "2026-06-08T10:00:07", "moved": null, "closed": null }
      /* full request record */
    }
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `404 not_found` (user doesn't exist)

```bash
acurl -X POST $API/api/v1/requests/2/assign \
  -H 'Content-Type: application/json' \
  -d '{"user_id": 99999999}'
```

```json
{ "error": { "code": "not_found", "message": "User 99999999 not found", "request_id": "…", "details": { "http_status": 404 } } }
```

## 5.7 POST `/api/v1/requests/<id>/transition` — move along the stage graph

Scope: `requests:write`. Success: **200**. Pass either `route_id`
(stage route) **or** `to_stage_id` (target stage, route auto-resolved).

### Request

```bash
acurl -X POST $API/api/v1/requests/2/transition \
  -H 'Content-Type: application/json' \
  -d '{"route_id": 1}'
```

### Success — `200 OK`

```json
{
  "data": {
    "transitioned_to": { "id": 2, "name": "New" },
    "request": {
      "id": 2,
      "reference": "INCIDENT-052026-0000002",
      "stage": { "id": 2, "name": "New", "code": "new", "closed": false },
      "dates": { "created": "2026-05-24T18:50:19", "assigned": "2026-06-08T10:00:07", "moved": "2026-06-08T10:00:08", "closed": null }
      /* full request record */
    }
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `400 invalid_request` (route doesn't apply to current stage)

```bash
# route_id=99 doesn't start at the request's current stage
acurl -X POST $API/api/v1/requests/2/transition \
  -H 'Content-Type: application/json' \
  -d '{"route_id": 99}'
```

```json
{
  "error": {
    "code": "invalid_request",
    "message": "Route 99 is not valid from the request's current stage",
    "request_id": "…",
    "details": { "http_status": 400 }
  }
}
```

## 5.8 POST `/api/v1/requests/<id>/comment` — add a comment

Scope: `requests:write`. Success: **200**. Internal vs public toggle via
`internal` flag. Posts through `mail.thread` so Odoo subscribers get
notified.

### Request

```bash
acurl -X POST $API/api/v1/requests/2/comment \
  -H 'Content-Type: application/json' \
  -d '{
    "body": "<p>Engineer onsite, isolating the affected breaker</p>",
    "internal": false
  }'
```

### Success — `200 OK`

```json
{
  "data": {
    "comment": { "id": 716, "internal": false, "subtype": "mail.mt_comment" },
    "request_id": 2,
    "request_reference": "INCIDENT-052026-0000002"
  },
  "meta": { "request_id": "88be5f54…", "timestamp": "…", "version": "v1" }
}
```

### Error — `400 invalid_request` (empty body)

```bash
acurl -X POST $API/api/v1/requests/2/comment \
  -H 'Content-Type: application/json' \
  -d '{"body": ""}'
```

```json
{ "error": { "code": "invalid_request", "message": "`body` is required", "request_id": "…", "details": { "http_status": 400 } } }
```

---

# §6 — Dashboards (8 endpoints, all GET, scope `dashboards:read`)

Pre-aggregated payloads consumed by the Odoo webclient AND any external
BI tool — the API just exposes the same compute function the UI calls.

## 6.1 GET `/api/v1/dashboard/kpis` — operations dashboard KPIs

```bash
acurl $API/api/v1/dashboard/kpis
```

### Success — `200 OK`

```json
{
  "data": {
    "fleet": { "total": 1609, "overdue": 0, "due_soon": 0, "ok": 1609, "no_schedule": 0 },
    "locations": { "total": 1166, "mapped": 1166 },
    "requests": { "open": 4, "maintenance": 0, "today": 0 },
    "vendors": { "total": 0, "approved": 0 }
  },
  "meta": { "request_id": "be056ab8…", "timestamp": "…", "version": "v1" }
}
```

### Error — `403 forbidden` (token missing `dashboards:read`)

```bash
# A token whose scopes don't include dashboards:read
acurl $API/api/v1/dashboard/kpis
```

```json
{ "error": { "code": "forbidden", "message": "Missing required scope: dashboards:read", "request_id": "…", "details": { "http_status": 403, "required_scope": "dashboards:read" } } }
```

## 6.2 GET `/api/v1/dashboard/map` — operations map data

```bash
acurl $API/api/v1/dashboard/map
```

### Success — `200 OK`

```json
{
  "data": {
    "locations": [
      { "id": 891, "name": "HQ - GF - Mail Room", "lat": 9.0579, "lng": 7.4951, "asset_count": 13 }
      /* … */
    ],
    "fleet": [
      { "id": 1, "plate": "FIRS191", "lat": 9.0579, "lng": 7.4951, "status": "ok" }
      /* … */
    ],
    "recent_requests": []
  },
  "meta": { "request_id": "5334e131…", "timestamp": "…", "version": "v1" }
}
```

### Error — `401 unauthorized`

```bash
curl -s $API/api/v1/dashboard/map
```

```json
{ "error": { "code": "unauthorized", "message": "Missing bearer token", "request_id": "…", "details": { "http_status": 401 } } }
```

## 6.3 GET `/api/v1/dashboard/fleet-command` — fleet command tab payload

```bash
acurl $API/api/v1/dashboard/fleet-command
```

### Success — `200 OK`

```json
{
  "data": {
    "kpis": { "total": 1609, "overdue": 0, "due_soon": 0, "ok": 1609, "idle": 0, "no_location": 691, "unassigned": 0, "vendors": 0 },
    "by_location": [
      { "location": "HQ", "count": 2152 },
      { "location": "FCT", "count": 1538 }
    ],
    "by_make": [
      { "make": "Toyota", "count": 850 },
      { "make": "Innoson", "count": 75 }
    ],
    "by_status": [
      { "status": "OK / Active", "count": 1609, "color": "#28a745" },
      { "status": "Due Soon", "count": 0, "color": "#ffc107" },
      { "status": "Overdue", "count": 0, "color": "#dc3545" },
      { "status": "No Schedule", "count": 0, "color": "#6c757d" }
    ],
    "vendors": [],
    "compliance": [],
    "recent_maint": [],
    "driver_stats": { "total_drivers": 782, "unassigned": 691, "assigned": 918 }
  },
  "meta": { "request_id": "de63f2c4…", "timestamp": "…", "version": "v1" }
}
```

### Error — `401 unauthorized`

Same shape as 6.2.

## 6.4 GET `/api/v1/security/kpis` — security KPIs

```bash
acurl $API/api/v1/security/kpis
```

### Success — `200 OK`

```json
{
  "data": {
    "incidents": { "open": 0, "critical": 0, "high": 0, "today": 0, "this_week": 0 },
    "guards": { "total": 0, "on_duty": 0 },
    "access": { "today_in": 0, "today_out": 0, "flagged": 0 }
  },
  "meta": { "request_id": "3c3983c1…", "timestamp": "…", "version": "v1" }
}
```

### Error — `401 unauthorized`

```bash
curl -s $API/api/v1/security/kpis
```

```json
{ "error": { "code": "unauthorized", "message": "Missing bearer token", "request_id": "…", "details": { "http_status": 401 } } }
```

## 6.5 GET `/api/v1/security/map-data` — security map markers

```bash
acurl $API/api/v1/security/map-data
```

### Success — `200 OK`

```json
{
  "data": {
    "incidents": [],
    "guards": [],
    "locations": []
  },
  "meta": { "request_id": "4b425018…", "timestamp": "…", "version": "v1" }
}
```

### Error

`401 unauthorized` — same shape as 6.4.

## 6.6 GET `/api/v1/security/trend` — incident trend (weekly)

```bash
acurl $API/api/v1/security/trend
```

### Success — `200 OK`

```json
{
  "data": {
    "weekly": [
      { "label": "W18", "count": 0 },
      { "label": "W19", "count": 0 },
      { "label": "W20", "count": 0 },
      { "label": "W21", "count": 0 },
      { "label": "W22", "count": 0 },
      { "label": "W23", "count": 0 },
      { "label": "W24", "count": 0 },
      { "label": "W25", "count": 0 }
    ]
  },
  "meta": { "request_id": "dfeaa203…", "timestamp": "…", "version": "v1" }
}
```

### Error

`401 unauthorized` — same shape as 6.4.

## 6.7 GET `/api/v1/security/recent` — recent security incidents

```bash
acurl $API/api/v1/security/recent
```

### Success — `200 OK`

```json
{
  "data": [],
  "meta": { "request_id": "bd212632…", "timestamp": "…", "version": "v1" }
}
```

(Empty array when no incidents are open; otherwise an array of summarized
request records with `priority`, `reference`, `location`, `created_at`.)

### Error

`401 unauthorized` — same shape as 6.4.

## 6.8 GET `/api/v1/fleet/dashboard` — fleet maintenance dashboard

```bash
acurl $API/api/v1/fleet/dashboard
```

### Success — `200 OK`

```json
{
  "data": {
    "kpis": { "total": 1609, "active": 1609, "ok": 1609, "due_soon": 0, "overdue": 0, "expiring_insurance": 0, "expiring_roadworthy": 0, "staff_buses": 0, "vendors": 0, "approved_vendors": 0 },
    "vehicles": [],
    "state_counts": {},
    "fuel_counts": {},
    "maintenance": []
  },
  "meta": { "request_id": "15df8b99…", "timestamp": "…", "version": "v1" }
}
```

### Error

`401 unauthorized` — same shape as 6.4.

## 6.9 GET `/api/v1/fm/dashboard` — Facilities Management dashboard (the home page)

```bash
acurl $API/api/v1/fm/dashboard
```

### Success — `200 OK`

```json
{
  "data": {
    "kpis": { "open": 0, "overdue": 0, "escalated": 0, "in_progress": 0, "resolved_today": 0 },
    "sla_data": [
      { "domain": "Building Services", "open": 0, "overdue": 0, "escalated": 0, "sla_pct": 100 },
      { "domain": "Plant & Machinery", "open": 0, "overdue": 0, "escalated": 0, "sla_pct": 100 },
      { "domain": "Plumbing", "open": 0, "overdue": 0, "escalated": 0, "sla_pct": 100 },
      { "domain": "Security", "open": 0, "overdue": 0, "escalated": 0, "sla_pct": 100 },
      { "domain": "Fleet", "open": 0, "overdue": 0, "escalated": 0, "sla_pct": 100 }
    ],
    "recent_requests": [],
    "team_workload": [],
    "overdue_list": [],
    "map_locations": [
      { "name": "General Register House", "lat": 55.9533, "lng": -3.1883, "request_count": 0 },
      { "name": "New Register House", "lat": 55.9537, "lng": -3.188, "request_count": 0 }
    ]
  },
  "meta": { "request_id": "dcebece6…", "timestamp": "…", "version": "v1" }
}
```

### Error

`401 unauthorized` — same shape as 6.4.

---

# §7 — Barcode & tag lookup (5 endpoints)

For the handheld scan-station workflow and the public-style tag portal.

## 7.1 GET `/api/v1/barcode/lookup?query=<q>` — find asset by tag

Scope: `assets:read`. Success: **200**.

### Request

```bash
acurl "$API/api/v1/barcode/lookup?query=HQ-GF-MR-EV-001"
```

### Success — `200 OK`

```json
{
  "data": {
    "found": true,
    "asset_id": 124,
    "asset_code": "NRS-EV-FAL-FAP-00001",
    "asset_name": "Fire Alarm Panel",
    "tag_number": "HQ-GF-MR-EV-001",
    "tag_id": 124,
    "category": "ELV Systems",
    "subcategory": "Fire Alarm",
    "location": "HQ - GF - Mail Room",
    "condition": "good",
    "state": "active",
    "last_service_date": null,
    "next_service_date": null,
    "custodian": null
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `400 invalid_request` (empty query)

```bash
acurl "$API/api/v1/barcode/lookup"
```

```json
{ "error": { "code": "invalid_request", "message": "`query` parameter is required", "request_id": "…", "details": { "http_status": 400 } } }
```

## 7.2 GET `/api/v1/barcode/kpis` — scan-station KPIs

Scope: `assets:read`. Success: **200**.

```bash
acurl $API/api/v1/barcode/kpis
```

### Success — `200 OK`

```json
{
  "data": {
    "total_assets": 1272,
    "active_tags": 1272,
    "pending_replacement": 0,
    "scrapped_tags": 0,
    "untagged": 0
  },
  "meta": { "request_id": "21d27c00…", "timestamp": "…", "version": "v1" }
}
```

### Error

`401 unauthorized` — see 6.4.

## 7.3 GET `/api/v1/barcode/recent-tags?domain_filter=&limit=` — recently scanned/printed

Scope: `assets:read`. Success: **200**.

```bash
acurl "$API/api/v1/barcode/recent-tags?limit=5"
```

### Success — `200 OK`

```json
{
  "data": [
    {
      "tag_id": 124,
      "tag_number": "HQ-GF-MR-EV-001",
      "tag_state": "active",
      "asset_id": 124,
      "asset_name": "Fire Alarm Panel",
      "domain": "elv",
      "location": "HQ - GF - Mail Room",
      "condition": "good"
    },
    {
      "tag_id": 123,
      "tag_number": "HQ-GF-MR-FF-001",
      "tag_state": "active",
      "asset_id": 123,
      "asset_name": "Fire Extinguisher (CO2)",
      "domain": "fire",
      "location": "HQ - GF - Mail Room",
      "condition": "good"
    }
    /* 3 more */
  ],
  "meta": { "request_id": "69ffd818…", "timestamp": "…", "version": "v1" }
}
```

### Error

`401 unauthorized` — see 6.4.

## 7.4 GET `/api/v1/barcode/print-url?tag_id=<id>&size=<size>` — Zebra print URL

Scope: `assets:read`. Success: **200**.
`size` ∈ `small | medium | large`.

```bash
acurl "$API/api/v1/barcode/print-url?tag_id=124&size=medium"
```

### Success — `200 OK`

```json
{
  "data": { "url": "/report/pdf/myservice_asset_register/action_report_asset_tag/124" },
  "meta": { "request_id": "cc4d94c0…", "timestamp": "…", "version": "v1" }
}
```

### Error — `400 invalid_request` (missing tag_id)

```bash
acurl "$API/api/v1/barcode/print-url?size=medium"
```

```json
{ "error": { "code": "invalid_request", "message": "`tag_id` parameter is required", "request_id": "…", "details": { "http_status": 400 } } }
```

## 7.5 GET `/api/v1/tags/lookup?query=<q>` — portal-style lookup

Scope: `assets:read`. Success: **200**.
Less data than `/barcode/lookup` — designed for the public tag portal.

```bash
acurl "$API/api/v1/tags/lookup?query=HQ-GF-MR-EV-001"
```

### Success — `200 OK`

```json
{
  "data": {
    "found": true,
    "tag_number": "HQ-GF-MR-EV-001",
    "asset_name": "Fire Alarm Panel",
    "category": "ELV Systems",
    "location": "HQ - GF - Mail Room",
    "condition": "good",
    "state": "active",
    "last_service_date": ""
  },
  "meta": { "request_id": "6ce29f11…", "timestamp": "…", "version": "v1" }
}
```

### Success — `200 OK` (not found — returns `found:false`, not 404)

```bash
acurl "$API/api/v1/tags/lookup?query=NO-SUCH-TAG"
```

```json
{
  "data": { "found": false, "tag_number": "NO-SUCH-TAG" },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `401 unauthorized`

```bash
curl -s "$API/api/v1/tags/lookup?query=HQ-GF-MR-EV-001"
```

```json
{ "error": { "code": "unauthorized", "message": "Missing bearer token", "request_id": "…", "details": { "http_status": 401 } } }
```

---

# §8 — Homepage (public form helpers)

## 8.1 GET `/api/v1/home/form-data` — dropdowns for the public form

Scope: `requests:read`. Success: **200**.

```bash
acurl $API/api/v1/home/form-data
```

### Success — `200 OK`

```json
{
  "data": {
    "services": [
      { "id": 6, "name": "Access Control" },
      { "id": 2, "name": "Building Operations" },
      { "id": 3, "name": "Cleaning & Janitorial" },
      { "id": 10, "name": "Driver Management" },
      { "id": 13, "name": "Fleet Operations" }
      /* 10 more */
    ],
    "request_types": [
      { "id": 1, "name": "Incident", "service_id": null }
      /* … */
    ],
    "locations": [
      { "id": 90, "name": "Aba", "parent_id": 88, "parent_name": "Abia" },
      { "id": 11, "name": "Abaji", "parent_id": 6, "parent_name": "FCT Abuja" },
      { "id": 97, "name": "Abakaliki", "parent_id": 96, "parent_name": "Ebonyi" }
      /* 1,163 more */
    ]
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error

`401 unauthorized` — see 6.4.

## 8.2 POST `/api/v1/home/quick-submit` — submit a request from the homepage

Scope: `requests:write`. Success: **201**. Idempotent via
`Idempotency-Key`.

### Request

```bash
acurl -X POST $API/api/v1/home/quick-submit \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-quicksubmit-001' \
  -d '{
    "name": "Adamu Bello",
    "email": "adamu.bello@firs.gov.ng",
    "phone": "+2348000000000",
    "subject": "AC not cooling in 4F open plan",
    "description": "Started yesterday, ~10 staff affected"
  }'
```

### Success — `201 Created`

```json
{
  "data": {
    "request_id": 6,
    "reference": "INCIDENT-062026-0000006",
    "stage": { "id": 1, "name": "Draft", "code": "draft" }
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `400 invalid_request` (missing required fields)

```bash
acurl -X POST $API/api/v1/home/quick-submit \
  -H 'Content-Type: application/json' \
  -d '{"email": "adamu.bello@firs.gov.ng"}'
```

```json
{ "error": { "code": "invalid_request", "message": "`name`, `subject`, and `description` are required", "request_id": "…", "details": { "http_status": 400 } } }
```

---

# §9 — Integrations (2 endpoints, scope `integrations:write`)

Inbound webhooks for upstream systems.

## 9.1 POST `/api/v1/integrations/sap/employee-sync` — SAP SuccessFactors employee event

Scope: `integrations:write`. Success: **200**.
Accepted statuses: `active`, `terminated`, `on_leave`.

### Request

```bash
acurl -X POST $API/api/v1/integrations/sap/employee-sync \
  -H 'Content-Type: application/json' \
  -d '{
    "ir_number": "FIRS-12345",
    "userId": "adaobi.eze@firs.gov.ng",
    "firstName": "Adaobi",
    "lastName": "Eze",
    "department": "ICT",
    "jobTitle": "Senior Manager",
    "status": "active",
    "officeCode": "HQ"
  }'
```

### Success — `200 OK`

```json
{
  "data": {
    "ir_number": "FIRS-12345",
    "employee_id": 717,
    "partner_id": 5234,
    "action": "created",
    "status": "active"
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

(Subsequent calls with the same `ir_number` return `"action": "updated"`.)

### Error — `400 invalid_request` (missing IR number)

```bash
acurl -X POST $API/api/v1/integrations/sap/employee-sync \
  -H 'Content-Type: application/json' \
  -d '{"userId":"x@firs.gov.ng","firstName":"X","lastName":"Y","status":"active"}'
```

```json
{ "error": { "code": "invalid_request", "message": "`ir_number` is required", "request_id": "…", "details": { "http_status": 400 } } }
```

## 9.2 POST `/api/v1/integrations/workflow/callback` — external workflow decision

Scope: `integrations:write`. Success: **200**.
Outcomes: `approved`, `rejected`, `queried`.

### Request

```bash
acurl -X POST $API/api/v1/integrations/workflow/callback \
  -H 'Content-Type: application/json' \
  -d '{
    "reference": "INCIDENT-052026-0000002",
    "workspace_ref": "CAMUNDA-PROC-INST-7821",
    "outcome": "approved",
    "comment": "Approved by FM Manager — proceed with vendor dispatch"
  }'
```

### Success — `200 OK`

```json
{
  "data": {
    "applied_outcome": "approved",
    "request_reference": "INCIDENT-052026-0000002"
  },
  "meta": { "request_id": "a23f1717…", "timestamp": "…", "version": "v1" }
}
```

### Error — `400 invalid_request` (bad outcome)

```bash
acurl -X POST $API/api/v1/integrations/workflow/callback \
  -H 'Content-Type: application/json' \
  -d '{"reference":"INCIDENT-052026-0000002","outcome":"definitely-not-a-real-outcome"}'
```

```json
{
  "error": {
    "code": "invalid_request",
    "message": "Unknown outcome 'definitely-not-a-real-outcome'",
    "request_id": "4b4c0f27…",
    "details": { "allowed_outcomes": ["approved", "rejected", "queried"], "http_status": 400 }
  }
}
```

### Error — `404 not_found` (reference doesn't exist)

```bash
acurl -X POST $API/api/v1/integrations/workflow/callback \
  -H 'Content-Type: application/json' \
  -d '{"reference":"NO-SUCH-REQUEST-12345","outcome":"approved"}'
```

```json
{
  "error": {
    "code": "not_found",
    "message": "Request 'NO-SUCH-REQUEST-12345' not found",
    "request_id": "c8723619…",
    "details": { "http_status": 404 }
  }
}
```

---

# Cross-cutting behaviours worth showing in the demo

## Idempotency

Any POST that creates a resource (`/assets`, `/locations`, `/requests`,
`/home/quick-submit`, `/assets/<id>/move`, etc.) accepts an
`Idempotency-Key` header. The first call creates; the second call with
the **same key** returns the **original** response even if the body
differs.

```bash
# First call — creates record id=481
acurl -X POST $API/api/v1/locations \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-idem-001' \
  -d '{"name":"Idem demo loc","description":"first call"}'

# Second call with SAME key but DIFFERENT body — returns id=481 with the
# ORIGINAL "first call" description; the second body is silently ignored
acurl -X POST $API/api/v1/locations \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-idem-001' \
  -d '{"name":"SHOULD-BE-IGNORED","description":"second call"}'
```

## Pagination (cursor-based)

Default `limit=50`, max `200`. Pass `?total=0` to skip the count query on
huge tables.

```bash
# Page 1
acurl "$API/api/v1/locations?limit=3"
# → "next_cursor": "eyJsYXN0X2lkIjozfQ"

# Page 2
acurl "$API/api/v1/locations?limit=3&cursor=eyJsYXN0X2lkIjozfQ"
```

## Scope enforcement

A token without `dashboards:read` calling `/api/v1/dashboard/kpis` gets:

```json
{ "error": { "code": "forbidden", "message": "Missing required scope: dashboards:read", "request_id": "…", "details": { "http_status": 403, "required_scope": "dashboards:read" } } }
```

This is the difference between **401 unauthorized** (token absent or
invalid) and **403 forbidden** (token valid but missing a required scope).

## All 13 scopes

`assets:read`, `assets:write`, `locations:read`, `locations:write`,
`requests:read`, `requests:write`, `approvals:write`, `dashboards:read`,
`integrations:write`, `ingestion:write`, `webhooks:admin`, `identity:read`,
`admin`.

## CORS / auth header

- Every authenticated endpoint expects `Authorization: Bearer <jwt>`
- `Idempotency-Key` is optional but recommended on every POST that creates
  state
- `Content-Type: application/json` on bodies; the API doesn't accept
  form-encoded payloads on JSON endpoints

---

# Demo cheat-sheet (paste into a fresh terminal)

```bash
# 0. Choose environment
API=https://staging.app.cadra.ng
export CLIENT_SECRET='<paste from docs/api/.creds>'

# 1. Get a token
TOKEN=$(curl -sX POST $API/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"test_client","client_secret":"'"$CLIENT_SECRET"'"}' \
  | jq -r .data.access_token)
echo "Token: ${TOKEN:0:32}…"

# 2. Authenticated helper
acurl() { curl -sS -H "Authorization: Bearer $TOKEN" "$@"; }

# 3. Five-call smoke test
acurl $API/api/v1/assets?limit=1                          | jq '.data[0].asset_code'
acurl $API/api/v1/locations?limit=1                       | jq '.data[0].name'
acurl $API/api/v1/requests?limit=1                        | jq '.data[0].reference'
acurl $API/api/v1/fm/dashboard                            | jq '.data.kpis'
acurl $API/api/v1/openapi.json                            | jq '.paths | keys | length'   # → 45
```

---

# Endpoint index (alphabetical inside groups)

| # | Method | Path | Scope |
|---|---|---|---|
| 1 | POST   | `/api/v1/auth/token` | (none) |
| 2 | GET    | `/api/v1/openapi.json` | (none) |
| 3 | GET    | `/api/v1/docs` | (none) |
| 4 | GET    | `/api/v1/assets` | `assets:read` |
| 5 | GET    | `/api/v1/assets/<id>` | `assets:read` |
| 6 | GET    | `/api/v1/assets/by-tag/<tag>` | `assets:read` |
| 7 | POST   | `/api/v1/assets` | `assets:write` |
| 8 | PATCH  | `/api/v1/assets/<id>` | `assets:write` |
| 9 | POST   | `/api/v1/assets/<id>/move` | `assets:write` |
| 10 | POST   | `/api/v1/assets/<id>/transfer-custody` | `assets:write` |
| 11 | GET    | `/api/v1/assets/export` | `assets:read` |
| 12 | GET    | `/api/v1/assets/export.csv` | `assets:read` |
| 13 | GET    | `/api/v1/locations` | `locations:read` |
| 14 | GET    | `/api/v1/locations/<id>` | `locations:read` |
| 15 | POST   | `/api/v1/locations` | `locations:write` |
| 16 | PATCH  | `/api/v1/locations/<id>` | `locations:write` |
| 17 | GET    | `/api/v1/locations/<id>/children` | `locations:read` |
| 18 | GET    | `/api/v1/locations/<id>/ancestors` | `locations:read` |
| 19 | GET    | `/api/v1/locations/<id>/descendants` | `locations:read` |
| 20 | GET    | `/api/v1/requests` | `requests:read` |
| 21 | GET    | `/api/v1/requests/<id>` | `requests:read` |
| 22 | GET    | `/api/v1/requests/by-reference/<ref>` | `requests:read` |
| 23 | POST   | `/api/v1/requests` | `requests:write` |
| 24 | PATCH  | `/api/v1/requests/<id>` | `requests:write` |
| 25 | POST   | `/api/v1/requests/<id>/assign` | `requests:write` |
| 26 | POST   | `/api/v1/requests/<id>/transition` | `requests:write` |
| 27 | POST   | `/api/v1/requests/<id>/comment` | `requests:write` |
| 28 | GET    | `/api/v1/dashboard/kpis` | `dashboards:read` |
| 29 | GET    | `/api/v1/dashboard/map` | `dashboards:read` |
| 30 | GET    | `/api/v1/dashboard/fleet-command` | `dashboards:read` |
| 31 | GET    | `/api/v1/security/kpis` | `dashboards:read` |
| 32 | GET    | `/api/v1/security/map-data` | `dashboards:read` |
| 33 | GET    | `/api/v1/security/trend` | `dashboards:read` |
| 34 | GET    | `/api/v1/security/recent` | `dashboards:read` |
| 35 | GET    | `/api/v1/fleet/dashboard` | `dashboards:read` |
| 36 | GET    | `/api/v1/fm/dashboard` | `dashboards:read` |
| 37 | GET    | `/api/v1/barcode/lookup` | `assets:read` |
| 38 | GET    | `/api/v1/barcode/kpis` | `assets:read` |
| 39 | GET    | `/api/v1/barcode/recent-tags` | `assets:read` |
| 40 | GET    | `/api/v1/barcode/print-url` | `assets:read` |
| 41 | GET    | `/api/v1/tags/lookup` | `assets:read` |
| 42 | GET    | `/api/v1/home/form-data` | `requests:read` |
| 43 | POST   | `/api/v1/home/quick-submit` | `requests:write` |
| 44 | POST   | `/api/v1/integrations/sap/employee-sync` | `integrations:write` |
| 45 | POST   | `/api/v1/integrations/workflow/callback` | `integrations:write` |
