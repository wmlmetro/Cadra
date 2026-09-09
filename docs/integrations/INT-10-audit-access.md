# Audit ↔ Cadra — Continuous Read Access for Audit and Value-for-Money

**For:** the NRS Internal Audit and Value-for-Money functions, and the Vendra team · **From:** WestMetro Limited (Cadra) · 8 September 2026 · **v0.1 — Cadra's half**
**Covers:** INT-10 (continuous read access for Audit and VFM) of the *End-to-End Integration Flow — Cadra · Vendra · SAP*, September 2026.

Companion to *SAP ↔ Cadra — Asset Master, Dual-Code and Lifecycle Interface Specification* (INT-06/07/09) and *INT-05 — Tag Affixed Callback*. Same programme, same conventions, same contact.

This is **Cadra's half of INT-10, written first and deliberately.** INT-10 spans both systems: Vendra holds the receipt and the money, Cadra holds the register and the lifecycle, and neither can answer an auditor alone. Rather than invent a contract twice, this document states what an auditor needs to ask, what Cadra can answer today, what it cannot, and what Vendra must supply — so Vendra's half can be written against this rather than beside it.

It is written to be argued with. Where Cadra falls short it says so with a number, not an adjective.

---

## ⚠️ 0. The one thing that blocks this document

**"INT-10" appears nowhere in the Cadra repository, and the *End-to-End Integration Flow* document is not in it either.** It is referenced twice as an external source and never quoted. `CLAUDE.md` enumerates the interfaces Cadra owns as INT-03, INT-04/05, INT-06/07 and INT-09 — INT-10 is not among them. The two `.docx` specifications under `docs/` do not use INT- numbering at all.

So **the authoritative definition of INT-10 is not available to the Builder**, and this document reconstructs the requirement from the in-repo specifications instead:

- **`Cadra_at_NRS_Specification_v0.1.docx` §13.4, "Audit and compliance reports"** — the closest thing to an INT-10 requirement list, and the spine of §2 below:
  > *"Standard audit reports available: Asset register snapshot at any historical date (point-in-time view); Custodianship chain for any asset (full history); Disposal report with documentation refs (per period); Access changes for any user (per period); Configuration change log (who changed what setting when). These support internal audit, external audit (AGF, etc.), and any regulatory inquiry."*
- **§13.3** — two delivery patterns offered, both marked `[NRS INPUT REQUIRED]`: webhook event subscription, or *"scheduled bulk extract — daily snapshot of asset register, location register, request register exported to warehouse via secure file transfer."*
- **§3 roles table** — `Auditor` / `audit_viewer` / *"Read-only access to audit logs"*, and `Finance Officer` / `finance_viewer` / *"Read-only access to asset financial data"*. **Neither role exists in Cadra** (§4).
- **§8.6** — likely webhook consumers include *"NRS audit system — subscribes to all events for audit retention."* §8.7, the subscription registry, is a `[TBD]` placeholder.
- **§15** — *"Audit logging: every action logged with actor, timestamp, action, result; 7-year retention."*
- **`Cadra_Platform_PRD_v0.4.docx` §8.14** — *"Every change to an asset is logged. The audit trail includes who, when, what changed (before/after values), and the source (which API call, which user or system)."*
- **PRD line 619** — *"Chain of custody is the full sequence of custodianship records for an asset. The chain is immutable; it cannot be edited retrospectively, only appended. This is an audit-grade record suitable for legal and compliance purposes."*

**Request 1 in §7 is therefore: send us the September flow's INT-10 section.** Everything below is built to survive being corrected by it, but §2's question list is our reconstruction and the delivery pattern in §5 is our recommendation, not a quotation.

---

## Live API reference — Cadra's OpenAPI document

**This document is the story; Cadra's OpenAPI document is the exact schemas.** Read this one first — it explains why the interfaces are shaped as they are, which no schema can. When you are writing code and need the precise field list, types and status codes, fetch:

```
GET https://<cadra-host>/openapi.json      # the machine-readable document
GET https://<cadra-host>/docs              # the same thing, rendered
```

It is generated from the running source, from annotations that sit on the route definitions themselves, so a field cannot be renamed in the code without changing there too.

**Where this document and the live reference disagree, the live reference is right** — tell us, because the disagreement is a defect on our side. It carries no credentials; it describes the authentication scheme and never a value.

---

## 1. The shape of it

INT-10 is not an event interface. It is **standing read access to two registers that must agree**, plus the histories behind them.

| | Route | Direction | Purpose |
|---|---|---|---|
| **1** | **Register query** — Audit calls Cadra | Audit → Cadra | The asset register, filtered and paginated. What exists, where, whose, in what condition and state, with what provenance and what SAP code. |
| **2** | **Asset history** — Audit calls Cadra | Audit → Cadra | For one asset: the chain of custody, the location moves, the tag lifecycle, and the field-level before/after trail. **Does not exist today — §3.** |
| **3** | **Bulk extract** — Cadra to a warehouse | Cadra → Audit | Specification §13.3's second option. A full periodic snapshot, for the questions that are joins rather than lookups. |
| **4** | **Receipt trace** — Audit calls Vendra | Audit → Vendra | The goods receipt, the line, the supplier, the price. **Cadra holds a reference to this and not the thing itself, by design — §5.** |

