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
- **§3 roles table** — `Auditor` / `audit_viewer` / *"Read-only access to audit logs"*, and `Finance Officer` / `finance_viewer` / *"Read-only access to asset financial data"*. **`Auditor` was built in handoff 23 and `finance_viewer` was ruled to be the same role under another name in handoff 24** (§4.3).
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

**Why an auditor should care how WRITES are refused — changed 21 September 2026 (handoff 31).** INT-10 is read access, but what it reads is only as good as what was allowed in. Until that date a write naming a field the API does not accept was answered **2xx**: the route wrote what it recognised, silently dropped the rest, and named the dropped keys in `data._warnings.rejected_fields`, which for most of the API's life no consumer read. **The register therefore holds records that are incomplete in ways their senders never learned** — the receiving system's own client treats a dropped field as a failed hand-off, but only *after* Cadra had created the asset; and a service request's `location_id` was dropped by `POST`/`PATCH /requests` for the life of that route, because the model's field had been renamed in the move to Odoo 19 and the route went on asking for the old name — so **a request raised THROUGH THE API before that date has no location** (requests raised by quick-submit, a PM schedule or the Odoo form kept theirs, and now show it); it is saved from that date. Since that date such a write is a **`400 invalid_request`** carrying `details.rejected_fields` and `details.writable`, and **nothing is written** — not the refused field and not the accepted ones beside it. So from that date a record in the register is what its sender asked for, whole, or it is not there. `docs/api/CHANGELOG.md` has the route-by-route table.

**Two more doors, 22 September 2026 (handoff 32), and they were the harder ones to find.** The eleven were found by searching for routes that declare a list of accepted fields. Two routes create records without declaring one — the homepage's quick-submit form and the SAP employee feed — so the search could not see them, and both went on dropping in silence for a day longer than the rest. Both now refuse the same way, and the employee feed refuses a whole batch rather than half-creating one. **What that closes for an auditor is a specific kind of hole**: a service request raised from the public form, or a staff record synced from SAP, that is missing a field its sender believed it had supplied and that nothing in either system records as missing. **And the sweep behind it found that the SAP feed's employment status had never been read at all** — the published key was `status`, the model reads `employmentStatus`, and every integrator following Cadra's own documentation sent a status that went nowhere under a 200. Since that date it is refused. A guard now checks every published key in the API against the model field it claims to write, in both directions, and fails when one stops resolving (`myservice_api/tests/test_published_names_resolve.py`).

**Cadra cannot answer route 4 and should not try.** Vendra owns the authoritative GRN and PO records. Cadra deliberately holds `grn_reference` as free text rather than modelling a shadow copy. §5 says what Cadra needs Vendra to expose so the two halves join.

---

## 2. What an auditor actually needs to ask

Eleven questions, drawn from specification §13.4, PRD §5.11 and §8.14, and from what a VFM review of a fixed-asset estate actually does. For each: **can Cadra answer it today, and how.**

**Scoreboard against §13.4's five named reports**, updated 9 September 2026. When this document was written Cadra had **none of the five** as an API surface.

| §13.4 report | Status |
|---|---|
| Custodianship chain for any asset | **Built** — handoff 14. §2.3 |
| Asset register snapshot at any historical date | **Built, with a published boundary** — handoff 16. §2.5 |
| Disposal report with documentation refs, per period | **Built** — handoff 16. §2.9 |
| Access changes for any user, per period | **Built** — handoff 23. Its honest answer was that no record existed; **handoff 24 started one**, so the report now answers for the period from `fidelity.record_starts_at` onward and still says `none` for anything before it. §2.10, §2.10c |
| Configuration change log | **Built, and thin — 22 recoverable keys estate-wide** — handoff 23. §2.10a |

**All five are now built.** The two log-shaped ones were never reports missing from an existing record — there was no record. What handoff 23 built is the endpoint that says so, in the response, in words, with the measurement behind it. **Handoff 24 then built the record itself for access changes** (§2.10c): grants, removals and implication changes are now written append-only as they happen, with the acting user, so the fourth report answers rather than only explaining. The configuration log remains as handoff 23 left it. §2.10b is what it would take to recover the period *before* the record began, and it remains NRS's decision.

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

**Yes over the API since handoff 27, for what is recorded — and the response says what is not.** Until then the answer was *"No, over the API. Partly, in the Odoo UI."*, and everything below that sentence about WHAT is tracked still stands; what changed is that it is now readable.

`GET /api/v1/assets/<id>/history` merges every place an asset's life leaves a mark — registration, the tag's issue, print and affix, the chain of custody (§2.3), location moves, the tracked fields listed below, the disposal approval (§2.9), events sent to SAP and the Tag-Issuing Unit, and maintenance requests — onto one clock, newest first (`?sort=oldest` reads it forwards), uncapped and unpaged for §2.3's reason. It came out of a live demonstration: NRS opened *Audit & Review* on an asset expecting this, and the screen had never asked for it.

**It does not make the records any better than they are, and it says so on every event.** Each carries `evidence`, one of five grades defined in the response by what somebody can do to the record:

| `evidence` | What it rests on | Which events |
|---|---|---|
| `append_only` | the application refuses edit and delete to everyone, sudo included (the refusal is Python — no database trigger) | a change of custodian; **for a move made since handoff 28**, a change of location; and — **made since handoff 30, 21 September 2026** — a verification, a verification date written by PATCH, **every change of status, with the reason where one was given**, and a change to the GRN reference, the purchase order reference or the SAP asset number. `fidelity.events` in the response gives the instant each began, per database |
| `system_stamp` | `create_date` / `create_uid`, not editable through the ORM, gone if the row is deleted | registration · tag issued |
| `guarded_record` | stamped from the acting user and refused to an ordinary write; a caller who sets the internal context flag can still rewrite it, and a tag label row is deletable by an asset manager | tag printed · tag affixed · outbox events |
| `editable_record` | an asset manager can edit or delete it and nothing records that they did; `nrs.asset.transfer` also cascades away with the asset | a location move **that has a transfer row** · a transfer that is not done · a tag scrapped · maintenance requests · **the disposal approval** — both columns are inputs on the Odoo form; a rewrite of the approver is listed as its own event |
| `chatter` | a `mail.message`, deletable by anyone with write on the asset — which is the same group that can edit the asset | condition · disposal paperwork · the vendor and import references · every other tracked field · **a location move made any other way** · and a change of status, a verification or a GRN/PO change **made before handoff 30** |

**A location move is the one to read twice — and handoff 28 changed it.** Until then, only `POST /assets/<id>/move` and a completed transfer wrote an `nrs.asset.transfer` row; PATCH (`location_id` is in `_WRITABLE_FIELDS`) and an import moved an asset and left chatter and nothing else. **Since handoff 28 every change of `location_id` is appended to `nrs.asset.movement`**, by `nrs.asset.write` and `nrs.asset.create`, underneath every writer — append-only on the model as custody is, `ondelete='restrict'` on the asset, holding the instant, who moved it, the full location paths as they read at the time, the reason, a `source`, and the transfer document where the move had one. PATCH was NOT closed and was NOT made to write a transfer: a move is not always a transfer. Two writers that are not Python were closed too — a location being DELETED (`ON DELETE SET NULL`, cascading from a parent) is recorded as a move to nowhere, and the Odoo form, which had never saved the location it displayed, now does.

**A move made before handoff 28 is exactly as it was**, and the history still grades it `editable_record` or `chatter`. Nothing was backfilled.

**A correction to a number this document carried.** It said *"on `nrs19`, 1,146 tracked location changes against 1 transfer row"*, and report 27 offered that as the scale of unrecorded moves. **It is a true count of rows and it is not that.** 1,145 of the 1,146 were written by Administrator within SIX SECONDS (2026-08-06 15:34:24–15:34:30), sixteen minutes after the register was loaded, each on a different asset exactly once: `FCT → North Central / FCT`, `Lagos → South West / Lagos`. That is a script re-mapping locations onto a hierarchy. Nobody moved anything. The structural finding stands and is proven by test — a PATCH did leave no durable record — but outside those six seconds `nrs19` holds exactly ONE tracked change of location (2026-09-06, authored by OdooBot, which is a script or a shell rather than a person at a screen), and the figure measures a seed.

`reconstructed: true` marks a custody link with `source: tracking_backfill`. `actor` is the user the record names, or null — never inferred, and never a created-by field that means something else. `fidelity.not_recorded` names, on every response, what the **Untracked** list below means in practice: a changed cost, a changed SAP field and a changed GRN reference leave nothing, and their absence from `events` is not evidence they did not happen. `fidelity.custody` says when custody recording began on this system and whether this asset was already held by somebody the chain never saw arrive — true of **6,643 assets on `nrs19`**, all assigned at creation on 2026-08-06, a month before the recorder existed. An asset with nothing after its registration says so in `summary.statement`, in words.

Message BODIES are not published — only tracked old/new values. A note typed on an asset was never promised to every holder of `assets:read`.

PRD §8.14 requires *"who, when, what changed (before/after values), and the source (which API call, which user or system)."* Cadra has the first three for **20 fields** and none of the fourth.

`nrs.asset` inherits `mail.thread`, and **20** fields are tracked. Eighteen carry `tracking=True` where you can see it: `name`, `asset_code`, `asset_tag`, `category_id`, `subcategory_id`, `asset_type_id`, `asset_level`, `domain`, `building_id`, `floor_id`, `room_id`, `location_id`, `custodian_id`, `condition`, `state`, `last_verified_date`, `retrieval_flag`, `depreciation_method`.

**Two more are tracked invisibly, and this document said 18 because of it.** `tag_label_state` (`related='physical_tag_id.label_state'`) and `active_tag_number` (`related='active_tag_id.name'`) declare no `tracking=` of their own — **a related field inherits `tracking` from its target**, and both targets are tracked on `nrs.asset.tag.label`. So a grep for `tracking=True` under-reports the tracked set, and the measured table below has been showing `tag_label_state` as the largest tracked field on `nrs.asset` while the prose above it denied the field was tracked at all. The authority is `ir_model_fields.tracking > 0` in a live registry, which reads 20 on both `nrs19` and `jaizbankplc`. Handoff 16 asserts that tuple against the registry in both directions, so the next invisible one cannot fall out silently.

