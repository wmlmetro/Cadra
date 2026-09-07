# SAP ↔ Cadra — Asset Master, Dual-Code and Lifecycle Interface Specification

**For:** the SAP team at NRS · **From:** WestMetro Limited (Cadra) · 6 September 2026 · **v1.0**
**Covers:** INT-06 (asset master creation into SAP), INT-07 (the SAP asset code returned to Cadra) and INT-09 (asset lifecycle updates into SAP) of the *End-to-End Integration Flow — Cadra · Vendra · SAP*, September 2026 — Stage 4 and Stage 6.

Companion to *SAP ↔ Vendra — Purchase Order Interface Specification* (INT-01/INT-02). Same programme, same conventions, same contact. Where that document covers the procurement legs, this one covers the asset legs.

This document specifies exactly what Cadra will send, what Cadra needs back, and what SAP must give us before either can be built. It is written to be implementable without further conversation; where a choice is yours, it says so, and where the choice is ours we have made it and given the reasoning.

---

## 1. The shape of it

Three interfaces, two of them outbound from Cadra and one inbound:

| | Route | Direction | Purpose |
|---|---|---|---|
| **1** | **Asset master create** — Cadra calls SAP | Cadra → SAP | INT-06. Fires when a physical tag is **confirmed affixed**. Asks SAP to create and capitalise the fixed asset. |
| **2a** | **SAP asset code, synchronous** | SAP → Cadra (in the response) | INT-07, preferred. The SAP asset number returned in the body of the route-1 response. |
| **2b** | **SAP asset code, callback** | SAP → Cadra | INT-07, required only if creation is deferred. SAP calls Cadra when the asset master exists. |
| **2c** | **Dual-code reconciliation query** | Cadra → SAP | INT-07 safety net. Cadra asks "what is the SAP code for these Cadra codes?" on a schedule. |
| **3** | **Lifecycle event** — Cadra calls SAP | Cadra → SAP | INT-09. Transfers, custodian and location changes, disposal and retirement. |

**Why 2a *and* 2c.** The September flow names dual-code reconciliation as a control point: *"an asset is complete only when both the Cadra Asset Code and the SAP asset code are linked on the register."* An asset carrying only one of the two codes is an audit finding — a Cadra code with no SAP code means finance never booked it. A control that depends on a single successful HTTP call is not a control; it is a hope. Route 2c is how the register heals itself without anyone noticing a gap, and it is the same reasoning Vendra used for its PO range query. **The redundancy is the design, not a fallback.**

**One delivery model for routes 1 and 3.** Both are outbound events from Cadra and both use the same queue, the same retry policy, the same idempotency header and the same response handling — described once in §6. Cadra already runs this machinery in production for INT-05; you are not being asked to accommodate anything bespoke.

---

## Live API reference — Cadra's OpenAPI document

**This document is the story; Cadra's OpenAPI document is the exact schemas.** Read this one first — it explains why the interfaces are shaped as they are, which no schema can. When you are writing code and need the precise field list, types and status codes for anything Cadra *receives* (INT-07's callback, and the asset resources behind these payloads), fetch:

```
GET https://<cadra-host>/openapi.json      # the machine-readable document
GET https://<cadra-host>/docs              # the same thing, rendered
```

It is generated from the running source, from annotations that sit on the route definitions themselves, so a field cannot be renamed in the code without changing there too.

That matters for a specific reason. Elsewhere in this programme a hand-written API document named an idempotency header one way while the code required another, and requests sent under the documented name were **silently ignored** — which is why `X-Idempotency-Key` is spelled with its prefix everywhere in §6 rather than left to memory. **Where this document and the live reference disagree, the live reference is right** — tell us, because the disagreement is a defect on our side.

It carries no credentials. It describes the authentication scheme and never a value.

---

## 2. Route 1 — INT-06, asset master creation and capitalisation

### 2.1 The endpoint we need from you

```
POST https://<sap-host>/<path>/fixed-assets
Content-Type: application/json
```

Or confirmation of the BAPI / OData service to call instead — `BAPI_FIXEDASSET_CREATE1` or your OData equivalent is fine, we simply need to know which, and the field names it expects. **If you give us a service rather than a REST endpoint, tell us the exact interface and we will map to it**; the payload in §2.3 is what we hold, not a demand about transport.