**Why routes 1 and 3 both.** They answer different shapes of question. "Show me this asset" is a lookup and belongs on the API. "Show me every asset over ₦5m acquired in FY2025 that has never been verified, by department" is a join across the whole register, and asking an auditor to paginate 12,000 records through an HTTP API to compute it is offering an answer in a form that makes the question expensive. §13.3 already anticipates both; we recommend building route 1 properly first, because route 3 without route 1 gives an auditor a file and no way to check a single record against the live system.

**Why route 2 is separate from route 1.** The register answers *what is true now*. Audit's characteristic question is *what was true then, and who changed it*. In Cadra those are different stores — the current value is a column, the history is Odoo's `mail.tracking.value` — and pretending one endpoint serves both is how "point-in-time" quietly becomes "as of the last write".

**Cadra cannot answer route 4 and should not try.** Vendra owns the authoritative GRN and PO records. Cadra deliberately holds `grn_reference` as free text rather than modelling a shadow copy. §5 says what Cadra needs Vendra to expose so the two halves join.

---

## 2. What an auditor actually needs to ask

Eleven questions, drawn from specification §13.4, PRD §5.11 and §8.14, and from what a VFM review of a fixed-asset estate actually does. For each: **can Cadra answer it today, and how.**

Legend: **Yes** · **Partly** — answerable but incomplete or degraded, and the caller is not told · **No**.

### 2.1 "Show me every asset that arrived on this goods receipt."

**Partly.**

```
GET /api/v1/assets?grn_reference=GRN-2026-00412        # exact match, indexed
GET /api/v1/assets?purchase_order_reference=PO-000913
GET /api/v1/assets?q=GRN-2026-00412                    # also works — see below
```

`grn_reference` and `purchase_order_reference` are stored, indexed `Char` columns, exact-matchable as filters and included in the free-text `q` search across 13 fields. That last is deliberate: *an auditor holding a GRN or a PO pastes it into the search box before they think to reach for a named filter.* Both come back in the response's `data.provenance` block alongside `purchase_vendor`, `import_source`, `import_date` and `import_ref`.

**Why only partly.** Three reasons, in order of severity:

1. **The result is capped at 100 rows and the response says it is complete.** See §2.11. This alone makes the answer unsafe for any GRN of more than 100 units.
2. **Nothing records how many units the receipt should have produced.** Cadra registers one row per physical unit; a GRN line of five laptops becomes five assets with five tags, and there is no quantity field. So the query returns *the assets Cadra has* for that GRN, which is not the same as *the assets that GRN produced*. "Did all five arrive and get registered?" is unanswerable from Cadra alone and needs Vendra's line quantity (§5).
3. **`grn_reference` is untracked and PATCHable.** It is in `_WRITABLE_FIELDS` for PATCH as well as POST, and carries no `tracking=True`, so it can be changed after the fact with no record anywhere. The code comment beside it asserts *"any later change is tracked on the asset's mail.thread"*; that is not true, and §3 lists it as a gap rather than leaving the comment to stand.

### 2.2 "Show me every asset tagged last month with no SAP code."

**Partly — the "no SAP code" half is excellent, the "last month" half does not exist.**

```
GET /api/v1/assets?is_tagged=true&has_sap_code=false
GET /api/v1/assets?sap_reconciliation_state=exception
```

`sap_reconciliation_state` is a stored compute over `sap_asset_number`, `tag_label_state` and `sap_posting_state` — it reads no clock, so ordinary dependency propagation keeps it correct and no cron is involved. Its `exception` value **is** this audit finding, computed and filterable: an asset whose tag is confirmed affixed and which carries no SAP asset number. That is the dual-code control point from INT-06/07 surfaced as a query.

**Why only partly: there are no date filters on the register, of any kind.** No `created_after`, no `updated_since`, no `tagged_between`, no `acquisition_date_from`. An auditor cannot ask "last month", and — more consequentially for a *continuous* access interface — **cannot ask "what changed since my last pull."** Every retrieval is a full retrieval, which is exactly what makes the 100-row cap in §2.11 binding rather than merely annoying.

An `updated_since` filter is the single highest-value addition to this API for INT-10 and is cheap: `write_date` is indexed by Odoo on every model.

### 2.3 "Show me who has held this laptop."

**Yes, from 9 September 2026 — with one qualification that must be read
before the answer is used.**

```
GET /api/v1/assets/<id>/custody          # paginated, oldest first
GET /api/v1/assets/<id>?include=custody  # the whole chain, embedded
```

Both take `assets:read`. A link carries the asset, the outgoing and incoming
custodian, the timestamp, **the acting user** — who moved it, which is a
different question from who held it and one the two custodian fields cannot
answer — a free-text reason where the caller gave one, and a `source`.

**Append-only, on the model rather than by access rule.** `nrs.asset.custody`
raises on `write` and on `unlink`, so a link cannot be altered or removed
once recorded: not over the API, not in the Odoo interface, and **not by an
administrator using `sudo()`** — which matters here because every API route
in this codebase calls `sudo()` on every request. An ACL would not have
carried this; an ACL is configuration, and `sudo()` bypasses configuration by
design. The asset link is `ondelete='restrict'`, so deleting an asset cannot
take its history with it either. There is deliberately **no write endpoint**:
a link is a side effect of a custodian change, never a payload.

