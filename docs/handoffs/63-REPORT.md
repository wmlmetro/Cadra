# Report — Handoff 63: what SAP holds, in Cadra

Branch `feat/what-sap-holds-in-cadra`, from `dev` at `0accbd6` (PR #121,
handoff 62, merged). Module versions: `myservice_asset_register`
19.0.1.31.0 (two new tables), `myservice_api` 19.0.3.34.0 (the fixture label
on both), `myservice_workflow` 19.0.3.4.0 (a migration);
`myservice_asset_depreciation` Python only.

## Needs the owner

1. **The PR merge.** The Builder's permission layer refuses `gh pr merge`.
2. **The deploy** (GO-LIVE §32.7): `deploy-dev`, then `upgrade-19` with
   `target_dbs=staging,gtb,jaizbankplc,lasg`,
   `upgrade_modules=myservice_asset_register,myservice_api,myservice_workflow,myservice_asset_depreciation`,
   `scale_down=true` — two new tables; a tenant running the code without
   them answers `503 server_misconfigured` on the new routes. Then
   `GET https://<tenant>/api/v1/meta/readiness` → `"ready": true` on each.
3. **Loading the mirror on `staging`** (§32.1): Settings → *SAP asset
   master*, as a system administrator, upload `NRS Asset (1).XLSX`. The
   Builder cannot: the cluster's sign-in is behind Turnstile and the file is
   NRS's register.
4. **Ask SAP's team for the location extract (ANLZ)** (§32.2, ruling 5):
   37,831 of 161,647 active records have no office.
5. **Tags active on two assets** (§32.4): 68 on `test19`, 15 on
   `jaizbankplc`, 1 on `nrs19` locally; the cluster's counts are printed by
   the deploy's upgrade. Resolving them is a person's choice per number.

## In plain words

SAP already holds NRS's whole fixed-asset register — 161,647 active assets.
Cadra now holds a **copy of it, kept apart from Cadra's own register**, so
Cadra can answer two things it could not before: *which SAP record is this
chair?* and *how much of SAP's register does Cadra hold?*

- **The System Administrator uploads SAP's own spreadsheet** on a new
  Settings screen. Cadra checks the column headings straight away (a missing
  one is refused, by name) and reads the rest in the background in short
  passes, because the file is 655 MB of data inside. The real October file
  took **100 seconds**; every count matched the Architect's reference
  document exactly. Uploading it again changed nothing. The file itself is
  not kept.
- **It is not Cadra's register.** Nothing from it appears in any list,
  count, report or export of assets — measured on the eleven screens that
  count assets, before and after loading 211,699 records.
- **Who can see it:** the Asset Controller, the Register Maker and Checker,
  the Auditor and the System Administrator. Not ordinary staff, not the
  Store Officer, not Vendra — Vendra's real credential was refused.
- **"Which SAP record is this?"** Give Cadra the old FIRS tag, a
  description, a class, an office or a serial and it offers up to five SAP
  records, each saying why: *old tag, unique*; *old tag, shared by 3;
  description matches*; *description and class; office unknown*. About
  three items in four end on exactly one record from their old tag, as
  report 61 predicted. Records already on Cadra's register are never offered.
- **The first real number for NRS:** **Cadra holds 0 of SAP's 161,647
  active assets.** Only 2 of Cadra's 11,959 NRS assets carry a SAP number,
  and neither is in SAP's file. But **2,445 of the others could be linked
  today with confidence** — the matcher finds exactly one SAP record for
  them by their old tag or serial — before any audit team goes into a room.
  Another 959 point at a SAP record that a second Cadra asset also points
  at: Cadra probably holds those items twice, and a person has to choose.
- **The smaller rulings:** a faded-tag number active on two assets is now
  listed for the owner and protected by the database wherever there are
  none; saving a category's depreciation policy went from about 30 seconds
  to 7 for a class of 18,000; Cadra now keeps trying a downed Vendra for 26
  hours, not 2, so a day's outage loses nothing.
- **Two things went wrong on the bench, and are now written down.** My
  unfinished code reached the shared test server before its database
  tables did, and broke `test19` for the Vendra builder for a few minutes;
  and recreating the web proxy quietly restarted Odoo without the setting
  that routes each tenant, for about a minute. Both are in
  ENVIRONMENT-FACTS.

---

## Step 0

- `git checkout dev && git pull --ff-only` (to `0accbd6`); committed
  `docs/handoffs/63-what-sap-holds-in-cadra.md` (`084cf4f`); pushed; branch
  `feat/what-sap-holds-in-cadra`.
