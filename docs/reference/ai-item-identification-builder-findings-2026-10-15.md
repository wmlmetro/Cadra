# AI item identification — the Builder's findings, 15 October 2026

**For:** the Architect, before an evaluation or a handoff is written.
**From:** the Builder. Nothing has been built and nothing has been committed.
**Sources, in this folder:**
- `ai-item-identification-addendum-2026-10-13.pdf`: *Cadra Mobile — AI Item Identification & Referencing*, requirements addendum to the Barcode Station mobile app BRD (@soji, 13 October 2026). 14 functional requirements (AI-FR-01…14), 8 non-functional (AI-NFR-01…08), acceptance targets, and six open questions for NRS.
- `ai-capture-backend-endpoints-2026-10-13.pdf`: *Backend Endpoints for AI Item Identification* (mobile team, 13 October 2026). It says 6 existing endpoints are reused "as is" and 18 are new, "checked against the live staging OpenAPI spec".

This file does what `docs/ADDENDUM-A-EVALUATION.md` did for Addendum A, from the Builder's side. It says what the code does today, where the addendum agrees with rulings already made, and where it contradicts them, with file and line for each. Rulings are yours. §8 lists the questions that block a handoff.

---

## 1 · In one paragraph

A field operator photographs an item that has no serial number, mostly furniture. A model on the phone suggests the class, the attributes and the condition, and the operator confirms them. The phone then takes the next asset code from a block reserved to that device, prints the tag on the spot, and registers the item **in one pass, offline**, syncing later. The photos also produce a visual signature, used for duplicate checks, lost-tag recovery (reprint under the same code), and tag-swap flags in audits. The main use is **Lot 4: audit and tagging of existing assets**.

**Most of this is phone-side. Cadra's part is to:**
- hand out codes;
- accept a registration carrying a code the phone already issued, exactly once;
- store photos, signatures and an audit trail of suggestion against confirmation;
- serve the catalogue, rooms and label layout for offline use.

**Three of those collide with rulings already built:**
1. the seven-gate receipt chain and its separation of duties;
2. where and when an asset code is minted;
3. what a tag replacement does to the number.

**One question decides how hard all three are:** is a Lot 4 audit capture of an *existing* asset the same act as a *receipt* of new goods? Nothing in the repo rules on it.

## 2 · What was checked, and what was not

- **Checked by reading code and docs:**
  - every one of the 6 "reuse as is" endpoints and all 18 new ones, against the routes in `myservice_api/controllers/`;
  - the addendum against `docs/DECISIONS.md`, `docs/ADDENDUM-A-EVALUATION.md`, `docs/reference/addendum-a-verification-gated-receipt.md`, `docs/GO-LIVE.md` and handoffs 53–60.
- **Opened at the source before writing down:** every claim §§3–7 depends on. That covers the asset-code mint, the gated label mint, the replacement's new number, the `by-tag` lookup, the condition enum, the pool refusal, the eight exclusion pairs, the idempotency window, `_order`, the capturable fields and the gate-switch state.
- **Not done:**
  - no request was made against any tenant or against staging;
  - the mobile team's "checked against the live staging OpenAPI" was not re-run, so this file reads the code, not the published spec;
  - `/verify`, `/mark-missing` and `/mark-found` on a receipt candidate were read, not driven (see §3).
- **Gate switch, as recorded:** `cadra.receipt.gated` is **on for `staging` only** and off on every other tenant. Turning it on for an NRS tenant is the owner's decision (`docs/handoffs/58-the-gates-kept.md:220`). So two different chains answer the mobile app today, depending on the tenant. Both are covered below.

---

## 3 · The six "reuse as is" endpoints: none is as is

