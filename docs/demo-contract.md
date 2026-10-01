# Cadra demo contract — the Cadra half of the end-to-end chain

**Tenant: `nrs19`. Re-verified live against it on 2026-09-06** (handoff 05).
Every request and response below was executed, not composed — see
`docs/handoffs/05-REPORT.md` for the run.

> **Corrections in this revision.** Vendra found six problems building against
> the 2026-09-05 text and we found a seventh. All are fixed here and in the
> code; if you have the previous revision open, these are the deltas:
>
> 1. **A tag label id is not an asset id.** The old Step 3 made them look
>    interchangeable. They are separate id spaces that collide numerically.
>    Read the box in Step 3 before you write any code that builds a print URL.
> 2. **`data.tagging.label_id` is new** — an asset payload now carries the
>    label id directly, so you no longer have to go via `recent-tags` to find
>    the id that `print-url` wants.
> 3. **`GET /api/v1/barcode/print-url` returned a URL that 404'd.** Fixed. The
>    old text quoted that broken URL. If you hard-coded it, re-read Step 3.
> 4. **`?tag_label_state=<bogus>` was `200 []` and is now `400`.** A typo in a
>    poller used to read as "nothing is tagged yet".
> 5. **`GET /api/v1/barcode/lookup` returned a bare 500.** Fixed.
> 6. **`GET /api/v1/asset-categories` is now documented** (Step 0).
> 7. **Asset 11879 is spent** — it is already `affixed`, so Step 4 cannot be
>    replayed against it. The worked example below uses a fresh asset and says
>    which steps are one-way.

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

### Do not hard-code the category id — read it

`category_id` is the one field in Step 2 that is a per-tenant integer, so
resolve it at runtime rather than shipping `17` in a config file:

```http
GET /api/v1/asset-categories
Authorization: Bearer <vendra token>          # scope: assets:read
```

`200` — a **plain array in `data`, not paginated**. Every category is
returned in one response, ordered by `name`; there is no `limit`, no `cursor`
and no `pagination` block, and any query string you send is ignored.

```json
{"data": [{"id": 17, "name": "Desktop / Laptop Computer", "code": "PC",
           "domain": "it", "description": null, "sequence": 10,
           "asset_count": 25, "depreciating_count": 25,
           "pm_interval_days": 365,
           "depreciation": {"method": "declining_balance",
                            "useful_life_months": 48,
                            "declining_rate": 33.3, "salvage_rate": null}},
          ...],
 "meta": {"request_id": "...", "timestamp": "...", "version": "v1"}}
```

Match on **`code`** (`"PC"`, `"SRV"`, `"PRT"`, `"FURN"`, `"VEH"`) rather than
on `name`, which is prose and will be re-worded. Two cautions: `code` and
`domain` are **nullable** — `nrs19`'s two largest categories (`IT Equipment`,
id 21, and `Fleet / Vehicles`, id 22) both carry `"code": null` — so a lookup
keyed only on `code` cannot see them; and the write endpoints on this path
(`POST`/`PATCH`/`DELETE /api/v1/asset-categories`) need `settings:write`,
which the `vendra` client deliberately does not hold.

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
 "serial_number": "DEMO-SN-272279601",
 "make": "HP", "model_name": "LaserJet Pro M404dn", "manufacturer": "HP Inc.",
 "category_id": 17,
 "condition": "new", "state": "active",
 "purchase_date": "2026-09-01", "purchase_value": 425000.0,
 "grn_reference": "GRN-DEMO-27788",
 "purchase_order_reference": "PO-DEMO-0001",
 "purchase_vendor": "Computer Warehouse Group",
 "import_source": "vendra",
 "import_date": "2026-09-06",
 "import_ref": "VENDRA-RCPT-DEMO-02"}
```

`201`, with the parts that matter:

```json
{"data": {"id": 11909,
          "asset_code": "NRS-AST-047543",
          "tag": "NRS-PC-027",
          "provenance": {"grn_reference": "GRN-DEMO-27788",
                         "purchase_order_reference": "PO-DEMO-0001",
                         "purchase_vendor": "Computer Warehouse Group",
                         "import_source": "vendra",
                         "import_date": "2026-09-06",
                         "import_ref": "VENDRA-RCPT-DEMO-02"},
          "tagging": {"label_id": 11905,
                      "tag_number": "NRS-PC-027",
                      "label_state": "issued",
                      "is_tagged": false,
                      "printed_at": null, "printed_by": null,
                      "affixed_at": null, "affixed_by": null,
                      "affixed_by_name": null}}}