One endpoint per environment (test, then production). Do not assume we can hard-code a single URL.

### 2.2 When it fires

**When a physical tag is confirmed affixed to the asset** — not when the asset record is created.

This is deliberate and it is the reason the tagging work was built before this interface. An asset record in Cadra is a claim; a confirmed tag is evidence, captured by an independent Tag-Issuing Unit through a scoped credential, with the tag number matched against the serial number at the point of tagging. Capitalising on record creation would put a value on your books for something nobody has yet proven exists in a building. The September register says the INT-06 trigger is *"tagging confirmed"* and Cadra implements exactly that: the event is raised on the transition of the label to `affixed`, once, on the physical act.

Consequences you can rely on:

- **One physical tagging produces one INT-06 call.** A Tag-Issuing Unit operative retrying a confirmation does not produce a second asset master request.
- **Cadra never asks you to capitalise something that did not commit.** The request is queued inside the same database transaction as the tag capture; a rollback discards it.
- **An untagged asset is never sent.** If it never gets tagged, you never hear about it — and it shows on our side as an incomplete asset, which is the point of the control.

### 2.3 What Cadra will send

```json
{
  "event_id": "633d46ed525c4c848d49b4b18f24b3d7",
  "event": "asset.master.create",
  "occurred_at": "2026-09-30T11:04:22Z",
  "source": "cadra",
  "company_code": "NRS1",
  "asset": {
    "cadra_asset_code": "NRS-IT-PC-00421",
    "cadra_asset_id": 11911,
    "description": "Dell Latitude 5450 — Finance, 3rd Floor",
    "asset_class": {
      "sap_asset_class": "3100",
      "cadra_category_code": "PC",
      "cadra_category": "Desktop / Laptop Computer"
    },
    "serial_number": "SN-5CG2419XYZ",
    "make": "Dell",
    "model": "Latitude 5450",
    "manufacturer": "Dell Inc.",
    "quantity": 1,
    "condition": "new",
    "capitalisation": {
      "amount": 450000.00,
      "currency": "NGN",
      "cost_basis": "acquisition_cost",
      "acquisition_date": "2026-09-25",
      "proposed_capitalisation_date": "2026-09-30"
    },
    "procurement": {
      "po_number": "4500001234",
      "grn_number": "GRN-2026-00042",
      "vendor_name": "Dell Nigeria Limited"
    },
    "location": {
      "sap_cost_center": "CC-ICT-001",
      "sap_plant": "1000",
      "building": "NRS HQ Abuja",
      "floor": "3rd Floor",
      "room": "Room 314",
      "cadra_location_id": 42
    },
    "custodian": {
      "name": "A. Bello",
      "ir_number": "IR-04821",
      "email": "a.bello@nrs.gov.ng",
      "department": "SUPPORT SERVICES GROUP"
    },
    "hierarchy": {
      "asset_level": "asset",
      "parent_cadra_asset_code": null
    },
    "tag": {
      "number": "NRS-PC-00421",
      "label_state": "affixed",
      "affixed_at": "2026-09-30T11:04:19Z"
    }
  }
}
```

### 2.4 Where every field comes from

Cadra's model is `nrs.asset`. This is the field-by-field source, so you can see what is authoritative and what is best-effort:

| Wire field | Source in `nrs.asset` | Always present? | Notes |
|---|---|---|---|
| `cadra_asset_code` | `asset_code` | **Yes** | System-generated, unique, `NOT NULL` and enforced in the database. Never entered by a person. This is the identifier the dual-code control is built on. |
| `cadra_asset_id` | `id` | **Yes** | Cadra's internal integer key. Stable. Quote it in support tickets. |
| `description` | `name` | **Yes** | Required field. Free text. |
| `asset_class.cadra_category_code` | `category_id.code` | **No — see §7** | Category is required; **its code is not, and two categories in the live register have none.** |
| `asset_class.sap_asset_class` | *mapping you supply* | **No — blocked on you** | Empty until you give us the mapping in §5.1. |
| `serial_number` | `serial_number` | No | Captured by Vendra at goods receipt for new assets; frequently absent on legacy stock. |
| `make` / `model` / `manufacturer` | `make` / `model_name` / `manufacturer` | No | Free text. |
| `quantity` | — | **Yes, always `1`** | Cadra registers one row per physical unit. A GRN line of five laptops becomes five Cadra assets with five tags. There is no quantity field to send. |
| `condition` | `condition` | **Yes** | One of `new`, `good`, `fair`, `poor`, `decommissioned`. Defaults to `good`. |
| `capitalisation.amount` | `acquisition_cost`, falling back to `purchase_value` | **No — see §7** | The single authoritative number to post. |
| `capitalisation.cost_basis` | — | **Yes** | Which of the two the amount came from: `acquisition_cost`, `purchase_value`, or `none`. Sent so the number is never ambiguous. |
| `capitalisation.currency` | `currency_id` | **Yes** | ISO 4217. `NGN` throughout. |
| `capitalisation.acquisition_date` | `acquisition_date`, falling back to `purchase_date` | No | |
| `capitalisation.proposed_capitalisation_date` | tag `affixed_date` | **Yes** | A proposal, not an instruction — see §2.5. |
| `procurement.po_number` | `purchase_order_reference` | No | Your PO number, carried from Vendra through INT-03. |
| `procurement.grn_number` | `grn_reference` | No | Vendra's GRN number. |
| `procurement.vendor_name` | `purchase_vendor` | No | **Free text, not a vendor code — see §5.4.** |
| `location.building` / `floor` / `room` | `building_id.name` / `floor_id.name` / `room_id.name` | Mostly | Cadra's own location tree. Human-readable, not SAP identifiers. |
| `location.cadra_location_id` | `location_id` | Mostly | Cadra's internal key. Meaningless to SAP; sent so a mismatch can be traced. |
| `location.sap_cost_center` / `sap_plant` | *mapping you supply* | **No — blocked on you** | Empty until §5.2. |
| `custodian.*` | `custodian_id` (`hr.employee`) | **No — 44% absent** | See §7. |
| `custodian.department` | `department` | No | **Free text with 808 distinct values in the live register.** Do not derive a cost centre from it — see §5.2. |
| `hierarchy.asset_level` | `asset_level` | **Yes** | `group`, `asset`, `sub_asset` or `component`. See the sub-number question in §8. |
| `hierarchy.parent_cadra_asset_code` | `parent_id.asset_code` | No | Set for sub-assets and components. |
| `tag.*` | `nrs.asset.tag.label` | **Yes** | By definition — the event only fires on an affixed tag. |

**What Cadra deliberately does not send.**

- **No depreciation key, useful life, or depreciation method.** SAP owns valuation. Cadra can hold a policy per category, but sending it would create two systems computing the same number and disagreeing. **Derive them from the asset class.** If you need them from us, say so in §8 and we will add them — but we recommend against it.
- **No vendor code.** Cadra holds a vendor *name*, not your `sap_vendor_code`. See §5.4.
- **No GL account.** It belongs to the asset class on your side.

### 2.5 On `proposed_capitalisation_date`

Cadra proposes the date the tag was confirmed affixed, because that is the date the September flow makes capitalisation follow. **You are expected to override it** where your period-close or posting-date rules require — a tag affixed on the 30th when the period closed on the 28th is your decision, not ours.

This is why §2.6 asks for the **actual posted capitalisation date back**, not an acknowledgement. If Cadra displayed the proposed date on the register while SAP posted a different one, the two systems would disagree about when NRS started owning an asset, and nobody would find out until an audit.

### 2.6 What Cadra needs back

**Beyond the asset code**, and this is the part that matters most for the register:

| Field | Why Cadra needs it | Required? |
|---|---|---|
| `sap_asset_number` | The dual-code control. Stored on the register beside the Cadra code. | **Yes** |
| `sap_asset_subnumber` | If you use sub-numbers, we must store the pair, not just the main number. Send `"0000"` if unused. | **Yes** |
| `company_code` | The same asset code can exist under two company codes. Without it the code is not unique. | **Yes** |
| `asset_class` *(as posted)* | Confirms which class SAP actually used. If it differs from what we sent, our mapping is wrong and we want to know on call one, not at year-end. | **Yes** |
| `capitalisation_date` *(as posted)* | See §2.5. | **Yes** |
| `capitalised_amount` and `currency` | If SAP posted a different value from the one we sent, the register must show yours. | **Yes** |
| `acquisition_value` / `accumulated_depreciation` / `net_book_value` | Cadra has a first-class **"ERP-managed"** depreciation mode built for exactly this: an external system owns the figures and Cadra never calculates them, only displays what it is given. Supplying these makes the register show finance's numbers instead of an estimate that will drift. | **Strongly preferred** |
| `useful_life` and `depreciation_key` *(as applied)* | Display only. Lets an asset manager see the basis without a SAP login. | Preferred |
| `cost_center` *(as posted)* | Confirms the §5.2 mapping took. | Preferred |

