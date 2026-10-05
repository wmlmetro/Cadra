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
`server_misconfigured` (500, and **503** on
`POST /integrations/workflow/callback` for a tenant with no WorkSpace
configuration).

**A field a route does not accept is refused — a 400, and nothing is
written.** Since 21 September 2026. Each of the eleven write routes that
filter a body of fields against an allow-list — assets, locations, requests, asset categories (create and update),
the two settings routes, and `approve-disposal`, which takes none — answers:

```json
{ "error": { "code": "invalid_request",
    "message": "This route does not accept: `asset_tag`. Nothing was written.",
    "details": { "rejected_fields": ["asset_tag"], "writable": ["…every key this route accepts…"], "http_status": 400 } } }
```

Not the refused field, and **not the accepted fields sent beside it**: on a
create, no record; on a `PATCH`, no change. `details.writable` is there so a
caller can repair itself from the response. On `/requests` it is what THIS
deployment's model can store, which can be narrower than the list in this
document where a field depends on a module that is not installed; on every
other route it is the route's allow-list. **A refusal does not use up the idempotency key:** errors are never
stored under one, so a corrected body sent under the same key succeeds.

**Thirteen routes since 22 September 2026.** The two that CREATE records by
handing the body to a function that reads what it knows —
`POST /home/quick-submit` and `POST /integrations/sap/employee-sync` — answer
the same way now (§8.2, §9.1). They were missed on the 21st because the
eleven were found by searching for routes that declare a list of accepted
fields, and neither of these has one.

**Still not covered, and said so you need not find out:** the ACTION routes,
which read the keys they know and ignore the rest — `/move`, `/verify`,
`/mark-missing`, `/mark-found`, `/condemn`, `/transfer-custody`,
`/tag-affixed`, and a request's `/assign`, `/transition` and `/comment`.
Their bodies are arguments to an act rather than fields of a record, and
whether they should refuse a stray key is not ruled.

Until that date these routes answered 2xx, wrote what they recognised,
dropped the rest, and named the dropped keys in
`data._warnings.rejected_fields`, which no longer exists. `CHANGELOG.md` has
the route-by-route table and the reasons.

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
    "refresh_token": "x7mE…opaque-not-a-jwt…",
    "refresh_token_expires_in": 2592000,
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

## 1.2 POST `/api/v1/auth/refresh` — rotate a refresh token for a fresh pair

Auth: **none** (the refresh token is the credential).
Success: **200**.

Issued by both `/auth/token` and `/auth/login`. The refresh token is an
opaque, server-side, **single-use** string (not a JWT) with a 30-day sliding
window — each refresh rotates it and resets the window. Use it to get a new
access token when the old one nears expiry, without re-sending credentials.

**Rotation + theft detection.** The presented token is revoked and replaced by
its successor on every call. Replaying an already-used token is treated as
theft: the entire token family is revoked and a `401` is returned. The client
must store the newly returned `refresh_token` after each call.

### Request

```bash
curl -sX POST $API/api/v1/auth/refresh \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token": "x7mE…opaque-not-a-jwt…"}'
```

### Success — `200 OK`

```json
{
  "data": {
    "token_type": "Bearer",
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9…",
    "expires_in": 3600,
    "refresh_token": "q3Zb…new-rotated-token…",
    "refresh_token_expires_in": 2592000,
    "scope": "assets:read assets:write …"
  },
  "meta": { "request_id": "a1b2c3…", "timestamp": "2026-06-17T12:00:00", "version": "v1" }
}
```

### Error — `401 unauthorized` (unknown / expired / revoked / replayed)

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Invalid or expired refresh token",
    "request_id": "9f8e7d…",
    "details": { "http_status": 401 }
  }
}
```

## 1.3 POST `/api/v1/auth/revoke` — log out (kill a refresh-token family)

Auth: **none**. Success: **200** (always).

Revokes the presented refresh token and its whole rotation family. Idempotent
and constant-response: an unknown token still returns `200 {"revoked": true}`,
so the endpoint never reveals whether a token existed. Outstanding access
tokens remain valid until their short TTL elapses; this only stops further
refresh.

### Request

```bash
curl -sX POST $API/api/v1/auth/revoke \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token": "q3Zb…"}'
```

### Success — `200 OK`

```json
{
  "data": { "revoked": true },
  "meta": { "request_id": "c4d5e6…", "timestamp": "2026-06-17T12:05:00", "version": "v1" }
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

Every asset payload carries a `financial.depreciation` object (PRD §8.6):

```json
{
  "method": "straight_line",
  "useful_life_months": 60,
  "declining_rate": null,
  "salvage_value": 240000.0,
  "depreciable_cost": 2400000.0,
  "start_date": "2022-06-15",
  "start_date_source": "acquisition",
  "start_date_is_estimated": false,
  "accumulated_depreciation": 1764000.0,
  "current_book_value": 636000.0,
  "state": "depreciating",
  "end_date": "2027-06-30",
  "uses_category_policy": false
}
```

`method` is one of `none | straight_line | declining_balance | erp_managed`.
For `erp_managed` the figures are supplied by the tenant's ERP and Cadra
does not compute them (NRS spec §6.2).

## 3.1 GET `/api/v1/assets` — list assets

Scope: `assets:read`. Success: **200**.

Filters: `q`, `category_id`, `location_id`, `building_id`, `custodian_id`,
`state`, `condition`, `domain`, `is_verified`, `grn_reference`,
`purchase_order_reference`, `purchase_vendor`, `import_source`,
`import_ref`, `warranty_status`, `warranty_expires_within_days`,
`limit` (default 50, max 200), `cursor`. The two warranty filters are
described under **Warranty** in §3.4.

`condition` is one of `new | good | fair | poor | decommissioned`.
`state` is one of `active | in_repair | disposed | transferred | missing`.

The five provenance filters match **exactly**, not fuzzily —
`?grn_reference=GRN-2026-00001` returns the assets that goods receipt
produced and nothing else, which is what makes it usable as an audit
trail. `q` also searches `grn_reference` and `purchase_order_reference`
so a pasted reference finds its assets from the search box.

**Exact means byte-exact** — case-sensitive, whitespace-significant, no
prefix matching. `?grn_reference=GRN-2026-0001` does not match
`GRN-2026-00011` or `grn-2026-0001`. A writing system must send the GRN in
the same form it will later query by, or the lookup returns zero rows with
no other signal. Use `q` for a forgiving search.

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
Idempotent via `X-Idempotency-Key` header — same key → same record.
`asset_code` auto-generated from category if omitted.

> **Breaking change (2026-09-05): `asset_tag` is no longer writable.** It was
> accepted on `POST` and `PATCH`; from that date it landed in
> `data._warnings.rejected_fields` and was ignored, and **since 21 September
> 2026 sending it is a 400 and nothing is written** (*Conventions*, above). The tag number is the number
> printed on the physical label, and a client that can edit it can walk the
> record away from the sticker on the asset — defeating the affix check in
> §3.8, which then returns a `400` that looks like the scanner's fault. Tags
> are minted by Cadra and change only through the tag-replacement flow, which
> prints a new label and takes a fresh affix confirmation.
>
> Announced rather than versioned: Vendra is the only live consumer and does
> not write this field. The same drift path is closed in the bulk import
> wizard, which no longer rewrites `asset_tag` on an existing asset.

> **Breaking change (2026-09-21): `building_id`, `floor_id` and `room_id` are
> no longer writable**, on `POST` or `PATCH`. Sending one is a 400 and
> nothing is written (*Conventions*, above). They never moved an asset: on the Odoo
> form they drive `location_id` through a rule the API does not run, so a
> `PATCH` of `building_id` answered 200, rewrote the building — and the
> published address and coordinates, which are computed from it — and left
> `location_id` where it was. Write `location_id`, or use §3.6. All three are
> still published under `data.location_hierarchy` and are still list filters.

> **`data.tag` is deprecated** (marked `deprecated: true` on
> `components.schemas.Asset` in `/api/v1/openapi.json`). It is still returned
> and will stay returned — breaking a published field to fix a naming problem
> is not a trade worth making with a live consumer. It holds the tag *number*,
> allocated at creation, so it has never answered "is there a label on this
> asset". Use `data.tagging.is_tagged` for that and `data.tagging.tag_number`
> for the number.

### Request

```bash
acurl -X POST $API/api/v1/assets \
  -H 'Content-Type: application/json' \
  -H 'X-Idempotency-Key: demo-create-asset-001' \
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

Re-running the same `X-Idempotency-Key` with **different** body returns the
**original** record (the second body is ignored).

### Acquisition provenance (INT-03)

A create may carry where the asset came from. All six fields are writable on
`POST` and `PATCH`, and come back under `data.provenance`:

| Field | Type | Meaning |
|---|---|---|
| `grn_reference` | string | Goods Receipt Note that brought the asset onto the register |
| `purchase_order_reference` | string | Purchase Order it was procured against |
| `purchase_vendor` | string | Supplier it was bought from — **not** `maintenance_vendor_id`, which is who services it |
| `import_source` | enum | `myservice \| sap \| redhubb \| vendra \| excel \| other` — which system wrote the record |
| `import_date` | date | When that system wrote it |
| `import_ref` | string | That system's own batch or transaction reference |

```bash
acurl -X POST $API/api/v1/assets \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Dell Latitude 7430",
    "category_id": 7,
    "grn_reference": "GRN-2026-00001",
    "purchase_order_reference": "PO-2026-00417",
    "purchase_vendor": "Dell Nigeria Ltd",
    "import_source": "vendra",
    "import_date": "2026-05-12",
    "import_ref": "VENDRA-RCPT-00114"
  }'
```

```json
{
  "data": {
    "id": 1274,
    "provenance": {
      "grn_reference": "GRN-2026-00001",
      "purchase_order_reference": "PO-2026-00417",
      "purchase_vendor": "Dell Nigeria Ltd",
      "import_source": "vendra",
      "import_date": "2026-05-12",
      "import_ref": "VENDRA-RCPT-00114"
    }
  }
}
```

They are correctable via `PATCH` but write-once in practice: they record an
event that already happened. Read them back with
`GET /api/v1/assets?grn_reference=GRN-2026-00001`.

### Warranty — from 19.0.3.12.0 (handoff 34)

Optional, and absent on almost every asset: an asset with no warranty is
the ordinary case, not a gap. Five writable fields on `POST` and `PATCH`,
published back under `data.warranty` **under the same names**:

| Field | Type | Meaning |
|---|---|---|
| `warranty_months` | integer 1–600 | How long it runs, as quoted — `24` for two years |
| `warranty_start_date` | date | The day it runs from — usually the day of receipt |
| `warranty_expiry` | date | The last day it covers. **Derived** when the two above are sent |
| `warrantor` | string | **Who honours it** — manufacturer, supplier or agent — a name as recorded, not a link |
| `warranty_reference` | string | The certificate or document number to quote |

**Send a duration and a start date; do not send the expiry.** With both,
Cadra works the expiry out (calendar months; 24 months from 12 March 2026 is
12 March 2028). Rules, each a `400 validation_failed` with nothing written:

- `warranty_months` without `warranty_start_date`, or the reverse — half a basis;
- a `warranty_months` that is not a whole number from 1 to 600;
- a `warranty_expiry` that contradicts the start date and duration sent or
  already on the asset. The same date is accepted.

A bare `warranty_expiry` with no start or duration is accepted, for whoever
holds only a date, and `basis` says so. Adding a start and a duration to such
an asset replaces that date with the derived one (the old date stays in the
history). Clearing the start and the duration clears an expiry that was
derived from them.

The block can be sent back **unchanged**. Change the duration or the start
and leave `warranty_expiry` out: the date you read is the answer to the old
basis and now contradicts the new one.

```bash
acurl -X POST $API/api/v1/assets -H 'Content-Type: application/json' \
  -d '{"name": "Dell Latitude 7430", "category_id": 7,
       "warranty_start_date": "2026-05-12", "warranty_months": 24,
       "warrantor": "Dell Nigeria Ltd", "warranty_reference": "DL-WC-55120"}'