| Endpoint | Exists at that path? | What the mobile team needs to know |
|---|---|---|
| `GET /asset-categories` | **Yes** (`v1_settings.py:284-294`, `assets:read`) | Already returns, per class, `identification_mode` (`serial`/`tag_id`/`pool`/`record_only`), `class_attributes_schema` `{"mandatory": [...]}` (always the effective schema, never null) and `sap_asset_class` (`v1_settings.py:76-103`). **This makes the proposed `GET /asset-classes/{id}/required-fields` redundant.** |
| `GET /locations`, `/{id}/children` | **Yes** (`v1_locations.py:329-368`, `:516-523`, `locations:read`) | `/children` is a plain array, not paginated. **No location has a barcode or QR field** (`crnd-19/generic_location/models/generic_location.py:138-159`). The nearest is `zone_code`, free text used for tag prefixes. AI-FR-10's "scanned room or zone barcode" has nothing to scan, and neither has Addendum A's AD-37 ("Scanning a room barcode lists every Tag-ID asset…"). |
| `GET /assets/by-tag/{tag}` | **Yes** (`v1_assets.py:1577-1598`, `assets:read`) | Matches tag, then asset code. **There is no serial step** (`:1590-1591`). It does see candidates. Tag → code → serial with `matched_by` and an ambiguity count is `GET /barcode/lookup?query=` or `GET /tags/lookup?query=` (`v1.py:2922`, `:3187`; resolver `myservice_barcode_station/controllers/main.py:44`). |
| `POST /assets/{id}/tag-affixed` | **Yes** (`v1_assets.py:2611-2856`, `tagging:write`) | **Gates ON:** refused on a freshly captured unit, with *"This asset has no active tag to confirm"* (`:2745-2749`). The label is minted only at `request-tagging`, and the model refuses an affix before `tag_issued` (`asset_gates.py:835-839`). A `tag_id` class also needs `attributes_confirmed: true` on the first affix (`:2761-2772`). Offline work is already provided for: `affixed_at` may be in the past, and a future one is refused (`:2685-2690`). |
| `POST /assets/{id}/verify` | **Yes** (`v1_assets.py:2082-2142`, `assets:write`) | Takes `notes` only. **No photo**, so AI-FR-12's "one photo checks the item against its stored photos" has nowhere to put the photo. |
| `/mark-missing`, `/mark-found` | **Yes** (`v1_assets.py:2146-2261`, `assets:write`) | `reason` is **required** on both, and each answers 409 on the wrong state. Read, not driven: neither the route nor `action_mark_*` (`asset.py:1279-1360`) reads `register_state`. The candidate guard blocks only custodian, move and disposal (`asset_gates.py:449-466`), so these probably act on a candidate. Is that intended? |

## 4 · The 18 new endpoints, one by one

**Verdicts:**
- **new**: nothing like it exists;
- **redundant**: it exists already;
- **extend**: it belongs on an existing route or model, not a parallel one (*one answer per rule*, handoff 31);
- **blocked**: it can't be specified until a ruling in §8 is made.

### Offline core and codes

| Endpoint | Verdict | Finding |
|---|---|---|
| `POST /devices` | new, **blocked on Q4** | There is no device model, pairing, or per-device anything in the backend. The only "pairing" in the repo is a person paired to groups (Asset User + TIU). Also open: does the phone authenticate as a **person** (`/auth/login`, scopes from groups) or as an **API credential**? Rule 2 of the role exclusions does not apply to API credentials' users (DECISIONS 2026-10-12), but the per-unit no-two-gates rule still does. |
| `POST /devices/{id}/code-blocks` | new, **blocked on Q2** | Today the code is `ir.sequence` `nrs.asset` (`NRS-AST-` + 6 digits, `myservice_asset_register/data/asset_sequences.xml:4-10`). It is assigned in `nrs.asset.create` **for every asset, gates on or off** (`asset.py:390-408`), and is never caller-settable: it is absent from `_WRITABLE_FIELDS`, and sending it is a 400 (`asset.py:100-101`). A block is mechanically easy: advance the sequence by N under a row lock and record the range against a device. It contradicts D1/AD-18, however (§5.2). |
| `GET /devices/{id}/code-blocks` | new, blocked on Q2 | Same. |
| `POST …/code-blocks/{block_id}/return` | new, blocked on Q2 | The addendum says both "unused codes return to the pool on sync" and "a code is never reused". Those are compatible only if "return" means **void the remainder**, not reissue it. Reissuing would break AD-18 ("a reserved code is never reused") and DECISIONS 2026-10-01 ("The old number never comes back"). The endpoint should be specified as a void. |
| `GET /ai/config` | new | No such parameters exist. Tenant thresholds would sit as `cadra.*` config parameters like every other switch, and so appear in the configuration-change report. **The capitalisation threshold has no value anywhere.** D10 is "None set; mode chosen per class", and it is an open question to SAP in `docs/integrations/INT-06-07-09-sap-requirements.md` §5.5. |