A worked success response:

```json
{
  "status": "created",
  "cadra_asset_code": "NRS-IT-PC-00421",
  "sap_asset_number": "000000012345",
  "sap_asset_subnumber": "0000",
  "company_code": "NRS1",
  "asset_class": "3100",
  "capitalisation_date": "2026-09-30",
  "capitalised_amount": 450000.00,
  "currency": "NGN",
  "acquisition_value": 450000.00,
  "accumulated_depreciation": 0.00,
  "net_book_value": 450000.00,
  "useful_life_months": 48,
  "depreciation_key": "LINR",
  "cost_center": "CC-ICT-001"
}
```

**Echo `cadra_asset_code` back.** A response that carries only your asset number forces us to correlate on request ordering, which is exactly the sort of thing that works in testing and mis-assigns a code under load.

### 2.7 Errors

Name the field. `400` with `{"error": "asset_class '3100' is not valid for company code NRS1"}` is worth more than a day of joint debugging; `400 Bad Request` alone is worth nothing. If a required master-data element is missing on your side, say which one.

**A rejection Cadra can act on is better than a silent success.** If SAP will not capitalise an asset — below a threshold, wrong class, missing cost centre — **return an error rather than creating something partial**. See §5.5.

---

## 3. Route 2 — INT-07, the SAP asset code coming back

### 3.1 Our recommendation, and why

**Synchronous in the INT-06 response (2a), with an asynchronous callback (2b) only if creation is deferred, and a scheduled reconciliation query (2c) as the safety net regardless.**

The reasoning, in order:

1. **Synchronous is the smallest system that works.** Asset master creation in SAP returns the asset number in the same call — that is how `BAPI_FIXEDASSET_CREATE1` behaves. Asking for it in the response body costs you nothing you are not already doing, and it removes an entire class of failure: there is no second delivery to lose, no second endpoint to secure, no window in which Cadra holds an asset it thinks is uncapitalised.

2. **Cadra's outbound machinery already stores it.** Our delivery queue reads an identifier out of the response body and records it against the event. A synchronous asset number lands in the register through code that is already running in production for INT-05. A callback needs a new inbound endpoint, new authentication for SAP as a client, and new idempotency handling. That is real work we will do if you need it — but only if you need it.

3. **A callback is the right answer if, and only if, creation is deferred.** If asset creation in your landscape goes through a workflow, an approval, or a nightly batch, then you cannot answer synchronously and should not pretend to. In that case: return `202 Accepted` with a reference, and call us back when the master exists. Tell us which of the two you are doing — **do not implement both**, because a system that sometimes answers synchronously and sometimes calls back is a system where nobody can tell a slow success from a lost message.

4. **The reconciliation query is not optional either way**, and it is the one thing we most need you to expose. The dual-code control has a name in the specification and a consequence in an audit. A control that depends on one HTTP call succeeding is not auditable. Route 2c is how Cadra proves, on a schedule, that every asset it believes is capitalised really is — and how it heals the ones that are not.

### 3.2 Route 2b — the callback, if you need it

```
POST https://<cadra-host>/api/v1/integrations/sap/asset-master
Content-Type: application/json
Authorization: Bearer <token we issue you>
X-Idempotency-Key: <stable unique id for this delivery>
```

Body: the same object as the §2.6 success response. `cadra_asset_code` is required and is how we match.

Cadra's responses: `200` on success, `200` with `"duplicate": true` if we have already recorded this code (not an error — stop), `400` naming the problem, `401` on a bad credential, `5xx` meaning retry with backoff. We will issue the bearer token and the per-environment URL once you confirm you need this route.

