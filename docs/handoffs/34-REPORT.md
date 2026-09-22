# Report 34 — Warranty

**Branch:** `feat/warranty` · **Base:** `dev` at `3c6ed0a`. That commit holds both instruction files, 33 and 34. PR #83 had merged (09:54 UTC). **34 ran before 33**, as 34's own Step 0 asked, because 33 had not started.

**Commits:** `18542e5` (the work) · this report.

> ## Which Cadra version accepts the new keys
>
> **`myservice_api` 19.0.3.12.0, with `myservice_asset_register` 19.0.1.18.0.** From that version, `POST` and `PATCH /api/v1/assets` accept `warranty_start_date`, `warranty_months`, `warrantor` and `warranty_reference`, beside `warranty_expiry`, which already existed.
>
> **Vendra can check this at runtime, without asking anybody.** On a Cadra that accepts the keys, `GET /api/v1/openapi.json` lists `warranty_months` among the request-body properties of `POST /api/v1/assets`. On one that does not, it is absent. This is the same kind of check that opened `provenance_fields_enabled()`. `tests/test_warranty.py::test_openapi_advertises_the_warranty_keys_on_create` asserts it.
>
> **Send `warranty_start_date` and `warranty_months`, and do NOT send `warranty_expiry`.** Cadra works the expiry out. An expiry that contradicts the start and duration is refused with a 400, and so is half a basis.
>
> **Where it is live:** all eight local databases were upgraded before the code was restarted onto them. **The cluster has not been upgraded**; that is the owner's deploy.

**Needs the owner:**
1. **The PR merge.**
2. **The staging/production deploy**, and the `cadra-upgrade` Job fanned out to every tenant before the new image serves them. This change adds stored columns (see `CLAUDE.md`). Vendra's half must not go live anywhere before this has.
3. **GitHub billing**, sixth report.

---

## 0 · What happened, in plain terms

A stakeholder asked how warranty is captured. The honest answer was that it isn't, even though a *Warranty expiry* date field had existed all along. It had a form input and a published key, and on every real tenant it was empty for 100% of assets.

**What now exists:**
- A storekeeper, or Vendra at goods receipt, records a warranty as it is quoted: *24 months from the day it arrived*.
- Cadra works out the expiry date from that, and publishes the working beside the answer: *"24 months from 2026-03-12"*.
- Cadra also records **who honours** the warranty, as a name, and the **certificate number**.
- The register can be filtered three ways: *under warranty*, *expired*, and *no warranty recorded*. That third state is honest, and today it is every asset.
- There is an *expiring soon* view, with its window of dates printed on the screen.
- The asset page has a Warranty section. The register dashboard has four warranty tiles, and each opens exactly the rows it counted.
- Every later change to a warranty is written into the asset's permanent history.

**What broke on the way:** four things, none of which reached anybody.
1. **The reviewer found a real defect.** When a warranty field was changed on several assets in one save, the save ran the SAP notification twice per asset. For a disposal, that would have told SAP twice. No screen or integration does this yet. It is now fixed, and a test proves the fix: that test failed against the old code before it passed against the new.
2. **The asset page would have hidden two facts.** Where a warrantor or certificate number was recorded without a date, the page said *"nothing has been entered"* and hid both.
3. **The browser test raced its own page.** It typed into the edit form before the form had loaded the asset.
4. **A guard caught two unregistered filters.** The query-parameter guard failed because the two new filters had no entry in its inventory. That is the guard working.

**What it means:** Cadra is ready for Vendra's half. The one sentence Vendra is gated on is in the box above.

---

## 1 · The shape, as built

### 1.1 · The fields

| Field | Written by | Note |
|---|---|---|
| `warranty_months` | caller | whole months, 1–600; 600 is fifty years, and anything above it is a year typed into the months box |
| `warranty_start_date` | caller | the day it runs from; the form offers the purchase date, visibly |
| `warranty_expiry` | **derived** when both of the above are set; otherwise the caller | same name, type and published key as before |
| `warrantor` | caller | **a name as recorded, not a partner link**, following the custody chain's rule |
| `warranty_reference` | caller | the certificate or document number, free text |
| `warranty_status` | computed, not stored | `under_warranty` / `expired` / `none`, judged against a **Lagos** day |