**Written wherever `custodian_id` moves, not by one route.** The recorder is
in `nrs.asset.write`, because `custodian_id` has at least five writers —
`POST /assets/<id>/transfer-custody`, `POST /assets`, `PATCH /assets/<id>`
(it is in `_WRITABLE_FIELDS`), `nrs.asset.transfer.action_complete`, and
`action_mark_retrieved` when an employee leaves — plus the field being
editable on the Odoo form. Recording in the transfer route alone would have
produced a chain that was incomplete on its first day, and **a gap in an
append-only record is indistinguishable from a period of no movement**, which
is the one failure this model cannot recover from.

**The qualification: `source`, and what `tracking_backfill` means.**

| `source` | what it is |
|---|---|
| `api_transfer` | `POST /assets/<id>/transfer-custody` |
| `api_write` | `POST /assets` or `PATCH /assets/<id>` |
| `transfer` | an `nrs.asset.transfer` completed |
| `direct` | a write that declared no source — the Odoo form, an import, a script |
| `tracking_backfill` | **reconstructed** from the chatter tracking values that predate the model |

The backfill is faithful: a tracking value carries the outgoing employee, the
incoming employee, the acting user and the timestamp, so nothing in a
backfilled link is invented. But it is still a reconstruction, and it **begins
where `custodian_id` became a tracked field, not where the register does**.
Rows written by direct SQL during seeding produced no tracking value and are
therefore absent entirely.

**So a chain is sparser than its asset is old, and that is the correct
picture rather than a defect.** An auditor told where the record begins can
work with it. One who discovers the gap later cannot trust any of it,
including the part that is complete — which is why `source` is published on
every link rather than left in a migration note.

Backfilled on 9 September 2026, per tenant:

| Tenant | tracking values read | custody links written |
|---|---|---|
| `jaizbankplc` | 221 | 221 |
| `gtb19` | 152 | 152 |
| `gtb` | 150 | 150 |
| `lasg` | 150 | 150 |
| `nrs19` | 1 | 1 |
| `cadra19`, `test19`, `nrs` | 0 | 0 |

The two columns agree on every tenant. Three tenants have no history at all
because their registers were seeded without producing tracking values; the
`nrs19` figure of 1 against ~11,878 assets is the same fact in its starkest
form. INT-10 §2.3 previously measured `jaizbankplc` at 217 — four custody
changes were made between that measurement and this one.

**What is still capped, and what is not.** The embedded `transfers` list is
capped at the last 20. `include=custody` is **not**: "the last twenty
custodians" is precisely the answer an auditor cannot use, because a
truncated chain cannot be told from a complete one. The paginated route
reports a true `total_estimate` and announces the record cap in
`_warnings.truncated` like every other list endpoint.

### 2.4 "Show me what changed on this asset, and who changed it."

**No, over the API. Partly, in the Odoo UI.**

PRD §8.14 requires *"who, when, what changed (before/after values), and the source (which API call, which user or system)."* Cadra has the first three for **18 fields** and none of the fourth.

`nrs.asset` inherits `mail.thread`, and 18 fields carry `tracking=True`: `name`, `asset_code`, `asset_tag`, `category_id`, `subcategory_id`, `asset_type_id`, `asset_level`, `domain`, `building_id`, `floor_id`, `room_id`, `location_id`, `custodian_id`, `condition`, `state`, `last_verified_date`, `retrieval_flag`, `depreciation_method`.

**Untracked, and materially so:** `serial_number`, `legacy_asset_code`, `make`/`model_name`/`manufacturer`, `department`, **`grn_reference`**, **`purchase_order_reference`**, **`purchase_vendor`**, `import_source`/`import_date`/`import_ref`, **every `sap_*` field including `sap_asset_number`**, **every financial field** (`purchase_value`, `acquisition_cost`, `current_value`, `replacement_cost`, `accumulated_depreciation`, `current_book_value`), every date except `last_verified_date`, `assignment_date`, `disposal_date`, `disposal_reason`, `notes`.

Read that list against the question a VFM review asks. **Every value an auditor would challenge — what we paid, which receipt it came from, which SAP code it was booked under — can be changed silently.** The identity and location of the asset are tracked; its money is not.

Measured today, `nrs.asset` chatter and tracking rows:

| Tenant | chatter messages | tracking rows | top tracked fields |
|---|---|---|---|
| `nrs19` | 36,901 | 24,959 | `tag_label_state` 11,934 · `depreciation_method` 11,878 · `location_id` 1,146 · `custodian_id` 1 |
| `jaizbankplc` | 3,984 | 1,599 | `tag_label_state` 1,029 · `custodian_id` 217 · `depreciation_method` 209 · `condition` 67 · `location_id` 67 |

The actor is `env.uid`, which since handoff 08 is the API client's **own** `res.users` rather than `Administrator` — so a change made by Vendra now says "Vendra" and one made by the Tag-Issuing Unit says so. **289 historic affix records still carry `Administrator`** and were deliberately not rewritten, because no evidence says which client wrote which and inventing one would fabricate an audit trail. An auditor reading affix records from before that date should treat the actor as unknown, not as the administrator.

There is **no audit-log model of our own** — no `cadra.audit.log`, no before/after table, no per-API-call request log. `workflow.dispatch.log` is an outbound delivery queue, not an audit log. PRD §10's *"every API call produces an audit log entry… immutable and queryable for compliance and forensic purposes"* is not built.