### Registering items

| Endpoint | Verdict | Finding |
|---|---|---|
| `POST /ai-captures/photos` (multipart) | new | **No API route reads or writes an asset photo.** `nrs.asset.image` exists (`asset.py:339`, max 1024²) but is in neither `serialize_asset` nor `_WRITABLE_FIELDS`. The one photo path is base64 `attachments` on `POST /assets/{id}/gates/verify` (`v1_gates.py:161-199`, `vfm:verify`), which is IAD's evidence step. The only multipart route under `/api/v1` is the employee xlsx import, a raw `@http.route` outside `cadra_route` and so outside the envelope (`v1.py:3565-3589`). A multipart route inside the envelope would be the first. |
| `POST /ai-captures` | new, **blocked on Q1 and Q2** | This is the core of the feature, and the mobile team's "most important rule" names its two requirements: accept a phone-issued code, and never create a second asset on replay. **On the code:** `asset_code` is deliberately not writable (rule 2), so the route needs either a code the server recognises as reserved to this device, or a ruling that the phone does not issue codes. **On replay:** `X-Idempotency-Key` lasts **24 hours** (`utils.py:1343`, scoped `(key, path)`), and AI-NFR-02 requires **5 working days** offline. A replay on day 6 would create a second asset. `capture_id` has to be a **stored, unique column**, not the idempotency cache. **On which chain:** with gates ON, `POST /assets` creates a `captured` candidate with no label (`v1_assets.py:1759-1760`). With gates OFF, it creates an asset with a **location-built** label (e.g. `HQ-GF-MR-FRN-001`, `asset_tag.py:640-721`) that is **not** the asset code, which is a second way the phone's printed code would disagree with the server. **On attributes:** see §7.4, because a furniture class requires `make` and `model_name` by default. **On the audit trail** (AI-NFR-05: suggestion, confirmed value, changed fields, model version, operator, times): no such record exists. It belongs as an append-only record on `nrs.asset.append.only.mixin`, either a new event type or a new model inheriting the mixin, not as fields on the asset. |
| `GET /ai-captures/{capture_id}` | new | Trivial once a capture record exists. |
| `POST /ai-captures/{capture_id}/void` | new, blocked on Q2 | Codes exist today only **on assets**. There is no "reserved code" record, so a code issued and then voided before any asset exists has nowhere to be recorded. A reservation/void ledger is the same thing AD-18 already asks for ("status reserved, not active") and was never built (§7.1). |
| `GET /asset-classes/{id}/required-fields` | **redundant** | `GET /asset-categories` already returns the effective mandatory schema per class (§3). |

### Duplicates, lost tags, audits

