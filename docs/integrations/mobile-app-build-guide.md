# Cadra Mobile: the build guide

**For:** the Cadra Mobile team and the coding agents building the app.
**What it is:** everything the app calls on Cadra's server, in the order the app
needs it, with the request, the answer, the refusals, and the rules the server
enforces. Build from this file. When you need more detail on one call, the full
contract is `docs/api/cadra_api_endpoint_reference.md` (section numbers are
given as **Ref §N**).
**Written:** 20 October 2026, against Cadra `dev` at release 68 (PR #129).
**Updated:** 28 October 2026 for release 69 (handoff 69, *where the captures
went*): `?q=` on the capture list (§5.8), refused syncs kept and shown to the
Asset Controller (§6.6), and one photo per capture (§7, item 11).
**Replaces nothing:** `docs/integrations/mobile-ai-capture-endpoints.md` is the
history of how each endpoint came to be. This file is the one to build from.

---

## 0 · Read this first (instructions for a coding agent)

1. **The server is finished for this app. Do not invent endpoints.** Every
   route in §5 exists today. If a screen seems to need a call that is not in
   this file, it is either in §11 (*what the server does not do*) or the
   screen is wrong. Ask; do not guess a path.
2. **Generate the client from the server's own spec.**
   `GET https://<tenant>/api/v1/openapi.json` (no sign-in) is the live OpenAPI
   3.0 document. Generate your typed models from it, then use this file for the
   behaviour the spec cannot express (order, offline, refusals).
3. **The phone never decides anything the server decides.** A person confirms
   every value; a second person reviews every capture; the server checks every
   code. The app collects evidence, shows the server's suggestions, and syncs.
4. **Every write the app makes can be replayed safely.** Captures by their own
   `capture_id`, photos by their bytes, other writes by `X-Idempotency-Key`.
   Design the offline queue around that (§7).
5. **Never hard-code a limit.** Read them from `GET /ai/config` (§5.4). The
   numbers in this file are today's values, for your tests.
6. **No secret belongs in the app or in the repo.** The app holds only the
   signed-in person's tokens, in the platform's secure storage. There is no
   API key, no client secret, and no AI provider key on the phone, ever.

---

## 1 · What the app is for

The app is the **audit team's tool in the room** (PRD Lot 4, *AI-assisted
capture and tagging*). An operator walks into a room, scans the door, and for
each item:

1. photographs it;
2. Cadra's server says what the item probably is (class, name, colour,
   condition) and which SAP records it might be;
3. the operator decides which of three things the item is:
   - **`on_register`**: already on Cadra's register (it has a Cadra label, or
     its old FIRS tag matches a Cadra asset, or the operator picks it from the
     room's list);
   - **`in_sap`**: in SAP's register but not yet in Cadra's (the operator picks
     the SAP record);
   - **`in_neither`**: in neither register;
4. for `in_sap` and `in_neither`, prints a label with the next code from the
   phone's block, sticks it on, and scans it back;
5. saves the **capture**, online or offline. It syncs later if offline.

A second person (the **reviewer**) accepts or returns each capture. Accepted,
an `on_register` item is verified in place, an `in_sap` item becomes a new
register asset with SAP's number, and an `in_neither` item becomes an exception
for the Asset Controller. **Nothing the app does is sent to SAP.**

Secondary jobs the same app can do (§9): look up any label, verify an asset,
mark it missing or found, add photos, and (for the Tag-Issuing Unit) confirm a
label affixed.

### 1.1 The people, and what each can call

A person's permissions are **scopes** carried in their sign-in token. They come
from the roles on their account; the app never grants anything.

| Role | Who | Scopes it adds | In the app |
|---|---|---|---|
| **Audit Capturer** | the operator | `audit:read`, `audit:capture`, `sap_mirror:read`, plus Asset User's | the capture flow (§6) |
| **Audit Reviewer** | the second person | `audit:read`, `audit:review`, `sap_mirror:read`, plus Asset User's | the review screens (§8), optional in the app |
| **Asset User** | everyone above | `assets:read`, `locations:read`, `candidates:read`, `requests:read/write`, `identity:read`, `dashboards:read` | lookups, lists |
| **Asset Officer** | register staff | `assets:write` | verify, mark missing/found, asset photos (§9) |
| **Tag-Issuing Unit** | label fitters | `tagging:write` | confirm a label affixed, record prints (§9) |
| **Asset Controller** | the audit lead | `audit:read`, `audit:manage`, `sap_mirror:read`, … | sets up devices, blocks, campaigns: **the web app's job**, listed in §10 |

**The Audit Capturer and the Audit Reviewer can never be the same person**, on
any capture. The server enforces it; the app should not offer a capturer the
review screens for their own captures.

Show or hide screens by the scopes in the sign-in answer (`scope`) or in
`GET /auth/whoami` (`scopes`). A route the token cannot call answers `403
forbidden` naming the missing scope, so a hidden screen is a courtesy, not the
control.

---

## 2 · Environments

| Tenant | Base URL | Use |
|---|---|---|
| staging (demo) | `https://staging.app.cadra.ng/api/v1` | build and test against this |
| local dev | `http://localhost:8069/api/v1` | the Cadra team only |
| production (NRS) | **not decided yet** | the system owner will give it |

Every path in this file is relative to the base URL. Test accounts (one per
role) come from the system owner, never from a file in this repo. Ask for at
least: two Audit Capturers, one Audit Reviewer, one Asset Controller, one
Tag-Issuing Unit account.

---

## 3 · Conventions every call follows

### 3.1 Headers

| Header | When |
|---|---|
| `Authorization: Bearer <access_token>` | every call except §4's sign-in calls and `openapi.json` |
| `Content-Type: application/json` | every JSON body (form-encoded bodies are not accepted) |
| `X-Cadra-Device: DEV-xxxxxxxx` | **every `/audit/captures` POST and `/audit/codes/printed`**; send it on every `/audit/*` call to be simple |
| `X-Idempotency-Key: <uuid>` | every POST/PATCH that changes something, at most 128 characters; lasts 24 hours per (key, path) |

### 3.2 The answer envelope

Success:

```json
{ "data": { "…": "…" },
  "meta": { "request_id": "a1b2c3…", "timestamp": "2026-10-20T08:14:03.512000", "version": "v1" },
  "pagination": { "next_cursor": "eyJsYXN0X2lkIjoxMjh9", "previous_cursor": null, "total_estimate": 1272 } }
```

`pagination` is on lists only. `meta.timestamp` is the **server's clock in
UTC, with no offset written**. Treat it as UTC.

Refusal:

```json
{ "error": { "code": "validation_failed",
             "message": "The scanned label NRS-AST-021341 is not the code NRS-AST-021340.",
             "request_id": "9f8e7d…",
             "details": { "http_status": 400, "…": "…" } } }
```

**Show `error.message` to the person as it is.** The server writes it in plain
words for a person to read. Log `request_id`; the Cadra team needs it to trace
a fault. Branch on `error.code` and, where this file says so, on
`details.reason`.

Two answers are not JSON: the photo bytes (`GET …/photos/<id>`) and the room
label PDF (`GET /locations/<id>/label`).