- Handoff 62's migration state: the eight local tenants were at 62's
  versions (readiness `true` on each before any change).
- Two untracked handoff files from other cycles (`53-…`, `55-…`) were in
  the tree and left alone; `64-what-the-photo-says.md` arrived during the
  work and is left for handoff 64's Step 0.

---

## §0 · Reports 61 and 62's rulings

**Ruling 1 — `POST /tags/printed` kept.** Nothing changed.

**Ruling 2 — tags active on two assets.**
- *Per tenant*, counted by `myservice_asset_register`'s own upgrade (the
  log line is the evidence): `test19` 68 numbers (136 labels),
  `jaizbankplc` 15 (30), `nrs19` 1 (2); `cadra19`, `gtb19`, `nrs`, `lasg`,
  `gtb` 0. 84, report 61's figure.
- *The back-office filter*: Asset Register → Asset Tags → **Tags active on
  two assets** (a new search view; `active_number_shared`, searched by SQL).
  It lists exactly the labels that keep the index from being created.
- *The index*: `nrs_asset_tag_label_active_name_uniq`, `UNIQUE (name) WHERE
  state = 'active'`, created by `nrs.asset.tag.label.init` on any upgrade
  where the count reads zero — **created on the five tenants with none**;
  on the other three the upgrade logs *"1 number(s) are active on more than
  one label (2 labels), so the unique index … is NOT created. Resolve them
  in the back office (…), then upgrade myservice_asset_register on this
  database to create it."* **How the owner turns it on**: resolve the listed
  labels (which asset holds the number is a person's call — the station's
  two-person *Replace tag*), then upgrade the module on that database.
  Nothing is cleaned automatically. Proved in-registry: duplicates listed,
  index refused while they stand, created once they are resolved, a second
  active label then a `UniqueViolation`.

**Ruling 3 — a category policy save.** Measured where the time goes
(`63-evidence/category-save-timing.txt`): on `test19`'s class of 18,008,
**208 queries — not one per asset — but 162,072 calls of
`nrs.asset.write`, nine per asset**: one policy write each, four figure
assignments inside it (each a `write`), four more after; mail tracking alone
25 s of 68. Fixed: one `write` per category for the policy, and the four
derived figures (nothing computes from them, no recorder watches them,
none is tracked) stored by batched SQL for the assets whose figures CHANGED.
After: **the category-1 save, 18,197 assets, 7.1 s**; a recompute that
changes nothing writes **0 of 20,284** assets. Report 61's curl timing was
27.9–29.3 s.

**Ruling 4 — the mobile map** (`docs/integrations/mobile-ai-capture-endpoints.md`):
`/ai/config` and the label template → **64** (the offline phone needs
both); `/ai/signatures` → **64**; swap flags → **after 64** (no audit
campaign yet). The sixth status, *not yet scheduled*, is gone; every row has
a release. The rows that said "63" for devices, code blocks and the capture
now say **64** (62 renumbered the evaluation; the map had not followed). A
§7 for the mobile team describes the slice and the matcher.

**Ruling 5 — untagged records carry no office.** Built as ruled: the office
from a `FIRS/<office>/…` tag, `none` otherwise; `office_source` has room for
`location_extract`, which an export import never overwrites (proved
in-registry). The importer for SAP's location extract is not built — there
is no file yet.

**Ruling 6 — INT-05 on a reprint:** no payload change. **Ruling 7:** nothing
to build.

**Ruling 8 — the retry budget.** *Deviation:* **32 attempts, not 30.** At
the built ladder (1, 2, 4, 8, 16, 32 minutes, then hourly) 30 attempts span
**24 h 3 min** — three minutes past a day; 32 span **26 h 3 min**, which is
the "about 26 hours" the ruling names (pinned by
`TestRetryBudget.test_a_new_target_tries_for_a_day_and_more`). The
migration's line per tenant (`63-evidence/retry-budget-migration.txt`):

```
retry budget on test19: 1 of 1 target(s) moved from 8 to 32 attempts (#4852 Vendra (INT-05 asset events)); 0 customised, left alone (none)
retry budget on cadra19: 0 of 0 target(s) moved …
retry budget on nrs19: 1 of 2 target(s) moved from 8 to 32 attempts (#2 SAP (mock) — INT-06/07/09); 1 customised, left alone (#1 Vendra (INT-05 asset events): 8/60s/300s)
retry budget on gtb19 / nrs / lasg / gtb: 0 of 0 …
retry budget on jaizbankplc: 1 of 1 target(s) moved from 8 to 32 attempts (#1 Handoff 08 — second-tenant scheduler proof); 0 customised, left alone (none)
```