| Endpoint | Verdict | Finding |
|---|---|---|
| `GET /ai/signatures?location_id=&since=` | new | No embedding storage exists. Postgres is plain `postgres:13` in every profile (`docker-compose.yml:26`, `k8s/dev/30-postgres-statefulset.yaml:23`); there is **no pgvector**, and nothing in the Odoo images or requirements mentions one. That isn't blocking: the addendum scopes matching to a room or zone, which means tens of candidates, and a float array compared in Python is enough at that size. |
| `GET /assets?location_id=&updated_since=` | **extend** | `location_id` is already a filter on `GET /assets` (`v1_assets.py:1366`). `updated_since` is not, though `updated_at` is published (`:947`, from `write_date`). Adding a filter is additive. It must refuse what it cannot parse (handoff 21). Note that the list hides candidates unless `register_state=any` (`candidates:read`). |
| `GET /assets/{id}/photos` | new | Same gap as the photo upload. |
| `POST /ai/lost-tag-requests` | **extend, blocked on Q3** | This is handoff 38's tag replacement with a different approver. Today: `POST /tags/{id}/request-replacement` (`tagging:write`, `reason` and `approver_id` required, `v1_tags.py:454`), approved by `approvals:write` (Asset Manager group, via `APPROVER_GROUP`), with self-approval refused. The addendum wants the **custodian and/or supervisor** to approve, and a reprint under the **same** code (§5.6). A parallel route would make two answers to "who approves a replacement". |
| `POST /assets/{id}/swap-flags` | new | Nearest existing pieces: the `exception` review status (handoff 30), `affix_refused` events (handoffs 51/52), and Addendum A's AD-37 count verification ("variances raise an exception with a mandatory explanation"), which is unbuilt. The NRS meeting evaluation (30 September, §3.8) recorded: "What does not exist: any campaign or session, any walk-round worklist, any way to verify by scanning." A swap flag needs a reviewable state, so it is not an append-only event on its own. |
| `GET /ai-captures/flags?since=` | new | Depends on server-side duplicate detection, which depends on stored signatures. |

### Printing and models

| Endpoint | Verdict | Finding |
|---|---|---|
| `GET /barcode/label-template` | new | **No route returns a layout as data.** `GET /barcode/print-url` returns a server-rendered QWeb PDF URL (`myservice_barcode_station/controllers/main.py:295-352`). Sizes: small 50×25 mm, medium 50×30, large 100×60, A4 sheet ×8 (`myservice_asset_register/data/asset_tag_report.xml:10-112`). Three constraints carry over to an offline phone renderer: (1) the QR and Code 128 payload is the tag value verbatim, and "a QR that encodes a URL or a prefix breaks every affix" (handoff 55 §3); (2) **the small and standard Code 128 read 0 of 24 by camera; the QR reads on every size** (handoff 54, GO-LIVE §28.2); (3) handoff 10's print funnel records every print, and a phone printing offline goes round it unless the sync reports the print. |
| `GET /ai/models/manifest` + download | new, mostly outside Cadra | A file host with checksums. AI-NFR-04's residency rule applies to it as well. |

---

## 5 · Where the addendum contradicts a ruling or built behaviour

1. **One operator, one pass, against the seven gates.**
   - Addendum A §1: *"No capital item enters the asset register until Store has received it, IAD has validated it… the Audit Tagging Team has tagged it, and a maker-checker pair has registered it."*
   - Addendum A §4 rule 1: the same user may not fire two different gates on one record. This is built: a refusal is `409 segregation_of_duties`, and the refusal names the earlier act (handoff 57).
   - GO-LIVE §29.1: *"With fewer than seven distinct people the no-two-gates rule makes the chain impossible to finish — it does not degrade, it stops."*
   - GO-LIVE §29.6: there is no "release all candidates" action, by design.
   - AI-FR-06 has the phone take a code and print the tag **on confirmation**, and AI-FR-09 creates draft records for "confirmation and batch tag printing". Under the gates that is receipt + request-tagging + affix by one person, refused at the second.

2. **The person who receives may not be the person who tags, by role and not only per unit.**
   - `myservice_api/data/role_exclusions.xml` seeds eight pairs. Six of them are Asset Officer × {IAD officer, IAD approver, Asset Controller, **Tag-Issuing Unit**, Register Maker, Register Checker}.
   - `POST /assets` needs `assets:write` (the Officer) and `/tag-affixed` needs `tagging:write` (the TIU).
   - So **no person can be granted both scopes the one-pass flow needs**, gates on or off. Gates off removes the per-unit rule, but not this one.
   - The only exemption is an API credential's user (DECISIONS 2026-10-12). Running a field team on a shared credential would erase *who* captured, which AI-NFR-05 requires.