The rules live in `nrs.asset._resolve_warranty`, inside `create` and `write`, so every writer passes through them. Each refusal happens before anything is written.

1. **A duration and a start date go together.** Either one alone is a `400 validation_failed`.
2. **With both, the expiry is derived.** Sending an expiry that contradicts them is **refused, not overwritten**. Sending the same date again is accepted, because a form that re-sends what it displayed contradicts nothing.
3. **A bare expiry with no basis is accepted**, for whoever holds only a date, and `basis` says that is how it was set.
4. **A derived expiry goes with its basis.** Clearing the start and the duration clears the expiry too.

The arithmetic uses calendar months and clamps at a month's end, so 24 months from 29 Feb 2024 is 28 Feb 2026. The expiry day itself is covered.

**`warranty_expiry` is not a stored compute, and that is on purpose.** A `compute=…, readonly=False` field lets the basis win silently over an explicit date sent in the same write. That is exactly the quiet overwrite rule 2 refuses.

### 1.2 · What the API publishes

`data.warranty` appears on every asset:

```json
"warranty": {
  "status": "under_warranty",
  "status_as_of": "2026-09-22",
  "warranty_expiry": "2028-03-12",
  "warranty_start_date": "2026-03-12",
  "warranty_months": 24,
  "warrantor": "Dell Nigeria Ltd",
  "warranty_reference": "DL-WC-55120",
  "basis": "24 months from 2026-03-12"
}
```

**The keys are the WRITABLE names.** The block is `warranty.warranty_months`, not `warranty.months`. Handoff 33 §B2 found six keys published under one name and accepted under another, so reading an asset and sending it back was refused. A new block should not be born with that problem.

So a block can be sent back **unchanged**. If you edit the duration, you leave out the expiry you read, because it now contradicts the new duration. That is rule 2 working. `tests/test_warranty.py::test_the_published_block_can_be_sent_back_as_read` does exactly that.

`dates.warranty_expiry` still publishes the same column.

**Filters:**
- `?warranty_status=under_warranty|expired|none`.
- `?warranty_expires_within_days=N`, where N is 1–3650. It covers today to today + N, both inclusive, both Lagos days, and **never includes an expired warranty**.
- A bad value is a 400, never the whole register.
- `GET /meta/enums` publishes `warranty_status`.

### 1.3 · Additive, checked against the sender

**Nothing was renamed, and nothing that used to be accepted is refused.** The verification pass read Vendra's `build_asset_payload` (`vendra_network/integrations/cadra/payload.py`). It sends no warranty key and never `warranty_expiry`. Every new refusal needs a start date or a duration, and neither existed before, so no receipt Vendra sends today can meet one.

---

## 2 · Is a warranty change an event? Yes.

**Each change is an append-only `nrs.asset.event` of type `warranty_changed`: one row per field that actually changed, including the derived expiry.**

**Why.** A warranty is a contractual fact that somebody could benefit from altering. It could be lengthened after the laptop broke, so the repair becomes somebody else's bill. It could be shortened, to justify a replacement. The person holding the broken asset needs the record as it stood on the day.

**What it costs, measured rather than assumed:**
- **An event is a CHANGE, so creating an asset with a warranty writes none.** Every INT-03 receipt carrying a warranty therefore leaves an asset that can still be deleted. `test_an_asset_created_with_a_warranty_writes_no_event` creates one and deletes it.
- **Only a later edit pins the asset.** `CLAUDE.md`'s list of what pins an asset now says so.
- **The five fields are NOT chatter-tracked**, deliberately. The event is their record, and a chatter row beside it would be the same fact twice, one copy of it deletable. Tracking them would also have pulled them into the register snapshot's roll-back contract, `test_every_tracked_field_is_rolled_back`, which warranty is not part of.
- **The history shows it with words**, for example *"Warranty Duration (months): 24 → 36"*, graded `append_only`. `fidelity.events` gains a fifth entry.
  - Its sentence does not promise a message-log fallback. The fields were never tracked, so there is none, and the verification pass caught the generic sentence pointing a reader at one.

---

## 3 · What the three filter states return on real data

The count and the denominator, per tenant, measured in SQL at the Lagos date 2026-09-22 under the API's own definitions:

| Tenant | Under warranty | Expired | No warranty recorded | Expiring ≤ 90 days | Of |
|---|---|---|---|---|---|
| `cadra19` | 0 | 0 | **1,335** | 0 | 1,335 |
| `nrs19` | 0 | 0 | **11,943** | 0 | 11,943 |
| `gtb19` | 0 | 0 | **156** | 0 | 156 |
| `nrs` | 0 | 0 | **1,272** | 0 | 1,272 |
| `lasg` | 0 | 0 | **150** | 0 | 150 |
| `gtb` | 0 | 0 | **150** | 0 | 150 |
| `jaizbankplc` | 0 | 0 | **4,164** | 0 | 4,164 |
| `test19` | 16 | 3 | 3,882 | 3 | 3,901 — 3,289 of them fixtures, and every warranty on it written by this handoff's tests |

**Zero of 19,170 real assets carry a warranty, and zero of them could.** Before this handoff there was nowhere to record who honours a warranty or for how long. The expiry column was the only warranty field, and it was empty on every row.

**There is no backfill**, as the handoff says. Every existing asset truthfully reads *no warranty recorded*.

**The count is its filter, proved three ways:**
- **In the model:** the filter on each state and its negation partition the register exactly. No asset is in neither, which is how 282 assets once went missing.
- **Over the API:** every row a status filter returns publishes that status.
- **In the browser:** the dashboard's *Under warranty* tile was read, clicked, and the register it opened announced the same number. The API was asked the same question as a third witness.

**`none` means no EXPIRY is recorded.** A warrantor or certificate number may still be on the asset. The asset page shows both in that case; the first draft did not.

---

## 4 · What it must never do: checked

A warranty moves nothing about the asset:
- The model test and the API test each write an expired warranty onto a working asset, then read `state`, `condition` and `is_verified` back unchanged.
- No non-warranty event is written.
- The front end touches no pill, no `deriveStatus`, no `statusToServerFilter` and no stock count.
- The dashboard's warranty tiles sit in their own group, labelled *"About the contract, not the asset — not counted in the stock figures above"*, in neutral colours.
- The asset page uses one neutral chip for every warranty status. There is no green for covered and no red for lapsed, because those are the colours of the service pills.

**Today is a Lagos day everywhere a warranty is judged:**
- The compute, the search, `status_as_of` and the within-days filter all use `snapshot_today()`.
- The front end's `lagosToday()` uses the same fixed offset.
- `test_the_day_is_a_lagos_day` freezes 23:30 UTC and asserts a warranty that ran through that day has already expired in Lagos.

---

## 5 · The verification pass

A fresh reviewer, who wrote none of it, attacked the diff against the handoff.

| Finding | Severity | Outcome |
|---|---|---|
| A multi-asset write re-entered `write` from the top of the chain, so `myservice_workflow`'s SAP trigger ran twice per asset: two `asset.disposed` events for one disposal | **defect (latent)** | **Fixed.** `write` now hands each resolved record to `_write_recorded`, below the overrides. **Proved to fail first:** the new `test_a_disposal_beside_a_warranty_field_is_announced_ONCE_per_asset` against the old code gave `1 failed, 0 error(s) of 1 tests`, `AssertionError: 2 != 1`. |
| The asset page said *"nothing has been entered"* beside a recorded warrantor or reference, and hid both | **defect** | **Fixed.** The short box is only for a warranty with nothing on it at all. |
| The dashboard tiles were never proved by clicking | risk | **Fixed.** Spec 34 now reads a tile, clicks it and checks the register's total. |
| The history's sentence for warranty promised a message-log fallback that cannot exist | risk | **Reworded.** It still opens *"From <instant>"*, which the existing test requires, and says there is no earlier record. |
| The docs said a GET "can be sent back", which is true only unchanged | nit | **Docs corrected.** |
| Adding a basis to a bare expiry replaces the date with no refusal | nit | **Kept, and documented.** The caller has just supplied the working, and the old date survives in the event. |
| A warranty write to an empty recordset validated nothing and could raise | nit | **Fixed.** An empty set skips resolution. |
| The Odoo form showed the old expiry until save | nit | **Fixed** with a display-only `onchange`. |
| `CLAUDE.md`'s row 34 sat between 31 and 32 | nit | **Moved.** |