A consequence: **"was this asset tagged on 31 March?" is answerable.** `is_tagged` is not a column — it is computed in the serialiser as `tag_label_state == 'affixed'` — so a rolled-back `tag_label_state` answers it. §2.6 listed that as unavailable.

> **Corrected 21 September 2026 — two of the entries below stopped being true and nobody updated this list.** `grn_reference`, `purchase_order_reference`, `purchase_vendor` and the three import fields have been TRACKED since handoff 28 (from `cadra.provenance_tracked_from`, stamped per database). And since handoff 30 a change to **`grn_reference`, `purchase_order_reference` or `sap_asset_number`** is recorded where nobody can alter it — value before, value after, who, when. **Money is still not recorded at all**, and neither is any SAP field other than the asset number; that half of the paragraph below stands.

**Untracked, and materially so** *(as written at handoff 16 — read with the correction above)*: `serial_number`, `legacy_asset_code`, `make`/`model_name`/`manufacturer`, `department`, **`grn_reference`**, **`purchase_order_reference`**, **`purchase_vendor`**, `import_source`/`import_date`/`import_ref`, **every `sap_*` field including `sap_asset_number`**, **every financial field** (`purchase_value`, `acquisition_cost`, `current_value`, `replacement_cost`, `accumulated_depreciation`, `current_book_value`), every date except `last_verified_date`, `assignment_date`, `notes`. ~~`disposal_date`, `disposal_reason`~~ — **both now tracked** (handoff 16 §B2), along with the five new disposal fields §2.9 describes.

Read that list against the question a VFM review asks. **Every value an auditor would challenge — what we paid, which receipt it came from, which SAP code it was booked under — can be changed silently.** The identity and location of the asset are tracked; its money is not.

Measured today, `nrs.asset` chatter and tracking rows:

| Tenant | chatter messages | tracking rows | top tracked fields |
|---|---|---|---|
| `nrs19` | 36,901 | 24,959 | `tag_label_state` 11,934 · `depreciation_method` 11,878 · `location_id` 1,146 · `custodian_id` 1 |
| `jaizbankplc` | 3,984 | 1,599 | `tag_label_state` 1,029 · `custodian_id` 217 · `depreciation_method` 209 · `condition` 67 · `location_id` 67 |

The actor is `env.uid`, which since handoff 08 is the API client's **own** `res.users` rather than `Administrator` — so a change made by Vendra now says "Vendra" and one made by the Tag-Issuing Unit says so. **289 historic affix records still carry `Administrator`** and were deliberately not rewritten, because no evidence says which client wrote which and inventing one would fabricate an audit trail. An auditor reading affix records from before that date should treat the actor as unknown, not as the administrator.

There is **no audit-log model of our own** — no `cadra.audit.log`, no before/after table, no per-API-call request log. `workflow.dispatch.log` is an outbound delivery queue, not an audit log. PRD §10's *"every API call produces an audit log entry… immutable and queryable for compliance and forensic purposes"* is not built.

### 2.5 "Show me the register as it stood on 31 March."

**Yes, for 28 fields, and the response says which 44 it is NOT answering.** Built in handoff 16: `GET /api/v1/reports/asset-register?as_of=YYYY-MM-DD`, scope `assets:read`.

**This section previously recommended against building it.** That recommendation was right about the thing it was arguing against — *"a reconstruction answers it approximately while looking exact, which is worse"* — and the build does not do that thing. What makes the difference is that the boundary is **in the response**, not in a document beside it: `data.fidelity` names every field the snapshot rolled back, every field published at today's value because no history supports a rollback, and every field it will not answer at all. The rows sit at `data.assets`, **inside** that declaration, so a consumer reading the obvious key cannot miss it.

| | count | what it means |
|---|---|---|
| `rolled_back` | **28** | answered AS OF THE DATE, from `mail.tracking.value` and, for custody, from `nrs.asset.custody` |
| `as_of_today` | **21** | published at its CURRENT value, labelled. Omitting them would send an auditor to a second query that answers as-of-today without saying so |
| `not_recoverable` | **23** | named and deliberately NOT published. A today's figure under a heading an auditor reads as historical is the specific harm |

**What cannot be rolled back, and why it matters most:** every financial figure (`current_value`, `replacement_cost`, `accumulated_depreciation`, `current_book_value`), every `sap_*` field including `sap_asset_number`, the acquisition provenance (`grn_reference`, `purchase_order_reference`, `purchase_vendor`), `serial_number`, `department`, and the asset hierarchy (`parent_id`). §2.4's observation stands and this report makes it concrete: **the identity and location of an asset are historical; its money is not.**

Three refinements the response carries beyond the field lists:

- **`data.cutoff`** — the exact instant the rollback cut at, naive UTC, with `fidelity.notes.cutoff` naming the day boundary taken: end of day **Africa/Lagos**, 23:00 UTC. WAT is a fixed +01:00 and Nigeria has never observed DST, so this is exact arithmetic. A change at 23:30 UTC on 31 March is 00:30 on 1 April locally and is not in the 31 March snapshot.
- **`data.filters`** — filters match **current** values. `?as_of=2026-03-31&state=active` means "assets active *today*, reported as they stood on 31 March", which is a different population from "active on 31 March". The response says so rather than implying otherwise.
- **Per-row `_fidelity`** — present only when a row is degraded beyond the global declaration: a custody chain that does not reach back to the date, an `erp_managed` asset with no value history, a selection label that would not map.

**Existence is handled and is the easy thing to get wrong.** An asset whose `create_date` is after the cutoff was not in the register on that date and is excluded. An asset **deleted** since is unrecoverable, so the snapshot is a **lower bound** on the register's size — `not_recoverable` says `deleted_assets` on its face, because an auditor reconciling a count has to know that.

**Depreciation remains the one genuinely exact answer.** `value_at(as_of)` rebuilds the whole board from the start date and persists nothing, so it is a pure function of the date. The caveat is now published per row rather than only in prose: only `depreciation_method` is tracked, so the cost basis, life, salvage and start date that `value_at` computes *from* are read as they stand today.

**The §13.3 scheduled bulk extract is still the right thing to build**, and this does not replace it. A stored daily snapshot answers "as at 31 March" for every field, including the 44 this one cannot. What changed is that "no answer at all" is no longer the alternative.

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

**Since handoff 30 (21 September 2026): *every time this asset was checked, and by whom* is answerable.** Each press of Verify — `POST /assets/<id>/verify` — appends a record nobody can edit or delete, including a second on the same day; `GET /assets/<id>/history` lists them as `verified`, graded `append_only`. The asset itself still keeps only the LAST date and verifier. A verification made before that date survives only as a message-log line, and `fidelity.events` says where the line falls on each database.

**A disposed asset may still be verified, by ruling (handoff 31).** A disposed asset somebody physically finds on the premises is an audit finding, and a register that refuses to record *"I saw it, today"* is suppressing the one fact that matters. Such a verification appears in the history like any other, after the change of status into `disposed`.

Two caveats for an auditor *(the first still stands; the second was closed in handoff 28)*:
- `last_verified_date` is in `_WRITABLE_FIELDS`, so an API client with `assets:write` can set it directly without going through `action_verify()` — which means without writing `last_verified_by` or a chatter note. A verification date with no verifier is a weaker record than it looks.
  **It is listed as what it is:** a `verification_date_set` event, not a `verified` one — a date was written, and the record does not say that anybody checked the asset. It also clears any verifier already there.
- ~~`last_verified_by` and `verification_notes` are **not in the serializer at all**.~~ Published since handoff 28.

### 2.9 "What has been disposed of, and on whose authority?"

**Yes, as of handoff 16** — `GET /api/v1/reports/disposals?from=&to=`, scope `assets:read`, both bounds inclusive.

This section used to read *"partly"*, and the missing halves were the ones that mattered: no documentation reference field, no approver, no method, no proceeds, `disposal_date` and `disposal_reason` untracked, and no period report. **All of that had to be built before a report could cite any of it.** `nrs.asset` now carries `disposal_method`, `disposal_reference` (the board minute, memo or disposal certificate), `disposal_approved_by`, `disposal_approved_date` and `disposal_proceeds` — all tracked, as `disposal_date` and `disposal_reason` now also are.

**Since handoff 30 (21 September 2026): who CARRIED OUT a disposal is recorded, and a disposal cannot be undone.** Until then the act of disposing recorded a date and no person; the approval named its approver and nothing named whoever pressed the button. The change of status into `disposed` is now an `append_only` event in `GET /assets/<id>/history` — its actor is who carried the disposal out, and `detail.reason` is the reason given at the time, which is kept separately from the editable `disposal_reason` on the asset. **Since handoff 31 every disposal is dated and decommissioned by the register itself, whichever route made it** — `PATCH {"state": "disposed"}`, the Odoo form and a script as much as `/condemn` — so the report's `no_disposal_date` finding now means one of three things: a disposal made before 21 September 2026; an asset REGISTERED as already disposed with no date given (deliberately not stamped: it was disposed of on a day this system never saw, and a wrong date would hide what a missing one shows); or a date somebody later CLEARED — `disposal_date` is writable, so `PATCH {"disposal_date": null}` un-dates a disposal, and nothing refuses it. Measured that day across eight databases, before this handoff's own tests ran: two such rows, both our own probes. **Disposal is terminal:** a disposed asset cannot change status, location or custodian through any route, and the location or employee it names cannot be deleted from under it. It is not recorded for a disposal made before that date, nor for an asset REGISTERED as already disposed.

**The findings are the product, not a by-product.** An auditor's test on a disposal is always *was it authorised, by whom, and is the paper there* — so a disposal missing any of that appears in the report **carrying the finding**, never filtered out. `summary.findings` counts each one across the whole period on every page, so *"41 of 63 carry no authorising reference"* is one read rather than a page walk.