```

```json
"warranty": {
  "status": "under_warranty",
  "status_as_of": "2026-09-22",
  "warranty_expiry": "2028-05-12",
  "warranty_start_date": "2026-05-12",
  "warranty_months": 24,
  "warrantor": "Dell Nigeria Ltd",
  "warranty_reference": "DL-WC-55120",
  "basis": "24 months from 2026-05-12"
}
```

`status` is `under_warranty` through the expiry day itself, `expired`
after it, and `none` where no expiry is recorded — **never folded into
`expired`** (a warrantor or a certificate number may still be). It is judged against `status_as_of`, a **Lagos** day (UTC+1),
and moves with the calendar with no write to the record. `basis` is how the
expiry was reached, in words. `dates.warranty_expiry` still publishes the
same column.

**A warranty says nothing about whether the asset is in service.** It is
not a condition, a lifecycle state or a review status, and no count on this
API treats it as one.

**Filters on `GET /api/v1/assets`:**
`?warranty_status=under_warranty|expired|none` — every row returned
publishes the same `warranty.status`; and
`?warranty_expires_within_days=N` (1–3650) — an expiry from today to
today + N, both inclusive and both Lagos days, so never an expired one. A
value outside those is `400 invalid_request`, never the whole register.

**Every change is recorded** as an append-only `warranty_changed` event in
`GET /assets/<id>/history`, with the value before and after. Creating an
asset with a warranty records none — an event is a change.

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
    "condition": "poor",
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

## 3.5.1 What may be done to a disposed asset

**Disposal is terminal, and the rule is in the model — so it holds on every
route, not only the ones that say so.** Since 21 September 2026:

| On a DISPOSED asset | Answer |
|---|---|
| change `state` to anything else — `PATCH` | **400** `validation_failed` |
| change `location_id` or `custodian_id` — `PATCH` | **400** `validation_failed` |
| `POST …/move`, `POST …/transfer-custody` | **400** `validation_failed` |
| `POST …/mark-missing`, `POST …/condemn` | **409** `conflict` |
| re-send the SAME `state`, `location_id` or `custodian_id` | 200 |
| edit the disposal paperwork, `notes`, anything else writable | 200 |
| `POST …/approve-disposal` | 200 |
| **`POST …/verify`** | **200 — allowed, by ruling.** A disposed asset somebody physically finds on the premises is an audit finding, and a register that refuses to record *"I saw it, today"* is suppressing the one fact that matters |

Every refusal is a plain sentence naming the asset, and **writes nothing**.
There is no route that reverses a disposal. `POST /assets` may still
register an asset as already `disposed`.

**Becoming disposed, by any route, sets the condition and the date.** Since
21 September 2026 a write that takes an asset into `disposed` —
`PATCH {"state": "disposed"}` as much as §3.6.3 — sets `condition =
decommissioned` and, where the asset has no `disposal_date` and the request
sent none, stamps the server's Lagos day. A date the caller sends is kept; a
`condition` sent beside `state: disposed` is overridden. An asset REGISTERED
as already disposed is not stamped: it was disposed of on a day this system
never saw. What `PATCH` still cannot carry is the REASON — that is §3.6.3.

Until this date a disposed asset could be marked missing, which overwrote
`disposed` and returned it to the register with a 200.

## 3.5.2 Nobody moves an asset alone — from 19.0.3.13.0 (handoff 35)

**On a tenant where approval is required, a move and a custody change need a
second person, and `PATCH` cannot make either** — a move or a handover, that
is. Clearing a location or a custodian is neither, and still saves. Whether this tenant requires
it is `GET /api/v1/settings/approvals` (§11.7). **Absent means required**, so
a tenant nobody has configured is a tenant that asks for an approver.

The rule is on the asset model, underneath every writer of `location_id` and
`custodian_id` — twelve and thirteen of them respectively — and not in the
three routes below. That is why a `PATCH` is refused as well as a `/move`.

| Through the API, on a tenant that requires approval | Answer |
|---|---|
| `POST …/move` with `approver_id` | **200**, `data.pending_approval: true`, asset UNCHANGED (§3.6) |
| `POST …/move` without `approver_id` | **400** `invalid_request`, `details.approvers` lists who may be asked |
| `POST …/transfer-custody` | the same (§3.7) |
| `PATCH` a `location_id` or `custodian_id` to a **different value** | **400** `invalid_request`, **nothing in the call is written** |
| `PATCH` a `location_id` or `custodian_id` with the value it already has | **200** — the edit form re-sends every field on every save |
| `PATCH` `location_id` or `custodian_id` to **`null`** | **200 — allowed.** Clearing hands the asset to nobody; it is not a grant, and it is still recorded |
| `PATCH` anything else | unchanged |
| a second request while one is pending on the asset | **409** `conflict`, `details.pending_request` names the one in the way |

### The PATCH refusal

```bash
acurl -X PATCH $API/api/v1/assets/124 \
  -H 'Content-Type: application/json' \
  -d '{"location_id": 905, "notes": "moved during the reshuffle"}'
```

```json
{
  "error": {
    "code": "invalid_request",
    "message": "This register requires a second person to approve a change of `location_id`, so it cannot be PATCHed: use POST /api/v1/assets/124/move, which raises a request. Nothing in this call was written.",
    "request_id": "…",
    "details": {
      "asset_id": 124,
      "approval_required": true,
      "rejected_fields": ["location_id"],
      "writable": ["…every other writable key…"],
      "use_instead": { "location_id": "POST /api/v1/assets/124/move" },
      "http_status": 400
    }
  }
}
```

**`notes` was not written either.** A `PATCH` carries a whole object;
applying half of it and refusing the other half would leave the caller with a
save they cannot reason about, so the body is refused whole — the contract
handoff 31 published for every write route.

### Clearing is not a grant, and is not refused

`PATCH {"custodian_id": null}` and `PATCH {"location_id": null}` still work
on a tenant that requires approval. Taking an asset back from somebody, or
off a location, hands it to nobody, and there is no second person to ask
about an asset returning to the store — the same argument the register's
employee-departure routine already makes.

**It is not a way round the rule.** Going from nobody to somebody, or from
nowhere to somewhere, IS a grant and IS refused, so dropping an asset and
then placing it is two calls that get a caller exactly what one would: the
second is refused. Both calls are recorded in the append-only movement and
custody records either way.

Refusing it was the first draft's behaviour and was a dead end rather than a
control: the message named `POST …/transfer-custody`, and that route answers
*"`to_custodian_id` is required"* — so un-assigning a custodian had become
impossible through the API, having worked for the register's whole life.

## 3.6 POST `/api/v1/assets/<id>/move` — move to a new location

Scope: `assets:write`. Success: **200**. Idempotent.

**A move leaves two records, and they are not worth the same.** The MOVE is
appended to `nrs.asset.movement`, which nobody can edit or delete — that is
the audit trail, and it is written by the asset model underneath every writer
of `location_id`, so a `PATCH` of `location_id` is recorded too. This route
additionally creates an `nrs.asset.transfer` row: a process document, in
state `done`, which an asset manager can edit or delete afterwards. It used
to be described here as the audit trail. It never was.

`reason`, when sent, must be a string (400 `invalid_request` otherwise), and
**every refusal on this route happens before anything is written.**

**From 19.0.3.13.0, on a tenant that requires approval (§3.5.2) this route
does not move the asset.** It raises a request and answers **200** with
`data.pending_approval: true`, the request, and `data.asset` UNCHANGED —
read back from the database in the same response. `approver_id` becomes
required. `data.movement_id` and `data.transfer` are **`null`**, explicitly,
because that is what this call did NOT produce.

**Read `data.pending_approval`, not the status code.** It stays 200: this API
has no per-call success status, and giving one route a 202 would have to be
carried through the idempotency cache as well or a replay of the same
`X-Idempotency-Key` would answer 202 once and 200 afterwards.

**An asset with NO current location is placed, not transferred.** A transfer
document needs both ends, so none is made: `data.transfer` is **`null`**,
`location_id` is set, and the movement record holds the placement (no `from`;
the history shows it as *"Placed at …"*). `data.movement_id` is at the top
level on every response for that reason — it is the one record this route
always produces. Until 2026-09-21 this case answered 400 *"Required field
missing: from_location_id"*, and such an asset could not be placed here at
all.

### Request — where approval is NOT required

```bash
acurl -X POST $API/api/v1/assets/124/move \
  -H 'Content-Type: application/json' \
  -d '{
    "to_location_id": 905,
    "reason": "Reshuffle after Q2 audit"
  }'