```

**Keep `data.tagging.label_id` (here `11905`).** It is the id of the printable
label and the only thing Step 3 accepts. It is **not** `data.id` (`11909`) —
see the warning in Step 3, which is the most important paragraph in this
document. Before 2026-09-06 no asset payload carried it and the only way to
find it was `GET /api/v1/barcode/recent-tags`, which returns `tag_id`
(a label id) and `asset_id` side by side; that endpoint still exists and is
still the way to enumerate recently issued labels, but you no longer need it
just to print.

Three more things to read carefully:

- **`data.tag` is populated already and means nothing physical.** It is the tag
  NUMBER, minted at creation. It is marked `deprecated` in the OpenAPI document
  for exactly this reason. **Branch on `data.tagging.is_tagged`**, which is
  `false` here and stays false until step 4.
- **`asset_tag` is not writable.** Send it and the whole request is refused —
  `400 invalid_request`, `details.rejected_fields: ["asset_tag"]`, and NO asset
  is created (since 21 September 2026; until then it was dropped with a 201
  and a warning). The tag number is Cadra's to mint, because
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

> ## ⚠ A tag label id is not an asset id
>
> **This is the one mistake in this document that damages physical property.**
>
> Cadra has two separate id spaces here and they **collide numerically**:
>
> | | what it identifies | where you get it |
> |---|---|---|
> | **label id** | a row in `nrs.asset.tag.label` — one printable sticker | `data.tagging.label_id`, or `tag_id` from `/barcode/recent-tags` |
> | **asset id** | a row in `nrs.asset` — one machine | `data.id`, the `<id>` in `/api/v1/assets/<id>` |
>
> In the worked example below one asset is **asset id 11909** with **label id
> 11905**. The numbers are close together and neither is derivable from the
> other.
>
> **This is not hypothetical.** On `nrs19` today there are **22 assets whose
> asset id is also a valid label id belonging to a different asset**. Run
> against the live data:
>
> ```
> GET /api/v1/assets/11881          → data.tagging.label_id = 11880  (tag NRS-PC-002)
>
> GET /barcode/print-url?tag_id=11880   → .../report_asset_tag_label/11881   ✅ correct
> GET /barcode/print-url?tag_id=11881   → .../report_asset_tag_label/11882   ⚠ 200 OK
> ```
>
> That second call passed asset 11881's **own id** where a label id belongs.
> It did not fail. It returned `200` and a URL that renders **asset 11882's**
> label — tag `NRS-PC-003`, a different machine. Nothing validates the
> mistake, because `11881` is a perfectly real label id; it just is not
> *this* asset's.
>
> So the failure mode has no error message: you get `200`, a real PDF, a real
> tag number, and somebody walks over and sticks it on the wrong machine. The
> register then says that machine carries a tag it does not carry, and the
> tag it does carry belongs to something else. Both statements survive an
> audit looking correct.
>
> Note also that `print-url` takes a **label id in** and hands an **asset id
> back** inside the URL, so round-tripping the id out of a returned URL and
> feeding it in again is the same bug one step removed.
>
> **Rule: `print-url` consumes `data.tagging.label_id` and nothing else.
> Never reconstruct a print URL yourself, and never take the id back out of
> one.**

Resolve the URL (needs `assets:read`, so this is the Vendra token):

```http
GET /api/v1/barcode/print-url?tag_id=11905&size=medium
Authorization: Bearer <vendra token>
```

`200`:

```json
{"data": {"url": "/report/pdf/myservice_asset_register.report_asset_tag_label/11909"}}
```

Read that carefully against the request: **`11905` went in, `11909` came
out.** The endpoint does the label→asset translation for you, because the
four label reports are all registered on `nrs.asset`. An unknown id is a
`404 not_found` envelope and a non-numeric one a `400 invalid_request`.

> **Changed in this revision.** Until 2026-09-06 this endpoint returned
> `/report/pdf/myservice_asset_register/action_report_asset_tag/<id>` — built
> from the report *action's xmlid* rather than its `report_name`. Odoo
> resolves that second path segment against `ir.actions.report.report_name`,
> so the URL matched no report and answered the website's **404 page**. The
> one published route from an asset to a printable label had never rendered
> anything. If you copied the old URL shape, take the `url` from the
> response instead of composing it.

Then fetch that URL. It is a stock Odoo report route: **session auth, not a
bearer token** — the JWT means nothing to it.

```
POST /web/session/authenticate   {"jsonrpc":"2.0","params":{"db":"nrs19","login":"...","password":"..."}}
GET  <the url from the response above>          # with the session cookie
```

`200`, `Content-Type: application/pdf`. The render is what stamps the label —
`ir.actions.report._render_qweb_pdf`, not the API call. Reading the asset
back afterwards:

```json
"tagging": {"label_id": 11905,
            "tag_number": "NRS-PC-027",
            "label_state": "printed",
            "printed_at": "2026-09-06T10:16:35",
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

## Replaying this — what is one-way, and what to reuse

The example above is a real run (`nrs19`, 2026-09-06): asset **11909**, label
**11905**, tag `NRS-PC-027`, serial `DEMO-SN-272279601`, GRN
`GRN-DEMO-27788`. Every request and response is copied from it. But **do not
point a demo script at 11909**, or at 11879 from the previous revision:

| Step | Replayable against an existing asset? |
|---|---|
| 1 — authenticate | yes, freely |
| 0 — `GET /asset-categories` | yes, freely |
| 2 — `POST /assets` | creates a **new** asset each run — this is the one to drive from |
| 3 — print | yes, repeatedly. A second render re-stamps nothing: `printed_at` keeps the **first** render's timestamp |
| 4 — `POST /tag-affixed` | **one-way.** Once `label_state` is `affixed` it does not go back, and a repeat confirmation is accepted but does **not** rewrite the original `affixed_at` / `affixed_by_name` |
| 5 — read back | yes, freely |

So a runnable script starts at Step 2 every time and carries `data.id`,
`data.tagging.label_id` and `data.tagging.tag_number` forward through steps 3
and 4. That is also the only way to watch `is_tagged` flip from `false` to
`true`, which is the thing worth showing.

**Asset 11879** — the worked example in the 2026-09-05 revision — is spent:
it is already `affixed`, with a null `printed_at` (it was affixed without
ever being printed, which the model permits and step 4's independence from
step 3 explains). Reading it back still demonstrates the end state, and the
403 refusals can be shown against it, but steps 3 and 4 cannot be replayed
against it in a way that changes anything.

---

## Step 4 — the Tag-Issuing Unit confirms the label is on the asset (INT-04/05)

This is the only call in the API that can make an asset read as tagged.

> **Since handoff 39 (2026-10-01) a person can make this call from the app:**
> the barcode station's card carries *Confirm affixed*, which opens a dialog
> the tagger scans the physical label into and sends exactly this request
> (`tag_number`, optional `serial_number` when the record has one, optional
> `affixed_by_name`). The dialog never pre-fills or suggests the expected
> number; the serial field is offered only when the record has a serial.
> The tag and serial mismatches below render in the dialog in the server's
> words (so the wrong-tag refusal names the issued number, as it does over
> HTTP); a repeat is shown as *already confirmed on <date>*.

```http
POST /api/v1/assets/11909/tag-affixed
Authorization: Bearer <tag_issuing_unit token>
X-Idempotency-Key: <uuid>
Content-Type: application/json

{"tag_number": "NRS-PC-027",
 "serial_number": "DEMO-SN-272279601",
 "affixed_by_name": "J. Okafor"}
```

Note the path takes the **asset** id (`11909`), not the label id — this is
the asset resource, not the label resource. The `tag_number` string, not an
id, is what gets matched against the issued label.

`200`:

```json
{"data": {"asset": { ... },
          "tagging": {"label_id": 11905,
                      "tag_number": "NRS-PC-027",
                      "label_state": "affixed",
                      "is_tagged": true,
                      "printed_at": "2026-09-06T10:16:35",
                      "affixed_at": "2026-09-06T10:16:49",
                      "affixed_by": {"id": 2, "name": "..."},
                      "affixed_by_name": "J. Okafor"}}}
```

Optional `affixed_at` (ISO 8601) records when a batch was tagged offline rather
than when it synced. A future timestamp is rejected.

### Both halves of the match are checked

| Sent | Result |
|---|---|
| tag number that is not the one Cadra issued | `400 validation_failed` — *"Scanned tag NOT-THE-TAG does not match the tag issued for this asset (NRS-PC-027)"* |
| correct tag, `serial_number` that is not the asset's | `400 validation_failed` — *"Scanned serial WRONG-SERIAL does not match the serial on this asset (DEMO-SN-272279601) — the label may be going onto the wrong asset"*, with `details.scanned_serial` and `details.expected_serial` |
| correct tag, `serial_number` omitted | `200` — optional, because a fixed asset with no legible serial still has to be taggable |
| correct tag, serial supplied but the record has none on file | `400 validation_failed` — it says it cannot check rather than passing quietly |
| correct tag and correct serial | `200`, `is_tagged: true` |

Serial comparison strips whitespace and ignores case.

A repeat confirmation is **not** an error and **does not** rewrite the original
`affixed_at` / `affixed_by_name`. The first record of an observed event is the
evidence; a later submission adds a chatter note.

### The refusals worth showing

```http
POST /api/v1/assets/11909/tag-affixed   with the VENDRA token
→ 403 {"error": {"code": "forbidden", "message": "Missing required scope(s): tagging:write"}}

GET  /api/v1/assets?limit=1             with the TAG-ISSUING-UNIT token
→ 403 {"error": {"code": "forbidden", "message": "Missing required scope(s): assets:read"}}
```

Show these. The separation is the point of the control, and a demo that only
shows the happy path has not demonstrated it.

**The separation now holds for session users too.** Until 2026-09-06,
`POST /api/v1/auth/login` minted `["*"]` for anyone who could authenticate,
so an Odoo login walked straight around the control that the two clients
above exist to enforce. Scopes are now derived from the user's Odoo groups:
`tagging:write` comes from the **Tag-Issuing Unit** group and from no other,
and an Asset Manager — the role that creates assets — is refused it by the
same 403 as the `vendra` client. This does not change anything you send; it
means the refusal is real from every direction rather than only from the one
the demo happened to show.

---

## Step 5 — read the result back

```http
GET /api/v1/assets/11909
Authorization: Bearer <vendra token>
→ 200, data.tagging.is_tagged == true

GET /api/v1/assets?is_tagged=true&grn_reference=GRN-DEMO-27788
Authorization: Bearer <vendra token>
→ 200, one asset
```

Filters that close the loop for the Vendra side:

| Query param | Meaning |
|---|---|
| `is_tagged=true\|false` | the physical question. Anything else — `1`, `yes` — is a `400`, never a silently unfiltered list |
| `tag_label_state=issued\|printed\|affixed\|scrapped` | where in the label lifecycle. **Changed 2026-09-06:** a value outside the enum is now a `400 invalid_request` carrying `details.allowed_values`. It used to answer `200 []`, so a typo in a poller read as *"nothing is tagged yet"* rather than as an error — the failure a retry loop cannot distinguish from a true negative |
| `grn_reference=`, `purchase_order_reference=`, `purchase_vendor=`, `import_source=`, `import_ref=` | provenance, exact match |
| `q=` | free text over name, `asset_code`, `asset_tag`, serial, **and** GRN / PO reference |

---

## Looking a tag up by number

Not part of the four-step chain, but the endpoint a scanner or a support desk
reaches for, and it was broken until 2026-09-06.

```http
GET /api/v1/barcode/lookup?query=NRS-PC-027
Authorization: Bearer <vendra token>          # scope: assets:read
```

`200`:

```json
{"data": {"found": true,
          "tag_id": 11905, "tag_number": "NRS-PC-027",
          "tag_state": "active", "tag_date": "2026-09-06",
          "asset_id": 11909, "asset_name": "HP LaserJet Pro M404dn",
          "asset_code": "NRS-AST-047543",
          "category": "Desktop / Laptop Computer",
          "domain": "IT & Communications",
          "location": "", "custodian": "",
          "condition": "Good", "state": "Active",
          "last_service_date": "", "next_service_date": "",
          "sap_asset_number": "", "import_source": "myservice"}}
```

`query` matches a tag number first, then an `asset_code`. Note this is the
other place both ids appear together (`tag_id` is the **label** id, `asset_id`
the asset), and that the string fields are **human labels** (`"Good"`,
`"Active"`, `"IT & Communications"`), not the enum keys the `/assets`
endpoints use — do not compare them against `condition=good`.

> **Fixed in this revision.** This endpoint returned a bare
> `500 internal_error` for every asset it actually found. It built a label
> lookup with `dict(field.selection)` on `nrs.asset.domain`, which is a
> *related* Selection whose `.selection` is a callable, not a list — so it
> raised `TypeError` precisely when the asset had a category domain, i.e. on
> every real result. An empty or unmatched `query` is a `404 not_found`
> envelope with `details.query`, not a `400`.

## Error codes you will actually meet

| Code | Status | When |
|---|---|---|
| `unauthorized` | 401 | bad or missing bearer; bad client credentials at `/auth/token` |
| `forbidden` | 403 | the token lacks the scope — the message names it |
| `invalid_request` | 400 | missing `name`, missing `tag_number`, unparseable/future `affixed_at`, an `is_tagged` value that is neither true nor false, a `tag_label_state` outside the enum (with `details.allowed_values`), a non-integer `tag_id`, an over-long `X-Idempotency-Key` |
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