### 2.5 "Show me the register as it stood on 31 March."

**No, except for depreciation.**

`GET /api/v1/assets/<id>/depreciation?as_of=YYYY-MM-DD` is a genuine point-in-time view, and it is genuine for a specific reason: the depreciation engine is a pure function of `as_of` — it rebuilds the whole schedule from the start date and reads off the last elapsed period, persisting no period rows. Missing twelve runs and missing one produce identical output.

Nothing else has an `as_of`. A register snapshot at a historical date would have to be reconstructed by replaying tracking values backwards over the 18 tracked fields, which is unsound for the reasons in §2.4 — the untracked fields cannot be replayed at all.

**Recommendation:** do not build a general point-in-time reconstruction. Build the §13.3 scheduled bulk extract instead and retain the snapshots. A stored daily snapshot answers "as at 31 March" exactly and honestly; a reconstruction answers it approximately while looking exact, which is worse.

### 2.6 "Show me every asset with no physical tag confirmed on it."

**Yes, and this one is genuinely good.**

```
GET /api/v1/assets?is_tagged=false
GET /api/v1/assets?tag_label_state=issued        # printed but never affixed, etc.
GET /api/v1/barcode/untagged                     # the exception list, directly
```

`is_tagged` is true only after an affix confirmation whose **scanned tag number matched the issued one** — the serial-to-tag match is the control, not a status somebody sets from a desk. `label_state` moves only through `_mark_printed` and `_mark_affixed`, guarded by a `write()` override that raises on any other write to the six capture fields, so `group_asset_manager` cannot set it over XML-RPC either.

One caveat an auditor must be told: **the `printed` state was not being recorded until 2026-09-08.** Two independent defects — an id-space guard that declined 99.97% of prints, and Odoo 19's report route being `readonly=True` so the cursor serving a print could not write at all — meant 2 prints were recorded across 17,217 labels, and 341 affixed labels had never passed through `printed`. Affixed is trustworthy throughout; **`printed` is only trustworthy from 8 September 2026 forward**, and a print-coverage question asked of earlier data will be wrong. This is stated here rather than left for someone to discover in a finding.

### 2.7 "What did we pay for it, and what is it worth now?"

**Structurally yes. In practice, no, and this is the binding constraint on Value-for-Money.**

The serializer's `financial` block carries `currency`, `purchase_value`, `replacement_cost`, `acquisition_cost`, `current_value` and a full `depreciation` sub-block (method, useful life, declining rate, salvage, depreciable cost, start date **and whether that start date was estimated**, accumulated depreciation, current book value, state, end date, and whether category policy is in use). `GET /api/v1/reports/depreciation` gives register-wide totals with a per-category breakdown **and two data-quality counts** — assets with inferred start dates, and assets with a method but no cost — which is the right instinct: the report reports its own unreliability.

The problem is coverage. Measured across every tenant today:

| Tenant | Assets | With a cost | With a PO ref | With a GRN ref | With a SAP number | With a serial | Affixed tags |
|---|---|---|---|---|---|---|---|
| `nrs19` | 11,942 | **56 (0.5%)** | 59 | 60 | 2 | 11,323 | 54 |
| `jaizbankplc` | 2,316 | 274 (11.8%) | 143 | 543 | 0 | 102 | 305 |
| `cadra19` | 1,335 | 1,329 | 0 | 13 | 0 | 13 | 0 |
| `nrs` (15-era) | 1,272 | 1,272 | 0 | 0 | 0 | 0 | 0 |
| `gtb19` / `gtb` / `lasg` | 156 / 150 / 150 | 156 / 150 / 150 | 0 | 0 | 0 | 0 | 0 |

These are measured facts, not estimates.

**On the migration target — the register INT-10 is actually about — 99.5% of assets carry no cost at all.** No API change fixes that. A Value-for-Money interface over this register will return nulls for the field VFM exists to examine, and it will do so honestly. The fix is upstream: costs arrive through INT-03 from Vendra, or through SAP on INT-07, or through a data-loading exercise. **Cadra should not synthesise a value it does not have**, and this document says so now rather than after an auditor finds a column of nulls.

Note also that `accumulated_depreciation` and `current_book_value` are in `_WRITABLE_FIELDS` so an ERP can feed `erp_managed` figures — and all 11,878 of `nrs19`'s ERP-managed assets are out of the depreciation cron's domain by design. For those, Cadra reports what SAP told it, not what Cadra computed. An auditor should know which of the two they are reading; `financial.depreciation.state` and `uses_category_policy` are how they tell.

### 2.8 "Has this asset been physically verified, and when?"

**Yes, as of handoff 09 — and it was a false "yes" before that.**

`is_verified` is a stored compute that expires on a per-category window (`nrs.asset.category.verification_interval_days`, falling back to `cadra.assets.verification_interval_days`, defaulting to 365 days), refreshed by a daily cron. `last_verified_date` and `last_verified_by` are written by `action_verify()`.

Until handoff 09 the compute read the clock but depended on nothing the clock changes, so **`is_verified` never expired** — once true, permanently true. It was measured before the fix at exactly **one** true row across 17,123 assets estate-wide, which is what made it safe to correct. Today, measured: `is_verified` is true on **1 of 15,000+ assets** across every tenant. The field is now honest and the answer it gives is "essentially nothing in this estate has been verified", which is a finding, not a defect.