```

### Success — `200 OK`, the asset has moved

```json
{
  "data": {
    "asset": { "id": 124, "asset_code": "NRS-EV-FAL-FAP-00001", "current_location": { "id": 905, "name": "HQ - 1F - Server Room" }, "condition": "good", "state": "active", "...": "full asset record" },
    "movement_id": 3301,
    "transfer": { "id": 17, "reference": "TRF/2026/0017", "from_location": { "id": 891, "name": "HQ - GF - Mail Room" }, "to_location": { "id": 905, "name": "HQ - 1F - Server Room" }, "movement_id": 3301 }
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `400 invalid_request` (same-location move forbidden)

Whichever way the tenant is configured: this is refused at the door, and no
request is raised for it either.

*This section said `422 unprocessable` until handoff 28 and had never been
true: the route has always answered 400. Corrected against a live response.*

```bash
# Asset 124 is already at location 891 — move-to-self rejected
acurl -X POST $API/api/v1/assets/124/move \
  -H 'Content-Type: application/json' \
  -d '{"to_location_id": 891, "reason": "no-op"}'
```

```json
{ "error": { "code": "invalid_request", "message": "Asset is already at the requested location", "request_id": "…", "details": { "current_location_id": 891, "http_status": 400 } } }
```

### Request — where approval is required

```bash
acurl -X POST $API/api/v1/assets/124/move \
  -H 'Content-Type: application/json' \
  -d '{
    "to_location_id": 905,
    "approver_id": 12,
    "reason": "Reshuffle after Q2 audit"
  }'
```

### Success — `200 OK`, and the asset has not moved

```json
{
  "data": {
    "pending_approval": true,
    "action": "move",
    "request": {
      "id": 41,
      "reference": "CR/2026/0041",
      "state": "pending",
      "change_type": "location",
      "approver": { "id": 12, "name": "Ngozi Bello" },
      "requested_by": { "id": 8, "name": "Tunde Alabi" },
      "requested_at": "2026-09-22T11:04:19",
      "to_location": { "id": 905, "name": "HQ - 1F - Server Room" },
      "to_custodian": null,
      "reason": "Reshuffle after Q2 audit"
    },
    "asset": { "id": 124, "current_location": { "id": 891, "name": "HQ - GF - Mail Room" }, "...": "UNCHANGED" },
    "movement_id": null,
    "transfer": null,
    "custody_change": null
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `400 invalid_request` (no approver named)

```bash
acurl -X POST $API/api/v1/assets/124/move \
  -H 'Content-Type: application/json' -d '{"to_location_id": 905}'
```

```json
{
  "error": {
    "code": "invalid_request",
    "message": "This register requires a second person to approve a change of this kind, so `approver_id` is required: name who you are asking. GET /api/v1/approvals/approvers lists who may be asked.",
    "request_id": "…",
    "details": {
      "asset_id": 124,
      "approval_required": true,
      "approvers": [ { "id": 12, "name": "Ngozi Bello" }, { "id": 19, "name": "Sade Okonkwo" } ],
      "http_status": 400
    }
  }
}
```

The other four refusals of `approver_id`: **400** *"`approver_id` must be an
integer"*, **404 `not_found`** if the user does not exist, **400** *"You
cannot ask yourself to approve your own change. Name somebody else."*, and
**400** if the person named could not have made the change themselves.

### Error — `409 conflict` (something is already waiting on this asset)

```json
{
  "error": {
    "code": "conflict",
    "message": "CR/2026/0041 is already waiting for approval on this asset — Tunde Alabi asked Ngozi Bello on 2026-09-22. Decide or withdraw that one first.",
    "request_id": "…",
    "details": {
      "asset_id": 124,
      "pending_request": {
        "id": 41, "reference": "CR/2026/0041", "change_type": "location",
        "requested_by": { "id": 8, "name": "Tunde Alabi" },
        "approver": { "id": 12, "name": "Ngozi Bello" }
      },
      "http_status": 409
    }
  }
}
```

## 3.6.1 POST `/api/v1/assets/<id>/verify` — record a verification, and who made it

Scope: `assets:write`. Success: **200**. Idempotent.

```bash
acurl -X POST $API/api/v1/assets/124/verify \
  -H 'Content-Type: application/json' \
  -d '{"notes": "Sighted at desk 4F-12, tag intact"}'
```

```json
{
  "data": {
    "asset": { "id": 124, "is_verified": true, "last_verified_by": { "id": 31, "name": "Adaobi Eze" }, "...": "full asset record" },
    "verification": { "verified_on": "2026-09-20", "verified_by": { "id": 31, "name": "Adaobi Eze" }, "notes": "Sighted at desk 4F-12, tag intact" },
    "event_id": 5120
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

**It takes no date and no verifier.** The date is today and the verifier is
the ACTING user — the person logged in, or the API client's own user. `notes`
is optional and describes THIS verification: when absent,
`verification_notes` is cleared rather than left carrying the previous
verifier's words.

**Why this exists beside `PATCH`.** `last_verified_date` is writable by
`PATCH`, and `last_verified_by` deliberately is not: a verifier a client can
name is a claim, not evidence. So a `PATCH` of the date records a day and
nobody — **and clears any verifier already there**, because a date that
arrives without a person has none, and leaving the old name beside the new
date would say somebody checked who did not. Until handoff 28 that PATCH is
what the Cadra app's own Verify button sent. Use `PATCH` to carry a verification made in another system; use this
route to make one.

**Every call is kept.** The asset itself holds ONE verifier and one date,
overwritten by the next verification. Since 21 September 2026 each call also
appends a record nobody can edit or delete, and `data.event_id` is the one
this call wrote — including a second call on the same day, which changes no
date and used to leave nothing. `GET /assets/<id>/history` lists them as
`verified` events graded `append_only`: *every time this asset was checked,
and by whom.*

**A `PATCH` of the date is a different fact, and is listed as one.** It
appears as `verification_date_set`, not `verified`: somebody wrote a date,
and the record does not say that anybody checked the asset.

**What it does not reach.** A verification made before 21 September 2026 is
still only a line in the message log (`evidence: "chatter"`), deletable by
anyone who can edit the asset. `fidelity.events` in the history gives the
instant, per database.

`last_verified_by` is published on every asset. **Null means nobody is
recorded, not that nobody checked.**

## 3.6.2 POST `/api/v1/assets/<id>/mark-missing` — mark an asset missing, and record why

Scope: `assets:write`. Success: **200**. Idempotent.

```bash
acurl -X POST $API/api/v1/assets/124/mark-missing \
  -H 'Content-Type: application/json' \
  -d '{"reason": "Not found at desk 4F-12 during the Q3 verification exercise; last sighted 2026-06-30."}'
```

```json
{ "data": { "asset": { "id": 124, "state": "missing", "...": "full asset record" }, "event_id": 5121 },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" } }
```

**The reason is an API feature.** The Odoo form's *Mark Missing* and *Condemn* buttons ask for none, so a status change made there is recorded with who and when and no reason.

**`reason` is required.** An asset that cannot be found may be a loss, and
*why* is the first question anybody asks. The reason is **not a field on the
asset**: it is kept on the `status_changed` event `event_id` names, which
nobody can edit or delete, and is published as `detail.reason` in
`GET /assets/<id>/history`.

`PATCH {"state": "missing"}` still works, and still records no reason — a
`PATCH` has nowhere to put a sentence. **Missing is not terminal:** an asset
that turns up is §3.6.4, which records where.

| Status | Code | When |
|---|---|---|
| 400 | `invalid_request` | `reason` absent, blank, or not a string |
| 404 | `not_found` | no such asset |
| 409 | `conflict` | already `missing`; or `disposed` — see §3.5.1 |

## 3.6.3 POST `/api/v1/assets/<id>/condemn` — dispose of an asset

Scope: `assets:write`. Success: **200**. Idempotent.

```bash
acurl -X POST $API/api/v1/assets/124/condemn \
  -H 'Content-Type: application/json' \
  -d '{"reason": "Beyond economic repair — motherboard failure, BER report ICT/2026/114."}'
```

Answers `{asset, disposal, event_id}`; `disposal` is the block every asset
publishes as `data.disposal`.

**It takes no date.** `state = disposed`, `condition = decommissioned` and
`disposal_date` are set together, on the server. **The date is a Lagos day**
— UTC+01:00, fixed, the same day the register snapshot cuts on — and not the
calling credential's timezone, which for an API client is unset and would
have meant UTC: every disposal made between 00:00 and 01:00 in Lagos dated
to the day before.

**`reason` is required**, and is written twice on purpose: to
`disposal_reason`, the editable paperwork the disposal report reads; and to
the `status_changed` event, which is what was said AT THE TIME and which
nobody can edit. **That event's actor is who carried the disposal out** —
which the register did not record anywhere before 21 September 2026.

**It does not approve the disposal.** That is
`POST /assets/<id>/approve-disposal`, which needs `approvals:write` — a
scope that gates nothing else, so holding it is a deliberate act.

### The date, whichever door the disposal came by — changed 22 September 2026

The rules below are in the MODEL, so they hold for `/condemn`, for
`PATCH /assets/<id> {"state": "disposed"}`, for the Odoo form and for the
importer alike.

- **A disposal is always dated.** If the caller sends no date, the register
  stamps today, in Lagos.
- **The caller's date is the one sent in the SAME request as the status.**
  A `disposal_date` PATCHed onto an asset while it was still live, with the
  status following later, is **not** the caller's date and is overwritten by
  today. `disposal_date` is writable on a live asset, so an asset given last
  year's date and disposed of this morning used to be dated last year, and
  the register said it left a year before it did. To record a date agreed in
  advance, send both together:
  ```json
  PATCH /api/v1/assets/1234
  { "state": "disposed", "disposal_date": "2026-09-15" }
  ```
- **The date cannot be taken off a disposed asset.**
  `PATCH {"disposal_date": null}` on a disposed asset is a
  **`400 validation_failed`** and nothing is written. Correcting it to
  another day is a proper act and is unchanged. A **live** asset's date can
  still be cleared, and an asset that is already undated may still be sent an
  empty date, so the edit form — which re-sends every field it displays — can
  still save a legacy row.

`disposal_date` is tracked, so a correction leaves the previous value in the
record.

| Status | Code | When |
|---|---|---|
| 400 | `invalid_request` | `reason` absent, blank, or not a string |
| 404 | `not_found` | no such asset |
| 409 | `conflict` | already disposed — disposal is terminal, §3.5.1 |

## 3.6.4 POST `/api/v1/assets/<id>/mark-found` — a missing asset turned up

Scope: `assets:write`. Success: **200**. Idempotent.

```bash
acurl -X POST $API/api/v1/assets/124/mark-found \
  -H 'Content-Type: application/json' \
  -d '{"reason": "Found in the 2nd-floor store room during the October count, tag intact."}'
```

Answers `{asset, event_id}` and sets `state` back to `active`.

***Where it turned up* is as much an audit fact as *why it went missing*.**
`reason` is required, and is kept on the `status_changed` event `event_id`
names — beside the one that says why it went — where nobody can edit it.
`PATCH {"state": "active"}` still works and records no reason. It does not
verify the asset: whoever found it may not be whoever checks it.

| Status | Code | When |
|---|---|---|
| 400 | `invalid_request` | `reason` absent, blank, or not a string |
| 404 | `not_found` | no such asset |
| 409 | `conflict` | the asset is not `missing` |

## 3.7 POST `/api/v1/assets/<id>/transfer-custody` — reassign custodian

Scope: `assets:write`. Success: **200**. Appends a link to the asset's
append-only chain of custody (§3.7.1) and posts a chatter note.

Until 9 September 2026 the chatter note WAS the audit trail. It no longer is:
a `mail.message` is deletable by any user holding the groups that let them
delete one, and the PRD requires a record that cannot be edited
retrospectively.

**From 19.0.3.13.0, on a tenant that requires approval (§3.5.2) this route
does not change custody.** It raises a request and answers **200** with
`data.pending_approval: true`, the request, and `data.asset` UNCHANGED.
`approver_id` becomes required, and `data.custody_change` is **`null`** —
no link was appended, because none was made. The same three refusals as
`/move`: 400 without an approver, 404 for a user that does not exist, 409
where a request is already pending on the asset.

```json
{
  "data": {
    "pending_approval": true,
    "action": "transfer-custody",
    "request": {
      "id": 42, "reference": "CR/2026/0042", "state": "pending",
      "change_type": "custody",
      "approver": { "id": 12, "name": "Ngozi Bello" },
      "requested_by": { "id": 8, "name": "Tunde Alabi" },
      "requested_at": "2026-09-22T11:09:02",
      "to_location": null,
      "to_custodian": { "id": 42, "name": "Adaobi Eze" },
      "reason": "Custodian handover at quarter-end"
    },
    "asset": { "id": 124, "current_custodian": null, "...": "UNCHANGED" },
    "movement_id": null,
    "transfer": null,
    "custody_change": null
  }
}
```

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
    "custody_change": { "custody_id": 5514, "message_id": 8123, "from_custodian": null, "to_custodian": { "id": 42, "name": "Adaobi Eze" }, "reason": "Custodian handover at quarter-end" }
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

## 3.7.1 GET `/api/v1/assets/<id>/custody` — the chain of custody

Scope: `assets:read`. Cursor-paginated, **oldest first**. INT-10 §2.3.

Every recorded change of custodian for one asset. **Append-only:**
`nrs.asset.custody` raises on `write` and on `unlink` on the model itself, so
a link cannot be altered or removed once recorded — not over the API, not in
the Odoo interface, and not by an administrator using `sudo()`. **There is no
write endpoint**: a link is a side effect of a custodian change, never a
payload.

### Request

```bash
acurl "$API/api/v1/assets/124/custody?limit=50"
```

### Success — `200 OK`

```json
{
  "data": [
    {
      "id": 5513,
      "changed_at": "2026-08-18T12:05:05",
      "from_custodian": null,
      "to_custodian": { "id": 15, "name": "Kunle Bello" },
      "from_custodian_name": null,
      "to_custodian_name": "Kunle Bello",
      "changed_by": { "id": 2, "name": "Administrator" },
      "changed_by_name": "Administrator",
      "reason": null,
      "source": "tracking_backfill"
    },
    {
      "id": 5514,
      "changed_at": "2026-09-09T11:02:41",
      "from_custodian": { "id": 15, "name": "Kunle Bello" },
      "to_custodian": { "id": 42, "name": "Adaobi Eze" },
      "from_custodian_name": "Kunle Bello",
      "to_custodian_name": "Adaobi Eze",
      "changed_by": { "id": 9, "name": "cadra_client_vendra" },
      "changed_by_name": "cadra_client_vendra",
      "reason": "Custodian handover at quarter-end",
      "source": "api_transfer"
    }
  ],
  "pagination": { "next_cursor": null, "previous_cursor": null, "total_estimate": 2 },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### The three fields that decide what a chain means

| Field | Why it is there |
|---|---|
| `changed_by` | **Who moved it**, which is a different question from who held it. The two custodian fields cannot answer it. |
| `from_custodian_name` / `to_custodian_name` | The names **as recorded at the time**. Not derived from the linked records: an employee deleted since is `null` in `from_custodian`/`to_custodian` and still named here. The link degrades, the evidence does not. |
| `source` | Where the change came from — `api_transfer`, `api_write`, `transfer`, `direct`, `tracking_backfill`, or `test`. |

### `tracking_backfill` — read this before drawing a conclusion

A link marked `tracking_backfill` was **reconstructed** from the Odoo chatter
tracking values that predate this model. The reconstruction is faithful:
those rows carry the outgoing employee, the incoming employee, the acting
user and the timestamp, so nothing in a backfilled link is invented.

But it **begins where `custodian_id` became a tracked field, not where the
register does.** Records seeded by direct SQL produced no tracking value and
are absent entirely. **A chain is therefore sparser than its asset is old,
and that is the honest picture rather than a defect** — an auditor told where
the record begins can work with it, one who discovers the gap later cannot
trust any of it, including the part that is complete.

### `test` — a link Cadra's own test suite wrote

Cadra's API test suite runs against live-shaped tenants and moves an asset's
custodian deliberately, because a test that does not exercise the recorder
proves nothing about whether the chain is written at all. The recorder is
append-only, so those links are **permanent** in whichever tenant the suite
ran against.

`source: "test"` is how you tell one. It is decided server-side from the
credential that made the change and can never be set by a caller — a request
saying "this one is a test" would let anybody disguise a real change of
custodian as an artefact.

Same reason `tracking_backfill` exists: a reader must be able to see what a
link is without having been told the artefacts are there.

### Neither form is capped

`GET /api/v1/assets/<id>/custody` is **exempt from the per-credential record
cap**. A client limited to the first 100 records of any one resource still
walks the entire chain with the cursor, and `total_estimate` is the true
count. A chain of custody is not a page of a register — it is one asset's
complete record, and a truncated chain cannot be told from a complete one.

The per-page ceiling still applies; it bounds one `SELECT` and is not the
commercial control.

### Embedded form

`GET /api/v1/assets/<id>?include=custody` returns the **whole** chain under
`data.custody`, uncapped. The embedded `transfers` list is capped at the last
20; this one deliberately is not, because "the last twenty custodians" cannot
be told from a complete chain and is therefore the one answer an auditor
cannot use. Use the paginated route above for a chain long enough to want
paging.

## 3.7.2 GET `/api/v1/assets/<id>/history` — what has happened to this asset

Scope: **`assets:read`**. Success: **200**. Not paged, not capped.

One ordered history of the asset, merged server-side from every place its
life leaves a mark: registration, the tag's issue, print and affix, the chain
of custody (§3.7.1), location moves, tracked field changes, the disposal
approval, events sent to SAP and the Tag-Issuing Unit, and maintenance
requests. Newest first; `?sort=oldest` reads it forwards. A `sort` outside
`newest|oldest` is a 400 `invalid_request` carrying `details.allowed_values`.

```bash
acurl "$API/api/v1/assets/124/history"
```

```jsonc
{
  "data": {
    "asset":   { "id": 124, "asset_code": "NRS-IT-000124", "name": "Dell Latitude 5440" },
    "order":   "newest_first",
    "summary": {
      "events": 6, "events_after_registration": 4,
      "by_evidence": { "append_only": 1, "system_stamp": 2, "guarded_record": 1, "editable_record": 1, "chatter": 1 },
      "reconstructed_events": 0,
      "statement": "4 recorded event(s) since registration on 2026-09-02. 1 of them rest on a record that nobody can edit or delete; the rest can be altered or removed afterwards, and each event says what its record is worth. This history is a lower bound on what happened, not a complete account of it."
    },
    "fidelity": {
      "registered_at": "2026-09-02T10:14:07.120331",
      "earliest_event_after_registration_at": "2026-09-03T08:40:12",
      "custody": { "recording_began_at": "2026-09-09T16:12:06.081420", "links": 1, "reconstructed_links": 0,
                   "first_link_at": "2026-09-11T09:02:44", "custodian_held_before_first_link": false,
                   "statement": "Changes of custodian are recorded on this system from …" },
      "evidence_grades": [ { "grade": "append_only", "meaning": "…" }, "… four more, strongest first" ],
      "not_recorded":    [ { "event": "financial_change", "statement": "A change to a cost or a value — … nothing records that it changed, when, or who changed it." }, "…" ],
      "verification": "The Verify button records who checked the asset, each time it is pressed, as an event that cannot be edited or deleted. …",
      "events": [ { "event": "verified", "recording_began_at": "2026-09-21T08:31:02", "statement": "From 2026-09-21 08:31 UTC, a verification made with the Verify button is recorded so that nobody can edit or delete it. …" }, "… three more: verification_date_set, status_changed, provenance_changed" ],
      "undated_records_omitted": 0
    },
    "events": [
      { "id": "custody_changed:nrs.asset.custody:5514", "type": "custody_changed",
        "title": "Custodian changed", "summary": "unassigned → Adaobi Eze",
        "at": "2026-09-11T09:02:44", "at_precision": "second",
        "actor": { "id": 31, "name": "Vendra (API client)" }, "actor_name": "Vendra (API client)",
        "evidence": "append_only", "reconstructed": false, "source": "api_transfer",
        "record": { "model": "nrs.asset.custody", "id": 5514 },
        "detail": { "from_custodian": null, "to_custodian": { "id": 42, "name": "Adaobi Eze" },
                    "from_custodian_name": null, "to_custodian_name": "Adaobi Eze",
                    "reason": "Custodian handover at quarter-end" } }
    ]
  }
}
```

### Read `evidence` before relying on an event

The records behind this list are not worth the same, and each event says
which it rests on. The grades are defined in the response
(`fidelity.evidence_grades`) by what somebody can **do** to the record:

| `evidence` | Meaning | Events |
|---|---|---|
| `append_only` | the application refuses to edit or delete it, for anyone | `custody_changed`; `location_moved`, for a move made since handoff 28; and — **made since handoff 30 (21 September 2026)** — `verified`, `verification_date_set`, `status_changed`, and a `provenance_changed` of the GRN reference, the purchase order reference or the SAP asset number |
| `system_stamp` | stamped when the row was created; gone if the row is deleted | `registered`, `tag_issued` |
| `guarded_record` | written from the acting user and refused to an ordinary edit; a privileged user can still rewrite it, and a tag label can be deleted by an asset manager | `tag_printed`, `tag_affixed`, `integration_event` |
| `editable_record` | an asset manager can edit or delete it, without trace | `location_moved` **made before handoff 28, when a transfer row exists**, `transfer_recorded`, `maintenance_request`, `tag_scrapped`, **`disposal_approved`** |
| `chatter` | a line in the message log that anyone able to edit the asset can delete, without trace | `condition_changed`, `disposal_recorded`, `details_changed`; a `provenance_changed` of the vendor or an import field; a `verified` that is a write of the VERIFIER alone, with no date (an asset manager can do that over XML-RPC, and it is not a verification); `status_changed`, `verified` and any other `provenance_changed` **made before handoff 30**; and `location_moved` **made before handoff 28, when no transfer row exists** |

**`disposal_approved` is `editable_record`, not more.** The approver and the
instant are absent from `_WRITABLE_FIELDS`, so no API client can name its own
approver — but both are ordinary inputs on the Odoo form. The event shows the
columns as they stand now (`detail.is_current_value`), and **a rewrite of the
approver since is listed as its own `disposal_recorded` event** carrying the
old and the new name, graded `chatter`.

**A location move is `append_only` — if it was made after handoff 28.** Every
change of `location_id` is appended to `nrs.asset.movement` by the asset
model itself, so `POST /move`, a `PATCH` of `location_id`, a completed
transfer, the Odoo form, an import and the deletion of a location all come
back as `location_moved` with `evidence: "append_only"` and a `source` saying
which door it came through. `detail.transfer` is the transfer document where
the move had one and **null where it did not — a move is not always a
transfer**, and `PATCH` still creates none. Where the document was deleted
since, `detail.transfer.id` is null and `detail.transfer.reference` is the
reference recorded with the move.

**A move made BEFORE that is reported as it always was:** `editable_record`
if a transfer row holds it, `chatter` if only the message log does. Nothing
was backfilled. `fidelity.location.recording_began_at` is the boundary, and
`fidelity.location.located_before_first_movement` is true for an asset that
was already somewhere when recording reached it — which, on a register
loaded before this release, is nearly every asset in it.

An asset created at a location opens its record there: a `location_moved`
with no `from`, summarised *"Placed at …"*. It is listed, and it is not
counted in `summary.events_after_registration` — nor is the tag or the
custody link written by the same `create`. That is the asset's opening
state, not something that happened to it.

### What the other keys promise

- **`reconstructed: true`** — recovered after the fact, not recorded when it
  happened. Today: a custody link whose `source` is `tracking_backfill`.
- **`actor`** — the user the record names; **null where it names nobody.**
  Never inferred and never filled from a created-by field that means
  something else. `actor_name` is the name as the record holds it, which
  outlives the user. A transfer row with no message-log line has a null
  actor: `detail.transfer.recorded_by` is who raised the transfer, which is
  not who moved the asset.
- **`at_precision`** — `second`, or `day` for a record that holds only a
  date. A `day` event's `at` is a bare date and it sorts at the start of that
  day, which is a placement and not a claim.
- **`type`** — a closed enum in the OpenAPI document that may GROW; a new
  type is an additive change announced in the changelog, and every event
  carries a human `title` so a consumer can display one it does not know. A
  tracked field with no type of its own arrives as `details_changed`, so a
  field that becomes tracked appears rather than being silently absent.
  `transfer_recorded` is a transfer that is NOT done (raised, approved or
  rejected) and is not a move. `integration_event` is any outbox row for this
  asset, whatever its `detail.status` — `pending` and `dead` included.
  `maintenance_request` says that a request was raised, when and by whom, to
  everybody who may read the asset. **Its reference is `detail.reference` for
  a caller that also holds `requests:read`, and `null` for one that does
  not** — and `detail.reference_withheld` says which, so that a `null` does
  not read as a request with no reference. Never its content. (Until 21
  September 2026 it was withheld from everybody, for a reason that turned
  out to be false.)
- **One act is listed once.** A change that has an `append_only` record is
  read from it, and the message-log line of the same act is folded away —
  matched by transaction, not by the clock. `verification_date_set` is a
  `last_verified_date` written by `PATCH`: a date, and nobody recorded as
  having checked. `status_changed` carries `detail.from`, `detail.to` — the
  enum KEYS — and `detail.reason`, which is where the reason given to
  `mark-missing` or `condemn` is published.
- **`fidelity.events`** — for each kind of event that has an `append_only`
  record, the instant it began to be kept ON THIS DATABASE, and a sentence.
  Per kind: they share a table and did not necessarily begin together.
- **An unmatched transfer says what its time is.** A `location_moved` read
  from a transfer row with no message-log line carries
  `detail.at_is_when_the_transfer_was_recorded: true`: for `/move` that is the
  move, for a transfer raised in Odoo and completed later it is when it was
  raised.
- **`fidelity.undated_records_omitted`** — records that hold no instant
  cannot be placed on a clock; they are left out and counted here.
- **Times are naive server time, which is UTC.**
- **`fidelity.not_recorded`** — on every response. A changed cost, and a
  changed SAP field other than the asset number, leave no record at all;
  their absence from `events` is not evidence that they did not happen. A
  changed GRN or PO reference, a changed SAP asset number, and who carried
  out a disposal are recorded **from the instant `fidelity.events` gives and
  not before**, and each statement says so.
- **`fidelity.custody`** — when custody recording began on this system, and
  `custodian_held_before_first_link`: true when the asset was already held by
  somebody the chain never saw arrive.
- **An empty history says so in words.** With nothing after registration,
  `summary.events_after_registration` is 0 and `summary.statement` begins
  *"There is no recorded history for this asset…"*. The registration event is
  still returned.

Message bodies are never published — tracked old/new values only.

## 3.8 POST `/api/v1/assets/<id>/tag-affixed` — confirm physical tagging

Scope: **`tagging:write`** (not `assets:write`). Success: **200**. Idempotent.

### Why this exists, and why `tag` is not the answer

`nrs.asset` auto-generates a tag record when the asset is created, so
`data.tag` is populated from the moment the asset exists. It says a tag
*number* was allocated. It says nothing about whether a label was ever
printed, let alone stuck on anything. Reading it as "tagged" reports every
asset as tagged the instant it is keyed in.

`data.tagging` answers the physical question:

| Field | Meaning |
|---|---|
| `is_tagged` | **The boolean to branch on.** True only after an affix confirmation |
| `label_state` | `issued` → `printed` → `affixed`, or `scrapped` |
| `tag_number` | The active label's number |
| `printed_at` / `printed_by` | When Cadra issued the print instruction, and who asked |
| `affixed_at` / `affixed_by` | When the confirmation was recorded, and which client sent it |
| `affixed_by_name` | The Tag-Issuing Unit operative who physically fitted it |

`label_state` is **not writable** through `POST`/`PATCH /assets`. The
Integration Flow makes the Tag-Issuing Unit independent of whoever created
the asset record, and a status an operator can set from a desk would be
evidence of nothing. This endpoint, under its own scope, is the only way an
asset becomes `is_tagged`.

### Request

```bash
acurl -X POST $API/api/v1/assets/124/tag-affixed \
  -H 'Content-Type: application/json' \
  -d '{
    "tag_number": "HQ-GF-MR-IT-042",
    "serial_number": "5XJZ8T3",
    "affixed_by_name": "J. Okafor",
    "affixed_at": "2026-09-14T11:32:07Z"
  }'
```

| Field | Required | Meaning |
|---|---|---|
| `tag_number` | yes | The number **read off the label on the asset**. Checked against the tag Cadra issued rather than trusted. |
| `serial_number` | no | The manufacturer serial **read off the asset**. When supplied it is checked against the serial on the record. |
| `affixed_by_name` | no | The Tag-Issuing Unit operative who fitted it. Free text — they are not Cadra users. |
| `affixed_at` | no | ISO 8601, with or without an offset. Defaults to now; supply it when confirming work recorded offline. A future timestamp is refused. |

**Send `serial_number`.** The tag check proves the label is the one Cadra
issued for this record; the serial check proves it went onto the right box.
The spec asks for the serial-to-tag match at the point of physical tagging,
and checking one side is half a control. It is optional only because a fixed
asset with no legible serial still has to be taggable — and if the record
itself has no serial on file, the endpoint says it cannot verify rather than
passing quietly.

Comparison strips whitespace and ignores case: a serial read off an engraved
plate is not case-sensitive information.

### Success — `200 OK`

```json
{
  "data": {
    "asset": { "id": 124, "...": "full asset record" },
    "tagging": {
      "tag_number": "HQ-GF-MR-IT-042",
      "label_state": "affixed",
      "is_tagged": true,
      "printed_at": "2026-09-13",
      "affixed_at": "2026-09-14T11:32:07",
      "affixed_by": { "id": 7, "name": "Tag Issuing Unit" },
      "affixed_by_name": "J. Okafor"
    }
  }
}
```

### Error — `400 validation_failed` (the tag does not match)

The control. A label from another asset, or a mis-keyed number, is refused
rather than recorded:

```json
{ "error": { "code": "validation_failed",
    "message": "Scanned tag HQ-GF-MR-IT-099 does not match the tag issued for this asset (HQ-GF-MR-IT-042). The label on the asset is not the one Cadra issued for it.",
    "details": { "http_status": 400 } } }
```

### Error — `400 validation_failed` (the serial does not match)

The other half. The label is the right label; the asset under it is not:

```json
{ "error": { "code": "validation_failed",
    "message": "Scanned serial WRONG-SERIAL does not match the serial on this asset (5XJZ8T3) — the label may be going onto the wrong asset",
    "details": { "asset_id": 124,
                 "scanned_serial": "WRONG-SERIAL",
                 "expected_serial": "5XJZ8T3",
                 "http_status": 400 } } }
```

Both serials are named, because an operative holding the wrong box needs to
know which one they should be holding. A `serial_number` sent against a record
that has none on file is refused the same way, with `expected_serial` absent
from the message and the reason given plainly.

### Finding what still needs tagging

```bash
acurl "$API/api/v1/assets?is_tagged=false&limit=50"      # not yet confirmed
acurl "$API/api/v1/assets?tag_label_state=printed"       # printed, not affixed
```

---

## 3.9 GET `/api/v1/assets/export` — bulk JSON export

Scope: `export:read` (since handoff 50, **BREAKING** — it took `assets:read`
until 2026-10-04; taking a copy of the register is its own permission, held
by the Auditor and the Administrator). Success: **200**. Returns every
asset; no pagination.
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

Scope: `export:read` (since handoff 50, **BREAKING** — see the JSON twin
above). Success: **200** (`text/csv`).
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

## 3.10 GET `/api/v1/assets/<id>/depreciation` — depreciation schedule

Scope: `assets:read`. Success: **200**.
Optional: `?as_of=YYYY-MM-DD` for a point-in-time view (PRD §13.4).

The board is **generated on demand**, not stored — it is a pure function of
cost, salvage, start date, useful life and method, so there is no persisted
schedule to fall out of date. Methods Cadra does not compute (`none`,
`erp_managed`) return an empty `periods` array; that is a valid state, not an
error.

### Request

```bash
acurl $API/api/v1/assets/1296/depreciation
```

### Success — `200 OK`

```json
{
  "asset": {
    "id": 1296,
    "asset_code": "NRS-AST-000024",
    "name": "pytest-depreciation-1786445763"
  },
  "summary": {
    "method": "straight_line",
    "useful_life_months": 60,
    "declining_rate": null,
    "salvage_value": 240000.0,
    "depreciable_cost": 2400000.0,
    "start_date": "2022-06-15",
    "start_date_source": "acquisition",
    "start_date_is_estimated": false,
    "accumulated_depreciation": 1764000.0,
    "current_book_value": 636000.0,
    "state": "depreciating",
    "end_date": "2027-06-30",
    "uses_category_policy": false
  },
  "as_of": null,
  "currency": {
    "id": 121,
    "name": "NGN"
  },
  "period_count": 60,
  "periods": [
    {
      "sequence": 1,
      "period_end": "2022-07-31",
      "charge": 36000.0,
      "accumulated_depreciation": 36000.0,
      "book_value": 2364000.0
    },
    {
      "sequence": 2,
      "period_end": "2022-08-31",
      "charge": 36000.0,
      "accumulated_depreciation": 72000.0,
      "book_value": 2328000.0
    },
    "\u2026",
    {
      "sequence": 60,
      "period_end": "2027-06-30",
      "charge": 36000.0,
      "accumulated_depreciation": 2160000.0,
      "book_value": 240000.0
    }
  ]
}
```

### Point in time — `?as_of=2023-12-31`

```bash
acurl "$API/api/v1/assets/1296/depreciation?as_of=2023-12-31"
```

Truncates the board at that date — `period_count` becomes 18 and the
last row is:

```json
{
  "sequence": 18,
  "period_end": "2023-12-31",
  "charge": 36000.0,
  "accumulated_depreciation": 648000.0,
  "book_value": 1752000.0
}
```

### Error — `400 invalid_request`

```bash
acurl "$API/api/v1/assets/1296/depreciation?as_of=notadate"
```

```json
{
  "error": {
    "code": "invalid_request",
    "message": "`as_of` must be a date in YYYY-MM-DD format",
    "request_id": "a07fe6a5f8954817af73fb8e0c26d485",
    "details": {
      "as_of": "notadate",
      "http_status": 400
    }
  }
}
```

### Error — `404 not_found`

```bash
acurl $API/api/v1/assets/99999999/depreciation
```

```json
{ "error": { "code": "not_found", "message": "Asset 99999999 not found", "request_id": "…", "details": { "http_status": 404 } } }
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
Idempotent via `X-Idempotency-Key`.

### Request

```bash
acurl -X POST $API/api/v1/locations \
  -H 'Content-Type: application/json' \
  -H 'X-Idempotency-Key: demo-create-loc-001' \
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
`X-Idempotency-Key`. Auto-generates `reference`, picks the initial stage
from the request type.

### Request

```bash
acurl -X POST $API/api/v1/requests \
  -H 'Content-Type: application/json' \
  -H 'X-Idempotency-Key: demo-create-req-001' \
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
    "location": { "id": 891, "name": "Building A" },
    "available_routes": [
      { "id": 1, "name": "New", "from_stage": { "id": 1, "name": "Draft" }, "to_stage": { "id": 2, "name": "New" } }
    ],
    "created_at": "2026-06-08T10:00:06",
    "updated_at": "2026-06-08T10:00:06"
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

> **`location_id` is saved — since 21 September 2026. Before that it never
> was**, although this example has always sent one. The request model's
> location field was renamed in the move to Odoo 19 and this route went on
> asking the model for the old name, so the key was dropped with a 201 and a
> `_warnings.rejected_fields` entry nobody read; `data.location` was always
> `null` and `?location_id=` filtered nothing. Found when a dropped field
> became a 400 (*Conventions*). **Only this route dropped it:** a request
> raised by quick-submit, a PM schedule or the Odoo form kept its location
> all along, read `location: null` here regardless, and now shows it.

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

# §6 — Dashboards (8 endpoints, all GET; two scopes since handoff 47)

`dashboards:read` is the asset register's own figures (`/dashboard/kpis`,
`/dashboard/map`, and §10's `/reports/depreciation`). Everything operational
— fleet command, the fleet maintenance dashboard, FM and all four security
endpoints — takes `operations:read`. One scope used to cover both;
splitting it is handoff 47's ruling 1, and it is BREAKING for a credential
that held `dashboards:read` for the operational half.

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

## 6.2 GET `/api/v1/dashboard/map` — register dashboard map data

Since handoff 50 (**BREAKING**) the payload is `locations` only. The
`fleet` rows (one per geocoded vehicle, with license plate and driver)
moved to `GET /api/v1/fleet/map` under `operations:read`, and
`recent_requests` was removed (read by nothing; its documented shape had
drifted from what the server sent).

```bash
acurl $API/api/v1/dashboard/map
```

### Success — `200 OK`

```json
{
  "data": {
    "locations": [
      { "id": 891, "name": "HQ - GF - Mail Room", "lat": 9.0579, "lng": 7.4951, "state": "FCT", "type": "location", "open_requests": 2, "model": "generic.location" }
      /* … */
    ]
  },
  "meta": { "request_id": "5334e131…", "timestamp": "…", "version": "v1" }
}
```

## 6.2a GET `/api/v1/fleet/map` — geocoded fleet vehicles

Scope: `operations:read`. The vehicle rows exactly as `/dashboard/map`
shaped them before handoff 50: `id`, `name`, `plate`, `lat`, `lng`,
`status`, `driver`, `location`, `state`, `type: "vehicle"`,
`model: "fleet.vehicle"`. Positions are the vehicle's home location's
coordinates (jittered for display), not live tracking.

```bash
acurl $API/api/v1/fleet/map | jq '.data.fleet | length'
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

# §7 — Barcode & tag lookup (7 endpoints)

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

## 7.5 GET `/api/v1/barcode/untagged?q=&limit=` — assets with no barcode

Scope: `assets:read`. Success: **200**.

An asset always has an `asset_code` (an `ir.sequence` value assigned when the
asset is created). The **barcode** is a separate, location-derived code living
on the tag record, and only exists once the asset has been tagged. This lists
the assets that have the former but not the latter — the candidates for 7.6.

`q` matches asset name, asset code, or serial number. `limit` defaults to 100
and is clamped to 500.

```bash
acurl "$API/api/v1/barcode/untagged?q=desk&limit=50"
```

### Success — `200 OK`

```json
{
  "data": [
    {
      "asset_id": 412,
      "asset_name": "Workstation Desk",
      "asset_code": "NRS-FF-DSK-00001",
      "category": "Furniture & Fittings",
      "domain": "furniture",
      "location": "HQ - GF - Mail Room",
      "condition": "good"
    }
  ],
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

## 7.6 POST `/api/v1/barcode/generate` — mint barcodes for assets

Scope: `tagging:write` (since handoff 47 — BREAKING; it was `assets:write`.
Minting a label is the Tag-Issuing Unit's job, and `POST /assets` still
mints its own tag server-side, so registration needs nothing extra).
Success: **200**. Idempotent (accepts `X-Idempotency-Key`).

Generates a tag for each asset id that does not already have one. The tag
number is built from the asset's building/floor/room zone codes plus its
category code — `HQ-GF-MR-FF-001` — see `_tag_prefix` in
`myservice_asset_register/models/asset_tag.py`.

Assets that already carry an active tag are **skipped, not re-tagged**: a
second live barcode on one asset means two physical labels in the field
resolving to the same thing with no way to tell which is current. That also
makes the call safe to retry after a dropped response. Replacing a damaged
tag is a different operation (`action_request_replacement` on the tag), which
preserves the replaces/replaced_by chain.

Max 500 asset ids per call.

```bash
acurl -X POST "$API/api/v1/barcode/generate" \
  -H "Content-Type: application/json" \
  -d '{"asset_ids": [412, 413, 99999]}'
```

### Success — `200 OK`

```json
{
  "data": {
    "generated": [
      {
        "asset_id": 412,
        "asset_name": "Workstation Desk",
        "asset_code": "NRS-FF-DSK-00001",
        "tag_id": 908,
        "tag_number": "HQ-GF-MR-FF-001",
        "location": "HQ - GF - Mail Room"
      }
    ],
    "skipped": [
      { "asset_id": 413, "reason": "already_tagged", "tag_number": "HQ-3F-FIN-IT-001" },
      { "asset_id": 99999, "reason": "not_found" }
    ]
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `400 invalid_request` (empty or oversized list)

```json
{ "data": { "error": "`asset_ids` must be a non-empty list of asset ids" },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" } }
```

## 7.7 GET `/api/v1/tags/lookup?query=<q>` — portal-style lookup

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
`X-Idempotency-Key`.

> **BREAKING, 22 September 2026 (handoff 32).** This route takes **seven
> keys and no others**. Anything else is a `400 invalid_request` and nothing
> is written. **This section's own example was wrong for the life of the
> route**: it sent `name`, `email`, `phone` and `subject`, four keys the
> route has never read, and `description` — and the route answered 201 to
> all five, raising a request that carried only the description. The test
> suite's own quick-submit test was written from this example and had been
> sending the same four since the day it was written. The example below is
> the corrected one, and the suite now fails if it drifts again.
>
> `type_id`, `service_id` and `location_id` are also a 400 when the value
> cannot be resolved — not a number, or a number naming no record — under
> `details.unusable_fields`. Both used to be dropped in silence by a bare
> `except: pass`, submitting a request quietly missing that detail.

| Key | | |
|---|---|---|
| `type_id` | required | `request.type` id — `GET /home/form-data` lists them |
| `description` | required | what the caller is reporting |
| `service_id` | optional | `generic.service` id |
| `location_id` | optional | `generic.location` id — **saved**, and published as `data.location` on `GET /requests/<id>` since handoff 31 |
| `priority` | optional | `0`–`4`, default `1` |
| `reporter_name` | optional | composed into the request text; there is no reporter field on the model |
| `reporter_contact` | optional | phone or email; an email resolves or creates the `res.partner` recorded as author |

### Request

```bash
acurl -X POST $API/api/v1/home/quick-submit \
  -H 'Content-Type: application/json' \
  -H 'X-Idempotency-Key: demo-quicksubmit-001' \
  -d '{
    "type_id": 1,
    "service_id": 4,
    "location_id": 12,
    "priority": "2",
    "description": "AC not cooling in 4F open plan — started yesterday, ~10 staff affected",
    "reporter_name": "Adamu Bello",
    "reporter_contact": "adamu.bello@firs.gov.ng"
  }'
```

### Success — `201 Created`

```json
{
  "data": {
    "success": true,
    "request_id": 6,
    "request_name": "INCIDENT-062026-0000006"
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

### Error — `400 invalid_request` (a key this route does not accept)

```bash
acurl -X POST $API/api/v1/home/quick-submit \
  -H 'Content-Type: application/json' \
  -d '{"type_id": 1, "request_text": "AC not cooling"}'
```

`request_text` is the sibling `POST /api/v1/requests` key. Until handoff 32
this body answered **201** and raised a request with no description at all.

```json
{ "error": { "code": "invalid_request",
    "message": "This route does not accept: `request_text`. Nothing was written.",
    "request_id": "…",
    "details": { "rejected_fields": ["request_text"],
                 "writable": ["description", "location_id", "priority", "reporter_contact", "reporter_name", "service_id", "type_id"],
                 "http_status": 400 } } }
```

### Error — `400 invalid_request` (an id that names no record)

```json
{ "error": { "code": "invalid_request",
    "message": "These fields name no record this register holds: `service_id`. Nothing was written.",
    "request_id": "…",
    "details": { "unusable_fields": ["service_id"],
                 "writable": ["description", "location_id", "…"],
                 "http_status": 400 } } }
```

### What a member of the public sees

The same function answers the unauthenticated homepage form at
`POST /api/myservice/quick-submit` (`docs/api/EXTERNAL-SURFACES.md`). **One
validator, two renderings** — the refusal is the same, the words are not:

> Sorry — we could not submit your request. Some of the information sent with
> this form was not recognised. Please reload the page and try again.

and, for an id the register cannot resolve — the one refusal a visitor can
act on:

> Please choose the service from the list on the form, then send your request
> again.

No key names, because the reader is a person on a phone and nothing they
typed is wrong.

---

# §9 — Integrations (2 endpoints, scope `integrations:write`)

Inbound webhooks for upstream systems.

## 9.1 POST `/api/v1/integrations/sap/employee-sync` — SAP SuccessFactors employee event

Scope: `integrations:write`. Success: **200**.
Accepts a single employee object or a list of them.

> **BREAKING, 22 September 2026 (handoff 32).** A key this route does not
> read is now a `400 invalid_request` naming it in
> `details.rejected_fields`, with the whole accepted set in
> `details.writable` — and **nothing is written for the whole batch**, not
> just the employee that carried it. A list is one request; refusing the
> eleventh employee after ten had been created would leave a partial sync
> under an idempotency key that replays the same answer on every retry.
>
> **`status` and `officeCode` are among the keys now refused, and this
> document is the reason they were being sent.** `nrs.sap.sync.log` has
> never read either: employment status arrives as `employmentStatus` (or
> `sap_status`). The example below sent `status: "active"` for the life of
> the route, the demo card sent it, and the API's own OpenAPI schema
> published it with an enum — `active`/`inactive`/`terminated` — of which
> only `active` and `terminated` are values this system has. So every
> integrator following our documentation sent an employment status that went
> nowhere, under a `200`. Per `CLAUDE.md` rule 4 the model is the published
> surface and the document is what gets corrected.

**Match keys** — one of `ir_number`, `userId`, `personIdExternal`.

**Accepted** — `ir_number`, `userId`, `personIdExternal`, `displayName`,
`firstName`, `lastName`, `email`, `phone`, `department`,
`jobTitle`, `costCenter`, `gradeCode`, `managerIR`, `hireDate`,
`terminationDate`, `locationName`, `location`, `employmentStatus`,
`sap_status`, `previous_status`, `event`. (`mobile` was removed by handoff
50 — measured sent by nothing and held by nobody; a body carrying it is
refused like any other unknown key.)

`employmentStatus` takes `active`, `terminated`, `suspended`, `onLeave` or
`transferred`; the capitalised spellings map to the same values.
`terminated` flags the employee's assets for retrieval.

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
    "employmentStatus": "active"
  }'
```

### Success — `200 OK`

```json
{
  "data": {
    "processed": 1,
    "results": [
      { "ir_number": "FIRS-12345", "status": "success",
        "employee_id": 717, "changes": "…" }
    ]
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

`results[].status` is the SYNC's outcome — `success`, `error` or `skipped` —
and is not the employee's employment status. The two have always had the
same name in this response and only one of them was ever an input.

### Error — `400 invalid_request` (a key this route does not read)

```json
{ "error": { "code": "invalid_request",
    "message": "This route does not accept: `status`, `officeCode`. Nothing was written.",
    "request_id": "…",
    "details": { "rejected_fields": ["status", "officeCode"],
                 "writable": ["costCenter", "department", "displayName", "…"],
                 "http_status": 400 } } }
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
    "request_reference": "INCIDENT-052026-0000002",
    "replayed": false
  },
  "meta": { "request_id": "a23f1717…", "timestamp": "…", "version": "v1" }
}
```

### Replay — `200 OK` with `replayed: true`

**An outcome already applied is a no-op that answers success.** Send the same
callback twice and the second one writes nothing at all: no dispatch-log row,
no chatter post, no stage change, no audit event. `data.replayed` is how you
tell the two apart.

```json
{
  "data": {
    "applied_outcome": "approved",
    "request_reference": "INCIDENT-052026-0000002",
    "replayed": true
  },
  "meta": { "request_id": "0d61b2aa…", "timestamp": "…", "version": "v1" }
}
```

Re-sending the request to the workflow engine resets it to `pending`, so a
second dispatch's decision is a second transition and applies normally.

### Error — `409 conflict` (a different outcome after a decision)

A request Cadra records as `approved` cannot be turned into `rejected` by a
later callback, and vice versa; `queried` after either is refused on the same
terms. Nothing is written, and the error says what Cadra currently holds.

```json
{
  "error": {
    "code": "conflict",
    "message": "Request 'INCIDENT-052026-0000002' is already 'approved'; refusing to apply 'rejected'",
    "request_id": "7c04e1f9…",
    "details": {
      "current_outcome": "approved",
      "attempted_outcome": "rejected",
      "http_status": 409
    }
  }
}
```

### Error — `503 server_misconfigured` (tenant not wired to a workflow engine)

```json
{
  "error": {
    "code": "server_misconfigured",
    "message": "Workflow integration is not available",
    "request_id": "10574f56…",
    "details": { "http_status": 503 }
  }
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
`X-Idempotency-Key` header. The first call creates; the second call with
the **same key** returns the **original** response even if the body
differs.

```bash
# First call — creates record id=481
acurl -X POST $API/api/v1/locations \
  -H 'Content-Type: application/json' \
  -H 'X-Idempotency-Key: demo-idem-001' \
  -d '{"name":"Idem demo loc","description":"first call"}'

# Second call with SAME key but DIFFERENT body — returns id=481 with the
# ORIGINAL "first call" description; the second body is silently ignored
acurl -X POST $API/api/v1/locations \
  -H 'Content-Type: application/json' \
  -H 'X-Idempotency-Key: demo-idem-001' \
  -d '{"name":"SHOULD-BE-IGNORED","description":"second call"}'
```

**Rules an integration should know:**

- The header is `X-Idempotency-Key`. A key sent under any other name is not
  seen, and the request is processed as new.
- Keys are scoped to `(key, path)` and live for **24 hours**.
- Maximum length is **128 characters**. A longer key returns
  `400 invalid_request` with `details.max_length` — it is never silently
  dropped, because a caller cannot detect the difference between a key that
  was honoured and one that was ignored. The length is validated on **every
  endpoint that goes through the standard envelope**, including the ones that
  do not cache; the header itself is accepted and ignored there rather than
  rejected. Nine routes predate that envelope and validate nothing — see the
  table below.
- Two requests arriving simultaneously under one key produce **one** record.
  The loser's work is rolled back and it receives the winner's response. In
  the rare case where the winner's response cannot be read back, the loser
  gets `409 conflict` — retry with the same key.

**Which endpoints actually honour it.** Sending the header anywhere else is
harmless but has no effect, so do not rely on it outside this list. The
generated spec is authoritative: an endpoint honours idempotency exactly when
its OpenAPI entry declares an `X-Idempotency-Key` header parameter.

| Honoured (16) | Accepted and ignored (10) |
|---|---|
| `POST /assets` · `PATCH /assets/<id>` | `PATCH /asset-categories/<id>` |
| `POST /assets/<id>/move` | `DELETE /asset-categories/<id>` |
| `POST /assets/<id>/transfer-custody` | `POST /auth/token` |
| `POST /asset-categories` | `POST /auth/login` |
| `POST /locations` · `PATCH /locations/<id>` | `POST /auth/refresh` |
| `POST /requests` · `PATCH /requests/<id>` | `POST /auth/revoke` |
| `POST /requests/<id>/assign` | `PATCH /settings/branding` |
| `POST /requests/<id>/comment` | `PATCH /settings/depreciation` |
| `POST /requests/<id>/transition` | `POST /settings/depreciation/recompute` |
| `POST /home/quick-submit` | `PATCH /settings/sidebar` |
| `POST /barcode/generate` | |
| `POST /integrations/sap/employee-sync` | |
| `POST /integrations/workflow/callback` | |

Nine routes are older than the shared envelope and go straight to
`@http.route`, so they neither honour the key nor validate its length:
`/auth/token`, `/auth/login`, `/auth/refresh`, `/auth/revoke`,
`/openapi.json`, `/docs`, `/assets/export.csv`,
`/integrations/employees/import` and `/brand`. An over-long key is silently
ignored there rather than answered with a 400 — worth knowing, because
`/auth/token` is the first endpoint any integration calls.

The auth endpoints are deliberately outside the *honoured* column too:
minting a token twice is not a duplicate resource, and caching a token
response under a client-supplied key would be a credential-replay hazard.

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

## All 19 scopes

`assets:read`, `assets:write`, `export:read`, `locations:read`,
`locations:write`, `requests:read`, `requests:write`, `approvals:write`,
`dashboards:read`, `operations:read`, `integrations:write`,
`ingestion:write`, `webhooks:admin`, `identity:read`, `access:read`,
`tagging:write`, `settings:write`, `settings:read`, `admin`.

**`export:read`** was split out of `assets:read` by handoff 50 (BREAKING):
it gates exactly the two bulk-export routes (§3.9), because reading a page
of the register and taking a copy of all of it are different acts. Granted
by the Auditor role; the `admin` wildcard covers it.

Two more were split out of wider names by handoff 47 (both BREAKING for
credentials provisioned under the old name):

- **`operations:read`** — the fleet, staff-bus, FM and security dashboards,
  carved out of `dashboards:read`, which now means only the asset
  register's own figures.
- **`access:read`** — `GET /reports/access-changes`, the record of who
  granted whom which role, carved out of `identity:read`, which now means
  only the employee roster and its routes. Granted by the Auditor role.

`settings:write` (added 2026-09-06) covers tenant configuration — the
category taxonomy and the branding and depreciation settings. It was carved
out of `admin` so those screens do not require a wildcard.

Two of these are not like the others:

- **`admin` is a wildcard.** `require_jwt` treats it exactly like `*`: a token
  holding `admin` passes every scope check, `tagging:write` included. Grant it
  only where you mean "everything".
- **`tagging:write` is deliberately narrow.** It gates the single endpoint that
  can make an asset read as physically tagged, and the Tag-Issuing Unit's
  client holds it *alone* — no `assets:read`, no `assets:write`. A credential
  that can both create an asset and confirm its own tag defeats the control
  (INT-04/05).

An unrecognised scope on a client record is now rejected when the record is
saved. It used to be accepted silently, minted into a token, and produce a
403 the caller could not tell apart from a real permission decision.

**An empty `scopes` field grants NOTHING** — it is a denial, not a wildcard.
Set the scopes you mean; write `admin` if you mean everything. (This document
said the opposite until 2026-09-06. It was wrong: a client created without
scopes used to receive the whole API, which is privilege escalation waiting
for a typo.)

### Session tokens carry the scopes the user's Odoo groups justify

`POST /auth/token` takes its scopes from the client record. `POST /auth/login`
derives them from the user's groups, and the returned `scope` can be **empty**
— an account with no Cadra role authenticates and is refused everywhere. Read
`scope` off the login response rather than assuming; it was `*` for every user
before `myservice_api` 19.0.3.1.0.

## CORS / auth header

- Every authenticated endpoint expects `Authorization: Bearer <jwt>`
- `X-Idempotency-Key` is optional but recommended on every POST that creates
  state
- `Content-Type: application/json` on bodies; the API doesn't accept
  form-encoded payloads on JSON endpoints

---

# Demo cheat-sheet (paste into a fresh terminal)

```bash
# 0. Choose environment
API=https://staging.app.cadra.ng
export CLIENT_SECRET='<paste from docs/api/.creds.<tenant>>'

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

# §10 — Reports

Register-wide aggregations. Scope `dashboards:read`.

## 10.1 GET `/api/v1/reports/depreciation` — depreciation & book value

Scope: `dashboards:read`. Success: **200**.
Optional: `?category_id=<int>` to scope the report to one category.

Aggregates the stored per-asset figures, so this is a cheap `read_group` rather
than a walk over schedules. The two data-quality counts matter in practice:
`needs_start_date` is assets whose start date was inferred from the record's
creation date rather than a real acquisition or purchase date, and
`missing_cost` is assets carrying a depreciation method with no cost to
depreciate. Both should be treated as backfill queues.

Depreciation here is **operational reference data, not the financial book of
record** — PRD §3.3 lists financial accounting and the general ledger as
explicit non-goals, and §8.6 confirms Cadra "does not produce the official
financial books".

### Request

```bash
acurl $API/api/v1/reports/depreciation
```

### Success — `200 OK`

```json
{
  "totals": {
    "asset_count": 1287,
    "depreciable_cost": 13600000.0,
    "accumulated_depreciation": 8452000.0,
    "current_book_value": 5148000.0
  },
  "by_category": [
    {
      "id": 50,
      "name": "Furniture & Fittings",
      "asset_count": 7,
      "depreciable_cost": 9600000.0,
      "accumulated_depreciation": 7452000.0,
      "current_book_value": 2148000.0
    }
  ],
  "by_state": {
    "depreciating": 3,
    "erp_managed": 4,
    "fully_depreciated": 1,
    "not_applicable": 1276,
    "not_started": 3
  },
  "by_method": {
    "declining_balance": 3,
    "erp_managed": 4,
    "none": 1276,
    "straight_line": 4
  },
  "needs_start_date": 1280,
  "missing_cost": 3
}
```

### Error — `400 invalid_request`

```bash
acurl "$API/api/v1/reports/depreciation?category_id=abc"
```

```json
{
  "error": {
    "code": "invalid_request",
    "message": "`category_id` must be an integer",
    "request_id": "aabff05435694208a02dec3add8ac74b",
    "details": {
      "category_id": "abc",
      "http_status": 400
    }
  }
}
```

---

# §11 — Approvals (7 endpoints, from 19.0.3.13.0)

`nrs.asset.change.request` — a person asking a second person to agree before
an asset is moved or handed to somebody else. **One model for both kinds of
change**, because *"what is waiting on me"* is one question and an approver
should not have to look in two places to answer it.

The requests themselves are NOT raised here. They are raised by `POST
/assets/<id>/move` and `POST /assets/<id>/transfer-custody` (§3.5.2), which
on a tenant that requires approval create one instead of making the change.

**Two fields that are never the same field.** `approver` is WHO IS BEING
ASKED — a nomination, sent by the requester, which puts the request in
somebody's queue and addresses the notification. `decided_by` is WHO CLICKED,
taken from the bearer token and never readable from any body. A body naming
`decided_by`, `approved_by`, `decided_at`, `approved_date`, `requested_by` or
`state` on any of the three action routes — `/approve`, `/reject`,
`/withdraw` — is **400 `invalid_request`**, not ignored. Those three accept
`reason` and nothing else.

**The record survives whatever NRS does to the rule later.** Who may approve
what — by value, by category, by office — is expected to change; who asked,
who approved, when, and what the asset was at the time are the columns that
do not.

## The request object

Every route below that returns a request returns this shape.

```json
{
  "id": 41,
  "reference": "CR/2026/0041",
  "state": "pending",
  "change_type": "location",
  "asset": { "id": 124, "name": "Dell OptiPlex 7090" },
  "asset_code": "NRS-EV-FAL-FAP-00001",

  "to_location": { "id": 905, "name": "HQ - 1F - Server Room" },
  "to_custodian": null,
  "reason": "Reshuffle after Q2 audit",

  "from_location": { "id": 891, "name": "HQ - GF - Mail Room" },
  "from_custodian": null,
  "from_location_name": "HQ - GF - Mail Room",
  "from_custodian_name": null,
  "to_location_name": "HQ - 1F - Server Room",
  "to_custodian_name": null,
  "from_state": "active",

  "requested_by": { "id": 8, "name": "Tunde Alabi" },
  "requested_by_name": "Tunde Alabi",
  "requested_at": "2026-09-22T11:04:19",
  "approver": { "id": 12, "name": "Ngozi Bello" },

  "decided_by": null,
  "decided_by_name": null,
  "decided_at": null,
  "decision_reason": null,

  "premise_holds": true,
  "premise_broken_reason": null,

  "movement_id": null,
  "custody_id": null,
  "transfer": null,
  "transfer_reference": null,

  "can_decide": true,
  "can_withdraw": false
}
```

### The keys worth reading twice

* **`from_*` — what the asset WAS when the request was raised.** Recorded at
  request time, not read from the asset at approval time. Without them an
  approval means *"yes, move it to B"*; with them it means *"yes, move it
  from A to B"*, and the difference is everything once somebody else has
  moved it to C. The `_name` copies are what the record keeps when a location
  is renamed or an employee is deleted, so the published premise cannot be
  emptied from outside. `from_location.name` is the location's own name;
  `from_location_name` is the display name as it was recorded, which for a
  nested location carries its parents with it.
* **`premise_holds` / `premise_broken_reason`** — computed fresh on every
  read, never stored. A stored value would be a snapshot of the last time
  something recomputed it, and the thing that breaks a premise is exactly the
  thing that happens without touching this record. A queue showing a stale
  `true` is the silent failure the field exists to prevent. `false` means
  `/approve` will answer **409**, and the reason says what changed.
* **`movement_id` / `custody_id`** — the append-only rows the approval
  produced. `null` until then, **and there is never a row before then**: a
  movement written when somebody merely ASKS would be a permanent record of a
  move that had not happened.
* **`transfer` / `transfer_reference`** — the `nrs.asset.transfer` document,
  made only for an approved move of an asset that HAD a location. An asset
  that is nowhere is placed, not transferred, and gets none. The reference is
  kept as text beside it because the document is deletable and the approval
  is not.
* **`can_decide` / `can_withdraw`** — computed for the CALLER, so a queue can
  grey out a row rather than offer a button the model will refuse. The model
  is still the authority.

## 11.1 GET `/api/v1/approvals` — the queue

Scope: `assets:read`. Success: **200**. Cursor-paginated, **newest first**.

`assets:read` and not `approvals:write`, so an Auditor can read who
authorised what without being able to authorise anything.

| Query parameter | |
|---|---|
| `state` | `pending` \| `approved` \| `rejected` \| `withdrawn` |
| `change_type` | `location` \| `custody` |
| `asset_id` | requests against one asset |
| `waiting_on_me` | `true` — only requests NAMING the caller as the approver. This is *what is waiting on me*. Anyone eligible may approve any pending request, so it is a convenience and not a boundary |
| `raised_by_me` | `true` — how a requester finds out what happened to theirs |
| `limit`, `cursor` | as everywhere else |

`?waiting_on_me=false` means *do not filter*, not *filter on nothing*.

### Request

```bash
acurl "$API/api/v1/approvals?state=pending&waiting_on_me=true"
```

### Success — `200 OK`

```json
{
  "data": [ { "id": 41, "reference": "CR/2026/0041", "...": "the request object above" } ],
  "pagination": { "next_cursor": null, "previous_cursor": null, "total_estimate": 1 },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

`total_estimate` counts the caller's own filter, not the capped window.

### Error — `400 invalid_request` (a value the filter cannot read)

```bash
acurl "$API/api/v1/approvals?state=maybe"
```

```json
{ "error": { "code": "invalid_request", "message": "`state` must be one of: pending, approved, rejected, withdrawn", "request_id": "…", "details": { "state": "maybe", "allowed_values": ["pending", "approved", "rejected", "withdrawn"], "http_status": 400 } } }
```

## 11.2 GET `/api/v1/approvals/<id>` — one request

Scope: `assets:read`. Success: **200**. Returns the request object.

### Error — `404 not_found`

```json
{ "error": { "code": "not_found", "message": "Approval request 99999999 not found", "request_id": "…", "details": { "http_status": 404 } } }
```

## 11.3 GET `/api/v1/approvals/approvers` — who this caller may ask

Scope: `assets:write`. Success: **200**.

Everyone who could have made the change themselves, **minus the caller**. The
caller's own exclusion is here and not only in the dialog: a picker offering
a choice the model refuses is an answer that looks like an answer.

| Query parameter | |
|---|---|
| `q` | free-text on the person's name |
| `limit` | default and cap as elsewhere |

### Request

```bash
acurl "$API/api/v1/approvals/approvers?q=bel"
```

### Success — `200 OK`

```json
{ "data": [ { "id": 12, "name": "Ngozi Bello" } ], "meta": { "…": "…" } }
```

Today that is the members of `group_asset_manager`, including anyone holding
it through another group — the one group granting `assets:write`, which is
the whole of the rule *the approver is anyone who could have made the change
themselves*. It is one method on the model (`_eligible_approver_domain`) so
that NRS reshaping it does not touch the record.

An Odoo system administrator may also DECIDE any request that is not their
own — withholding it would be theatre, since such a user can execute
arbitrary server actions — but is not offered by this picker.

## 11.4 POST `/api/v1/approvals/<id>/approve` — agree, and make it happen

Scope: `approvals:write`. Success: **200**. Idempotent.

The body takes **`reason` and nothing else**; any other key is a 400 carrying
`details.rejected_fields` and `details.writable`.

### Request

```bash
acurl -X POST $API/api/v1/approvals/41/approve \
  -H 'Content-Type: application/json' \
  -d '{"reason": "Checked with the store — fine."}'
```

### Success — `200 OK`

```json
{
  "data": {
    "request": {
      "id": 41, "reference": "CR/2026/0041", "state": "approved",
      "approver": { "id": 12, "name": "Ngozi Bello" },
      "decided_by": { "id": 12, "name": "Ngozi Bello" },
      "decided_by_name": "Ngozi Bello",
      "decided_at": "2026-09-22T13:40:55",
      "decision_reason": "Checked with the store — fine.",
      "movement_id": 3301,
      "custody_id": null,
      "transfer": { "id": 17, "reference": "TRF/2026/0017" },
      "transfer_reference": "TRF/2026/0017",
      "...": "the rest of the request object"
    },
    "asset": { "id": 124, "current_location": { "id": 905, "name": "HQ - 1F - Server Room" }, "...": "full asset record, MOVED" }
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

**The asset is in every decision response, including a rejection.** The one
thing a caller needs to know after any of these three calls is whether the
asset moved; on an approval it did, on a rejection and a withdrawal it did
not, and the asset proves it rather than asking the caller to trust the verb.

The `nrs.asset.transfer` this produces is created already `done` **and
already approved, by the person who actually clicked** — `approved_by` had
been null on 264 of the 265 transfer rows on the development cluster before
this. A custody approval makes no transfer document at all: that model
requires both locations and forbids them being equal, so a pure custody
change cannot be recorded in it.

### Error — `403 forbidden`

Two reasons, told apart by `details.is_own_request`.

```json
{ "error": { "code": "forbidden", "message": "You raised this request and cannot approve it. The point of an approval is that a second person agrees.", "request_id": "…", "details": { "request_id": 41, "is_own_request": true, "requested_by": { "id": 8, "name": "Tunde Alabi" }, "http_status": 403 } } }
```

Self-approval is refused **in the model**, not by hiding a button: the same
answer comes back from the Odoo screen and from a shell.

### Error — `409 conflict` (already decided)

```json
{ "error": { "code": "conflict", "message": "This request was already approved by Ngozi Bello. A decision is taken once.", "request_id": "…", "details": { "request_id": 41, "state": "approved", "decided_by": { "id": 12, "name": "Ngozi Bello" }, "decided_at": "2026-09-22T13:40:55", "http_status": 409 } } }
```

### Error — `409 conflict` (the premise no longer holds)

```json
{ "error": { "code": "conflict", "message": "This request can no longer be approved. The asset was at HQ / GF / Mail Room when this was raised and is now at HQ / 2F / Store. Raise a new request if the change is still wanted.", "request_id": "…", "details": { "request_id": 41, "premise_broken_reason": "The asset was at HQ / GF / Mail Room when this was raised and is now at HQ / 2F / Store.", "asset": { "id": 124, "name": "Dell OptiPlex 7090" }, "http_status": 409 } } }
```

A disposed asset breaks the premise in the same way and says so in those
words — a disposed asset cannot be moved or change hands by any route.

## 11.5 POST `/api/v1/approvals/<id>/reject` — refuse, with a reason

Scope: `approvals:write`. Success: **200**. Idempotent.

**`reason` is REQUIRED.** A rejection without one leaves the requester with a
dead request and nothing to act on, and they will simply raise it again —
the shape of control that produces noise and no information. `/condemn`,
`/mark-missing` and `/mark-found` require one for the same argument.

### Request

```bash
acurl -X POST $API/api/v1/approvals/41/reject \
  -H 'Content-Type: application/json' \
  -d '{"reason": "That room is being repurposed next month — hold the asset where it is."}'
```

### Success — `200 OK`

Same envelope as `/approve`: `data.request` with `state: "rejected"`, and
`data.asset` **unchanged**.

### Error — `400 invalid_request` (no reason)

```json
{ "error": { "code": "invalid_request", "message": "`reason` is required — say why this is being rejected. The person who asked sees it.", "request_id": "…", "details": { "http_status": 400 } } }
```

### Error — `403 forbidden`

A requester who tries to reject their own is told to withdraw it instead.

## 11.6 POST `/api/v1/approvals/<id>/withdraw` — take back your own

Scope: **`assets:write`**, not `approvals:write`. Success: **200**.
Idempotent.

Withdrawing is not a decision about somebody else's request; it is taking
back your own, and the people who raise requests are exactly the people
holding `assets:write`. Requiring `approvals:write` would leave a requester
who cannot approve unable to cancel their own request, and a dead row in
somebody's queue for ever.

`reason` is **optional** here and required on `/reject`, and that is the
difference between the two acts: an approver refusing somebody else's request
owes them an explanation; a requester withdrawing their own owes nobody one.

### Request

```bash
acurl -X POST $API/api/v1/approvals/41/withdraw \
  -H 'Content-Type: application/json' -d '{"reason": "Asked the wrong person."}'
```

### Error — `403 forbidden` (not yours)

```json
{ "error": { "code": "forbidden", "message": "Only Tunde Alabi, who raised this request, can withdraw it. Reject it instead if you are deciding on it.", "request_id": "…", "details": { "request_id": 41, "requested_by": { "id": 8, "name": "Tunde Alabi" }, "http_status": 403 } } }
```

## 11.7 GET `/api/v1/settings/approvals` — does this register need a second person?

Scope: **`assets:read`**, and deliberately not `settings:read` like every
other block on that controller. The app has to ask this question wherever it
draws a Move button, and `settings:read` is granted only by Asset Manager and
Auditor — gating it that way would make the answer unreadable to some
signed-in users while the button was still on their screen, and the front end
fails CLOSED on an unreadable answer, so the symptom would be a
correct-looking dialog asking for an approver on a tenant that does not want
one. The value is not sensitive: it says whether this register asks for a
second person, which anybody who can see an asset may as well know.

Success: **200**.

### Request

```bash
acurl $API/api/v1/settings/approvals
```

### Success — `200 OK`

```json
{
  "data": {
    "required": true,
    "setting": null,
    "configured": false,
    "default_when_unset": true,
    "parameter": "cadra.approval.required"
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

* **`required`** — the answer. What every route above behaves by.
* **`setting`** — the raw recorded value, `"on"`, `"off"` or **`null`** when
  nothing recognisable is recorded.
* **`configured`** — whether anybody ever set it. *Nobody has ever thought
  about this and it is getting the default* and *somebody deliberately turned
  it on* are the same behaviour and very different facts, and a screen that
  cannot tell them apart cannot tell an administrator which one they are
  looking at.
* **`default_when_unset`** — `true`. **Absent, blank, misspelt and
  unrecognised all mean required.** The two ways to be wrong are not equally
  bad: a register that asks for a second person when it need not has a slower
  afternoon and a visible symptom; one that skips the second person because a
  parameter was misspelt has no symptom at all, and finds out when an auditor
  asks who authorised a move.

### There is deliberately no PATCH twin

Every other settings block on this controller has one. This does not, and
that is the point of the control: `assets:write`, `approvals:write` and
`settings:write` are all granted by the single group `group_asset_manager`,
so a `PATCH` here would let exactly the people the rule constrains switch it
off, move the asset, and switch it back on. That is not a control; it is a
speed bump with an audit trail nobody reads.

An administrator sets `cadra.approval.required` in the database, once, and
the exact command is printed inside the refusal a gated write raises. The
value is read with a single indexed `SELECT` on every call — never through
`ir.config_parameter.get_param`, which is cached per worker and once served
a deleted parameter's old value to twenty-four writing tests.

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
| 10a | GET    | `/api/v1/assets/<id>/custody` | `assets:read` |
| 11 | GET    | `/api/v1/assets/export` | `export:read` |
| 12 | GET    | `/api/v1/assets/export.csv` | `export:read` |
| 13 | GET    | `/api/v1/assets/<id>/depreciation` | `assets:read` |
| 14 | GET    | `/api/v1/locations` | `locations:read` |
| 15 | GET    | `/api/v1/locations/<id>` | `locations:read` |
| 16 | POST   | `/api/v1/locations` | `locations:write` |
| 17 | PATCH  | `/api/v1/locations/<id>` | `locations:write` |
| 18 | GET    | `/api/v1/locations/<id>/children` | `locations:read` |
| 19 | GET    | `/api/v1/locations/<id>/ancestors` | `locations:read` |
| 20 | GET    | `/api/v1/locations/<id>/descendants` | `locations:read` |
| 21 | GET    | `/api/v1/requests` | `requests:read` |
| 22 | GET    | `/api/v1/requests/<id>` | `requests:read` |
| 23 | GET    | `/api/v1/requests/by-reference/<ref>` | `requests:read` |
| 24 | POST   | `/api/v1/requests` | `requests:write` |
| 25 | PATCH  | `/api/v1/requests/<id>` | `requests:write` |
| 26 | POST   | `/api/v1/requests/<id>/assign` | `requests:write` |
| 27 | POST   | `/api/v1/requests/<id>/transition` | `requests:write` |
| 28 | POST   | `/api/v1/requests/<id>/comment` | `requests:write` |
| 29 | GET    | `/api/v1/dashboard/kpis` | `dashboards:read` |
| 30 | GET    | `/api/v1/dashboard/map` | `dashboards:read` |
| 31 | GET    | `/api/v1/dashboard/fleet-command` | `operations:read` |
| 32 | GET    | `/api/v1/security/kpis` | `operations:read` |
| 33 | GET    | `/api/v1/security/map-data` | `operations:read` |
| 34 | GET    | `/api/v1/security/trend` | `operations:read` |
| 35 | GET    | `/api/v1/security/recent` | `operations:read` |
| 36 | GET    | `/api/v1/fleet/dashboard` | `operations:read` |
| 36a | GET    | `/api/v1/fleet/map` | `operations:read` |
| 37 | GET    | `/api/v1/fm/dashboard` | `operations:read` |
| 38 | GET    | `/api/v1/barcode/lookup` | `assets:read` |
| 39 | GET    | `/api/v1/barcode/kpis` | `assets:read` |
| 40 | GET    | `/api/v1/barcode/recent-tags` | `assets:read` |
| 41 | GET    | `/api/v1/barcode/print-url` | `assets:read` |
| 42 | GET    | `/api/v1/barcode/untagged` | `assets:read` |
| 43 | POST   | `/api/v1/barcode/generate` | `tagging:write` |
| 44 | GET    | `/api/v1/tags/lookup` | `assets:read` |
| 44a | GET    | `/api/v1/tags/<id>` | `assets:read` |
| 44b | GET    | `/api/v1/tags/pending-replacements` | `assets:read` |
| 44c | GET    | `/api/v1/tags/replacements` | `assets:read` |
| 44d | POST   | `/api/v1/tags/<id>/request-replacement` | `tagging:write` |
| 44e | POST   | `/api/v1/tags/<id>/approve-replacement` | `approvals:write` |
| 44f | POST   | `/api/v1/tags/<id>/reject-replacement` | `approvals:write` |
| 45 | GET    | `/api/v1/home/form-data` | `requests:read` |
| 46 | POST   | `/api/v1/home/quick-submit` | `requests:write` |
| 47 | POST   | `/api/v1/integrations/sap/employee-sync` | `integrations:write` |
| 48 | POST   | `/api/v1/integrations/workflow/callback` | `integrations:write` |
| 49 | GET    | `/api/v1/reports/depreciation` | `dashboards:read` |
| 50 | GET    | `/api/v1/approvals` | `assets:read` |
| 51 | GET    | `/api/v1/approvals/<id>` | `assets:read` |
| 52 | GET    | `/api/v1/approvals/approvers` | `assets:write` |
| 53 | POST   | `/api/v1/approvals/<id>/approve` | `approvals:write` |
| 54 | POST   | `/api/v1/approvals/<id>/reject` | `approvals:write` |
| 55 | POST   | `/api/v1/approvals/<id>/withdraw` | `assets:write` |
| 56 | GET    | `/api/v1/settings/approvals` | `assets:read` |


## 12 · People and roles (handoffs 41, 42, 43)

Three admin-scoped reads (handoff 41) and one write (handoff 42, §12.4).
Creating and deactivating people is handoff 43.

## 12.1 GET `/api/v1/roles` — the role vocabulary

Derived from the group→scope table that mints session tokens, never
restated. One entry per group that grants API scopes, in table order.

### Success — `200 OK`

```json
{"data": [
  {"key": "asset_manager", "name": "Asset Manager",
   "xmlid": "myservice_asset_register.group_asset_manager",
   "scopes": ["approvals:write", "assets:write", "ingestion:write",
              "integrations:write", "locations:write", "settings:read",
              "settings:write"],
   "description": "Full access — create, edit, transfer, dispose, manage PM schedules.",
   "installed": true, "implies": ["asset_user"]}
]}
```

`implies` lists the OTHER roles in this vocabulary a holder of this one
also holds. A role whose group is not installed on the tenant is still
listed, with `installed: false`. `grantable` (handoff 42) says whether §12.4
may grant or remove it: `true` for exactly `asset_user`, `asset_manager`,
`tag_issuing_unit` and `auditor`, `false` for `system` and every other
group — read off the same constant the model refuses on.

## 12.2 GET `/api/v1/users` — who has what

### Request

`q` (name, login or email, substring) · `role` (a key from 12.1 — EFFECTIVE
membership, *who can act as*) · `role_direct` (direct membership only) ·
`active` (`true`/`false`; absent returns both) · `is_api_client`
(`true`/`false`; absent returns both) · `limit`, `cursor`. An unknown role
key is `400 invalid_request` with `details.allowed_values`.

### Success — `200 OK`

```json
{"data": [
  {"id": 7427, "name": "H41 Manager (probe)", "login": "h41_manager",
   "email": "h41.manager@example.invalid", "active": true,
   "kind": "person", "api_client": null,
   "roles_direct":    [{"key": "asset_manager", "name": "Asset Manager"}],
   "roles_effective": [{"key": "asset_user", "name": "Asset User", "via": ["Asset Manager"]},
                       {"key": "asset_manager", "name": "Asset Manager", "via": []}],
   "scopes": ["approvals:write", "assets:read", "assets:write", "..."],
   "scopes_source": "roles",
   "last_login_at": "2026-10-01T21:12:40", "created_at": "2026-10-01T21:04:07"}
 ],
 "pagination": {"next_cursor": null, "previous_cursor": null, "total_estimate": 6}}
```

**`roles_direct` and `roles_effective` are different questions.** On Odoo
19 an implication grants rights without writing a membership row, so the
manager above is a MEMBER of one group and HOLDS two; `via` names the
account's direct group(s) that imply the role, which may be a group outside
this vocabulary (an administrator holding Security Officer through Security
Administrator). A screen that shows
one of these as if it were the other is wrong about access; the SPA leads
with direct (what somebody granted) and shows the implied beside it.

For an API credential `kind` is `"api_credential"`, `api_client` names it,
and `scopes` are the credential's own with `scopes_source: "credential"` —
a client's token is not minted from its groups.

## 12.3 GET `/api/v1/users/<id>` — one account

The same row. `404 not_found` for an unknown id, a structural account
(`__system__`, `public`, `portaltemplate`) or a portal user.

## 12.4 POST `/api/v1/users/<id>/roles` — grant and revoke, as one set

Scope: `admin`. Success: **200**. Idempotent.

The body takes **`roles` and `dry_run` and nothing else**; any other key is
a 400 carrying `details.rejected_fields` and `details.writable`, and nothing
is written. `roles` is the **full set of DIRECT roles** the account should
hold afterwards, among the keys of §12.1 — not a delta. Groups outside the
vocabulary (`base.group_user`, a mail or fleet group) are never touched.

### Request

```bash
acurl -X POST $API/api/v1/users/7427/roles \
  -H 'Content-Type: application/json' \
  -H 'X-Idempotency-Key: 6d1f…' \
  -d '{"roles": ["asset_manager", "tag_issuing_unit"], "dry_run": true}'
```

### Success — `200 OK`

```json
{
  "data": {
    "user": { "id": 7427, "login": "h41_manager", "...": "the row GET /users/7427 would now publish" },
    "before": {
      "roles_direct":    [{"key": "asset_manager", "name": "Asset Manager"}],
      "roles_effective": [{"key": "asset_user", "name": "Asset User", "via": ["Asset Manager"]},
                          {"key": "asset_manager", "name": "Asset Manager", "via": []}]
    },
    "after": {
      "roles_direct":    [{"key": "asset_manager", "name": "Asset Manager"},
                          {"key": "tag_issuing_unit", "name": "Tag-Issuing Unit"}],
      "roles_effective": [{"key": "asset_user", "name": "Asset User", "via": ["Asset Manager"]},
                          {"key": "asset_manager", "name": "Asset Manager", "via": []},
                          {"key": "tag_issuing_unit", "name": "Tag-Issuing Unit", "via": []}]
    },
    "granted": ["tag_issuing_unit"],
    "revoked": [],
    "applied": false
  },
  "meta": { "request_id": "…", "timestamp": "…", "version": "v1" }
}
```

**`dry_run: true` is the same write, rolled back.** Odoo computes the
change exactly as it would apply it — implication included, which is why
`after.roles_effective` is what the screen shows before anybody clicks —
and the savepoint is rolled back: `applied` is `false` and nothing is
written. A change the model refuses is refused on preview as well.

`granted` and `revoked` are the diff of the two DIRECT lists. A replay
under the same `X-Idempotency-Key` returns this body unchanged and applies
nothing twice.

**No second audit.** An applied change is recorded by the hooks on the
models (`GET /reports/access-changes`), naming the TOKEN'S user as the
actor — the credential or the person who called — not Administrator,
although the route runs under sudo.

### Error — `403 forbidden` (not grantable)

```json
{ "error": { "code": "forbidden", "message": "Over the API only these roles can be granted or removed: Asset User, Asset Manager, Tag-Issuing Unit, Auditor. 'Administration / Settings' is not one of them. Making somebody a system administrator, or changing any other Odoo group, is done in the Odoo back office, signed in as a person.", "request_id": "…" } }
```

`system` is a valid key at the route **on purpose**: it reaches the write,
and the refusal is raised on the model under every writer of membership
(`models/access_guard.py`), so what the caller reads is the model's own
sentence. Not by an administrator, not by a credential, not with a flag.

### Error — `403 forbidden` (your own account)

```json
{ "error": { "code": "forbidden", "message": "Nobody grants themselves a role. h41_manager asked to add Auditor to their own account; another administrator has to do that. Removing your own roles is allowed.", "request_id": "…" } }
```

A caller may remove their own roles — a downgrade, within Odoo's
last-administrator guard — and may not add one. The same shape as a move
and a tag replacement: an action that matters takes a second person.

**A refusal writes nothing**, the access record included: it is an
exception, and the transaction rolls back.

### Error — `400 invalid_request`

An unknown key in `roles` names the vocabulary in `details.allowed_values`
and the offenders in `details.rejected_values`; `roles` that is not a list
of strings, or `dry_run` that is not a boolean, is the same code with
`details.field`. A key the body does not accept is the standard refusal
with `details.rejected_fields` and `details.writable` (`["dry_run",
"roles"]`).

### Error — `404 not_found`

An unknown id, a structural account (`__system__`, `public`,
`portaltemplate`) or a portal user — through the same domain as §12.3.

## 12.5 POST `/api/v1/users` — create a person, send the invitation

Scope `admin`. Idempotent (`X-Idempotency-Key`). Handoff 43.

```json
{"name": "Amina Bello", "email": "amina.bello@nrs.gov.ng",
 "roles": ["asset_user", "tag_issuing_unit"], "send_invitation": true}
```

| Key | Required | Meaning |
|---|---|---|
| `name` | yes | As it will appear on records |
| `email` | yes | Their address, and their sign-in name (stored lower-cased as `login`) |
| `roles` | no, `[]` | DIRECT roles to start with, among `GET /roles`; written as `/users/{id}/roles` writes them |
| `send_invitation` | no, `true` | Send the letter now; `false` creates the account silent, to be invited later |

Answers **201** with the user row of §12.2, `invitation.state` `outstanding`
(letter sent) or `never`. The create and the letter share one savepoint: a
letter that cannot be delivered takes the account with it.

| Status | Code | When |
|---|---|---|
| 400 | `invalid_request` | a key outside the four (`details.rejected_fields`, `details.writable`); a missing or malformed `name`/`email`; a `roles` entry outside the vocabulary (`details.rejected_values`, `allowed_values`); a non-boolean `send_invitation` |
| 403 | `forbidden` | a role the model does not let the API grant — `system` or any other `base.*` group — in the model's own sentence (`models/access_guard.py`). **Nothing is created** |
| 409 | `conflict` | the address is already an account's `login` or `email`, active or not — `details.user_id`, `details.active`, and the message says which |
| 500 | `server_misconfigured` | the letter could not be sent: no outgoing mail server, the relay refused — `details.delivery_error`. **Nothing is created.** (A missing sender address is not one of these: the From falls back, as core's reset does, to the company's address, then the sender's, then the recipient's own) |

What the letter is: `myservice_api/data/mail_templates.xml`, rendered by
`res.users._action_reset_password` with the tenant's brand
(`cadra.brand_*`), the organisation's name (`res.company`), and a link on
the host the request came in on. The same method serves the user form, a
create with an email in the back office, and `/web/reset_password`.

## 12.6 POST `/api/v1/users/<id>/invite` — send it again

Scope `admin`, idempotent, **no body key accepted**. A new link, the same
letter, `invitation.sends` + 1, `state` back to `outstanding`. The earlier
link is NOT revoked by this — the token's payload is unchanged — so it stays
valid until its own expiry; what kills every outstanding link is a sign-in or
a deactivation.

| Status | Code | When |
|---|---|---|
| 400 | `invalid_request` | a body key (`rejected_fields`); the account behind an API credential; an account with no email |
| 404 | `not_found` | not an account §12.2 lists |
| 409 | `conflict` | deactivated ("Reactivate the account before inviting them"); has already signed in ("a password reset is theirs to ask for from the sign-in page") |
| 500 | `server_misconfigured` | the letter could not be sent; nothing changed on the account |

## 12.7 POST `/api/v1/users/<id>/deactivate` — take access away

Scope `admin`, idempotent, no body key. Writes `active = False` and nothing
else: roles, records and custody are untouched (handoff 43 §2 measures what
that leaves). From the write: `/auth/login` refuses, every live token is
refused on its next request (`require_jwt`), the refresh family is revoked
on next use, an outstanding invitation token is cancelled.

| Status | Code | When |
|---|---|---|
| 400 | `invalid_request` | a body key; the account behind an API credential ("revoke or deactivate the credential instead") |
| 403 | `forbidden` | your own account ("Another administrator has to") |
| 404 | `not_found` | |
| 409 | `conflict` | already deactivated; the last active system administrator on the tenant **who is a person** — the users behind API credentials hold the group too (bootstrap) and do not count |

## 12.8 POST `/api/v1/users/<id>/reactivate` — give it back

Scope `admin`, idempotent, no body key. `active = True`. Their password, if
they had one, still works; a cancelled invitation is NOT re-sent — the row
says `cancelled` and §12.6 is one call away.

| Status | Code | When |
|---|---|---|
| 400 | `invalid_request` | a body key; the account behind an API credential |
| 404 | `not_found` | |
| 409 | `conflict` | already active |

## 12.9 The `invitation` block on every user row

| Key | Meaning |
|---|---|
| `state` | `never` · `outstanding` (sent, valid, unused) · `expired` (past `expires_at`, unused) · `redeemed` (the person has signed in since the send — tested first, because one sign-in kills the token whatever else says) · `cancelled` (voided unused: a deactivation, or a password reset asked for from the login page, which replaces the token) |
| `sent_at` | last send, naive UTC |
| `sent_by` | `{id, name}` of the administrator, or `null` when the system sent it |
| `sends` | how many times, re-sends included |
| `expires_at` | `sent_at` + `auth_signup.signup.validity.hours` (144 by default); the token carries its own expiry, this is the arithmetic |

Always `never` for an API credential.

## 12.10 GET `/api/v1/brand/logo` — public

The tenant's `cadra.brand_logo` decoded and served as an image, 404 when
none is set. For the letters; mail clients strip `data:` images.

# 13 · What this tenant's sidebar shows (handoff 48)

**Presentation, not permission.** These switches decide which items the app
draws in the sidebar on this tenant. No route reads them: an item switched
off still opens by its address, and every API answers exactly as it did.
What a person may do is their role's scopes; whether a tenant has a module at
all is installation. The payload carries the sentence (`statement`) and
`is_a_permission: false` so no consumer has to infer it.

An item is DRAWN when the tenant shows it (here) **and** the person's scopes
open it (the app's nav table, handoff 46). Neither axis consults the other.

## 13.1 GET `/api/v1/settings/sidebar` — any signed-in caller

Any valid token, whatever its scopes — the app asks on every screen.

```json
{
  "statement": "This decides what the sidebar shows on this tenant. It is not a permission: …",
  "is_a_permission": false,
  "default_when_unset": true,
  "rule": "An item is shown when its own switch and its group's switch are both on. …",
  "locked_reason": "The Sidebar screen is where these switches are changed. …",
  "parameter_prefix": "cadra.sidebar.",
  "hidden_items": ["fleet", "staff_bus"],
  "groups": [
    {"key": "fleet_transport", "enabled": false, "configured": true, "locked": false,
     "changed_by": {"id": 10371, "name": "Oluwaseun Ajayi"}, "changed_at": "2026-10-03 12:18:16.661209",
     "items": [
       {"key": "fleet", "enabled": true, "shown": false, "configured": false, "locked": false,
        "changed_by": null, "changed_at": null}
     ]}
  ]
}
```

- `enabled` is the switch's own position; `shown` (items only) is what is
  drawn: the item's switch AND its group's. A group switched off hides its
  items and leaves their own switches as they are, so switching it back on
  restores exactly what was there.
- `configured: false` means nobody ever set it and the default (on) applies.
- `locked`: the Sidebar screen (`sidebar_settings`) and its group
  (`settings`) are always on — see the refusal below.
- `changed_by` / `changed_at`: the LAST write only, as
  `/reports/configuration-changes` reports it. `changed_at` is UTC in the
  API's usual `YYYY-MM-DD HH:MM:SS.ffffff` form (no zone suffix), like every
  other timestamp this API serialises.

**The keys are stable identifiers**, not labels, paths or scopes. A key is
never renamed or reused; one that leaves the table is retired. 10 groups, 28
items: `dashboards` (`facility_command_center`, `fleet_command`,
`it_assets_command`), `asset_register` (`asset_dashboard`, `all_assets`,
`approvals`, `new_asset`), `operations` (`locations`, `new_location`),
`hr_staff` (`employees`, `sap_sync`, `bulk_import`, `identity_clearance`),
`fleet_transport` (`fleet`, `staff_bus`), `reports` (`fleet_roster`,
`asset_inventory`, `maintenance_readiness`, `location_coverage`,
`tag_adoption`, `depreciation_report`), `settings` (`asset_categories`,
`branding`, `depreciation_settings`, `sidebar_settings`), `audit`
(`access_changes`), `administration` (`users`), `tools`
(`barcode_station`).

## 13.2 PATCH `/api/v1/settings/sidebar` — `admin`

```json
{"groups": {"fleet_transport": false}, "items": {"fleet_command": false}}
```

Only the switches named change. `true` = shown, `false` = hidden. Answers
the GET's payload. Every refusal is a `400 invalid_request` that says
*Nothing was written* — the other switches in the same body included:

| refused | `details` |
|---|---|
| a body key other than `items` / `groups` | `rejected_fields`, `writable` |
| neither names anything | `writable` |
| an unknown item or group key | `unknown`, `allowed_values` |
| a value that is not a JSON boolean | `not_boolean` |
| `items` / `groups` present and not an object — `false`, `[]` and `""` included | the value |
| `sidebar_settings` or `settings` to `false` | `locked_items`, `locked_groups` |

The last is the lockout: with the screen these switches are changed from
hidden, nothing could be switched back on from the app.

**Storage, and the audit trail.** One `ir.config_parameter` row per switch —
`cadra.sidebar.item.<key>` / `cadra.sidebar.group.<key>`, value `on` or `off`
— so each appears in `/reports/configuration-changes` under its own key with
the person who last wrote it. Switching on what nobody switched off writes
no row; switching back on writes `on` and never deletes, because a deleted
parameter leaves no tombstone in that report.