Re-measured on the real drain (report 62's simulation, new expectations):
**down 07:00 → 07:00: 490 of 490 delivered, the last 3,596 s after Vendra
returned** (was 490 of 490 dead); **back at noon: 0 dead, 218 late, 272 on
time** (was 107 dead); a two-day outage still dead-letters after exactly 32
attempts spanning 26 h 3 min. Rows already queued keep their budget.

---

## §1 · The SAP mirror

`nrs.sap.asset` (`myservice_asset_register/models/sap_mirror.py`), with the
fields the handoff lists: company code; asset number and sub-number (the
key, both normalised — the number stripped and upper-cased as 59 does, the
sub-number with leading zeros dropped); class; both descriptions; the old
tag as written and normalised; the office and which source filled it; the
serial (real only), its kind and a placeholder kept aside; capitalised,
first acquisition, created-in-SAP and deactivation dates; `sap_active`
(computed from the deactivation date); vendor; `in_latest_export`; the first
and last import. Read-only: the ORM refuses `create`/`write` to everyone but
the importer, and `unlink` always.

**The import is a job.** `POST /sap-assets/imports` (multipart `file`)
reads the header row in the request — a missing column refused there, by
name, nothing stored — and records an `nrs.sap.import.run`; the cron reads
the rest in ticks of ≤ 25 s of CPU. Why ticks (DECISIONS): a full pass is
~52 s of CPU and an Odoo cron worker is killed at `limit_time_cpu` (60 s
here); the employee import's thread would get the whole HTTP worker killed.
The reader (`sap_export_reader.py`) streams the 655 MB sheet through lxml's
pull parser, decodes only the 13 wanted columns, clears each row, and
resumes at a row boundary by skipping to the offset and feeding the sheet's
own opening first. Proved: on the real file, a read resumed twice is
row-for-row the single pass (211,699 rows); in-registry, a read resumed at
every one of >10 boundaries.

Each run records who, when, the file's name and size, rows read, created,
updated, unchanged, refused **with the reasons counted** (never the rows),
marked not in the latest export, duration, CPU, passes and peak memory. The
upload is deleted when the run ends, done or failed — the row, and its bytes
from the filestore at once (proved: the stored file is gone when the run
reads `done`).

**Who reads it**: `sap_mirror:read` — Asset Controller, Register Maker and
Checker, Auditor (`GROUP_SCOPES`; a credential granted it is put in the
Auditor group, `evidence:read`'s shape) and `admin`. **Who imports**:
`settings:write` held by a system administrator — the route also requires
`admin` and refuses an Asset Manager in words before reading the body.

**The link — computed, not stored**, and why (DECISIONS): `sap_asset_number`
has many writers; a stored link refreshed "on every SAP-number write" goes
stale on the forgotten one. A receipt candidate whose maker typed the number
counts as linked. First built as a plain join, which Postgres planned as a
hash of the whole mirror (it estimated 6,999 assets with a SAP number on
`nrs19`, which has 2): **370 ms a matcher call**. Now an index probe per
candidate (`LINKED_EXISTS`) and a `MATERIALIZED`, asset-driven form for
whole-table counts (`LINKED_CTE`): **1.1 ms** a tag lookup. The import
`ANALYZE`s the table when it ends.

**Routes** (reference §16): `POST/GET /sap-assets/imports`,
`GET /sap-assets/imports/<id>`, `GET /sap-assets`, `GET /sap-assets/match`,
`GET /sap-assets/<id>`, `GET /assets/<id>/sap-record`,
`GET /reports/sap-coverage`. **Screens**: Settings → *SAP asset master*
(drawn for `admin`), Reports → *SAP Coverage* (`sap_mirror:read`).

## §2 · The matcher

`GET /sap-assets/match` with any of `old_tag`, `description`, `class`,
`office`, `serial` (an office alone is refused: it matches everything in
it). Up to five active, unlinked records, ranked as §2 says; each says why
(`reason`, `reason_code`); records already linked are excluded and counted
(*"3 more already on Cadra's register"*). **One addition, additive:**
`serial`, because §6 counts confident links "by a unique old tag or an
exact serial"; tried only when no active record carries the tag, a
placeholder never matched (the answer says so). Description matching:
whole-word, case-insensitive, both columns; no fuzzy library.

Timing on `nrs19`: an old-tag lookup **1.1 ms**; a nationwide description
search **190 ms** (a scan of the class — 80,370 furniture records).

**The slice for offline phones** (`63-evidence/slice-size-nrs19.txt`): the
largest office's active furniture is **2,712 rows, 1,601,465 bytes (1.5 MB)
over the wire in 2 pages, 1.0 s**. For scale, the records with no office —
which no per-office slice contains (ruling 5) — are 18,910 furniture rows,
10.3 MB.

## §3 · The first reconciliation

`GET /reports/sap-coverage`, by class and by office, every count with its
definition in the response; Cadra's side by the SAP class of each asset's
category; by office, Cadra's columns are `null` (Cadra's locations carry no
SAP office code) and say so. On the Reports page for `sap_mirror:read`.

## §4 · What did not change

- **The register-filter probe, with the mirror loaded** — handoff 57's
  eleven routes on `nrs19`, before and after importing 211,699 records
  (`63-evidence/register-filter-probe-nrs19.txt`): **all eleven
  unchanged**, `GET /sap-assets` 0 → 211,699 as the witness. Also driven on
  `test19` by `test_the_register_does_not_move_when_the_mirror_does`: an
  imported record's number and words are nowhere on the register,
  candidates included.
- No gate, batch or event of 57–62 was touched (no file of
  `asset_gates.py`, `v1_gates.py`, the event model or the INT-05b code is
  in the diff).
- **No row of the export entered the repository.** Tests and the browser
  spec invent records in the export's shapes through one generator
  (`myservice_asset_register/tests/sap_export_shapes.py`); evidence prints
  counts, masks office codes and describes examples by shape. The
  verification pass found one example number I had believed invented that
  IS in SAP's October export; replaced by one checked absent, and the
  branch's history rewritten before the first push so the number is in no
  commit.

---

## Verification

### 5.1 The suites — gates on and gates off, `test19`

Run in CI's order — the HTTP suite, then each module's in-registry suite
(`--workers=0`), then the browser suite — once with the receipt switch ON
and once OFF, the switch turned through the API as the administrator and put
back ON at the end (`63-evidence/suite-results.txt`):

| Suite | Gates ON | Gates OFF |
|---|---|---|
| HTTP (`pytest tests/`) | 1,486 passed, **5 failed**, 7 skipped — **of 1,498** | **1,491 passed, 0 failed, 7 skipped — of 1,498** |
| `myservice_api` | **4 failed**, 0 errors of **509** | 0 failed, 0 errors of **509** |
| `myservice_asset_register` | 0 failed, 0 errors of **503** | 0 failed, 0 errors of **503** |
| `myservice_workflow` | **1 failed**, 0 errors of **119** | 0 failed, 0 errors of **119** |
| `myservice_barcode_station` | 0 failed, 0 errors of **20** | 0 failed, 0 errors of **20** |
| `myservice_asset_depreciation` | 0 failed, 0 errors of **16** | 0 failed, 0 errors of **16** |
| browser (Playwright) | 263 passed, **3 failed**, 12 skipped — **of 278** | **247 passed, 0 failed, 31 skipped — of 278** |

0 `CRITICAL` in every module run. **The same test set both ways** — the
denominators match. The gates-ON run went first, and every failure in it was
fixed or explained before the gates-OFF run, which is green throughout; the
gates-ON failures were then **rerun on the final code, gates ON: 5 of 5
HTTP, 0 failed of 37 in-registry, spec 63 3 of 3.**

What the gates-ON failures were:

- **Mine, pins meeting the new surface (fixed):** the sidebar's pinned 33
  items (now 35); the Auditor's pinned scope set (now with
  `sap_mirror:read`, in two tests); the published-names census, which
  requires every new body route and serializer classified (the import route
  and both serializers added); a dead letter's re-send budget pinned at
  `1 + 8` (now `1 +` the target's 32).
- **Mine, spec 63 (fixed):** it signed in through the page while the suite's
  stored administrator session was still in the browser — the other persona
  specs start signed out; now so does this one.
- **Not mine — a day boundary, four tests (`[open]`, GO-LIVE §32.8):** the
  four tests that read today's configuration-change report ran between
  **00:00 and 01:00 Lagos** (the gates-ON run crossed midnight). They ask
  for `from = to = <Lagos date>`, and `ir.config_parameter.configuration_change_report`
  bounds its days in **UTC**, so in that hour a change just made falls on
  the previous UTC day and is not in "today's" report. All four passed in
  the gates-OFF run (01:10–01:22 Lagos) and in the rerun. It is the same
  shape as handoff 37's one-hour-a-night defect: the register's day is a
  Lagos day everywhere else.

**The skip count** (HTTP, both ways): **7** — 2 Turnstile, 2
partition-data-absent (`closed`, `is_staff_bus`), 1 no `workflow.config`,
1 the documented `is_tagged` `null`, 1 the untagged-serial lookup. It was 9
in CLAUDE.md's last count; the `is_verified` partition and the SAP-asset-number
skip have data on `test19` now. Browser: 12 ON / 31 OFF, as in report 61.

### 5.2 The import of the real export on `nrs19`

From `~/Downloads/NRS Asset (1).XLSX`, uploaded through the API as the
tenant's administrator (`/auth/login`; `nrs19` has no admin API credential):

| | Run 1 | Run 2 (same file) |
|---|---|---|
| upload | 74,664,054 bytes, `202` in 5.1 s | same |
| state | `done` | `done` |
| rows read | 211,699 | 211,699 |
| created / updated / unchanged | **211,699 / 0 / 0** | **0 / 0 / 211,699** |
| refused | 0 | 0 |
| marked not in the latest export | 0 | 0 |
| duration (first pass to the end) | **100 s** | 85 s |
| CPU / passes | 74.8 s / 3 | 69.0 s / 3 |
| peak memory (the cron worker's `ru_maxrss`) | **296 MB** | 321 MB |
| file kept | no | no |

The newest `write_date` in the mirror did not move on run 2
(`2026-10-18 21:47:14` before and after).

**Against the reference doc**: 211,699 records; **161,647 active**; 50,052
retired; 53 with a sub-number (211,694 distinct numbers — the five main
numbers that appear twice); 131,724 active records with an old tag; the
class table exactly:

| class | total | active |
|---|---|---|
| 1000 | 2,809 | 2,237 |
| 2000 | 95,362 | 80,370 |
| 3000 | 62,230 | 45,330 |
| 3500 | 59 | 59 |
| 4000 | 34,721 | 24,978 |
| 6000 | 91 | 90 |
| 7000 | 15,289 | 7,848 |
| 8000 | 764 | 361 |
| 9000 | 16 | 16 |
| 9300 | 358 | 358 |

Serials (active): no serial 81,519 (the doc's figure); placeholder **33,092**
and real 47,036 against the doc's 33,096 and 47,032 — four records apart.
Cadra classifies by the tenant's placeholder list (handoff 59), and 33,092
is exactly what handoff 59 measured with that list; the doc's own list
counted four more. Not a reading error.

**A header removed**: a scratch copy of the real file with *Inventory
number* renamed (made in the container's `/tmp`, deleted after) → `400
validation_failed` in 2.7 s: *"The file has no "Inventory number" column, so
it cannot be imported. Columns are found by their header in the first row;
export SAP's asset master with it included. Nothing was imported."*,
`details.missing: ["Inventory number"]`; no run recorded (2 before, 2
after).

### 5.3 The matcher — report 61 §12's table, from the matcher

`63-evidence/matcher_table.py` puts every active furniture and office-equipment
record to the matcher as if it were the item found (219 s;
`63-evidence/matcher-table-nrs19.txt`):

| | Furniture (2000) | Office equipment (4000) | 61 §12 (the script) |
|---|---|---|---|
| active records | 80,370 | 24,978 | same |
| has an old tag | 65,660 (81.7%) | 20,736 (83.0%) | same |
| tag unique (→ `old tag, unique`) | 52,604 of 65,660 (80.1%) | 14,923 of 20,736 (72.0%) | 52,795 (80.4%) / 14,998 (72.3%) |
| tag follows `FIRS/<office>/…` | 61,460 (93.6%) | 19,062 (91.9%) | 61,427 / 19,055 |
| a shared tag made unique by the office | 0 of 7,570 shared tags | 0 of 3,622 | 0 |
| shared tag: candidates by tag + description | mean 8.50, median 1, max 200; one left for 9,408 of 13,056 (72.1%) | mean 14.89, median 1, max 160; one for 3,505 of 5,813 (60.3%) | 8.55/1/200, 75.1% · 15.02/1/160, 64.4% |
| shared tag: candidates by office + description | mean 100.6, median 48, max 600 | mean 61.3, median 24, max 475 | 92.2/41/600 · 58.8/21/443 |
| no tag: candidates by description, nationwide | 14,710: mean 3,211, median 775 | 4,242: mean 283, median 118 | 727/373 · 195/66 |
| **ends on one record by tag (+ description)** | **62,012 (77.2%)** | **18,428 (73.8%)** | 77.7% / 74.8% |

**Where it differs and why.** The tag rows differ by a fraction of a point
because the matcher normalises harder (`\` → `/`, inner spaces removed — 61
measured that form as "< 0.4 points"). The description rows differ more:
61 compared descriptions for EQUALITY; the matcher compares WORDS, so every
record whose description contains all the item's words ties at the top
(the shortest is ranked first). That is what the operator really faces with
an untagged chair: a median of 775 nationwide records that say "chair". A
fuzzy library would widen that pool, not narrow it; none was added.

**Five worked examples**, by shape (`63-evidence/worked-examples-nrs19.txt`):

1. *Old tag, unique* — a tag shaped `XXXX/nnnn`: pool 1, `old_tag_unique`.
2. *Shared tag, settled by the description* — a tag shared by 3 records,
   the description given: #1 *"old tag, shared by 3; description matches"*,
   #2 *"…matches 2 of 3 words"*, #3 *"…does not match"*; tied at top 1.
3. *No record carries the tag; a unique serial* — an invented tag that
   exists nowhere, a real serial shaped `nXXXnnnnnn`: `serial_unique`,
   with the note that no record carries the tag.
4. *Tag not in SAP, office inside it* — a `FIRS/XXXX/nnnnnnnn` tag no record
   has: the office is read from the tag (`office_from: tag`) and the
   description searched within it: `description; office XXXX`, pool 1.
5. *Untagged, nationwide* — a four-word description, class 2000, no office:
   pool 16,705, tied at the top 70, five results *"description and class;
   office unknown"* — the operator chooses.

### 5.4 The coverage report on `nrs19` — every row

`63-evidence/coverage-nrs19.txt` (office codes masked):

> *Cadra holds 0 of SAP's 161647 active assets (0.0%). Of the 11957 Cadra
> assets on the register with no SAP asset number, the matcher ranks 3404
> first by a unique old tag or serial (3031 by tag, 373 by serial); 959 of
> those point at a SAP record another Cadra asset also points at, which
> leaves 2445 that could be linked with confidence today.*

| class | SAP active | linked | not linked | SAP retired | Cadra assets | with SAP no. | SAP no. not in SAP | no SAP no. |
|---|---|---|---|---|---|---|---|---|
| 1000 | 2,237 | 0 | 2,237 | 572 | 0 | 0 | 0 | 0 |
| 2000 | 80,370 | 0 | 80,370 | 14,992 | 0 | 0 | 0 | 0 |
| 3000 | 45,330 | 0 | 45,330 | 16,900 | 0 | 0 | 0 | 0 |
| 3100 | 0 | 0 | 0 | 0 | 71 | 2 | 2 | 69 |
| 3500 | 59 | 0 | 59 | 0 | 0 | 0 | 0 | 0 |
| 4000 | 24,978 | 0 | 24,978 | 9,743 | 0 | 0 | 0 | 0 |
| 6000 | 90 | 0 | 90 | 1 | 0 | 0 | 0 | 0 |
| 7000 | 7,848 | 0 | 7,848 | 7,441 | 0 | 0 | 0 | 0 |
| 8000 | 361 | 0 | 361 | 403 | 0 | 0 | 0 | 0 |
| 9000 | 16 | 0 | 16 | 0 | 0 | 0 | 0 | 0 |
| 9300 | 358 | 0 | 358 | 0 | 0 | 0 | 0 | 0 |
| no SAP class | 0 | 0 | 0 | 0 | 11,888 | 0 | 0 | 11,888 |
| **all** | **161,647** | **0** | **161,647** | **50,052** | **11,959** | **2** | **2** | **11,957** |

By office: 901 rows — 900 offices (active records per office: mean 137.6,
median 19, max 8,046) and one row of **37,831 active records with no
office**; 0 linked on every one. The report answers in 2.2 s.

### 5.5 Scopes

- **Served** (`tests/test_sap_mirror.py::test_the_readers_are_served`,
  `test19`, real sign-in): the Asset Controller, the Register Maker, the
  Register Checker, the Auditor and the System Administrator — the slice,
  the runs, the matcher and the coverage report, `200` each.
- **Refused** (`…::test_the_store_officer_and_an_asset_user_are_refused`):
  the Store Officer and the tagger (an Asset User), `403` naming
  `sap_mirror:read`, on all four.
- **Vendra's credential**: in-registry with Vendra's exact scopes
  (`TestSapMirrorScope`), and **live with Vendra's real credential on
  `nrs19`** (`63-evidence/vendra-refused-nrs19.txt`): scopes `assets:read
  assets:write locations:read candidates:read`, `403 Missing required
  scope(s): sap_mirror:read` on all four reads; the Tag-Issuing Unit's
  credential the same.
- **The import**: the Asset Manager (holds `settings:write`) `403` *"Importing
  SAP's asset master is the System Administrator's act…"*; the Store
  Officer `403`; nothing recorded.

### 5.6 The register-filter probe

§4 above: all eleven unchanged on `nrs19` with 211,699 records loaded.

### 5.7 §0

The duplicate-tag counts, the category-save timing, the retry-budget lines
and the map's placements: §0 above.

### 5.8 Fan-out, readiness, deploy

Every local tenant was upgraded in the same sitting as each schema change
(`myservice_asset_register` ×8, `myservice_api` ×8, `myservice_workflow` +
`myservice_asset_depreciation` ×8); `GET /meta/readiness` → `ready: true` on
all eight after each. The owner's deploy steps are in Needs the owner and
GO-LIVE §32.7.

---

## §6 · The question for the report

**From the coverage report on `nrs19`: Cadra holds 0 of SAP's 161,647 active
assets.** 2 of `nrs19`'s 11,959 assets carry a SAP number, both in a
category mapped to `3100` (not a SAP class), and neither number is in SAP's
export.

**Of the 11,957 Cadra assets with no SAP number, the matcher ranks 3,404
first by a unique old tag (3,031, from the asset's legacy asset code) or an
exact unique serial (373)**, onto 2,894 SAP records. **959 of those 3,404
point at a SAP record another Cadra asset also points at** (449 records) —
Cadra holds the item twice, or one of the pair is the wrong asset, and a
person has to choose — **which leaves 2,445 that a reconciliation could link
with confidence before any audit team goes into a room.** Cross-checked: the
report's single query and 11,957 separate matcher calls give the same five
numbers (`matcher-table-nrs19.txt`, last lines).

---

## The verification pass (a fresh agent, not an author)

It read the diff against the handoff and CLAUDE.md, ran the static guards
(283 of 283) and re-derived counts on `nrs19`. **Three confirmed defects,
all fixed** (`f21501c`):

1. **A recompute still moved `write_date` on most assets** — the engine's
   `None` end date against the cache's `False` (and unrounded money against
   rounded columns) made 19,453 of 22,042 `test19` assets look changed
   every time; my test used only assets with a schedule. Now 0 of 20,284;
   the test has a no-schedule, a no-cost and an odd-cost asset.
2. **The 200 MB limit was unreachable**: Odoo caps a request at 128 MiB
   before the route runs, with werkzeug's HTML 413. The route now raises
   its own ceiling (`cadra_route(max_content_length=…)`) and refuses above
   **150 MB** in words — below the proxies' 200 MB, so the words are
   reachable.
3. **An "invented" number was real** — an 11-digit example in a docstring
   and a test is a record in SAP's export. Replaced by one checked absent;
   the unpushed branch rewritten so no commit carries it.

Also taken from its plausible list: the duplicate-tag filter now lists
exactly what blocks the index; the no-target retry fallback is 32; the
migration's log survives a NULL; a failed tick does not roll back the test
runner's cursor; a broken zip is a `400` in words, not a `500`; the upload's
bytes leave the filestore when the run ends (Odoo's collection run at once —
until then they stayed up to a day). **Left, and said:** a refused row is
not "seen", so a record the mirror holds whose new row was refused is marked
not in the latest export (reference §16.1 says so; a re-import of a fixed
file restores it); an import has no floor against a truncated file marking
most of the mirror absent (records are kept; re-import restores); an asset
with no company code links to a record of any company code (one exists);
a concurrent duplicate tag mint is the envelope's `409` *Unique constraint
violation*, not a sentence of its own.

---

## Deviations, with why

- **32 attempts, not 30** (ruling 8) — arithmetic above.
- **A `serial` input on the matcher** (§2) — §6 asks for exact-serial
  confidence; additive.
- **A file refused at the door is not a run** (§1 "each run is recorded"):
  it imported nothing; the 400 says so and names the column.
- **The office-less records are a filter value** (`office=none`), so the
  phone can page them — the handoff's slice is per office, and 37,831 active
  records have none.
- **The proxy's upload limit raised** (`config/nginx.dev.conf`, 50m → 200m,
  the cluster's figure) — the October file is 75 MB.
- **The mirror's key ignores the company code** (as ruled); the link
  compares it only when the asset has one.

## For the Architect

1. **The 959 contested assets** (449 SAP records) are a data finding about
   Cadra's own NRS register: two Cadra assets carrying the same old tag or
   serial. Whether they are duplicates is NRS's question; the audit capture
   (64) will meet them.
2. **The untagged search is wide** — a median of 775 nationwide candidates
   for an untagged chair. Until SAP's location extract gives every record an
   office, the matcher can rank an untagged item but cannot pick it.
3. **The configuration-change report's day is a UTC day** (GO-LIVE §32.8):
   from 00:00 to 01:00 Lagos a change made now is not in "today's" report.
   Four tests failed on it this run. Not touched here — it is a published
   report's period semantics — but it should be a Lagos day like every other
   date the register publishes.
4. **A truncated export marks the rest absent.** Should an import refuse to
   mark more than, say, 5% of the mirror absent without a confirmation?
   Not built.
5. **Where Cadra keeps an old FIRS tag**: `nrs.asset.legacy_asset_code` —
   FIRS-shaped on 6,077 of 11,959 `nrs19` assets (7,694 carry a legacy
   code at all). That is the field §6 matched on; no other column on
   `nrs19` holds a FIRS-shaped value (measured over every text column of
   `nrs_asset`). The audit capture (64) should read the same field.

## The standing sentence check

Every new refusal and notice says what happened and what to do, in words:

| Where | Sentence |
|---|---|
| Import, a column missing | *"The file has no "Inventory number" column, so it cannot be imported. Columns are found by their header in the first row; export SAP's asset master with it included. Nothing was imported."* |
| Import, not a workbook | *"This file is not an .XLSX workbook (it is not a zip archive). Upload the export as SAP produced it."* |
| Import, a broken workbook | *"This file cannot be read as SAP's .XLSX export (XMLSyntaxError). Upload the export as SAP produced it. Nothing was imported."* |
| Import, not an administrator | *"Importing SAP's asset master is the System Administrator's act. This account holds `settings:write` but is not a system administrator (the token carries no `admin`). Nothing was imported."* |
| Import, one at a time | *"Import 2 (NRS Asset.XLSX, uploaded by Administrator) is still running. One import runs at a time; upload this file when it has finished. Nothing was imported."* |
| Import, too big | *"The file is N bytes; an export import takes up to 157286400. Nothing was imported."* |
| Import, empty | *"The file is empty. Nothing was imported."* |
| A refused row (counted) | *no asset number* · *an unreadable date in "Capitalized on"* · *the same asset number and sub-number twice in this file* |
| A run that failed | *"The uploaded file is no longer stored, so this run cannot continue. Upload the export again."* |
| Matcher, nothing said | *"Say something about the item: an `old_tag`, a `description`, a `class` or a `serial` (an `office` alone matches every record in it)."* |
| Matcher, notes | *"No active SAP record carries the old tag …"* · *"The serial XXXX is a placeholder, not a serial; it was not matched."* · *"3 more already on Cadra's register"* |
| Asset → SAP record | *"Not linked: this asset carries no SAP asset number. GET /sap-assets/match proposes candidates."* · *"Not linked: this asset carries SAP asset number N and the SAP mirror holds no record of it."* |
| The mirror, written to | *"The SAP mirror is SAP's register, read-only in Cadra. A record changes only when a newer export of SAP's asset master is imported."* · *"A record of the SAP mirror is never deleted…"* |
| Coverage, empty mirror | *"No export of SAP's asset master has been imported on this tenant; every SAP count is zero because the mirror is empty, not because Cadra holds nothing."* |
| Upgrade log, tags | *"Tag numbers on nrs19: 1 number(s) are active on more than one label (2 labels), so the unique index … is NOT created. Resolve them in the back office (Asset Tags → filter "Tags active on two assets"), then upgrade myservice_asset_register on this database to create it."* |

## Commits

| Commit | What |
|---|---|
| `084cf4f` (on `dev`) | Step 0: the handoff |
| `aa51d54` | the mirror, the reader, the import job, the matcher, coverage, the routes, the screens, §0 (tags, category save, retry budget), the tests |
| `b1d62ae` | the endpoint reference §16, CHANGELOG, DECISIONS, GO-LIVE §32, STATUS, ENVIRONMENT-FACTS, DEPLOYMENT, the mobile map, CLAUDE.md, evidence |
| `f21501c` | the verification pass's fixes |
| `b050d7f` | the pins the gates-on run found meeting the new surface, and spec 63 signed out |
| (this commit) | this report, its evidence, GO-LIVE §32.8, CLAUDE.md's skip count |