### 3.3 Route 2c — the reconciliation query (what we need from you)

**This is the endpoint we are asking you to expose.** Cadra calls it on a schedule and on demand.

```
GET https://<sap-host>/<path>/fixed-assets?company_code=NRS1
      &cadra_asset_codes=NRS-IT-PC-00421,NRS-IT-PC-00422
      &page=1&page_size=100
```

and, for the sweep in the other direction:

```
GET https://<sap-host>/<path>/fixed-assets?company_code=NRS1
      &capitalised_from=2026-09-01&capitalised_to=2026-09-30
      &page=1&page_size=100
```

Requirements, in order of importance:

1. **Let us look up by our code.** For this to work, the **Cadra asset code must be stored on the SAP asset master in a queryable field** — your inventory number, an external reference, or a Z-field, whichever suits. Please tell us which and we will send it in whatever field it needs to be in. Without this, the dual-code control cannot be verified from either side and the whole reconciliation is manual.
2. **Return the same object** as the §2.6 response, in a list. An envelope of your choosing around it is fine; the asset object itself should not differ. One shape means one mapper and no class of bug that appears only on the recovery path.
3. **Support the date-window form too**, filtering on capitalisation date. It answers the other half of the control: *an SAP asset code with no Cadra code means there is money on the books with no physical thing behind it.* We cannot find those by asking about codes we already have.
4. **Paginate**, and tell us how — a `next` cursor or a total count both work. Say which.
5. **Include retired and deactivated assets**, with their status, so reconciliation reflects reality rather than only additions.

---

## 4. Route 3 — INT-09, lifecycle events

### 4.1 One endpoint, typed events

```
POST https://<sap-host>/<path>/fixed-assets/events
Content-Type: application/json
```

**One endpoint with an `event` discriminator, not one endpoint per event type.** Every event carries the same envelope, the same identifiers and the same idempotency guarantees; only the `change` object differs. One endpoint means one authentication setup, one retry policy and one place to look when something has not arrived — and adding a fourth event type later is a payload change rather than a deployment on both sides.

Every event body:

```json
{
  "event_id": "9a1f...",
  "event": "asset.transferred",
  "occurred_at": "2026-11-02T09:15:00Z",
  "source": "cadra",
  "company_code": "NRS1",
  "asset": {
    "cadra_asset_code": "NRS-IT-PC-00421",
    "sap_asset_number": "000000012345",
    "sap_asset_subnumber": "0000"
  },
  "change": { }
}
```

**Both codes on every event.** `sap_asset_number` is what you will key on; `cadra_asset_code` is what makes the message diagnosable when the two disagree.

**If Cadra does not yet hold your asset number, no lifecycle event is sent at all.** Not queued, not held — not sent, and logged as such. An asset with no SAP asset number was never capitalised, so there is no asset master for the change to apply to, and a message you cannot key would be noise you have to discard. Nothing is lost by it either: the INT-06 create carries the asset's **current** location and custodian, so a move that happened before capitalisation is already in the create payload when it eventually fires.

### 4.2 The events, and what each carries

Stage 6 of the September flow defines two exchanges — 6.2 *"location/custodian updates and transfers affecting the asset master"* and 6.3 *"disposal/retirement instruction"*. That gives three event types:

| `event` | Trigger in Cadra | `change` carries |
|---|---|---|
| `asset.transferred` | An approved transfer is **completed** — the asset has physically moved | `from` / `to` objects with `location` (building, floor, room, `cadra_location_id`, `sap_cost_center`) and `custodian` (name, IR number, department); `transfer_reference`, `transfer_date`, `reason`, `approved_by`, `approved_at` |
| `asset.custodian_changed` | Custody reassigned without a location move | `from.custodian` / `to.custodian`, `changed_at`, `changed_by`, `reason` |
| `asset.disposed` | Asset moves to `disposed` | `disposal_date`, `disposal_reason`, `condition_at_disposal`, `approved_by`, `approved_at`, `disposal_type` (`disposal` or `retirement`) |