Two caveats for an auditor:
- `last_verified_date` is in `_WRITABLE_FIELDS`, so an API client with `assets:write` can set it directly without going through `action_verify()` — which means without writing `last_verified_by` or a chatter note. A verification date with no verifier is a weaker record than it looks.
- `last_verified_by` and `verification_notes` are **not in the serializer at all**. An auditor cannot see who verified an asset over the API even when the field is set.

### 2.9 "What has been disposed of, and on whose authority?"

**Partly.** `state = 'disposed'`, `disposal_date` and `disposal_reason` exist and are filterable via `?state=disposed`. `state` is tracked, so the transition has an actor and a timestamp in chatter.

Missing against §13.4's *"disposal report with documentation refs (per period)"*: there is **no documentation reference field** — no board minute, no approval reference, no disposal certificate — `disposal_date` and `disposal_reason` are untracked, and there is no period report endpoint. Note also that `state = 'missing'` is deliberately **not** a disposal; an asset that cannot be found has not been disposed of, and conflating them would let a loss be written off as a disposal.

### 2.10 "Who had access to what, and when did that change?"

**No.** Specification §7.6 requires *"every identity-related event in Cadra (login, role change, account creation, deactivation) recorded in Cadra's audit log with reference to the upstream IdP event"*, and §13.4 requires *"access changes for any user (per period)"*.

There is no such log. Group membership changes are Odoo's own `res.users` writes; API client scope changes are writes to `myservice.api.client`; neither is exposed, and neither is tracked in a form an auditor can query. There is one specific hazard worth recording: `_provision_client_user` writes a client user's groups with `(6, 0, …)` — a full replace — on every scope change, so a group granted to a client user by hand is destroyed the next time the scope list grows, silently.

### 2.11 "Give me the whole register." — and why every answer above is capped

**No, and this is the defect that must be fixed before INT-10 can be built at all.**

A token minted by `POST /api/v1/auth/token` — i.e. **every machine credential**, which is what an audit integration holds — carries no `aud` claim. Tokens minted by `POST /api/v1/auth/login` carry `aud="frontend"`. The pagination layer treats the second as internal and the first as external, and the external limits are:

```
MAX_PAGE_LIMIT          = 2000
EXTERNAL_MAX_PAGE_LIMIT = 100
EXTERNAL_TOTAL_CAP      = 100
```

The external domain is narrowed to `("id", "in", <first 100 ids>)` **before** cursor filtering. Proven live against `jaizbankplc`, whose register holds 2,316 assets, on a client-credentials token asking for 2,000:

```json
"pagination": {
  "next_cursor": null,
  "previous_cursor": null,
  "total_estimate": 100
}
```

100 rows returned. `next_cursor: null` — there is no next page. `total_estimate: 100` — **the response asserts that 100 is the whole register.** `GET /api/v1/assets/export.csv` on the same credential returns 101 lines: a header and 100 rows.

This is not a rate limit an integrator works around. It is a silent, complete, confident wrong answer, and it fails Cadra's own architecture rule 3 — *anything that silently degrades is a defect even when it returns 200.* Every "yes" and "partly" in §2 above is subject to it: an auditor filtering by GRN, by SAP exception, by tag state or by disposal gets at most 100 matches and is told that is all there were.

**Nothing here argues the cap should not exist** — it protects the register from an unbounded scan. The three things wrong with it are that it applies to the wrong axis (audience, not scope or client), that it lies in `total_estimate`, and that there is no cursor by which a legitimate caller can walk past it. §7 asks for the specific fix.

---

## 3. What is missing — the fields an auditor relies on, and what keeps each honest

A register can answer a question with a field that has not been true for a year. `is_verified` was exactly that: a published boolean, permanently true once set, backing a control nobody had checked. That is the shape of the problem this section exists to prevent.

Every field below is stored — either a plain column or a stored compute. **A stored compute whose body reads the clock is wrong from the moment it is written unless something recomputes it**, and until handoff 08 no `ir.cron` ran on any local tenant at all, so "there is a cron" was itself an unverified claim for the whole life of these fields.

### 3.1 The stored computes, and what refreshes each

| Field | Model | Kind | What keeps it honest | Trustworthy since |
|---|---|---|---|---|
| `is_verified` | `nrs.asset` | stored compute, reads the clock | `_cron_refresh_verification`, **daily** | 2026-09-08 (h09) |
| `is_overdue` | `nrs.asset.pm` | stored compute, reads the clock | `_cron_refresh_overdue`, **daily**, priority 1 | 2026-09-08 (h09) |
| `sla_breached` | `request.request` | stored compute, reads the clock | `_cron_refresh_sla_breached`, **hourly** | 2026-09-08 (h09) |
| `on_duty` | `security.guard` | stored compute, reads the clock | `_cron_refresh_on_duty`, **daily** | 2026-09-08 (h09) |
| `maintenance_status` | `fleet.vehicle` | stored compute, reads the clock | `_cron_refresh_maintenance_status`, **daily** | 2026-09-08 (h09) |
| `sap_reconciliation_state` | `nrs.asset` | stored compute, **no clock** | ordinary `@api.depends` propagation — no cron needed | always |
| `physical_tag_id`, `active_tag_id`, `tag_label_state` | `nrs.asset` | stored computes, no clock | `@api.depends` on the label's state | always |
| `next_service_date` | `nrs.asset` | stored compute, no clock | depends on `pm_schedule_ids.next_due_date`, refreshed indirectly by the PM cron | always |
| `depreciable_cost`, `salvage_value`, `depreciation_start_is_estimated` | `nrs.asset` | stored computes, no clock | `@api.depends` | always |
| `accumulated_depreciation`, `current_book_value`, `depreciation_state`, `depreciation_end_date` | `nrs.asset` | **plain stored, not computes** | `cron_asset_depreciation`, **monthly**; `erp_managed` assets excluded by design | see below |