### 3.3 Error codes (the complete list)

| `error.code` | HTTP | Meaning | What the app does |
|---|---|---|---|
| `invalid_request` | 400 | the request is malformed: a field the route does not take (`details.rejected_fields`, `details.writable`), an unreadable date or cursor | a bug in the app: log it, show the message |
| `validation_failed` | 400, 413, 415 | well-formed, but a rule refused it (wrong scanned label, photo too big, wrong type) | show the message; let the person fix it |
| `unauthorized` | 401 | no token, an expired one, or a bad sign-in | refresh once (§4.2); if that fails, sign in again |
| `forbidden` | 403 | the token lacks a scope, or the person may not do this (not on the campaign, device bound to someone else, the AI switched off) | show the message; do not retry |
| `not_found` | 404 | no such record (also a serial shared by many: `details.ambiguous`) | show the message |
| `conflict` | 409 | the record's state does not allow it now (`details.reason`: `invalid_state`, `not_on_the_register`, `segregation_of_duties`) | show the message; do not retry |
| `tag_number_taken` | 409 | `details.retryable: true`; nothing was written | **retry the same request**, same idempotency key |
| `rate_limited` | 429 | today's AI identifications are used up | fall back to manual entry (§6.4) |
| `internal_error` | 500, 502, 503 | the server or a service it calls failed | retry later with backoff; quote `request_id` |
| `server_misconfigured` | 500, 503 | the tenant is not set up (e.g. AI provider has no key) | tell the person; report to the Cadra team |

A plain network failure, a timeout, or a 5xx: **retry with the same
idempotency key / `capture_id`**. Every other 4xx: **do not retry**; show it.

### 3.4 Lists and paging

- Cursor paging by record id, ascending. Pass `limit` and the previous
  answer's `pagination.next_cursor` as `cursor`; stop when it is `null`.
- `limit` defaults to 50. Most lists cap at 200. `GET /assets` with a person's
  sign-in token takes up to 2,000.
- `?total=0` skips the count when you do not need `total_estimate`.

### 3.5 Syncing a list without missing a row (`updated_since`)

`GET /assets`, `GET /sap-assets` and a campaign's `…/slice` take
`updated_since=<ISO-8601>`. The rule:

1. Ask for page 1 with `updated_since=<the value you saved last time>` (omit it
   the first time).
2. **Save page 1's `meta.timestamp`.** Not the phone's clock, and not the
   largest `updated_at` you saw.
3. Follow `next_cursor` to the end. Upsert every row by `id`.
4. Next time, send the saved timestamp **minus 5 minutes**.

A row may arrive twice; the upsert by `id` makes that harmless. A date the
server cannot read is `400`, never ignored.

### 3.6 Dates and times

Send ISO-8601 **with an offset** (`2026-10-20T09:14:03+01:00`). Nigeria is
UTC+1 with no daylight saving; the server counts "days" on Lagos time.

---

## 4 · Sign-in

A **named person** signs in, never the device (ruling R4). There is no shared
login and no device credential.

### 4.1 `POST /auth/login`

```json
{ "login": "a.person@nrs.gov.ng", "password": "…", "turnstile_token": "…" }
```

`turnstile_token` is needed only on a tenant with Cloudflare Turnstile
switched on (see §11.8). **200:**

```json
{ "data": { "token_type": "Bearer",
            "access_token": "eyJhbGciOi…",
            "expires_in": 3600,
            "refresh_token": "x7mE…opaque…",
            "refresh_token_expires_in": 2592000,
            "scope": "assets:read locations:read audit:read audit:capture sap_mirror:read …" },
  "meta": { "…": "…" } }
```

Refusals: `400` missing `login`/`password` (or `turnstile_token` where
required); `401` *"Invalid login or password"* or *"Account is disabled"*;
`502` the Turnstile check could not be made. An account with no Cadra role
signs in with an empty `scope` and is refused everywhere: tell the person to
ask their administrator for a role.

### 4.2 `POST /auth/refresh`

```json
{ "refresh_token": "x7mE…" }
```

Same answer shape as login, with a **new** refresh token. The access token
lasts 1 hour; the refresh token 30 days from its last use.

**The refresh token is single-use. Replaying a spent one revokes every token
in the chain and signs the person out on every device.** So:

- store the new refresh token **before** you use the new access token;
- run **one refresh at a time** (a single-flight lock). Two requests that both
  see a 401 and both refresh with the same token will sign the person out;
- refresh when the access token is within 5 minutes of expiry, or on a 401,
  then retry the original call once.

`401` means the chain is dead: send the person to sign in. **Keep the offline
queue** (§7) through a sign-in; it belongs to the device, and the server checks
that each item is the signed-in person's.

### 4.3 `POST /auth/revoke`

```json
{ "refresh_token": "…" }
```

Sign-out. Always `200 {"revoked": true}`. Then delete both tokens. The access
token stays valid until it expires (≤ 1 hour).

### 4.4 `GET /auth/whoami`

Any valid token. **200 `data`:** `id`, `login`, `name`, `email`, `partner_id`,
`scopes` (array), `roles` (`[{key, name}]`), `token_type`, `expires_at` (Unix
seconds). Call it at app start to restore the session and draw the menu.

### 4.5 `POST /auth/password-reset` (optional)

The web app's *Forgot password?* flow. It answers the same sentence whether or
not the account exists. Turnstile applies as on sign-in. You may simply link to
the web app's page instead.

---

## 5 · The endpoint catalogue

Every route the app calls, grouped by what it is for. **Scope** is what the
token must carry. **Offline** says whether to cache the answer before the team
goes into the building.

### 5.1 Sign-in (§4)

| Method | Path | Scope | Purpose |
|---|---|---|---|
| POST | `/auth/login` | none | sign in |
| POST | `/auth/refresh` | none (the refresh token) | new token pair |
| POST | `/auth/revoke` | none | sign out |
| GET | `/auth/whoami` | any token | who am I, my scopes and roles |

### 5.2 Reference data (cache for offline)

| Method | Path | Scope | Offline | Purpose |
|---|---|---|---|---|
| GET | `/asset-categories` | `assets:read` | **yes** | every asset class; not paginated |
| GET | `/locations` | `locations:read` | **yes** | the location tree, paged; filters `q`, `parent_id`, `location_type`, `active` |
| GET | `/locations/<id>` | `locations:read` | | one location |
| GET | `/locations/<id>/children` | `locations:read` | | direct children, a plain array |
| GET | `/locations/<id>/label?size=medium\|large` | `locations:read` | | a room's door label as a PDF (`small` refused) |
| GET | `/settings` | `assets:read` | yes | tenant settings; `ai_identify` (`enabled`, `provider`, `provider_label`, `notice`) |
| GET | `/ai/config` | `audit:capture` or `assets:write` | **yes** | the AI switch, calls left today, label layout, capture limits (§5.4) |

**`/asset-categories`, per class:** `id`, `name`, `code`, `domain`,
`description`, `identification_mode`, `class_attributes_schema`
(`{"mandatory": [...]}`, never null), `sap_asset_class` (SAP's four digits, or
null). `identification_mode` decides what a class can be in the app:

| `identification_mode` | Meaning | In an audit capture |
|---|---|---|
| `serial` | identified by the maker's serial | allowed |
| `tag_id` | no maker serial; identified by Cadra's code (furniture) | allowed |
| `record_only` | land, buildings, software: never labelled | **not allowed** for `in_sap` / `in_neither`; hide these classes in the class picker |
| `pool` | not built yet | hide |

**`/locations`, per location:** `id`, `name`, `parent_id`, `parent_path`
(`"1/4/12/"`, the id chain: rebuild the tree from one walk), `location_type`,
and **`location_code`** (e.g. `LOC-HQ-F10-OFCN`), the value printed on the
room's door label.

### 5.3 Scanning and lookup

| Method | Path | Scope | Purpose |
|---|---|---|---|
| GET | `/barcode/lookup?query=<scanned text>` | `assets:read` | resolve **anything scanned**: tag number, asset code, serial, or room code |
| GET | `/assets/<id>` | `assets:read` | one asset in full |
| GET | `/assets?location_id=&updated_since=&limit=&cursor=` | `assets:read` | assets, filtered and synced (§3.5) |

**Use `/barcode/lookup` for every scan.** It tries, in order: tag number →
asset code → serial (trimmed, any case) → room code, and says which matched in
`data.matched_by` (`tag_number`, `asset_code`, `serial_number`, `location`).

- An asset: `found: true`, `asset_id`, `asset_code`, `asset_name`,
  `tag_number`, `tag_id`, `category`, `location`, `condition`, `state`,
  `custodian`.
- A room (`matched_by: "location"`): `matched_location` = `{id, name,
  location_code, path, location_type, parent_id, asset_count}`, no asset.
  **That is "you are in this room", not "not found".**
- A serial on more than one asset: `404` with `details.ambiguous: true` and
  `details.matches`. Ask the person to scan the Cadra label instead.
- Nothing: `404`.

### 5.4 `GET /ai/config`: read once before going offline

```json
{"ai_identify": {"enabled": true, "provider": "anthropic", "model": "claude-opus-5-5",
                 "daily_cap": 500, "calls_today": 37, "remaining_today": 463,
                 "route": "/api/v1/ai/identify"},
 "label": {"content": "the asset code, verbatim — nothing added, nothing removed",
           "symbologies": [{"format": "qr_code", "sizes": ["small", "medium", "large"], "first": true},
                           {"format": "code_128", "sizes": ["large"], "first": false, "note": "…"}],
           "text_line": "the code, printed under the symbol, …",
           "sizes_mm": {"small": [50, 25], "medium": [50, 30], "large": [100, 60]}},
 "capture": {"earliest_captured_on": "2026-10-13", "max_working_days_back": 5,
             "device_header": "X-Cadra-Device", "max_block_size": 500,
             "confirmed_fields": ["name", "category_id", "condition", "make", "model_name",
                                  "serial_number", "colour", "material", "dimensions",
                                  "legacy_asset_code", "notes"],
             "outcomes": ["on_register", "in_sap", "in_neither"]}}
```