**Why `asset.transferred` fires on completion, not approval.** The September register says the trigger is *"transfer approved"*. Taken literally that is wrong, and we are saying so rather than implementing it: in Cadra, approval authorises the move and completion records that it happened — the asset's location and custodian fields change on completion. Firing on approval would tell SAP an asset had moved to a new cost centre while it was still in the old building, and an approved-then-abandoned transfer would leave your asset master permanently wrong with nothing in Cadra to reconcile against. **Cadra will fire on completion.** If SAP needs the commitment at approval time as well, tell us and we will add a distinct `asset.transfer_approved` event rather than overloading this one.

### 4.3 What we are **not** sending, and why

**Revaluation and impairment.** The Architect's brief for this work listed them; the September flow's Stage 6 does not, and neither does INT-09 in the integration register. We agree with the flow. These are valuation judgements: SAP is the system of record for financial postings, Cadra is the system of record for the physical asset. Cadra has no revaluation or impairment concept — no approval, no effective date, no audit trail for one — and inventing one so it can push numbers into the system that owns them would put two systems in charge of the same figure.

**Our recommendation: revaluation and impairment flow SAP → Cadra**, as part of the `net_book_value` / `accumulated_depreciation` refresh in the §3.3 reconciliation. Cadra displays them; it does not originate them. If NRS wants the *decision* captured in Cadra with approvals and evidence, that is a scope change we would price and build — say so and we will.

**`missing` assets.** Cadra has a `missing` state for an asset that cannot be located during verification. It is deliberately **not** a disposal: an asset that has been missing for a week is very often found. Whether a missing asset should trigger anything in SAP — a write-off after some period, a flag, or nothing — is a **finance policy question we need NRS to answer**, not one we should decide. See §8. Until it is answered, Cadra sends nothing on `missing`.

**Condition changes and maintenance.** `good` → `poor` is not a financial event and is not in the flow. Not sent.

---

## 5. What SAP must give us before any of this can work

This is the section that blocks the build. Each item below is an identifier that exists on both systems and means different things — the failure mode is not an error, it is a `201` and a wrong number on a balance sheet.

### 5.1 The asset class mapping

Cadra classifies assets into **22 categories** on the NRS register today. SAP has asset classes. **We need the mapping, category by category.**

The live categories, with the codes Cadra holds:

| Code | Category | Code | Category |
|---|---|---|---|
| `GEN` | Generator | `FEXT` | Fire Extinguisher |
| `UPS` | UPS / Battery Backup | `SRV` | Server / Network Equipment |
| `LIFT` | Lift / Elevator | `PC` | Desktop / Laptop Computer |
| `HVAC-P` | HVAC Plant / Chiller | `PRT` | Printer / Photocopier |
| `COMP` | Compressor | `FURN` | Office Furniture |
| `AHU` | Air Handling Unit | `VEH` | Vehicle |
| `AC` | Air Conditioning Unit | `ELEC` | Electrical Panel / Distribution Board |
| `FIRE` | Fire Safety System | `PUMP` | Water Pump / Borehole |
| `WTP` | Water Treatment Plant | `TANK` | Overhead / Storage Tank |
| `CCTV` | CCTV System | `ACS` | Access Control System |
| *(none)* | IT Equipment | *(none)* | Fleet / Vehicles |

**Send us your asset class list and we will map it once, up front, and hold it in Cadra.** We will not guess. An asset posted to the wrong class gets the wrong useful life and the wrong depreciation key, and nothing about that failure looks like a failure.

*(The two categories with no code are a data-quality problem on our side, not yours; we are fixing them. They are shown so the count matches.)*

### 5.2 The cost centre list, and how to derive one

**This is the one we are most likely to get wrong, and we would rather say so now.**

SAP will want a cost centre on the asset. Cadra has two candidates and neither is usable as it stands:

- **`department`** is **free text**, and the live register contains **808 distinct values** — `MSTD`, `SMALL TAXPAYERS DEPT NORTH`, `FCT`, `SUPPORT SERVICES GROUP` and 804 others, including near-duplicates and typos. Deriving a cost centre from this by string matching would be a fiction.
- **`location`** is a structured tree (building → floor → room) and is populated for 97% of assets, which makes it the far better basis — **if** cost centres at NRS follow location rather than organisational unit.

**What we need from you:**

1. The **cost centre master list** — code and description.
2. Which of the two a cost centre actually follows at NRS: **location, or organisational unit?**
3. If organisational unit: the **authoritative department list** with cost centre codes. We will map our 808 free-text values onto it as a one-off data-cleansing exercise and then constrain the field so it cannot drift again.