Findings published: `no_authorising_reference`, `no_approver`, `no_approval_date`, `no_disposal_method`, `no_disposal_date`, `no_disposal_reason`, `no_proceeds_recorded`, `disposal_date_reconstructed`, `no_sap_asset_number`.

Four things worth knowing before reading one:

- **A date can be recovered, and says so.** `action_condemn` wrote no date for the life of the product, so an undated disposal is the common case rather than the edge one. Where `disposal_date` is null the report places the row by the tracked `state → disposed` transition, marks `date_source: "state_transition"` and raises `no_disposal_date`. The migration that recovered dates into the column marks each one `disposal_date_reconstructed`, on the same reasoning as `nrs.asset.custody.source = 'tracking_backfill'`: a reconstructed value written into the same column as a recorded one is otherwise indistinguishable from it.
- **`data.unplaceable`** carries disposals with no date and no recoverable transition — placeable in no period at all. Returned in full and uncapped in every report, never mixed into the period totals. Dropping them makes them invisible in every report, which is the hole this closes; putting them in one period double-counts them in the next.
- **`state = 'missing'` is not a disposal** and never appears. An asset that cannot be found has not been disposed of, and conflating them would let a loss be written off as a disposal.
- **The approver cannot be asserted over the API.** `disposal_approved_by` and `disposal_approved_date` are deliberately absent from `_WRITABLE_FIELDS`: a client able to PATCH the approver could create a disposal and name any user as its authority in the same request, turning the `no_approver` finding into a clean row with nobody having authorised anything. `action_approve_disposal` records who pressed the button. ~~The consequence is a real gap: there is no API route that records a disposal approval, and closing it needs its own scope decision.~~ **Closed in handoff 23 and never corrected here:** `POST /assets/<id>/approve-disposal`, scope `approvals:write`, records the ACTING user as approver and takes no body — and since handoff 31 (21 September 2026) a body naming ANY key is a `400` and no approval is recorded, where an unrecognised key used to be reported beside a 200.

**Measured across all eight tenants at the time of building: zero disposals.** 17,795 assets, none disposed, none missing, and `state` carries no tracking rows anywhere — no asset has ever changed state in Cadra. So the report ships against an empty set, which is exactly what makes it safe to have added required-shaped fields now, before anybody relies on the old behaviour. It also means `no_sap_asset_number` will fire on essentially every future row: 2 of 11,942 assets on `nrs19` carry a SAP number and none does elsewhere, so INT-09 has never sent a disposal instruction to the financial system.

### 2.10 "Who had access to what, and when did that change?"

**Partly, and the endpoint tells you which part before it tells you anything else.**

```
GET /api/v1/reports/access-changes?from=2026-01-01&to=2026-03-31    # identity:read
```

Specification §7.6 requires *"every identity-related event in Cadra (login, role change, account creation, deactivation) recorded in Cadra's audit log with reference to the upstream IdP event"*, and §13.4 requires *"access changes for any user (per period)"*. **Cadra records no role changes, and no query against these databases can produce them.** That is not a reporting gap that better SQL would close; it is a property of the schema.

#### What makes it unrecoverable, measured rather than asserted

| Where a grant could have left a trace | What is actually there |
|---|---|
| `res_groups_users_rel` — the membership table | **Two integer columns, `(gid, uid)`.** No `create_date`, no `create_uid`, no `write_date`, no `write_uid`. Odoo models group membership as pure present tense, so a grant writes nothing that outlives it. Even accepting "current state plus timestamps" instead of a history gets nothing. |
| `res.users.group_ids` tracking → `mail.tracking.value` | **No `tracking=` in Odoo core**, first-party code, `crnd-19/` or `oca-19/`. **0 tracking rows** on `res.users` and `res.groups` across all eight tenants. |
| `ir_logging` | **0 rows on every tenant.** Odoo writes it only when `log_db` is set; it is not set in `config/odoo.19.conf` and never has been. |
| An audit module | **None installed or vendored.** `oca-19/` carries one module and it is `web_responsive`; none of the 23 in `crnd-19/` is an audit log. |
| `res_groups` / `ir_model_access` / `ir_rule` write stamps | Present, and **100% written by uid 1 `__system__`** — module install and upgrade churn. Not one ACL, group or rule in any tenant has ever been written by a human. |
| `res_users_log` | 1–6 rows per tenant, garbage-collected. It records that a user was *active* at a time. No group, no model, no field. |

**So the report synthesises nothing.** What it returns instead:

- **`summary.statement`** — the sentence, above the table, saying that group grants and removals are not recorded anywhere in this system and that this report can speak for no period on that question. Branch on `summary.coverage` (`none` / `partial`), never on the wording. There is deliberately no `empty`: the record cannot hold a group change in any period, so a quiet quarter is not a different *kind* of answer here — unlike the disposal report, where an empty period genuinely is.
- **`summary.group_changes_in_period`** — **a real count since handoff 24** (§2.10c), read from the append-only access record. It was a structural zero when this was written, and a zero still means one of two things — nothing happened, or the record does not reach the period. `summary.coverage` and `fidelity.record_starts_at` are what tell those apart.
- **`events`** — the access events that *are* evidenced: an account **created** (`precision: exact`, with its real timestamp and creator) and an account **last modified** (`precision: last_write_only`). Each row names the `evidence` it rests on. An `account_modified` row does not say which field changed — a timezone edit and a group grant are indistinguishable in `res_users.write_date`. Since handoff 24 a recorded `granted` / `removed`, and since handoff 45 a recorded `deactivated` / `reactivated` (§2.10d), are events too, each `precision: exact` with its actor.
- **`roster`** — the present-tense answer to the question an auditor asks next: who has access *now*, with each account's groups and, where it is an integration, its API scopes. Labelled as current state throughout, never presented as history.
- **`fidelity`** — the table above, re-derived **on every request** rather than carried as a constant. It reads `information_schema` for the membership table's real columns and counts the tracking and logging rows live. The day somebody adds tracking or installs an audit module, `coverage` becomes `partial` and the report says the record has grown, instead of continuing to publish a limitation that has stopped being true.

One specific hazard is still worth recording: `_provision_client_user` writes a client user's groups with `(6, 0, …)` — a full replace — on every scope change, so a group granted to a client user by hand is destroyed the next time the scope list grows, silently.

### 2.10a "Who changed what setting, and when?"

**Partly, and the ceiling is low.**

```
GET /api/v1/reports/configuration-changes?from=2026-01-01&to=2026-03-31   # settings:read
```

`ir.config_parameter` does carry real audit columns — `create_uid`, `create_date`, `write_uid`, `write_date` — unlike the membership table. But it is **last-write-wins and untracked**, so for each key exactly three facts survive:

> the **current** value · the **last** writer · the **last** write time

Not the previous value. Not how many times it changed. A key modified five times is one row showing the fifth.

**The measurement, taken across all eight local tenants:**

| | keys |
|---|---|
| Parameters present per tenant | 21–26 |
| **Written after they were created** (the whole recoverable change set) | **22, estate-wide** |
| Of those, attributable to a named human | **12** |
| Of those, `__system__` — cron, CLI or module upgrade | 10 |

Per tenant: `jaizbankplc` 7 (5 human), `cadra19` 7 (5), `nrs19` 2 (1), `test19` 2 (1), `gtb19`/`nrs`/`lasg`/`gtb` 1 each (0 human).

**And the Settings screen writes to a table that self-destructs.** `res.config.settings` is a `TransientModel` and its rows are vacuumed — **0 rows on every tenant**. A change made through the settings form leaves only the resulting parameter row: who opened the form, what else they changed in the same save, and what the form showed them are all gone. That is the single biggest reason this report is thin and the one an auditor is least likely to guess, so `fidelity.notes.settings_screen` says it in the payload.

**Values whose key names a credential are redacted.** `ir_config_parameter` is where `myservice_api.jwt_secret` lives — the key every access token in the tenant is signed with — alongside `database.secret` and the relay, webhook and API keys the identity modules read. A configuration report that published values verbatim would hand the token-signing secret to every holder of the read scope, and an audit credential is exactly the broad, long-lived, widely-shared credential that must not be carrying it.

The redaction replaces the value with `[redacted] sha256:<16 hex>` — no prefix, no last-four, no length, because a truncated secret is still a head start and a published length narrows a brute force. The fingerprint answers the only legitimate question a redacted value has: *is this the same value as the one over there.* `value_is_redacted` marks the row and `summary.redacted_values` counts them. **The rule matches the key NAME, not a list of known secrets** — a deny-list of the six that exist today is a deny-list that misses the seventh. It over-redacts in one known case (`auth_signup.reset_password`, whose value is a boolean), and that direction is the correct one to err in.

**Out of scope, named rather than reported:** views, crons, server actions, ACLs and record rules also change what the system does, and all carry a write stamp. On every tenant measured, **every one of those stamps is `__system__`** — the 800 "changed" `ir_ui_view` rows on `jaizbankplc` are module-upgrade churn, not human edits. A table of 1,634 view rows nobody edited would bury the handful of parameters somebody did.

### 2.10b What it would take to close the access-change gap

Nothing here is retroactive. **No query, no tool and no forensic step against the existing databases will recover a single day of group-change history**, and the honest thing to tell an auditor is that the record begins on the day something below is done — not to produce a reconstruction.

| Option | What it buys | Cost |
|---|---|---|
| `tracking=True` on a `res.users` override of `group_ids` | Every future grant and removal lands in `mail.tracking.value` with actor and timestamp, and the existing snapshot-style rollback machinery can read it. | Small. One field override plus a module upgrade. **The tracking value for a many2many is a different shape from the m2o/selection/boolean cases `_snapshot_decode` handles**, so the reader is the real work, not the declaration. |
| An audit module (OCA `auditlog` or equivalent) | A general model-level change log, not just users. | Larger, and a vendored tree to carry through every upgrade. |
| Set `log_db` in the server configuration | Populates `ir_logging`. | Cheap, but it is a *log*, not a queryable change record, and it grows without bound. |