`provider` is `anthropic` or `openai` (the tenant chooses); the app never
calls either. Draw the *Identify* button only when `ai_identify.enabled` is
true. Show `ai_identify.notice` from `GET /settings` once per person (*"Photograph
the item, not people. The photo is sent to … to read it."*).

### 5.5 The audit: device, codes, campaign, room

| Method | Path | Scope | Offline | Purpose |
|---|---|---|---|---|
| GET | `/audit/devices?mine=true` | `audit:read` | | the devices bound to me, each with `device_code`, `open_block_id` |
| GET | `/audit/blocks/<id>` | `audit:read` | **yes** | my block, with every `code` and its `state` |
| GET | `/audit/blocks?device_id=&state=issued` | `audit:read` | | blocks for a device |
| GET | `/audit/codes?block_id=&state=reserved&cursor=` | `audit:read` | | the code ledger, paged |
| POST | `/audit/codes/printed` | `audit:capture` + device | | record that I printed these codes |
| POST | `/audit/codes/<code>/void` | `audit:capture` | | void one spoiled code |
| POST | `/audit/blocks/<id>/return` | `audit:capture` (own block) | | hand back my block: unused codes are voided |
| GET | `/audit/campaigns?state=open` | `audit:read` | **yes** | open campaigns (keep those whose `capturers` include me) |
| GET | `/audit/campaigns/<id>` | `audit:read` | | one campaign, with `rooms` progress |
| GET | `/audit/campaigns/<id>/slice?location_id=<room>&kind=assets` | `audit:read` | **yes** | the Cadra assets in a room and under it |
| GET | `/audit/campaigns/<id>/slice?location_id=<room>&kind=sap_records` | `audit:read` | **yes** | the SAP records for that room's office |

**A device** (`GET /audit/devices`): `{id, name, device_code, bound_to: {id,
name}, bound_at, bound_by, active, registered_by, registered_at,
open_block_id}`.

**A block** (`GET /audit/blocks/<id>`): `{id, name ("BLK-000012"), device,
issued_to, size, state ("issued" | "returned"), first_code, last_code,
issued_by, issued_at, returned_by, returned_at, return_reason,
codes_by_state, codes: [...]}`.

**A code:** `{code, state, source, block_id, device_id, reserved_to,
reserved_at, used_at, activated_at, voided_at, voided_by, void_reason,
asset_id, capture_id, print_count, first_printed_at, last_printed_at,
last_printed_by}`. `state`: `reserved` → `in_review` → `active` | `void`.
**A code is never issued twice, to anyone.**

**A campaign:** `{id, name, state ("open" | "closed"), scope: [{location_id,
office_code}], capturers: [...], reviewers: [...], date_start, date_end,
progress: {captured, waiting_for_review, accepted, returned, reviewed,
duplicates_held, exceptions, exceptions_open}}`. A campaign with no location
lines covers every room.

**The room slice, `kind=assets`, per row:** `id`, `asset_code`, `name`,
`asset_tag`, `legacy_asset_code` (the old FIRS tag), `serial_number`,
`category`, `condition`, `state`, `sap_asset_number`, `location_id`,
`updated_at`. Receipt candidates are left out.

**`kind=sap_records`, per row:** `id`, `asset_number`, `sub_number`, `class`,
`description`, `old_tag`, `serial_number`, `capitalized_on`,
`linked_asset_id`, `updated_at`. A room whose office is unknown gets no rows
and a `note` saying so. Both kinds page with `cursor` and sync with
`updated_since` (§3.5). A room outside the campaign is `409`.

**`POST /audit/codes/printed`** `{"codes": ["NRS-AST-021340", …]}` (1–100). All
must be reserved to me on this device and still `reserved`, or nothing is
recorded (`403`; `409` used or void; `400` unknown). **200:** `{"recorded":
[{code, print_count, last_printed_at}]}`. Call it after each print run; it is
the audit trail of how many labels were made.

**`POST /audit/codes/<code>/void`** `{"reason": "label torn at print"}`
(required). Only my own `reserved` code (`403` / `409` / `404`). Answers the
code row. Move on to the next code; this one is gone for good.

**`POST /audit/blocks/<id>/return`** `{"reason": "end of shift"}` (optional).
Every still-`reserved` code is voided; codes `in_review` stay. Answers the
block with `voided_now`. A second return is `409`. Do this at the end of a
shift so the device can be rebound.

### 5.6 SAP's register (read-only)

| Method | Path | Scope | Offline | Purpose |
|---|---|---|---|---|
| GET | `/sap-assets/match?old_tag=&serial=&description=&class=&office=` | `sap_mirror:read` | | up to 5 SAP records this item may be |
| GET | `/sap-assets?office=&class=&updated_since=` | `sap_mirror:read` | optional | a page of SAP records (prefer the room slice in an audit) |
| GET | `/sap-assets/<id>` | `sap_mirror:read` | | one SAP record |

**`/sap-assets/match`**: send any of the five parameters (`office` alone is
refused). It returns up to five **active records not already on Cadra's
register**, ranked: exact old tag → among records sharing that tag, the
description → (no tag match) exact serial → class and description within the
office. Each item: `rank`, `reason_code`, `reason` (show it: *"old tag,
unique"*, *"old tag, shared by 7; description matches"*), and the record
(`id`, `asset_number`, `sub_number`, `class`, `description`, `old_tag`,
`office_code`, `serial_number`, `capitalized_on`, …). The answer also says
`already_linked_note` (*"3 more already on Cadra's register"*): show it, so the
operator knows to look on the room's Cadra list instead. A placeholder serial
(`XXXX`, `0`) is never matched, and `notes` says so.

**Offline**, run the same ranking over the cached `kind=sap_records` slice.

### 5.7 Photos and AI identification

| Method | Path | Scope | Purpose |
|---|---|---|---|
| POST | `/audit/photos` | `audit:capture` | upload a capture's photo (multipart) |
| GET | `/audit/photos/<id>` | `audit:read` | the photo's bytes |
| POST | `/ai/identify` | `audit:capture` or `assets:write` | what is this item? (multipart) |

**`POST /audit/photos`**, multipart: `file` (required), `source` = `mobile`.

- **JPEG or PNG, judged by the bytes.** Anything else `415` (`details.detected`).
- **At most 300 KB (307,200 bytes).** Larger is `413`, never resized by the
  server. Compress on the phone: long edge about 1600 px, JPEG quality 70–80,
  then step down until it fits. Strip EXIF (the location goes in the capture's
  `gps`, not in the picture).
- Damaged, empty, or over 50 megapixels: `400`.
- **201:** `{id, url, mimetype, size, width, height, sha256}`. The same bytes
  sent again by the same person answer the same photo with
  `already_synced: true`. Keep the `id`.

**`POST /ai/identify`**, multipart, **exactly one of**:

| Part | When |
|---|---|
| `audit_photo_id` | **in an audit: always this.** The id `/audit/photos` gave you. Upload once. Only a photo you synced (`403 not_yours`). |
| `photo_id` | a photo already on an asset (§9) |
| `file` + `source=mobile` | outside an audit, for an item not saved yet |

Send `X-Idempotency-Key`: a re-send gets the same answer and is not counted
twice. Expect several seconds (the example below took 4.2 s); set a 30-second client timeout. **201:**

```json
{"suggestion_id": 412, "prompt_version": "67.1", "provider": "anthropic",
 "provider_label": "Anthropic (Claude)", "model": "claude-opus-5-5", "latency_ms": 4210,
 "photo": {"kind": "audit_photo", "id": 55},
 "category": {"id": 12, "name": "Office Chairs", "identification_mode": "tag_id",
              "sap_asset_class": "2000", "confidence": 0.86,
              "alternatives": [{"id": 14, "name": "Office Furniture", "confidence": 0.08,
                                "identification_mode": "tag_id", "sap_asset_class": "2000"}]},
 "attributes": {"name": "HIGH BACK EXECUTIVE SWIVEL CHAIR", "colour": "BLACK",
                "material": "LEATHER", "make": null, "model_name": null, "dimensions": null},
 "condition": {"value": "good", "note": null},
 "size_band": {"value": "medium", "approximate": true, "label": "Approximate size",
               "definition": "…", "definitions": {"small": "…", "medium": "…", "large": "…"}},
 "text_read": [{"text": "FIRS/ABJ/0412", "looks_like": "firs_tag_like"}],
 "sap_candidates": {"count": 1, "basis": "old_tag",
                    "query": {"old_tag": "FIRS/ABJ/0412", "serial": null, "class": "2000",
                              "description": "HIGH BACK EXECUTIVE SWIVEL CHAIR"},
                    "items": [{"id": 9001, "rank": 1, "reason_code": "old_tag_unique",
                               "reason": "old tag, unique", "asset_number": "…", "sub_number": null,
                               "class": "2000", "description": "…", "old_tag": "FIRS/ABJ/0412",
                               "office_code": "ABJ"}],
                    "note": null},
 "notes": [],
 "notice": "Photograph the item, not people. The photo is sent to Anthropic (Claude) to read it.",
 "is_test_fixture": false}
```

How to use it:

- `category` is always one of the tenant's classes; `alternatives` at most two.
  Pre-select `category`, offer the alternatives.
- Pre-fill `attributes` and `condition.value` **as suggestions the person
  confirms or changes**. `make`/`model_name` are null unless legible;
  `dimensions` null unless a label states them.
- `condition.value` is `new`, `good`, `fair` or `poor`. When `condition.note`
  is `"unserviceable"`, put that word in the capture's `fields.notes`.
- `size_band` is display only (*"Approximate size: medium"*). It is not saved.
- `text_read`: a `firs_tag_like` string is probably the old FIRS tag: offer it
  as `legacy_asset_code`, and look it up (§6.3). A `serial_like` string: offer
  it as `serial_number`.
- `sap_candidates.items`: the SAP records to offer for `in_sap` (§6.3).
- `is_test_fixture: true` means a test stand-in answered, not a real model.
  Show a "TEST" badge.

Refusals, each meaning *"fill the details by hand"*: `403` switched off;
`429` today's cap used; `503` provider not ready, timed out or failed; `502`
the provider's answer was discarded. The photo's own `400`/`413`/`415`. On any
of them, continue the capture without a suggestion. **Nothing depends on the
AI being reachable.**

### 5.8 Captures

| Method | Path | Scope | Purpose |
|---|---|---|---|
| POST | `/audit/captures` | `audit:capture` + `X-Cadra-Device` | save a capture (§6.6) |
| GET | `/audit/captures/<capture_id>` | `audit:read` | one capture: confirm a sync, read the review result |
| GET | `/audit/captures?mine=true&state=&campaign_id=&location_id=&outcome=&duplicates=&cursor=` | `audit:read` | lists |
| GET | `/audit/captures?q=<capture_id or code>` | `audit:read` | find one capture, wherever it is (release 69) |

**Confirm my capture arrived.** After a sync, `GET
/audit/captures/<capture_id>` answers the capture, or `404` if the server
does not hold it. From release 69 the same question can be asked of the list:
`GET /audit/captures?q=<capture_id>` (or `?q=<code>`, or the old FIRS tag
the person confirmed) answers every capture whose `capture_id`, code or old
tag IS that text — compared exactly, never a partial match — in any campaign,
open or closed, and combines with the other filters. **No match is `200` with
an empty list**, not a `404`. Each row's `campaign` now carries its `state`
and its `reviewers`, so a support screen can say *"waiting for review in HQ
floor 10, reviewed by …"*. Use `<capture_id>` for the sync check (one row, one
call); use `?q=` for a person's *"where is the chair I captured?"*. Ref §19.6.

The list is **id ascending, cursor-paged**: follow
`pagination.next_cursor` until it is `null`, or the newest captures are the
ones you never see.

The body and every refusal are in §6.6. **A capture as the server answers
it:** `capture_id`, `id`, `campaign`, `location` (`id`, `name`,
`location_code`), `outcome`, `state` (`pending_review` | `accepted` |
`returned`), `asset`, `sap_record`, `code`, `scanned_label`, `label`, `name`,
`category`, `condition`, `fields`, `photos` (each with `url`),
`ai_suggestion` (`id`, `result`, `suggested`), `gps`, `captured_at`,
`received_at`, `captured_by`, `device`, `duplicate_of`, `duplicate_basis`
(`cadra_asset` | `sap_record` | `old_tag`), `reviewed_by`, `reviewed_at`,
`return_reason`, `result_asset` (`id`, `asset_code`, `register_state`),
`reprint_label_id`, `photos_copied`, `exception_state` (`open` | `registered`
| `voided`), and `replayed`.

---

## 6 · The capture flow, screen by screen

### 6.1 First run on a phone (once per device)

1. The Asset Controller registers the phone on the web app and binds it to the
   operator. The web app shows the phone's **`device_code`** (`DEV-` and eight
   hex characters, e.g. `DEV-3fa94c1e`).