We will hold the mapping in Cadra and send `sap_cost_center` resolved. **We will not send a guess**; where a cost centre cannot be resolved, the field is null and you should reject the asset rather than default it.

### 5.3 Company code, plant and business area

- **Company code** — `NRS1` in our examples is a placeholder. Confirm the real value, and whether NRS uses **more than one**. If it does, tell us what determines which one an asset belongs to, because that determines whether Cadra needs a new field to hold it.
- **Plant / storage location** — Vendra already receives these on INT-01 and returns them on INT-02. Confirm whether the fixed asset needs them too, and whether they can be derived from location.
- **Business area / segment** — if your asset master requires one, we need the list and the derivation rule. It is not in the flow, so we have not assumed it.

### 5.4 Vendor identity

Cadra holds `purchase_vendor` as a **free-text name**, not your `sap_vendor_code`. The Vendra specification makes `sap_vendor_code` required on the PO precisely because it is the only vendor identity in the chain.

**Our recommendation: SAP derives the vendor from the `po_number` we send**, since you own the PO and the vendor master and the link between them. We should not maintain a shadow vendor master in an asset register.

If your asset master genuinely requires the vendor code on the create call, say so — the fix is for Vendra to carry `sap_vendor_code` through INT-03 into Cadra, which is a change on the Vendra side that we would need to schedule. **It is not a change we can make unilaterally, and it is not one to discover during testing.**

### 5.5 The capitalisation threshold

**What is the minimum value at which NRS capitalises an asset rather than expensing it?**

Cadra will send every asset that gets tagged. If SAP silently expenses the ones below a threshold and returns no asset number, those assets sit on our register permanently as dual-code exceptions — a growing list of audit findings that are not actually findings, which is the fastest way to make an exception report worthless.

We need: **the threshold**, and **what SAP returns for an item below it**. Our strong preference is an explicit, distinguishable response — a `200` with `"status": "not_capitalised", "reason": "below_threshold"` — so Cadra can mark the asset *"correctly not capitalised"* rather than *"missing its SAP code"*. Those are different facts and an auditor needs to be able to tell them apart.

---

## 6. Delivery, idempotency and retries (routes 1 and 3)

Cadra does **not** POST inline from the user action. The event is written to an outbox inside the same transaction as the business change, and a scheduler delivers it. This is the same machinery, with the same behaviour, that Cadra runs today for INT-05.

**Headers on every request:**

```
Content-Type:      application/json
Accept:            application/json
Authorization:     Bearer <token>        # or X-API-Key / Basic — configurable
X-Idempotency-Key: <event_id>
X-Event-Id:        <event_id>
X-Request-Id:      WDL-2026-0001         # the Cadra outbox row; quote it in logs
```

**`X-Idempotency-Key` must be honoured.** It equals `event_id` in the body, and the two are always equal. If you receive a key you have already processed, **return the original result rather than creating a second asset master.** A retry that capitalises the same laptop twice is not a rounding error.

**Retry policy.** Capped exponential backoff — `min(base × 2^(attempts-1), cap)`, defaulting to 60 s base, 1 h cap, 8 attempts. After the budget is exhausted the event is **dead-lettered**: it stops retrying, is listed for a human in Cadra, and a note is posted to the asset's audit trail. Somebody then fixes the cause and presses Retry, which reuses the same `event_id`.

**How Cadra classifies your responses:**

| You return | Cadra records | Retries? |
|---|---|---|
| `200`/`201`/`202`/`204` with an identifier in the body | Acknowledged, and stores your identifier | no |
| `2xx` with no identifier | Sent | no |
| **`409`** | **Acknowledged** — a duplicate is a successful dedupe, not a failure | no |
| `408`, `425`, `429` | Failed, backs off | **yes** |
| `5xx`, timeout, connection error | Failed, backs off | **yes** |
| **any other `4xx`** | **Dead-lettered immediately** | **no** |

That last row is deliberate and you should know about it: **a request does not become valid by being sent eight more times.** A `400` or a `422` stops on the first attempt and raises a human, rather than burning a retry budget and delaying the moment somebody looks at it. So please make your `4xx` bodies say what was wrong.