**Recommendation at the time: the first.** ~~It is the smallest change that makes §13.4's fourth report answerable, it reuses machinery that already exists for the register snapshot, and it degrades honestly in the meantime.~~

### ⚠️ 2.10c The forward record exists — handoff 24, and it is NOT the option recommended above

**The gap is closed forward. It is still not closed backward, and it never will be.**

`myservice.api.access.change` is an append-only record of grants, removals and implication changes, written as they happen with the acting user. `write` and `unlink` raise unconditionally so the guard holds under `sudo()`; rows are written only as a side effect of membership actually moving.

**The recommendation above was not followed, and the reason is the whole point.** `tracking=True` on `res.users.group_ids` would have recorded only what passes through `res.users.write` — and the writers were enumerated before the hooks were placed, which found that to be **about half** of them. Measured against Odoo 19 core:

| Writer | Passes `res.users.write`? |
|---|---|
| `res.users.write` with `group_ids` — including the admin user form, which on 19 submits the real field because the reified `sel_groups_*` pseudo-fields were deleted | yes |
| `res.users.create` — every seed script, the API-client provisioner, and `auth_signup`'s template `copy()`; also `_default_groups()`, which puts a user in a group a create never mentioned | **no** |
| `res.groups.write` with `user_ids` — `scripts/bootstrap.py` and eight security XML files that re-apply on **every module upgrade**, not only install | **no** |
| `res.groups.write` with `implied_ids` — and `res.config.settings` group toggles, which are this case | **no** |
| `res.users.unlink` — `ON DELETE CASCADE` erases every membership row | **no** |

The last of those is the one that most changes the picture. **On Odoo 19 group implication writes no membership rows at all**: `res.groups.all_implied_ids` is declared `compute=` with no `store=True`, so adding an implication grants every member of that group the rights of another group while `res_groups_users_rel` is untouched. There are no "implied rows" to record — only an implication edge, which is recorded here as its own event because it moves what a group *means* rather than who is in it.

**What the report now publishes.** `data.fidelity.record_starts_at` is the instant this tenant's record begins, measured from the earliest row it holds at request time — never a migration date, and `null` until the first change is recorded. `summary.group_changes_in_period` is a real count. `summary.coverage` gains a third value:

| `coverage` | Meaning |
|---|---|
| `recorded` | The record covers the whole requested period. The changes listed are every grant and removal in it. |
| `partial` | The period straddles the start. The count is a **lower bound**. |
| `none` | The period ended before the record began, or no record exists on this tenant yet. **Nothing can be said about it** — and an empty table here must not be read as "no access changed". |

**A change nobody can attribute says so.** A grant made by a module upgrade, a cron or the command line arrives as `uid 1` and is recorded with the actor `__system__` and `attributable: false`, never a person's name. Report 23 measured 100% of this estate's ACL stamps as `uid 1`; a record rendering those as "the administrator granted this" would invent somebody.

**Still open, and still NRS's decision:** the reconstruction of grants made *before* the record began. The three options in the table above remain the options, and none of them is retroactive. What has changed is that the clock has started, so the unrecoverable period stops growing.

### 2.10d An account switched off, and back on — handoff 45

*"Who removed this person's access, and when?"* Deactivating an account is the most complete removal of access there is, and until 2 October 2026 the answer sat in `res_users.write_uid` / `write_date` — which the next write to the account overwrites — and not in this report. **The same append-only record now holds it.**

| `data.events[].event` | Meaning |
|---|---|
| `deactivated` | The account's `active` flag went from true to false. The person can no longer sign in; any outstanding invitation was cancelled by the same write (Odoo's `auth_signup`), and there is no separate cancellation act or event. |
| `reactivated` | The flag went from false to true — including on an account that was *created* inactive and switched on later. |

Both are `precision: exact`, carry `actor` and `attributable` exactly as a grant does (`__system__` for a script, an upgrade or the command line), and carry `group: null` — they are about the account, not a group. They are written under **every** writer of the flag, not only the API's `POST /users/<id>/deactivate` and `/reactivate`: the back office's *Archive*, core's portal self-deletion and a script all pass the same hook on `res.users.write`. A write that does not move the flag records nothing, a user created inactive is not a deactivation, and deleting a user is recorded as the group removals it cascades, as before. Raw SQL against `res_users` is not seen — the same boundary as the rest of the record.

**They are counted on their own, and bounded on their own.** `summary.account_state_changes_in_period` (with `account_state_changes_not_shown` for accounts no longer on the roster) never mixes with `group_changes_in_period` or `implication_changes_in_period`. This half of the record began later than the group half, so a period the group record covers completely can still hold a deactivation nobody wrote down: `fidelity.account_state_record_starts_at` is measured from the earliest such row (`null` until the first), and `summary.account_state_coverage` takes the same three values as `coverage` against that instant. **`coverage` speaks for group changes only.** Before the account-state start, a deactivation survives only as the roster's current `active: false` and, at best, an `account_modified` stamp.

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
2. **An audit log.** §2.4, §2.10. No before/after table, no per-API-call record, no actor-and-source trail beyond `mail.thread`'s 20 fields.
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