2. The operator signs in on the phone (§4.1).
3. The app asks for the device code (typed, or scanned if the Controller shows
   it as a QR) and checks it: `GET /audit/devices?mine=true` must list a device
   with that `device_code`, `active: true`. Store the code in the app's own
   storage. **Do not pick it from the list**: a person may be bound to several
   devices.
4. That device's `open_block_id` is the operator's code block. No block yet:
   show *"Ask the Asset Controller to issue you a block of codes."*

### 6.2 Before going into the building (online)

Download, in this order, and show a "Ready to work offline" tick when all are
done:

1. `GET /ai/config` (limits, label layout, AI on or off).
2. `GET /settings` (the AI notice).
3. `GET /asset-categories` (the class picker; hide `record_only` and `pool`).
4. `GET /locations` (all pages; rebuild the tree from `parent_path`).
5. `GET /audit/devices?mine=true`, then `GET /audit/blocks/<open_block_id>`:
   the codes still `reserved` are the codes this phone may print.
6. `GET /audit/campaigns?state=open`: keep those whose `capturers` include the
   signed-in person. One campaign: select it. Several: let the person choose.
7. For each room the team will visit today (or every room in the campaign's
   scope): `…/slice?location_id=<room>&kind=assets` and `&kind=sap_records`,
   all pages. Save each slice's page-1 `meta.timestamp` for the next sync.

Warn the person when the block has fewer reserved codes than they expect to
need (say, under 20).

### 6.3 In the room

1. **Scan the door label.** `GET /barcode/lookup?query=<code>` online, or find
   the `location_code` in the cached tree offline. `matched_by: "location"`
   sets the room. A room outside the campaign: say so and stop (the server
   would refuse the capture `409`).
2. **For each item, decide what it is.** Work down this list and stop at the
   first answer:

   | The person… | Then the item is… | How the app finds it |
   |---|---|---|
   | scans a **Cadra label** on the item | `on_register`, `label: "present"` | `/barcode/lookup` (online) or the room's `kind=assets` slice by `asset_code`/`asset_tag` (offline). An asset found in another room is fine: acceptance moves it here. |
   | reads an **old FIRS tag** (typed, scanned, or from `text_read`) and a Cadra asset has it as `legacy_asset_code` | `on_register`, `label: "missing"` (no Cadra label on it) | the room slice (`legacy_asset_code`), then online `GET /assets?q=<tag>` |
   | the old tag (or the description) matches a **SAP record** | `in_sap` | `sap_candidates` from identify, or `GET /sap-assets/match`, or the cached `kind=sap_records` slice. A record with `linked_asset_id` set is already on Cadra's register: treat it as `on_register` with that asset. |
   | picks the item from the **room's Cadra list** | `on_register` (`label` as seen) | the `kind=assets` slice |
   | none of these | `in_neither` | — |

3. **Photograph it** (at least one photo; several are fine). Compress (§5.7).
4. **Identify it**, when online and the AI is on: upload the photo
   (`POST /audit/photos`), then `POST /ai/identify` with `audit_photo_id`. Show
   the suggestions as pre-filled, editable values. Offline, or on any refusal:
   the person fills the details by hand.
5. **Confirm the details.** `fields.condition` is always required. For
   `in_sap` and `in_neither`, `fields.category_id` is required; for
   `in_neither`, `fields.name` too. Use the class's
   `class_attributes_schema.mandatory` to mark which other fields to ask for.

### 6.4 The label (`in_sap` and `in_neither` only)

1. Take the **next `reserved` code** from the block that no capture in the
   phone's queue has used yet.
2. Print it. **What the label must encode** (`GET /ai/config` → `label`):
   - **the code itself, verbatim** (`NRS-AST-021340`). No URL, no prefix, no
     suffix, nothing else inside the symbol. The server compares the scanned
     value with the code character for character.
   - **QR code** on every size. **Code 128 only on the large label** (on small
     and medium, a phone camera read it 0 times in 24).
   - the code as text under the symbol.
   - Sizes: small 50×25 mm, medium 50×30 mm, large 100×60 mm.
3. Record the print: `POST /audit/codes/printed` with the code(s) (online;
   queue it offline).
4. Stick it on the item and **scan it back**. The scanned value is
   `scanned_label`. It must equal `code`, or the capture is refused `400`. This
   is the proof the label is on the item. If they differ, the wrong label was
   stuck: fix it before saving.
5. A label that tore or misprinted: `POST /audit/codes/<code>/void` with a
   reason, then use the next code.

**`on_register` takes no code.** The item keeps its own. When its Cadra label
is missing or unreadable, set `label` to `"missing"` or `"unreadable"`: after
review, the Tag-Issuing Unit reprints it under the same code (§11.3). Do not
print anything for it from the block.

### 6.5 GPS (optional)

If the person allows location: `"gps": {"latitude": 9.0579, "longitude":
7.4951, "accuracy_m": 12.5}`. `accuracy_m` is optional; latitude −90…90,
longitude −180…180, any other key is refused. It is stored on the capture only
and is never sent to the AI provider.

### 6.6 Save the capture: `POST /audit/captures`

Headers: `Authorization`, `X-Cadra-Device`. The body:

```json
{"capture_id": "1b9d6bcd-bbfd-4b2d-9b5d-ab8dfbbd4bed",
 "campaign_id": 3,
 "location_id": 812,
 "outcome": "in_sap",
 "sap_record_id": 90211,
 "code": "NRS-AST-021340",
 "scanned_label": "NRS-AST-021340",
 "photo_ids": [55, 56],
 "ai_suggestion_id": 412,
 "captured_at": "2026-10-20T09:14:03+01:00",
 "gps": {"latitude": 9.0579, "longitude": 7.4951, "accuracy_m": 12.5},
 "fields": {"name": "HIGH BACK EXECUTIVE SWIVEL CHAIR", "category_id": 12,
            "condition": "good", "colour": "BLACK",
            "legacy_asset_code": "FIRS/ABJ/0412"}}
```

| Key | Required | Notes |
|---|---|---|
| `capture_id` | always | **a UUID v4 the phone makes the moment the item is captured**, stored with the capture and never changed. It makes the sync replay-safe on any day. |
| `campaign_id` | always | |
| `location_id` | always | the room, from its scanned door label |
| `outcome` | always | `on_register`, `in_sap`, `in_neither` |
| `photo_ids` | always | at least one; each uploaded by this person (`POST /audit/photos`) |
| `captured_at` | always | when the item was captured; at most **5 working days** back (Mon–Fri, Lagos), never in the future (5 minutes' skew allowed). `GET /ai/config` → `capture.earliest_captured_on` is the first day accepted today. |
| `fields` | always | only the 11 keys in `capture.confirmed_fields`; `condition` required (`new`, `good`, `fair`, `poor`) |
| `ai_suggestion_id` | optional | the `suggestion_id` the person saw. Its photo must be in `photo_ids`. |
| `gps` | optional | §6.5 |
| `asset_id` | `on_register` | the Cadra asset |
| `label` | `on_register` | `present` (default), `missing`, `unreadable` |
| `sap_record_id` | `in_sap` | the SAP record the person picked |
| `code`, `scanned_label` | `in_sap`, `in_neither` | equal to each other |
| `fields.category_id` | `in_sap`, `in_neither` | a class that is not `record_only` |
| `fields.name` | `in_neither` | |

Do not send a key that does not belong to the outcome: an `on_register`
capture with a `code`, for instance, is refused `400`.

**201** answers the capture (§5.8). `replayed: true` means the server already
had it: **that is success**.

**A duplicate is held, not refused.** A second capture in the campaign of the
same Cadra asset, SAP record or old tag is saved `201` with `duplicate_of` and
`duplicate_basis`. Tell the person (*"This item was already captured in this
campaign; the reviewer will decide."*) and carry on.

**Refused (no capture saved), and what to tell the person:**

| Status | When | What the app does |
|---|---|---|
| 400 | `X-Cadra-Device` missing or unknown | re-check the device setup (§6.1) |
| 400 | scanned label is not the code | re-scan the label on the item |
| 400 | `captured_at` too old or in the future | the capture is lost to the window: tell the person to re-capture the item |
| 400 | a field not allowed, a `record_only` class, a missing required key | an app bug: log it |
| 403 | device deactivated or bound to someone else | *"Ask the Asset Controller to rebind this device."* |
| 403 | not a capturer on this campaign | stop capturing in this campaign |
| 403 | code not reserved to this device and person | refresh the block; use another code |
| 403 | `capture_id` synced by another person | an app bug (UUIDs must be new) |
| 409 | campaign closed; room outside the campaign | stop; tell the person |
| 409 | code already used (`details.code_state`) | refresh the block; re-label with a new code |
| 409 | the asset is a receipt candidate (`not_on_the_register`) or disposed | show the message; the item cannot be audited now |
| 409 | SAP record retired, not in the latest export, or already on Cadra's register (the message names the asset) | re-decide: capture it as `on_register` with that asset |

**The Asset Controller sees your refusals** (release 69). Every refused
`POST /audit/captures` made with a valid token is kept on the server for
**90 days** — who sent it, from which device, the `capture_id`, `code`,
campaign and room as sent, and the status, error code and sentence the
phone was answered — and the Asset Controller reads it on the web app's
**Devices and codes › Refused syncs** (`GET /audit/refusals`, Ref §19.10).
A `401` and a missing-scope `403` are not kept (there is no verified person
to attribute them to). Nothing of the capture itself is kept: no photo, no
fields, no GPS — the capture still has to be sent again. So:

- **Show the server's `error.message` to the person, verbatim, on any 4xx.**
  The Controller will be reading the same sentence; the person must have seen
  it too.
- **Never mark a capture submitted on any 4xx.** Only a `201` (including
  `replayed: true`) is submitted. A capture the phone shows as submitted that
  the server refused is exactly how handoff 69 began: the person believed it
  sent, the reviewer could not find it, and nothing on the server said why.
- Keep the refused capture on "Needs attention" (§7, item 5) with the
  `error.request_id` from the answer, so the person and the Controller can
  point at the same row.

### 6.7 After the sync: the review result

Cadra does not push. Poll (§11.1):

- after a sync, `GET /audit/captures/<capture_id>` confirms the server has it;
- every few minutes while the app is open (and on app start),
  `GET /audit/captures?mine=true&state=returned` lists the person's returned
  captures, with `return_reason`.

**A returned capture is re-done as a NEW capture, with a NEW `capture_id`.**
Its code (if any) goes back to `reserved` for this device and person, so the
label already on the item can be used again: same `code`, same
`scanned_label`. Re-sending the old `capture_id` only answers the old,
returned capture.

Show per capture: *waiting for review*, *accepted*, or *returned (reason)*.
For an accepted `in_sap` capture, `result_asset.asset_code` is the new
register asset.

### 6.8 End of shift

`POST /audit/blocks/<id>/return` voids the codes not used. Do it only when the
queue is empty: a code used by a capture still in the queue would be voided
before the capture syncs, and the capture would then be refused.

---

## 7 · Offline: the queue

The phone must work a whole day without signal. Design:

1. **Everything the person does is written to a local queue first**, then
   sent. Each item has a local id, its type, its payload, its state (`queued`,
   `sending`, `sent`, `refused`), the last error, and attempts.
2. **One capture is three kinds of queue item, in order:** its photos
   (`POST /audit/photos`), any print records (`POST /audit/codes/printed`),
   then the capture (`POST /audit/captures`). The capture waits until each of
   its photos has a server `id`, then is sent with those ids.
3. **Send in the order the person worked**, one capture at a time.
4. **Retry** on a network failure, a timeout, a `5xx` or a `tag_number_taken`:
   back off (5 s, 30 s, 2 min, 10 min, then every 10 min). The same photo
   bytes and the same `capture_id` are re-sent unchanged, so a retry can never
   make a duplicate.
5. **Do not retry** any other `4xx`. Mark the item `refused`, keep it, and
   show the server's message on a "Needs attention" list.
6. A `401`: refresh once (§4.2). If the person must sign in again, pause the
   queue; resume after sign-in. A queue item made by one person must not be
   sent under another person's sign-in: hold it until the first person signs
   back in.
7. **The 5-working-day window.** A capture not synced within 5 working days
   of `captured_at` will be refused. Warn on the home screen from day 4.
8. **Codes in the queue are spent.** Mark a block code as used locally the
   moment a capture uses it, so the next item never gets it.
9. **AI offline: no suggestion.** A capture made offline carries no
   `ai_suggestion_id`. Link a suggestion only if the person saw it before
   confirming the details: the acceptance report counts what people accepted,
   so a suggestion nobody saw must not be linked.
10. Refresh the cached slices (`updated_since`, §3.5) whenever the phone is
    online and the queue is empty.
11. **Each capture uploads its own photo.** Found on staging in handoff 69:
    the same photo bytes were sent for four different captures (staging
    captures 3, 4, 5 and 6, all carrying photo 8 — three rooms, about 14
    hours apart). The server keeps one copy of the same bytes from the same
    person and answers it again with `already_synced: true` (§5.7), so four
    different items reached the reviewer with one item's picture. Take the
    photo for this item, upload those bytes, and use the `id` that comes
    back for this capture only. **`already_synced: true` on a photo the
    person has just taken of a new item means the app sent an old photo —
    treat it as a bug and log it**; it is correct only for a retry of the
    same capture's upload.

---

## 8 · Review screens (optional in the app; the web app has them)

For an **Audit Reviewer** (`audit:review`). The reviewer is never the
capturer.

| Method | Path | Body | Purpose |
|---|---|---|---|
| GET | `/audit/captures?campaign_id=&location_id=&state=pending_review` | | what waits |
| GET | `/audit/captures?campaign_id=&duplicates=true` | | held duplicates, side by side |
| GET | `/audit/photos/<id>` | | the photos (bytes; `ETag` = SHA-256, cache forever) |
| POST | `/audit/captures/<capture_id>/accept` | none | accept one |
| POST | `/audit/captures/<capture_id>/return` | `{"reason": "…"}` (required) | send back for re-capture |
| POST | `/audit/captures/accept` | `{"capture_ids": [...]}` (1–100) or `{"campaign_id": 3, "location_id": 812}`, plus `"dry_run": true` to preview | accept a room at once; held duplicates are left for one-by-one review |

Accept refusals: own capture `409` (`details.reason: segregation_of_duties`);
not a reviewer on the campaign `403`; already reviewed or campaign closed
`409`; another capture of the same asset or SAP record already accepted `409`
(`details.duplicate_of`: return this one). The batch answers `200` with
`{action, dry_run, total, done, refused, results: [{capture_id, outcome
("done" | "would_do" | "refused"), status, code, message, details,
asset_id}]}`; one refused capture does not stop the others.

Show the reviewer the AI's suggestion beside what the capturer confirmed
(`ai_suggestion.suggested` vs `fields`), and the photos.

---

## 9 · Outside an audit: the field tasks

The same app can serve register staff and the Tag-Issuing Unit. None of these
needs a device code.

| Method | Path | Scope | Body | Purpose |
|---|---|---|---|---|
| GET | `/barcode/lookup?query=` | `assets:read` | | scan anything (§5.3) |
| GET | `/assets/<id>` | `assets:read` | | the asset |
| POST | `/assets/<id>/verify` | `assets:write` | `{"notes": "…"}` (optional) | "I have seen it." The date is today; the verifier is the signed-in person. |
| POST | `/assets/<id>/mark-missing` | `assets:write` | `{"reason": "…"}` (required) | it is not where it should be |
| POST | `/assets/<id>/mark-found` | `assets:write` | `{"reason": "…"}` (required) | a missing asset turned up |
| GET | `/assets/<id>/photos` | `assets:read` | | its photos, newest first |
| POST | `/assets/<id>/photos` | `assets:write` | multipart `file`, `source=mobile`, `caption` (optional) | add a photo (same 300 KB / JPEG-PNG rules; at most 12 current photos) |
| GET | `/assets/<id>/photos/<photo_id>` | `assets:read` | | the bytes |
| POST | `/assets/<id>/photos/<photo_id>/supersede` | `assets:write` | `{"reason": "…"}` (required) | retire a photo (photos are never deleted) |
| POST | `/assets/<id>/tag-affixed` | `tagging:write` | below | confirm a label is on the asset |
| POST | `/tags/printed` | `tagging:write` | `{"tag_ids": [..]}` | record that labels were printed (needed before a reprint can be affixed) |
| POST | `/tags/<id>/request-replacement` | `tagging:write` | `{"reason": "…", "approver_id": N}` | a lost or faded label; an Asset Manager approves |

Send `X-Idempotency-Key` on all of them.

`verify`, `mark-missing` and `mark-found` are refused on a unit still being
received (`409 not_on_the_register`). `mark-missing` on a missing asset, or
`mark-found` on one that is not, is `409`.

**`POST /assets/<id>/tag-affixed`:**

```json
{"tag_number": "NRS-AST-000123", "serial_number": "5XJZ8T3",
 "scanned_format": "qr_code", "attributes_confirmed": true,
 "affixed_by_name": "J. Okafor", "affixed_at": "2026-10-20T11:32:07+01:00"}
```

- `tag_number` (required): the value scanned off the label just fixed.
- `serial_number` (send it when the item has one): the serial read off the
  item; checked against the record.
- `scanned_format` / `serial_format`: the symbology your scanner reports
  (`qr_code`, `code_128`, `data_matrix`, …); recorded when a check fails.
- `attributes_confirmed: true`: **required** the first time a `tag_id` item
  (furniture) is tagged.
- `affixed_at`: when it was fixed, if recorded offline; never in the future.
- A wrong number or serial is `400 validation_failed`, and the refusal is kept
  on the asset's history. A reprint whose print was never recorded on
  `/tags/printed` is refused.

**A photo on an asset can be identified too:** `POST /ai/identify` with
`photo_id`. To save what the person confirmed onto the asset, send
`PATCH /assets/<id>` with the fields plus
`"ai_suggestion": {"id": <suggestion_id>, "ignored": ["material"]}` (Ref §17.2).

---

## 10 · Set-up the Asset Controller does (the web app; listed so you know)

The phone cannot do these. They need `audit:manage`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/audit/devices` | register a phone: `{"name": "Phone 3", "user_id": 42}`; answers its `device_code` |
| POST | `/audit/devices/<id>/bind` | `{"user_id": 42}` or `null`; refused while a block issued to someone else is open |
| POST | `/audit/devices/<id>/deactivate` | refused while a block is open |
| GET | `/audit/people` | who can be bound or named on a team |
| POST | `/audit/blocks` | `{"device_id": 7, "size": 200}` (1–500 codes) |
| POST | `/audit/blocks/<id>/return` | return any block |
| POST / PATCH | `/audit/campaigns`, `/audit/campaigns/<id>` | open a campaign: name, scope (locations, SAP office codes), capturers, reviewers, dates |
| POST | `/audit/campaigns/<id>/close` | refused while anything waits for review |
| GET | `/audit/campaigns/<id>/lists` and `/lists.csv?list=found_not_in_sap\|in_sap_not_found` | the audit's two closing lists |
| POST | `/audit/captures/<capture_id>/register-new` | a *found, not in SAP* item goes onto the register |
| POST | `/audit/captures/<capture_id>/void` | `{"reason": "…"}`; the exception and its code are voided |

**For your testing:** ask the system owner (or use the Asset Controller test
account on staging) to register your test phones, bind them, issue a block of
about 50 codes, and open a campaign covering a few staging rooms, naming your
two capturer accounts and the reviewer.

---

## 11 · What the server does not do (design around these)

1. **No push.** Nothing tells the phone a capture was accepted or returned.
   Poll (§6.7). The capture list has no `updated_since`; filter by `state`,
   `campaign_id`, `location_id`.
2. **No device self-enrolment.** The Asset Controller registers and binds the
   phone; getting the `device_code` onto the phone (typing it, or a QR the web
   app could show) is the app's to design. Cadra prints no device label.
3. **The audit roles cannot finish a reprint.** Accepting an `on_register`
   capture with `label: "missing"` or `"unreadable"` creates the reprint
   (`reprint_label_id`), but printing it (`POST /tags/printed`) and fixing it
   (`POST /assets/<id>/tag-affixed`) need `tagging:write`, which capturers and
   reviewers do not hold. The Tag-Issuing Unit does it (§9). Tell the
   capturer: *"A new label will be issued after review."*
4. **SAP records with no office are not in any room's slice** (about 38,000
   active records today: SAP's export has no location; the office is read
   from the old `FIRS/<office>/…` tag). Find them with `GET /sap-assets/match`
   (online), by old tag, serial or description.
5. **The printer is the app's.** Cadra publishes the codes and the layout
   (§6.4); the printer, its driver and the printing are yours.
6. **Public holidays count as working days** in the 5-day window (it counts
   Monday to Friday only).
7. **No capitalisation threshold** exists anywhere yet (NRS's open question).
   Do not build a "below threshold" rule.
8. **Sign-in on a tenant with Cloudflare Turnstile is not solved for a native
   app.** The server requires `turnstile_token` on `/auth/login` only where
   the tenant has Turnstile configured, and it publishes no site key.
   **Before you build the sign-in screen, ask the system owner whether the
   tenant you will use has Turnstile on.** Build the sign-in so a
   `turnstile_token` can be added later without rework (for example from a
   web view showing the challenge). If it is on, raise it: the Cadra team will
   decide the approach and change the server if needed.
9. **Photos are hosted on Cadra's current servers**, not in Nigeria. NRS must
   accept that in writing before the first photo is stored on the production
   tenant. It does not block building or testing on staging.

---

## 12 · Done when (acceptance checks for the build)

Test each on staging with the test accounts.

**Sign-in and session**

- [ ] Sign in, see the person's name and roles (`/auth/whoami`); screens follow the scopes.
- [ ] After an hour the app refreshes silently; two calls failing at once trigger **one** refresh, and the person stays signed in.
- [ ] Sign-out revokes the refresh token and clears both tokens.

**Set-up and offline**

- [ ] Enter the device code; a wrong or someone else's code is rejected with the server's words.
- [ ] "Ready to work offline" downloads config, classes, locations, block, campaign, and the room slices.
- [ ] With the phone in flight mode: scan a door label, capture three items (one of each outcome), print and scan labels, all saved to the queue.

**The capture**

- [ ] Online with the AI on: a photo of a chair pre-fills class, name, colour, condition, and offers SAP candidates with their reasons.
- [ ] With the AI off (or `429`), the same capture is done by hand with no error shown beyond the server's sentence.
- [ ] A scanned label that differs from the code cannot be saved.
- [ ] A spoiled label is voided and the next code is used.
- [ ] A second capture of the same item is saved and marked as a held duplicate.
- [ ] `on_register` captures send no code; `in_sap` and `in_neither` send code and scanned label.
- [ ] A photo over 300 KB never leaves the phone: it is compressed first.

**Sync**

- [ ] Back online, the queue sends photos then captures; killing the app mid-sync and reopening sends each capture **once** (`replayed: true` is treated as success).
- [ ] A refused capture lands on "Needs attention" with the server's message and is not retried, is never shown as submitted, and appears on the web app's Devices and codes › Refused syncs with the same sentence.
- [ ] Three captures of three different items each carry their own photo: no two captures share a photo `id`, and no fresh photo answers `already_synced: true`.
- [ ] `GET /audit/captures?q=<capture_id>` finds a synced capture; a `capture_id` never sent answers an empty list.
- [ ] A capture 4 working days old shows a warning.

**Review**

- [ ] The reviewer account sees the captures and accepts one; the capturer's app shows *accepted*.
- [ ] The reviewer returns one with a reason; the capturer sees the reason and re-captures it as a new capture, reusing the label already on the item.
- [ ] The capturer account cannot accept its own capture (server `409`, and the app does not offer it).

**End of shift**

- [ ] Returning the block with the queue empty voids the unused codes; with the queue not empty, the app refuses to return it.

---

## 13 · Every route in one list

```
POST   /auth/login
POST   /auth/refresh
POST   /auth/revoke
GET    /auth/whoami
GET    /openapi.json                                   (no sign-in)

GET    /settings
GET    /ai/config
GET    /asset-categories
GET    /locations
GET    /locations/<id>
GET    /locations/<id>/children
GET    /locations/<id>/label?size=medium|large

GET    /barcode/lookup?query=
GET    /assets?location_id=&updated_since=&q=
GET    /assets/<id>

GET    /audit/devices?mine=true
GET    /audit/blocks?device_id=&state=
GET    /audit/blocks/<id>
POST   /audit/blocks/<id>/return
GET    /audit/codes?block_id=&state=&code=
POST   /audit/codes/printed                            (X-Cadra-Device)
POST   /audit/codes/<code>/void
GET    /audit/campaigns?state=open
GET    /audit/campaigns/<id>
GET    /audit/campaigns/<id>/slice?location_id=&kind=assets|sap_records&updated_since=

GET    /sap-assets/match?old_tag=&serial=&description=&class=&office=
GET    /sap-assets?office=&class=&updated_since=
GET    /sap-assets/<id>

POST   /audit/photos                                   (multipart)
GET    /audit/photos/<id>
POST   /ai/identify                                    (multipart)

POST   /audit/captures                                 (X-Cadra-Device)
GET    /audit/captures/<capture_id>
GET    /audit/captures?mine=true&state=&campaign_id=&location_id=&duplicates=
GET    /audit/captures?q=<capture_id | code | old tag>       (release 69)

POST   /audit/captures/<capture_id>/accept             (reviewer)
POST   /audit/captures/<capture_id>/return             (reviewer)
POST   /audit/captures/accept                          (reviewer, batch)

POST   /assets/<id>/verify
POST   /assets/<id>/mark-missing
POST   /assets/<id>/mark-found
GET    /assets/<id>/photos
POST   /assets/<id>/photos                             (multipart)
GET    /assets/<id>/photos/<photo_id>
POST   /assets/<id>/photos/<photo_id>/supersede
PATCH  /assets/<id>                                    (saving an AI suggestion)
POST   /assets/<id>/tag-affixed                        (Tag-Issuing Unit)
POST   /tags/printed                                   (Tag-Issuing Unit)
POST   /tags/<id>/request-replacement                  (Tag-Issuing Unit)
```

All prefixed with `https://<tenant>/api/v1`. Questions about any of them go to
the Cadra team with the `request_id` of the call.