3. **The code is minted at the server, at a ruled moment, not on a device.**
   - D1: *"Reserved at tagging request, made active at registration approval, and never reused | Fixed"*.
   - AD-18: *"On request, Cadra reserves an asset code per candidate"*.
   - AD-17: the tag request is *"unavailable to users holding a Store role"*, and D3 places it with *"Asset Controller in a non-Store unit"*.
   - A device-reserved block moves the moment of issue from the Asset Controller to the field operator, and from the server to a phone.

4. **The tagger is not handed the number.**
   - Handoff 39 ruling (DECISIONS 2026-10-01): *"The screen never HANDS the expected tag number over"*. The affix check is evidence only if the number comes off the physical label.
   - Handoff 60 §2c extends that: it hides the asset code on the tagging tab's rows.
   - When the same phone issues the code, prints the label and confirms the affix, AD-19's check ("payload equals the reserved code") compares the device with itself and proves nothing.

5. **Every receipt starts from a PO or GRN.**
   - AD-05: *"Store can receive only against a NOTIFIED schedule line."*
   - INT-03 from Vendra is the hand-off (evaluation §8).
   - An existing chair found in a room has no PO, no GRN and no schedule line, so there is no door into the gated chain for it at all. This is Q1.

6. **A replacement mints a new number. The addendum, and our own evaluation, want the same code.**
   - `action_approve_replacement` scraps the label and calls `_generate_tag(source='manual')` (`asset_tag.py:283`).
   - The gated override passes a tagged candidate to the location-prefix generator (`asset_gates.py:868-886`). So **on a gated unit the replacement label is no longer the asset code**, which contradicts ruling 4.3 (*"the asset code is what the label carries"*) today, independently of this addendum.
   - The code's own comment argues against same-number reissue: two physical labels sharing one code make the history ambiguous.
   - ADDENDUM-A-EVALUATION §4.4 recommends the opposite: *"Change the replacement flow to a reprint with a void reason and a count."* §4.4 is **not** in the owner's §7 rulings table and is not built.
   - The DB constraint is unique-*active* (`_check_unique_active`), so a same-code reprint is possible once there is a reprint count and a void reason.

7. **Pooling is refused today.**
   - A gated receipt of a `pool` class raises *"Pool identification is not built yet (Addendum A Phase E)"* (`asset_identification.py:341-345`; pinned by `myservice_api/tests/test_gates_kept.py:222`). The mode is labelled "Pool (not built yet)" (`:63`).
   - D10 (threshold) has no value, D11 says *"no class defaults to Pool"*, and D12 (capitalised or memorandum) is open.
   - The evaluation §5 places Pool in Phase C, while the refusal text says Phase E. That inconsistency is ours.
   - A `tag_id` unit is one record per unit with no quantity field. The 30 September evaluation says *"There is no quantity field to send and there never should be."* AI-FR-13's "qty 12" is a pool or nothing.
   - **Name clash:** the register list already prints *"Pool — {department}"* for an asset with no custodian (GO-LIVE l.1142). A real Pool mode would collide with it.

8. **The condition grades don't match the published enum.**
   - AI-FR-04: New, Good, Fair, Poor, **Unserviceable**.
   - `nrs.asset.condition` (`asset.py:159-165`): `new`, `good`, `fair`, `poor`, **`decommissioned`**, default `good`.
   - Architecture rule 4 says enums are published surface. The model is not changed to match a document. Either the mobile app maps *Unserviceable* → `decommissioned` (if that is the same thing), or a new value is a versioned change with Vendra downstream.
   - Condemn already sets the condition as well as the state (handoff 29). If NRS answers yes to "should condition drive disposal" (open question 4), that is where it connects.

