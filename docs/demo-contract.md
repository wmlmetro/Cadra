# Cadra demo contract — the Cadra half of the end-to-end chain

**Tenant: `nrs19`. Verified live against it on 2026-09-05** (handoff 04). Every
request and response below was executed, not composed — see
`docs/handoffs/04-REPORT.md` for the run.

This is the document the Vendra side builds its runnable demo script against:
a goods receipt in Vendra → assets in Cadra with provenance → tags printed →
tags confirmed affixed → the assets reading as genuinely tagged.

---

## 0. What you need before you start

| Thing | Value | Where it comes from |
|---|---|---|
| Base URL (local) | `http://nrs19.localhost:8069` | host-based tenancy |
| Base URL (staging) | `https://<tenant>.cadra.ng` | same rule, real DNS |
| `Host` header | **`nrs19.localhost`** | see the warning below |
| Vendra credentials | `client_id=vendra` | `docs/api/.creds.nrs19` |
| Tag-Issuing Unit credentials | `client_id=tag_issuing_unit` | `docs/api/.creds.nrs19` |
| Asset category | **`category_id: 17`** (`PC` — Desktop / Laptop Computer) | `nrs19`'s own tree |

> **Cadra routes by `Host`, and everything below is per-database.** Client ids,
> secrets, `jwt_secret` and **category ids** all belong to one tenant. Vendra's
> `default_cadra_category` was `73`, which is `cadra19`'s id for
> *Desktop / Laptop Computer*; on `nrs19` that category is **17** and id 73 does
> not exist. Send 73 here and you get a `400`, not a wrong-category `201` — but
> do not rely on that: an id that happens to exist on both tenants and means
> different things would file the asset in the wrong place with a `201`.
> `nrs19`'s categories are ids **1–22**; the full list is in the report. The
> observed response to the stale id:
>
> ```json
> {"error": {"code": "validation_failed",
>            "message": "Referenced record does not exist",
>            "details": {"db_detail": "Key (category_id)=(73) is not present in table \"nrs_asset_category\".",
>                        "constraint": "nrs_asset_category_id_fkey",
>                        "http_status": 400}}}
> ```
>
> The `nrs19` ids the demo is likely to want:
>
> | id | code | name |
> |---|---|---|
> | 16 | `SRV` | Server / Network Equipment |
> | **17** | **`PC`** | **Desktop / Laptop Computer** |
> | 18 | `PRT` | Printer / Photocopier |
> | 19 | `FURN` | Office Furniture |
> | 20 | `VEH` | Vehicle |

Provisioning both clients is a step in `scripts/bootstrap.py`
(`ensure_vendra_client`, `ensure_tagging_client`), not a command anyone has to
remember. Re-running it re-narrows the scopes.

### The two credentials are deliberately not one

| Client | Scopes | Can | Cannot |
|---|---|---|---|
| `vendra` | `assets:read assets:write` | create and read assets | **confirm a tag affixed** (403) |
| `tag_issuing_unit` | `tagging:write` | confirm a tag affixed | **read the register** (403) |

That separation is the control, not decoration. An affix confirmation submitted
by the same credential that created the asset would prove only that one system
said so twice. Do not run the demo as `test_client` (which holds `admin`, a
wildcard) — it would pass every step and demonstrate nothing.

---

## Step 1 — authenticate, twice

```http
POST /api/v1/auth/token
Host: nrs19.localhost
Content-Type: application/json

{"client_id": "vendra", "client_secret": "<from docs/api/.creds.nrs19>"}
```

`200`:

```json
{"data": {"token_type": "Bearer",
          "access_token": "<jwt>",
          "expires_in": 3600,
          "refresh_token": "<opaque>",
          "scope": "assets:read assets:write"},
 "meta": {"request_id": "...", "timestamp": "...", "version": "v1"}}
```

Repeat for `tag_issuing_unit` — its `scope` comes back as exactly
`tagging:write`. **Check the `scope` field.** If it comes back empty, the client
has no permissions and every call below will 403; if it comes back wider than
the table above, someone widened the client by hand.

Both tokens are `Authorization: Bearer <access_token>` from here on.

---

## Step 2 — Vendra creates the asset (INT-03)