**There is no read-only-everything scope**, and there should not be one — `admin` is what happens when a scope means "everything", and the whole point of the scope table is that it is enumerable. This section previously proposed a named `audit:read` that was the union of the five. **Handoff 23 built the role and rejected that scope**, for the reason §4.3 now sets out: an audit credential is made visible by the GROUP it holds, which is what `whoami` and the client list show, and a scope nothing else grants makes a report unreachable the day it ships.

### 4.3 What the specification asks for and Cadra does not have

Specification §3 names two roles: `Auditor` / `audit_viewer` (*"read-only access to audit logs"*) and `Finance Officer` / `finance_viewer` (*"read-only access to asset financial data"*), federated from SuccessFactors / Active Directory.

**`Auditor` now exists — `myservice_api.group_auditor`, handoff 23.** **`Finance Officer` / `finance_viewer` will not be built as a second group, because it is `group_auditor` under another name — handoff 24.**

"Asset financial data" resolves to four blocks of the asset serializer — `financial` (including the whole `depreciation` sub-block), `sap`, `disposal` and `provenance` — plus `GET /reports/depreciation` and `GET /settings/depreciation`. Every one of them is reached by `assets:read`, `dashboards:read` or `settings:read`, and `group_auditor` grants all three.

**There is no field-level access control anywhere in Cadra, and that is what decides this.** Three things were measured rather than assumed:

- `grep -rn "groups=" --include="*.py"` across every first-party module returns **nothing** — no field definition is gated.
- `serialize_asset` (`myservice_api/controllers/v1_assets.py:502`) has the signature `def serialize_asset(a, *, include=())`. It takes **no scope argument**. `include` is an additive embed selector the CALLER chooses, not an allow-list, and the `financial`, `sap`, `disposal` and `provenance` blocks are emitted unconditionally on every response.
- Every route runs `.sudo()` (§4.4), so an Odoo group cannot subtract from what a scope already grants.

The finest cut this platform can make is **route × scope**, and financial fields are not a route — they are nested blocks riding on `assets:read`, which is indivisible. So a `finance_viewer` built honestly today would be `group_auditor` minus `locations:read`, `requests:read` and `identity:read` — **a narrower auditor, not a finance role**, since not one of those three scopes is financial. A genuinely field-scoped role needs machinery that does not exist, and building it would be a breaking change to a serializer Vendra builds against.

**A finance user who needs read-only access to asset financial data is placed in `myservice_api.group_auditor`.**

Two things this ruling does not cover, flagged rather than closed:

- **Specification §3.4 and §3.5 cast Finance as a disposal *approver*** — the disposal flow is "Asset Manager approval → Finance Director approval". That is `approvals:write`, the opposite of a read-only row, and handoff 23 built that route. If an approver is what NRS actually wants, it is a different question with a different answer, and the §3.6 row is not the place it was asked.
- **`workflow_payment_ref` (`myservice_workflow/models/request_request.py:27`) and `workflow.dispatch.log.payment_ref` (`:82`) are stored and serialised by nothing.** A Finance Officer expecting to trace a payment reference over the API cannot, and neither can an auditor. That is a real gap and it is not closed by any group.

**The `audit:read` scope this section used to propose was NOT built, and the reasoning changed.** A single scope meaning "the audit reports" would have been a scope that no existing client holds and no group granted on the day it shipped — which is the argument `v1_assets.py` already used to keep the register snapshot and the disposal report on `assets:read`. The five §13.4 reports are views of three different things: the register, the identity roster and the configuration. They take those things' scopes.

So `group_auditor` grants six READ scopes and nothing else:

```
assets:read  locations:read  requests:read  identity:read  dashboards:read  settings:read
```

Five of the six already existed. **`settings:read` is new**, and it is a read scope rather than a reuse of `settings:write` for a reason worth stating: an auditor whose only way to read what the settings are is to hold the right to change them is an auditor the control has been handed to.

The group is **implied by nothing and implies nothing**, deliberately — an auditor who is also an Asset Manager is not independent of what they are auditing, and hanging it under an existing group would make that the default rather than a decision. It carries the same "do not tidy this into the hierarchy" instruction as the Tag-Issuing Unit.

**Proved by acting, not by reading permission rows.** `myservice_api/tests/test_auditor_access.py` creates a user holding exactly this group, logs in through `POST /api/v1/auth/login`, takes the real token, and opens all five reports with it; then attempts five writes with the same token and asserts each is refused. Reading the configuration would not have been enough: in the sibling Vendra repository a role was named in a report's own roles table and the report was still unopenable, because of a second gate nobody had read. A configuration test passed. An acting test caught it.

The standing constraint on the other direction is unchanged: `SCOPE_GROUPS` is deliberately **not** the inverse of `GROUP_SCOPES`, and `admin` maps to no group at all, so a scope string typed into a form can never provision a system administrator. `settings:read` maps to `group_auditor` and nothing else.

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