9. **Data residency.**
   - AI-NFR-04 requires photos, signatures and training data in NRS-approved hosting **in Nigeria**.
   - The repo does not record the region of the `cadra-dev` DOKS cluster, and `docs/DEPLOYMENT.md` names none.
   - If photos are stored as `ir.attachment` on the same Postgres and filestore, the residency question is the whole deployment's, not this feature's. Somebody should establish where the cluster and the client deployments run before the first photo is stored.

## 6 · Where it agrees with what we have

1. **No serial, identified by the asset code.**
   - Addendum A §12, owner ruling 4.1, and handoff 58's `identification_mode = tag_id`, seeded for furniture.
   - Addendum principle 1 ("Cadra issues the reference, not the model") and principle 2 (opaque, immutable code, barcode and QR verbatim) are ruling 4.3 and handoff 55 §3 restated.
   - The label minted at `request-tagging` already has `name = asset_code` (`asset_gates.py:799`).
2. **Codes are never reused.** This is AD-18 and DECISIONS 2026-10-01.
3. **Offline affix time.** `affixed_at` in the past is accepted on `/tag-affixed`, documented for "a batch recorded offline".
4. **Attributes.**
   - AI-FR-03's material, colour and dimensions map onto `CAPTURABLE_FIELDS` (`asset_identification.py:69-80`).
   - Brand maps onto `make`.
   - Upholstery and number of drawers or seats have **no field**; the capturable set is fixed at eight names.
5. **Photo of the item.** AD-10 (Store may attach photos) and AD-34 (*"takes a photo showing the tag on the item, and records the room"*) already ask for it. Neither is built.
6. **Duplicates scoped to a room** match how the register is already partitioned by `location_id`.
7. **The scanner runs on phones.** The bundled `zxing-wasm` engine is THE engine on every device (handoff 54). An offline mobile app can reuse `scanDecision.ts`'s acceptance rules, which are pure functions.
8. **Classification never bypasses the cascade** (addendum principle 5), and **classification gaps block capitalisation, never registration** (§5 of the addendum). That is the shape handoff 59 built: a missing `sap_asset_class` blocks the maker and the checker, and receipt is not affected.
9. **"The AI proposes, a person confirms"** is the same stance as handoff 40's camera: *a detection fills the field and does not submit*.

## 7 · Facts about the code the design depends on

1. **The asset code is assigned at creation, not reserved at tagging request, even with the gates on.**
   - `asset.py:390-408` fills `asset_code` in `create` for every unit, and a `captured` candidate already has one.
   - D1/AD-18 say it is *reserved at tagging request*, and handoff 59 §2 says for `record_only` that "the asset code is still assigned at registration".
   - So the built behaviour already differs from D1. No "reserved" status exists for a code. A code-block design, or Q2's ruling either way, should fix this at the same time.
2. **`_order = 'asset_code desc'`** (`asset.py:92`) relies on lexical order being creation order. Device blocks break that: device A's block 100–149 is used after device B's 150–199. This affects back-office list order only. The API paginates on `id` (`utils.py`) and is unaffected.
3. **The 24-hour idempotency window** (`utils.py:1343`) is shorter than the 5-day offline requirement (§4, `POST /ai-captures`).
4. **A `tag_id` class requires `make` and `model_name` by default** (`DEFAULT_MANDATORY`, `asset_identification.py:82-88`). AI-FR-03 extracts a brand only "where a logo or stamp is visible". A generic chair with no visible brand **cannot be received** under the default schema. Each class can be changed today with `PATCH /asset-categories/{id}` (`settings:classes`), but the default for furniture should be looked at.
5. **Placeholder serials are refused at a gated receipt, `tag_id` units included** (handoff 59, ruling 4 of handoff 60). An AI capture must send no serial, not a dummy one.
6. **A tagged label is checked at the affix**, and the refusals are append-only `affix_refused` events with the symbology (handoffs 51/52/54). This is the existing record a swap flag would sit beside.
7. **Gates-off labels are location-built** (`asset_tag.py:640-721`), so on every tenant except `staging` today, the number printed on a label is not the asset code.