```http
POST /api/v1/assets
Authorization: Bearer <vendra token>
X-Idempotency-Key: <uuid, one per receipt line>
Content-Type: application/json

{"name": "HP LaserJet Pro M404dn",
 "serial_number": "DEMO-SN-66604160",
 "make": "HP", "model_name": "LaserJet Pro M404dn", "manufacturer": "HP Inc.",
 "category_id": 17,
 "condition": "new", "state": "active",
 "purchase_date": "2026-09-01", "purchase_value": 425000.0,
 "grn_reference": "GRN-DEMO-CA347C",
 "purchase_order_reference": "PO-DEMO-0001",
 "purchase_vendor": "Computer Warehouse Group",
 "import_source": "vendra",
 "import_date": "2026-09-05",
 "import_ref": "VENDRA-RCPT-DEMO-01"}
```

`201`, with the parts that matter:

```json
{"data": {"id": 11879,
          "asset_code": "NRS-AST-047513",
          "tag": "NRS-PC-001",
          "provenance": {"grn_reference": "GRN-DEMO-CA347C",
                         "purchase_order_reference": "PO-DEMO-0001",
                         "purchase_vendor": "Computer Warehouse Group",
                         "import_source": "vendra",
                         "import_date": "2026-09-05",
                         "import_ref": "VENDRA-RCPT-DEMO-01"},
          "tagging": {"tag_number": "NRS-PC-001",
                      "label_state": "issued",
                      "is_tagged": false,
                      "printed_at": null, "printed_by": null,
                      "affixed_at": null, "affixed_by": null,
                      "affixed_by_name": null}}}
```

Three things to read carefully:

- **`data.tag` is populated already and means nothing physical.** It is the tag
  NUMBER, minted at creation. It is marked `deprecated` in the OpenAPI document
  for exactly this reason. **Branch on `data.tagging.is_tagged`**, which is
  `false` here and stays false until step 4.
- **`asset_tag` is not writable.** Send it and it is dropped and reported in
  `data._warnings.rejected_fields` — the tag number is Cadra's to mint, because
  a record whose tag can be edited no longer matches the sticker in the room.
- **`send serial_number`.** Step 4 verifies it, and it cannot verify what it
  was not given.

`X-Idempotency-Key` is scoped `(key, path)` for 24 hours: replaying the same
key returns the identical `201` body rather than a second asset. Use one key
per receipt line so a retried batch cannot duplicate the register.

---

## Step 3 — print the label

**There is no bearer-token endpoint that marks a tag printed, and pretending
otherwise in a demo script would be the false-completeness bug again.** Printing
is stamped where printing actually happens: `ir.actions.report._render_qweb_pdf`.
Anything that renders a tag label PDF stamps it; nothing else does.

Resolve the URL (needs `assets:read`, so this is the Vendra token — note it
takes the **tag label id**, not the asset id):

```http
GET /api/v1/barcode/print-url?tag_id=<tag label id>&size=medium
Authorization: Bearer <vendra token>
```

`200` → `{"data": {"url": "/report/pdf/myservice_asset_register/action_report_asset_tag/11881"}}`
(the id in the URL is the **asset** id — the label reports are all registered on
`nrs.asset`). An unknown id is a `404 not_found` envelope and a non-numeric one a
`400 invalid_request`.

Then fetch that URL. It is a stock Odoo report route: **session auth, not a
bearer token.**

```
POST /web/session/authenticate   {"params": {"db": "nrs19", "login": ..., "password": ...}}
GET  /report/pdf/myservice_asset_register/action_report_asset_tag/<asset id>
```

The render stamps the label. Reading the asset back afterwards:

```json
"tagging": {"label_state": "printed",
            "printed_at": "2026-09-05T21:49:59",
            "printed_by": {"id": 2, "name": "Administrator"},
            "is_tagged": false}
```

**Known limit, stated rather than papered over:** `printed` records that a PDF
was *generated*, not that paper came out of a printer. A print queue would be
more honest and is not worth building. And `is_tagged` is still `false` —
printing a label is not putting it on anything.

Step 4 does not require step 3. A demo that skips printing still works; the
chain is just less complete.

---

## Step 4 — the Tag-Issuing Unit confirms the label is on the asset (INT-04/05)

This is the only call in the API that can make an asset read as tagged.

```http
POST /api/v1/assets/11879/tag-affixed
Authorization: Bearer <tag_issuing_unit token>
X-Idempotency-Key: <uuid>
Content-Type: application/json

{"tag_number": "NRS-PC-001",
 "serial_number": "DEMO-SN-66604160",
 "affixed_by_name": "J. Okafor"}
```