**On the depreciation figures.** They are plain columns written by a monthly cron, so between runs they are up to a month stale — measured at ~₦23.1m of drift estate-wide, all of it exactly one month, corrected by a single run. That is acceptable and self-healing, because the engine is a pure function of `as_of`; it never appends. But an auditor comparing a book value read on the 28th against one computed on the 1st should expect a month's difference and not treat it as an error. `nrs19`'s 11,878 ERP-managed assets are outside the cron entirely — those figures are SAP's, not Cadra's.

**The distinction that matters:** the five clock-reading computes are correct *because a cron exists and runs*, and the rest are correct *because Odoo's dependency graph makes them so*. The first group has an operational failure mode — a dead scheduler, a `limit_time_real` kill, a tenant nobody upgraded — and the second does not. Any audit claim resting on the first group should be qualified by "as of the last cron run", and Cadra should expose that. It currently does not.

### 3.2 Fields that nothing keeps honest

| Field | Why it matters to an auditor | What guards it |
|---|---|---|
| `grn_reference`, `purchase_order_reference`, `purchase_vendor` | the whole provenance trail | **nothing** — writable on PATCH, untracked, unvalidated against Vendra |
| `sap_asset_number` | the dual-code control | **deliberately unguarded** so legacy linking can happen; `sap_code_source` (`integration`/`import`/`manual`) is the control instead, and *it* is guarded — only the integration context may claim `integration` |
| `sap_synced_at`, `sap_code_source` | the evidence that SAP said so | guarded — a hand-write raises |
| `serial_number` | the identity control on INT-05's match | **nothing** — freely PATCHable and untracked |
| `department` | every departmental VFM cut | **nothing** — free text, 808 distinct values on the live register |
| `label_state`, `printed_*`, `affixed_*` | the tagging control | strongly guarded — a `write()` override raises unless the capture context flag is set; `_mark_affixed` verifies the scanned number and refuses to overwrite a prior affix |
| `asset_code` | the primary key of the whole programme | `required` + `NOT NULL` + DB `UNIQUE`, `readonly`, minted from a sequence, tracked, and **not writable over the API** |
| `asset_tag` | the physical label number | tracked, minted by Cadra, **deliberately removed from `_WRITABLE_FIELDS`** — a client could otherwise PATCH it until it no longer matched the physical label, defeating the affix control |
| `last_verified_date` | the verification control | tracked, but **writable over the API without an actor** — §2.8 |
| `assignment_date`, `last_verified_by`, `verification_notes`, `retrieval_*` | custody and verification evidence | stored but **not serialized** — invisible over the API |
| `nrs.asset.custody` (every column) | the chain of custody itself | strongly guarded — `write` and `unlink` raise on the model, so no link can be altered or removed after the fact, including under `sudo()`; the asset link is `ondelete='restrict'` so deleting the asset cannot erase it either |

**The pattern is worth naming.** Everything Cadra *generates* — the asset code, the tag number, the affix record, the SAP code source — is guarded properly, most of it by a write override rather than by `readonly=True`, because `readonly=True` is a web-client hint and not an ORM guard. Everything Cadra *receives from another system* — the provenance references, the serial, the department, the money — is guarded by nothing at all. For an interface whose purpose is tracing an asset back to what was paid for it, that is the wrong way round.

### 3.3 The three things that do not exist

1. ~~**A custody history model.**~~ **Built** — `nrs.asset.custody`,
   9 September 2026. §2.3. What remains is the *reach* of the backfill, not
   the model: three tenants start empty and `nrs19` starts with one link,
   because the history before this date only exists where chatter tracking
   captured it.
2. **An audit log.** §2.4, §2.10. No before/after table, no per-API-call record, no actor-and-source trail beyond `mail.thread`'s 18 fields.
3. **A `Vendra`-side link.** §5. `grn_reference` is a string; nothing validates that it names a real receipt.

---

## 4. Access, and the segregation that already exists

Audit is a read role that must see everything and change nothing, across tenants it does not own. Two of those three are already solved; the third is not, and the fourth requirement — *see everything* — is contradicted by §2.11.

### 4.1 The scopes that exist

Fifteen, of which **five are read scopes**: `assets:read`, `locations:read`, `requests:read`, `dashboards:read`, `identity:read`. The others are `assets:write`, `locations:write`, `requests:write`, `approvals:write`, `ingestion:write`, `integrations:write`, `tagging:write`, `settings:write`, `webhooks:admin` and `admin`.