## 8 · Questions that block a handoff, in the order they unblock things

1. **Q1: Is a Lot 4 audit capture of an existing asset a receipt?**
   - This is the question with the widest consequences. The gate chain was written for goods arriving against a PO (AD-05) and has no door for a chair already in a room.
   - **If an audit capture is its own path**, it needs its own (shorter) chain in the one `TRANSITIONS` table (`asset_gates.py:171`). `record_only` is the precedent: gates *skipped, not fired*, with an event saying why. It also needs its own rule on who may do which step.
   - **If it is a receipt**, AI-FR-06's one pass cannot exist under the gates. The phone becomes a capture tool feeding `captured` candidates, and tagging happens later, by someone else.
2. **Q2: Does the phone issue codes, or does Cadra?**
   - Either answer should close §7.1 (code assigned at create vs D1's "reserved at tagging request").
   - **If the phone issues codes**, a device reservation ledger with `reserved → active | void` states is the AD-18 ledger that was never built, and the "return" endpoint is a void.
   - **If Cadra issues codes**, offline capture records a provisional local id and the code arrives on sync, which means the tag cannot be printed offline.
3. **Q3: Replacement keeps the code?**
   - ADDENDUM-A-EVALUATION §4.4 recommended yes and was never ruled.
   - The gated override already breaks ruling 4.3 on replacement (§5.6), whatever this addendum says.
   - Who approves: the custodian, the supervisor, or today's Asset Manager group? This is the addendum's own open question 5.
4. **Q4: How does the phone authenticate: as a person or as a device credential?**
   - It decides whether role exclusions apply, whether AI-NFR-05's "operator" is a real account, and whether a "device" is a model or just a header.
5. **Q5: Condition, *Unserviceable* vs `decommissioned`.** Is this a mapping or a new enum value? (rule 4)
6. **Q6: Pool.** It needs D10/D12 and the "Pool —" label clash resolved first, and the Phase C/E inconsistency fixed.
7. **Q7: Where do the cluster and the client deployments run?** (AI-NFR-04)
8. **Q8: What does a "room barcode" encode, and on which model does it live?** AI-FR-10 and AD-37 both assume one. `generic.location` has none.

## 9 · The addendum's own open questions for NRS, against what we already hold

| NRS question | What the repo already says |
|---|---|
| Capitalisation threshold, and may items below it be pooled (AI-FR-13)? | Unanswered: D10 has no value, D12 is open, and the question is put to SAP in INT-06-07-09 §5.5. **It is one question asked in three places. Ask it once.** |
| Which pilot sites for Lot 4? | Nothing in the repo. |
| Which device models? | Handoff 54 measured the camera floor: Code 128 at small/standard sizes unreadable on any camera, QR fine. §6c's real-device table is still owner-blocked. |
| Should condition grades drive maintenance or disposal? | Condemn already writes condition (handoff 29). The enum mismatch is Q5. |
| Who approves a lost-tag replacement for identical items? | Today: a named Asset Manager, never the requester (handoff 38). This is Q3. |
| Photo retention after disposal? | An asset with any append-only row cannot be deleted (custody, movement or event, and every asset created at a location has one from birth). Attachments therefore outlive disposal by default. No retention or purge exists. |

## 10 · What a first build could safely contain without any ruling

These hold whichever way §8 is answered, and are additive under rule 1:
- a `GET /assets` `updated_since` filter;
- photo upload and read on an asset, multipart, inside the envelope, with a size cap per AI-NFR-07;
- the asset's photos on `GET /assets/{id}/photos`;
- a barcode/QR field on `generic.location`, which Q8 decides the content of but not its existence;
- correcting the mobile team's list: `/asset-categories` replaces `/asset-classes/{id}/required-fields`, and serial lookup is `/barcode/lookup`, not `/by-tag`.

Everything that issues a code, creates an asset from a capture, or reprints a tag waits on Q1–Q3.