---

## 7. What the live register actually looks like

The NRS production register holds **11,914 assets**. Before you size anything or assume a field is present, these are measured facts, not estimates:

| | Count | Share |
|---|---|---|
| Assets with **no cost at all** (neither acquisition cost nor purchase value) | **11,885** | **99.8%** |
| Assets with no custodian | 5,271 | 44% |
| Assets with no serial number | 618 | 5% |
| Assets with no department | 451 | 4% |
| Assets with no location at all | 330 | 3% |
| Assets with a PO reference | 32 | 0.3% |
| Assets with a confirmed affixed tag | 34 | 0.3% |
| Assets carrying a SAP asset number | **0** | **0%** |

**The cost figure is the one that matters.** The register was populated by a physical verification exercise that captured what exists and where — not what it cost. Almost none of it carries a value, and **an asset master posted with a zero acquisition value is not a capitalisation, it is a defect on your books.**

Two consequences, and NRS needs to decide between them (§8):

- **Going forward this solves itself.** Assets arriving through Vendra carry a PO, a GRN and a cost from the goods receipt, because Vendra captures the value at the point of receipt. The 34 tagged assets are the leading edge of that.
- **The 11,880 legacy assets do not.** They will need a valuation exercise before they can be capitalised, or an explicit decision that they are already on SAP's books from a prior migration and should be *linked* to existing SAP asset numbers rather than created as new ones.

**Our recommendation: do not run INT-06 over the legacy population at all.** Load the existing SAP asset numbers into Cadra as a one-off reconciliation against the assets already on your books, and let INT-06 handle only assets tagged from go-live forward. Creating twelve thousand asset masters at zero value to satisfy a completeness control would defeat the control.

For that one-off we need a **flat extract of your existing fixed asset register** — asset number, sub-number, description, serial number where you hold it, cost centre, capitalisation date, acquisition value and net book value. We will match on serial number and description and report what matched, what did not, and what exists on one side only. **That report is the dual-code control's opening balance**, and it is the first thing an auditor will ask for.

---

## 8. What we need from you to proceed

**Endpoints and services:**

1. **The asset master create endpoint or BAPI/OData service** (§2.1) — and confirmation you will honour `X-Idempotency-Key`.
2. **Which INT-07 route** (§3.1) — synchronous (2a) or callback (2b). Not both.
3. **The reconciliation query endpoint** (§3.3) — URL, auth scheme, pagination style — **and which field on the SAP asset master will hold the Cadra asset code** so it is queryable.
4. **The lifecycle event endpoint** (§4.1).
5. **Two environments** — a test SAP we can integrate against before touching production.
6. **Which authentication** across all of the above: bearer, API key, or OAuth2 client-credentials. We will implement to whatever you specify; tell us the token lifetime if it expires.

**Master data:**

7. **The asset class list**, for the §5.1 mapping.
8. **The cost centre list**, and whether a cost centre follows **location or organisational unit** (§5.2).
9. **The company code**, and whether there is more than one (§5.3).
10. **The existing fixed asset register extract** (§7), for the opening reconciliation.

**Answers to six questions that change what we build:**

11. **What is the capitalisation threshold, and what do you return for an item below it?** (§5.5)
12. **Do you use asset sub-numbers?** Cadra models sub-assets and components under a parent. Should a Cadra component become a **sub-number of its parent's SAP asset**, or its own asset master? This changes the payload and the reconciliation, and it is easier to answer now than to migrate later.
13. **Is the vendor code required on the asset master**, or will you derive the vendor from the PO? (§5.4)
14. **Should a `missing` asset trigger anything in SAP** — and after how long? (§4.3) This is a finance policy decision, not a technical one.
15. **Do you want the revaluation and impairment figures to flow back to Cadra** for display in the reconciliation refresh, as we recommend? (§4.3)
16. **What is your expected volume?** Roughly 30–50 assets a month through new procurement, plus whatever the legacy decision in §7 produces as a one-off. It sets our batching and your rate limits.

Cadra's callback URL, bearer token and test-environment details will be issued once you confirm items 1–4, so both directions can be tested together rather than one at a time.

**Contact:** WestMetro Limited · apps@westmetrong.com