**`admin` is a wildcard.** In `require_jwt`, `admin` (or the literal `"*"`) satisfies every route including `tagging:write` — an accepted, documented posture, "absolute below system-administrator". **An audit credential must never hold it**, and this is the one thing most likely to be got wrong when someone provisions the credential in a hurry.

### 4.2 What an auditor's credential should be

```
assets:read  locations:read  identity:read  dashboards:read  requests:read
```

Five scopes, no writes. As an **API client** this works today and is genuinely read-only: scope enforcement is declarative and per-route, `assets:read` is not in the required list of any POST, PATCH or DELETE, and unknown scopes are rejected on save so a typo cannot mint a token that 403s indistinguishably from a real permission decision.

As a **human session** it does not work. Session scopes derive from Odoo groups, and the group that grants the five read scopes — `group_asset_user` — **also grants `requests:write`**, because the group's own description is "view assets, log verifications, raise requests" and raising one is a write. So an auditor logging in through the SPA cannot currently be given read-only.

**There is no read-only-everything scope**, and there should probably not be one — `admin` is what happens when a scope means "everything", and the whole point of the scope table is that it is enumerable. A named `audit:read` that is explicitly the union of the five is the better shape, because it makes the audit credential visible in `whoami` and in the client list as what it is.

### 4.3 What the specification asks for and Cadra does not have

Specification §3 names two roles: `Auditor` / `audit_viewer` (*"read-only access to audit logs"*) and `Finance Officer` / `finance_viewer` (*"read-only access to asset financial data"*), federated from SuccessFactors / Active Directory. **Neither group exists in Cadra.** The groups that ship are `group_asset_user`, `group_asset_manager`, `group_tag_issuing_unit`, `group_identity_manager` and the three security groups. `audit_viewer` appears nowhere in the codebase.

Adding `group_auditor` → `audit:read` in the scope table is small and closes §4.2's session gap. Note the standing constraint on the other direction: `SCOPE_GROUPS` is deliberately **not** the inverse of `GROUP_SCOPES`, and `admin` maps to no group at all, so that a scope string typed into a form can never provision a system administrator. An `audit:read` scope must map to `group_auditor` and nothing else.

### 4.4 The segregation that is already right

**A scope is the only gate, and that is deliberate.** Every list and get route runs `.sudo()`, so an Odoo group cannot act as a second, undeclared gate behind a declared scope. When handoff 09 made the dashboard routes `sudo()`, a Security Officer holding `dashboards:read` but no fleet group went from an error to data — and that was the point. For an audit credential this is exactly the property wanted: the scope says "may read everything", and no group membership silently subtracts from it.

The corollary is that an API client user is an internal Odoo user with real groups, and would be writable over `call_kw` if it ever had a password. **Client users are created with no password at all**, which is what prevents it. An audit credential must be provisioned the same way; it must never be a human account with an API token bolted on.

### 4.5 Cross-tenant access: one credential, one tenant, no exceptions

**Tenancy is host-based and absolute.** A database is reached as `https://<tenant>.cadra.ng`; `myservice.api.client` is an ordinary model, so one client row exists per database; and the **JWT signing secret is per-database** (`ir.config_parameter myservice_api.jwt_secret`). A token minted against one tenant will not verify against another. There is no cross-tenant endpoint of any kind, and no way to build one without a deliberate new interface.

For INT-10 this means: **NRS Audit needs one credential, one secret and one base URL per tenant it audits**, and any consolidated view is assembled on the audit side, not requested from Cadra. That is the right default for a multi-tenant register — the alternative is a credential whose compromise crosses organisational boundaries — but it must be stated up front rather than discovered when the second tenant is added.

---

## 5. What Vendra must supply

Cadra holds a *reference* to the receipt and not the receipt. That is deliberate: Vendra owns the authoritative GRN and PO records, and modelling them in Cadra would mean maintaining a shadow copy that goes stale. The cost of that choice is that an auditor holding a Cadra asset has a string, and needs Vendra to turn it into a document.

Five things, in order of how much they unblock.

**1. A GRN lookup that takes the string Cadra holds.** Something of the shape `GET /api/method/…?grn_reference=GRN-2026-00412` returning the receipt: date, supplier (name **and** code), the lines, quantity per line, unit price, currency, total, and a stable document URL a human can open. Cadra's `data.provenance.grn_reference` is the join key and it is already exact-matchable in both directions.

**2. `sap_vendor_code` carried through INT-03.** Cadra holds `purchase_vendor` as **free text** — a name, not a code. A VFM question of the form "how much did we spend with this supplier across the estate" cannot be answered by matching name strings, and Cadra should not be the system that guesses which spellings are the same company. This is a change on the Vendra side: add the field to the INT-03 payload; Cadra adds it to `_WRITABLE_FIELDS`, the serializer and `data.provenance` in the same change. **This is the single highest-value item on this list for Value-for-Money specifically.**

**3. Acquisition cost on INT-03, wherever Vendra has it.** §2.7's table is the argument: 0.5% cost coverage on the migration target. Vendra knows the receipt price at the moment it hands the asset over, and that is the cheapest point in the whole programme at which the number can enter the register. Cadra already accepts `acquisition_cost`, `purchase_value` and `currency_id` on `POST /assets`; nothing needs building on our side.