The reviewer also confirmed, by live read-only query:
- all 8 `test19` rows with a basis have `expiry = start + months`;
- 0 rows have a warrantor or reference with no expiry;
- the tile counts on `test19` partition the register (26 + 6 + 4,046 = 4,078 of 4,078);
- the four enum lists agree;
- there is no AI attribution in the diff.

---

## 6 · Tests, with their denominators

| Suite | Result |
|---|---|
| HTTP, `test19`, first full run | 1 failed, 1,051 passed, 8 skipped. The failure: the query-parameter guard, correctly refusing two filters with no inventory entry. Fixed, 15 of 15. |
| HTTP, `test19`, second full run | 1 failed, 1,051 passed, 8 skipped. The failure: `fidelity.events` requires every statement to open *"From "*, and my first rewording did not. Reworded; the three affected files then gave 126 of 126. |
| HTTP, `test19`, final full run | **1,052 passed, 8 skipped, 0 failed** |
| in-registry, CI's exact 11-module command, `test19`, `--workers=0` | **0 failed, 0 error(s) of 820 tests** |
| static front-end guards (`test_frontend_enums`, `test_source_guards`) | 240 passed of 240 |
| front end | `tsc --noEmit` exit 0; `BASE_PATH=/app/ npm run build` built. No front-end unit tests exist: 0 of 0. |
| browser, `test19`, first full run | 141 passed, 4 skipped, 3 failed. Two are the depreciation specs `GO-LIVE.md` §13.5.13 already records as failing on `dev`; the third was spec 34 racing its own page. |
| browser, specs 34 + 19, `--retries=0`, after the fix | 6 passed of 6 |
| browser, `test19`, final full run | **142 passed, 4 skipped, 2 failed** — the same two depreciation specs, and nothing else |

The 8 HTTP skips are the documented categories for `test19`: 2 Turnstile, 3 partition-data-absent, 1 with no `workflow.config`, 1 with no SAP asset number, and 1 for the documented `is_tagged` case.

**Two existing tests were changed, and each says why.**
- `_RECORDED_TYPES` in `tests/test_asset_events_api.py`, and its twin in `myservice_api/tests/test_asset_history.py`, each gained `warranty_changed`.
- The two tests that write *"one event of every kind"* now also write a warranty change. Without it they would be claiming a kind they no longer cover.

**Upgrade fan-out:** `-u myservice_asset_register,myservice_api` was run on all eight databases, one at a time, **before** the restart. Every run exited 0 with zero `ERROR`/`CRITICAL` lines. `ir_module_module` was then read on each database: 19.0.1.18.0 and 19.0.3.12.0 on all eight, and the four new columns present on all eight.

---

## 7 · Noticed, not fixed

- **58 `no translation language detected` warnings** in the in-registry run. None come from this handoff's code: my one instance was moved onto the model the same afternoon. They come from `asset_custody.py:32/41`, `asset_movement.py:30/39`, `access_change.py:147/156` and `asset_disposal.py:186/194`: messages built with `_()` in module-level code, which cannot find a language. They are harmless, since the text simply goes untranslated. They are listed rather than fixed because they are not warranty.
- **The front end shows `basis` exactly as the server sends it**, so the date inside it is ISO (`2026-03-12`) while the rest of the page reads *12 Mar 2026*. The server's sentence is the API's, and a client that rewrites it would be publishing a second version of the working. Say if you want the server to format it.
- **Your INT-01 question stands:** whether SAP's purchase order carries warranty terms that should arrive on the order rather than be typed at receipt.

---

## 8 · Wall-clock, and the correction share

**About 70 minutes**, from the instruction commit (11:30 Lagos) to this report (12:40). Most of that was test runs waiting on one another, because they are serialised on this machine.
- **Roughly a third of that went to corrections**: the four verification findings, including the fail-first run; the two guard catches; the browser spec's race; and the two rewordings of one sentence.
- **Every one of those was caught by a guard, a test or the reviewer, and none by reading.** That is report 32's closing line again.

**On your question at the end of handoff 33 — whether anything a person has actually hit is left:** this one came from a person, at a demonstration, and it is built. Handoff 33 is next and has not started.