`200`:

```json
{"data": {"asset": { ... },
          "tagging": {"tag_number": "NRS-PC-001",
                      "label_state": "affixed",
                      "is_tagged": true,
                      "affixed_at": "2026-09-05T21:43:52",
                      "affixed_by": {"id": 2, "name": "..."},
                      "affixed_by_name": "J. Okafor"}}}
```

Optional `affixed_at` (ISO 8601) records when a batch was tagged offline rather
than when it synced. A future timestamp is rejected.

### Both halves of the match are checked

| Sent | Result |
|---|---|
| tag number that is not the one Cadra issued | `400 validation_failed` — *"Scanned tag NOT-THE-TAG does not match the tag issued for this asset (NRS-PC-001)"* |
| correct tag, `serial_number` that is not the asset's | `400 validation_failed` — *"Scanned serial WRONG-SERIAL does not match the serial on this asset (DEMO-SN-66604160) — the label may be going onto the wrong asset"*, with `details.scanned_serial` and `details.expected_serial` |
| correct tag, `serial_number` omitted | `200` — optional, because a fixed asset with no legible serial still has to be taggable |
| correct tag, serial supplied but the record has none on file | `400 validation_failed` — it says it cannot check rather than passing quietly |
| correct tag and correct serial | `200`, `is_tagged: true` |

Serial comparison strips whitespace and ignores case.

A repeat confirmation is **not** an error and **does not** rewrite the original
`affixed_at` / `affixed_by_name`. The first record of an observed event is the
evidence; a later submission adds a chatter note.

### The refusals worth showing

```http
POST /api/v1/assets/11879/tag-affixed   with the VENDRA token
→ 403 {"error": {"code": "forbidden", "message": "Missing required scope(s): tagging:write"}}

GET  /api/v1/assets?limit=1             with the TAG-ISSUING-UNIT token
→ 403 {"error": {"code": "forbidden", "message": "Missing required scope(s): assets:read"}}
```

Show these. The separation is the point of the control, and a demo that only
shows the happy path has not demonstrated it.

---

## Step 5 — read the result back

```http
GET /api/v1/assets/11879
Authorization: Bearer <vendra token>
→ 200, data.tagging.is_tagged == true

GET /api/v1/assets?is_tagged=true&grn_reference=GRN-DEMO-CA347C
Authorization: Bearer <vendra token>
→ 200, one asset
```

Filters that close the loop for the Vendra side:

| Query param | Meaning |
|---|---|
| `is_tagged=true\|false` | the physical question. Anything else — `1`, `yes` — is a `400`, never a silently unfiltered list |
| `tag_label_state=issued\|printed\|affixed\|scrapped` | where in the label lifecycle |
| `grn_reference=`, `purchase_order_reference=`, `purchase_vendor=`, `import_source=`, `import_ref=` | provenance, exact match |
| `q=` | free text over name, `asset_code`, `asset_tag`, serial, **and** GRN / PO reference |

---

## Error codes you will actually meet

| Code | Status | When |
|---|---|---|
| `unauthorized` | 401 | bad or missing bearer; bad client credentials at `/auth/token` |
| `forbidden` | 403 | the token lacks the scope — the message names it |
| `invalid_request` | 400 | missing `name`, missing `tag_number`, unparseable/future `affixed_at`, an `is_tagged` value that is neither true nor false, an over-long `X-Idempotency-Key` |
| `validation_failed` | 400 | tag mismatch, serial mismatch, a scrapped tag, an unusable `category_id` |
| `not_found` | 404 | no such asset or tag |
| `conflict` | 409 | two requests racing the same idempotency key |

Every response — success or failure — is the PRD §10.7 envelope with a
`meta.request_id` (or `error.request_id`). Quote it when reporting a problem.

---

## What Cadra does NOT do yet

Say this out loud in the demo rather than letting it be inferred:

- **No outbound callback to Vendra.** Cadra records the affix confirmation; it
  does not push a tag event back. Vendra polls
  `GET /api/v1/assets?is_tagged=true&grn_reference=<grn>`. The transport —
  `ir.cron` retry, backoff, `event_id` idempotency, dead-letter — is its own
  piece of work and is not started.
- **No SAP leg.** INT-06/07 (dual-code reconciliation) and INT-09 (lifecycle
  events) are not built.
- **`printed` means a PDF was rendered**, not that a label physically exists.