**4. The line identity, not just the document name.** `import_ref` holds the Purchase Receipt **name**; resolving to a specific line today requires `import_ref` plus `serial_number`, and 5% of assets have no serial (and on `nrs19`, 619 do not). A `grn_line_id` or equivalent carried into `import_ref` — or better, a new dedicated field — makes the trace exact rather than probabilistic.

**5. The expected unit count per line.** §2.1's second gap. Cadra registers one row per physical unit and has no quantity field, by design. Given the line's quantity, "this GRN line was for five and Cadra holds four" becomes a query. Without it, that finding is invisible from either system alone — **which is the strongest single argument that INT-10 is one interface across two systems and not two interfaces that happen to share a name.**

**And one thing Vendra should expect from Cadra.** Vendra's half should assume Cadra will expose, per asset: the provenance block as it does today, the SAP dual-code state including the `exception` finding, the tag lifecycle with actors and timestamps, and the custody chain (§2.3, built). INT-05 already echoes the whole provenance block back to Vendra on every affix *so you never need to hold a Cadra id to match*; the same principle should hold for INT-10. **Neither system should need the other's primary keys to answer an auditor.**

---

## 6. Delivery, and our recommendation

Specification §13.3 offers two patterns and marks both `[NRS INPUT REQUIRED]`. Our recommendation is **both, in this order**, and the order is the point.

1. **Fix the pagination cap (§2.11) and add `updated_since` (§2.2).** Until these exist there is no continuous read access, only a demonstration of one. Together they turn every query in §2 from "the first 100 matches, described as all of them" into a walkable result set, and turn "pull the register again" into "pull what changed". Small, and blocking.
2. ~~**Build the custody chain (§2.3).**~~ **Done, 9 September 2026.** `nrs.asset.custody`, append-only on the model itself, backfilled from the chatter tracking rows and readable at `GET /assets/<id>/custody`. What is NOT done is the reach backwards: the chain starts where `custodian_id` became a tracked field, and three of the eight tenants therefore start empty. Every backfilled link says so on its face (`source: tracking_backfill`) rather than leaving an auditor to discover the gap.
3. **Then the scheduled bulk extract.** A daily snapshot of the asset register, the location register and the request register, retained — which also gives §2.5's point-in-time answer honestly, by storing it rather than reconstructing it.
4. **Webhook event subscription last, if at all.** §8.6 imagines an NRS audit system subscribing to all events for retention. Cadra has the machinery — the INT-05 outbox with capped exponential backoff, `event_id` idempotency, 4xx-is-permanent classification and a visible dead-letter state — so this is cheap to add. But an event stream is a poor primary audit interface: it tells you what happened while you were listening, and an auditor's first question is always about a period that predates the subscription.

Delivery mechanics for anything outbound follow INT-05 and INT-06/07/09 exactly: same queue, same retry policy, same `X-Idempotency-Key` spelling, same response classification. **You are not being asked to accommodate anything bespoke.**

---

## 7. What we need to proceed

**The specification:**

1. **The September flow's INT-10 section**, verbatim. §0 — it is not in the Cadra repository and everything in §2 is our reconstruction from `Cadra_at_NRS_Specification_v0.1.docx` §13.4.
2. Confirmation of the delivery pattern (§6): API, bulk extract, events, or a combination — and if bulk extract, the transport, the schedule and the retention.
3. The retention requirement in force. §15 says 7 years; nothing in Cadra implements a retention policy today.

**Decisions that change what we build:**

4. **Is `audit:read` a new scope and `group_auditor` a new group** (§4.2, §4.3), or does Audit hold an API client with the five read scopes and never log in as a human? The second works today; the first is what the specification's `audit_viewer` role implies.
5. **How should the pagination cap behave for a trusted machine credential** (§2.11)? Our recommendation: keep the cap, move it off the `aud` claim onto a per-client setting, make `total_estimate` report the true count regardless, and always emit a `next_cursor` while more rows exist. A cap the caller can see and walk is a protection; one that reports itself as completeness is a defect.
6. **Is the custody chain a new append-only model** (§2.3), and do we backfill the 217 existing tracking rows into it? They carry actor and timestamp, so the backfill is faithful — but it will be visibly sparser than the register, because it only covers changes made since `custodian_id` became tracked.
7. **Which fields must become tracked** (§2.4)? Our recommendation: the three provenance references, `sap_asset_number`, `serial_number`, and every financial field. Tracking is not free — it writes a row per change — but the alternative is that the values an auditor exists to challenge are the ones that change silently.
8. **Does Audit need cross-tenant access** (§4.5)? If yes, that is a new interface and a new security boundary, and it must be scoped as one rather than assumed.

**From Vendra:**

9. The GRN lookup endpoint (§5.1).
10. `sap_vendor_code` through INT-03 (§5.2).
11. Acquisition cost through INT-03 (§5.3).
12. Line identity (§5.4) and expected unit count (§5.5).

**From NRS, and this one is not a software question:**

13. **A decision about the 99.5%.** On `nrs19` — the migration target — 11,886 of 11,942 assets carry no cost at all. A Value-for-Money interface over that register returns nulls for the field VFM exists to examine. Cadra will not synthesise a value it does not have. Either the costs are loaded from SAP or from procurement records, or INT-10 goes live knowing it cannot answer the money question for the estate, and that limitation is stated to the auditors rather than discovered by them.

**Contact:** WestMetro Limited · apps@westmetrong.com
