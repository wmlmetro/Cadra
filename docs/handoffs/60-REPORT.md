# Report — Handoff 60: seventy a day

Branch `feat/seventy-a-day`, from `dev` at `d73448f` (PR #118 merged).
Step 0: the Architect's two edits (handoff 59 and the SAP asset-master
reference, shapes instead of NRS identifiers — ruling 1) committed on `dev`
as their own docs commit (`19bf956`), then the instruction file (`5a25ee8`),
pushed, then the branch. No history rewrite, as ruled.

## Needs the owner

1. **The PR merge.** The Builder's permission layer refuses `gh pr merge`.
   The merge is also your authorisation of §1.1, Vendra's `candidates:read`
   (granted by migration, never by hand).
2. **The deploy.** Run `deploy-dev`, then `upgrade-19` on all four tenants
   (`staging, gtb, jaizbankplc, lasg`) with modules
   `myservice_asset_register,myservice_api`, `scale_down=true`. It must run
   before any traffic: there is a new column (`nrs_asset.register_state_since`)
   and a renamed one (`nrs_asset.reference` → `record_reference`). Then
   `https://<tenant>/api/v1/meta/readiness` must say `"ready": true`.
3. **The deployed check on `staging`** (Turnstile — yours, in the browser),
   after the deploy:
   1. Without signing in: `https://staging.app.cadra.ng/api/v1/meta/readiness`
      → `{"data": {"ready": true, …}}`.
   2. Sign in as the **IAD officer** persona. The sidebar's *Candidates*
      carries a number. Open it: the *Waiting on me* tab is selected, and the
      list is oldest first with the age in bold.
   3. Type a GRN into the search box at the top; tick its units (click the
      GRN in a row to select the whole receipt); *Verify selected* →
      *All four* → attach one file → *Verify N*. The results say *N of N
      verified*. The badge drops by N.
   4. Sign in as the **IAD approver**: the badge shows those N. *Evidence*
      on a row shows the file and the four checks. Open the unit: the asset
      page shows the same evidence, and *Back to Candidates* returns to the
      same search.
4. **Your question in §6 of the handoff** — `docs/seed/`'s NRS rows — is
   yours; nothing here touches it.
5. **One thing to know:** `test19` now sends INT-05 to the local Vendra
   bench (§1.3), so every affix the test suites make reaches that bench and
   is recorded there as an unmatched delivery. It is harmless; it is also
   noise in Vendra's message log. Say if you would rather the target be
   switched off between demonstrations.

## In plain words

Report 59 counted what it would take to put 70 received items a day
through the seven approval steps, and found three places where people would
drown in clicks. This handoff fixes those three without weakening any rule.

- **Everyone is now told.** Each person sees a number beside *Candidates*:
  how many units are waiting on *them*, counting only units they are allowed
  to act on. The list now shows the longest-waiting unit first, and the
  search box works (type a delivery's GRN to see only that delivery).
- **Internal Audit verifies a delivery at once, not unit by unit.** The
  officer ticks the units of one delivery, ticks *all four* checks once, and
  attaches the delivery note once. Behind the scenes, Cadra still records a
  separate verification for every unit, exactly as if each had been done
  alone. If the officer is not allowed to verify some of them (because they
  received them), those few are refused with the usual sentence and the
  rest go through. **The IAD approver can now see the evidence** before
  approving — until now they approved blind — and can approve a delivery
  at once too.
- **The tagger's station clears itself.** After each confirmation the scan
  box empties and is ready for the next scan. A new *Labels to fix* panel
  lists the units waiting for labels, oldest first, and can be filtered to
  one delivery, so their labels print in one go.
- **The Register Maker pastes instead of typing.** The cost comes from the
  unit. Cost centre and date are remembered from the last submission. A
  list of *asset code, SAP code* lines can be pasted, previewed line by line
  (which are fine, which would be refused and why), and then submitted. The
  Checker sees SAP code, cost, cost centre and class on each row and
  approves a batch.
- **Three fixes Vendra asked for.** Vendra can now see units that are still
  in the approval chain. A chair created with the approval chain switched
  off now says it is identified by tag and attributes, not "unknown". And
  the test tenant now sends tag events to Vendra; it had nowhere to send
  them.
- **A rename the Architect ruled**: the field handoff 59 called `reference`
  is now `record_reference`, before any other system started using it.

**What did not change:** one person still may not do two different steps on
the same unit; every unit still gets its own permanent record of every step.
With the approval chain switched off, nothing a person sees changes except
the number beside *Candidates*, which reads zero on a tenant with nothing in
the chain.

**What went wrong on the way, plainly:** I added the rename to a database
upgrade step that the test database had already run, so on that one test
database the old values were dropped instead of moved: 23 values, all
belonging to test records made by the previous handoff's tests. No real
tenant was affected — every other database had not yet run the step and
carried its values over (none of them held any). Details under *The rename*.

## §1 · Three Cadra fixes from Vendra

### 1.1 Vendra sees the candidates

`scripts/bootstrap.py` now gives the Vendra client
`assets:read assets:write candidates:read` (`VENDRA_CLIENT_SCOPES`). The
`myservice_api` 19.0.3.32.0 migration adds the scope to every existing client
named `Vendra (INT-03)` or with client id `vendra` (`=ilike`, as 19.0.3.3.0
does), archived clients included, and prints one line per tenant
(`60-evidence/fanout.txt`):

```
handoff 60: Vendra clients on test19 — 1 of 1 given candidates:read (1 of 3 API clients are Vendra's)
handoff 60: Vendra clients on nrs19 — 1 of 1 given candidates:read (1 of 4 API clients are Vendra's)
handoff 60: Vendra clients on boot44 — 1 of 1 given candidates:read (1 of 4 API clients are Vendra's)
handoff 60: Vendra clients on cadra19 — 0 of 0 given candidates:read (0 of 1 API clients are Vendra's)
… gtb19 0 of 0 (of 1), nrs 0 of 0 (of 2), lasg 0 of 0 (of 2), gtb 0 of 0 (of 2), jaizbankplc 0 of 0 (of 3)
```

Three things the grant does that are worth knowing:
- **It adds no group.** `candidates:read` maps to Asset User, which
  `assets:read` already grants.
- **The write goes through the ORM.** Rule 7's re-sync therefore moved the
  `nrs19` and `boot44` Vendra users off the Asset Manager group they still
  held from before handoff 47, onto Asset Officer, which is what
  `assets:write` grants today.
- **Vendra must call `/auth/token` again.** A client's refresh family keeps
  the scopes it was issued with.

`nrs19`'s client also holds a hand-added `locations:read`. The migration
keeps it. A future bootstrap run on `nrs19` would still strip it, as it
would have before this handoff; that is recorded and not changed.

**Driven with Vendra's own client and its own credential**, in the bench
console (`60-evidence/vendra-fixes.txt`):

```
nrs19 (Vendra's paired tenant):  GET /assets?register_state=any&limit=1 → 200, total_estimate 11959
test19 (Vendra's saved test19 config, loaded in memory, bench files untouched):
  GET /assets?register_state=any&q=MAT-PRE-2026-00640 → 200, 2 units, both 'captured'
```

Report 55 recorded both of these as `403 required_scopes: candidates:read`.

### 1.2 A new asset carries its class's mode, with the gates off too

The cause: `identification_mode` was stamped only by
`_check_receipt_identity`, which runs only for a gated receipt (`create`
with `register_state = 'captured'`). With the switch off, nothing stamped
it. Asset 12016 on `nrs19` was a chair of a `tag_id` class created that way.

The fix: `create` now stamps `category.identification_mode or 'serial'`
whenever nothing else did. The mode is **stamped, not checked**: none of
the receipt rules applies, so a gates-off receipt is refused nothing new.
This is not a computed field, because AD-31 fixes the mode at receipt and a
recompute would rewrite it when a class changes. **Existing records keep
what they had.**

The fan-out measured what records have today:

| Tenant | Assets with no mode | Of |
|---|---|---|
| `nrs19` | 11,959 | 11,959 |
| `jaizbankplc` | 4,164 | 4,164 |
| `cadra19` | 1,335 | 1,335 |
| `nrs` | 1,272 | 1,272 |
| `boot44` | 231 | 231 |
| `gtb19` | 156 | 156 |
| `gtb` | 150 | 150 |
| `lasg` | 150 | 150 |
| `test19` | 16,474 | 17,903 |

All of these were created with the gates off before 60.

Two consequences come from the mode itself, and both are announced in the
CHANGELOG:
- A new `tag_id` unit is affixed with the attributes tick. The app already
  sends it; an external caller that omits it now gets a 400.
- A new `record_only` unit is minted no label at creation. Before this
  change, creating one failed outright, because `_generate_tag` refuses
  such a unit.

The verification pass found a follow-on: with the gates off, such a unit
would then never send its asset master to SAP, because that send is
triggered by a label being affixed. It now sends the master at creation
(`NRSAssetGatesSAP.create`), with an in-registry test.

The tests:
- **HTTP**: a chair created with the switch off reads `tag_id`; a unit of a
  serial class reads `serial`.
- **In-registry**: `tag_id`, `serial`, and `record_only` with no label and
  exactly one INT-06 master queued.

Two handoff-58 tests that pinned the old `null` now pin the stamped mode.

### 1.3 INT-05 from `test19` — configuration, fixed

`test19` had **no `workflow.config` row at all**. Every affix there logged
*"no asset-event target configured on this database; asset.tag.affixed …
not queued"* and wrote no dispatch row. `nrs19` has a target and had
delivered 29 events, all acknowledged.

`test19` now has the same target:
- address: `http://vendra.network:8080`;
- Vendra's INT-05 endpoint;
- a bearer key.

It was created through the ORM, with the key copied from `nrs19`'s row
inside the script. The key was never printed. I compared it by hash: it is
the one token Vendra's bench expects in all three of its saved site configs.

Measured afterwards (`60-evidence/vendra-fixes.txt`):

```
Cadra, test19:  asset.tag.affixed | acknowledged | 109   (06:53–07:39 UTC, every one HTTP 202)
Vendra:         INT-05 | Inbound | Dead | 109             (Lagos time, the same window)
                TagUnmatchedError: INT-05 callback names no unit this Vendra holds … The delivery was accepted and nothing was changed.
```

**It arrives.** All 109 deliveries Cadra sent are in Vendra's own log. They
are "unmatched" because they are `test19`'s test fixtures, not units of a
Vendra receipt; for those, that is the right answer.

I did **not** affix one of Vendra's own `test19` chairs (receipt
MAT-PRE-2026-00640, still `captured`) to see a matched delivery. Walking it
through the gates would change state that Vendra's next session expects.
That drive is Vendra's.

Note (also in *Needs the owner*): INT-05 sends every affix, not only
Vendra's units. So every affix the test suites make on `test19` now reaches
the bench.

## §2 · The three bottlenecks, relieved — all four parts built, in order

Nothing stopped short: §2a, §2b, §2c and §2d are each built in full.

**The rule held in the code's shape.** Each batch route calls
`nrs.asset._fire_gate` once per unit:
- each unit in its own savepoint, all of them inside one outer savepoint;
- with the payload the single route builds;
- refused through `utils.gate_refusal_parts`, the function the single
  routes' envelope is now built from.

So a unit refused inside a batch carries the status, code and sentence it
would have had alone. The HTTP test fires a barred unit alone and compares
the two sentences character for character.

A batch never writes one event for many units, and one refused unit never
rolls back the others.

### 2a · Told, and oldest first

- **`GET /api/v1/candidates?waiting_on_me=true`** lists the units waiting on
  an act the caller may do. They must hold the act's scope, and the
  no-two-gates rule must not bar them. It is computed in
  `nrs.asset._waiting_on_me_domain`, from the `WAITING_ACT` table, which an
  in-registry test pins against `TRANSITIONS`.
- **The sidebar badge** is that list's `total_estimate` at `limit=1`, the
  approvals badge's cheap count. Its query key `candidates-badge` is kept
  out of the persisted cache.
- **Oldest first:** `sort=oldest` orders by a new stored, indexed
  `register_state_since`, which `create` and `_gate_move` set. `paginate`
  gained a keyset that walks by value, then id. `sort=newest` stays the
  default, so the published order is unchanged; the app asks for `oldest`.
- **Search:** the existing `?q=` search (which matches the GRN) is turned on
  in the app.
- **Barred units:** *Waiting on me* is the first tab. A unit the person is
  barred from stays findable under the plain gate tab, with its refusal
  sentence.

### 2b · IAD verification

- **`POST /api/v1/candidates/gates/verify`** takes one checklist and one
  evidence set for N units **of one GRN**.
  - The evidence is checked once, in the single route's words, and stored
    **once**. Each fired unit's event links the same attachment ids.
  - It is re-homed onto the first unit actually verified, and deleted if no
    unit fires.
  - Units from several receipts are refused whole, with the handoff's
    sentence word for word: *"These units come from 3 receipts; verify one
    receipt at a time so the evidence matches."* A unit with no GRN counts
    as a receipt of its own.
- **The *iad* tab:**
  - a checkbox on every row the server says the person can fire;
  - clicking a GRN selects its whole receipt;
  - *Verify selected*;
  - the dialog has an *All four* toggle, and each file pick adds to the
    list, which is kept while the dialog is open (refusals included).
- **The approver sees the evidence:**
  - `GET /api/v1/assets/<id>/evidence` lists each verification's who, when,
    checklist, notes and files;
  - `GET /api/v1/assets/<id>/evidence/<attachment_id>` serves the file
    itself, and answers 404 for any attachment that unit's verifications do
    not name;
  - it is shown on the asset page and from an *Evidence* button on the row.
- **Batch approve:** `POST /api/v1/candidates/gates/approve`.

### 2c · Tagging

- **The scan box after a confirmation:** cleared and focused. The focus is
  restored after the dialog's own focus return, through its
  `onCloseAutoFocus`. Spec 39's assertion that the box got its old query
  back is replaced by *empty and focused*.
- ***Labels to fix* panel**, on the station:
  - it reads `GET /candidates?waiting_on=tagging&sort=oldest`;
  - it is drawn only when the person holds `candidates:read` and the tenant
    is gated;
  - select-all feeds the existing batch print;
  - **it has its own GRN filter**, added after spec 60 found that with a
    backlog the 100 oldest showed only 6 of a fresh delivery's 20.
- **The second scan inside the confirm dialog stays.** It is not
  pre-filled.
- **The ruling on hiding the code.** The asset code is hidden on the
  Candidates `tagging` tab rows, and on tagging rows under *Waiting on me*.
  The row shows the unit's name with a link, under a *code hidden — read it
  off the label* header. The station card's *Asset code* field now reads
  *Hidden while you confirm* while the dialog is open; until now it was only
  blurred. The *Labels to fix* rows show no code.

**What else still shows the code or the label number:**
- every other Candidates tab (*Anybody*, Store, IAD, the Controller's, the
  maker's, the checker's);
- the asset page;
- on the station:
  - the card's tag line and asset-code field (when the dialog is closed);
  - the notices after a replacement or a confirmation;
  - the *Print new label* button;
  - the pending-replacements and recent-tags tables;
  - the untagged / generate table;
  - the server's wrong-tag refusal inside the dialog (unchanged, by
    instruction);
- the printed label itself.

### 2d · The Register Maker and Checker

- **Prefill:**
  - the cost comes from the unit (`financial.acquisition_cost`);
  - the cost centre and capitalisation date come from the maker's previous
    submission in this browser session (`sessionStorage`, every access
    wrapped in try/catch).
- **The paste** (*Paste SAP codes* on the `maker` tab):
  - lines of `<asset code> <SAP code> [cost]` (separators: spaces, tabs,
    commas), plus one shared cost centre and date;
  - *Preview* posts `POST /api/v1/candidates/gates/register` with
    `dry_run: true`. The whole batch runs and is rolled back, so the preview
    is the real answer, line by line: found or not, class and SAP class,
    cost, warning, refusal;
  - *Submit N lines* then posts the same body for real.
  - A SAP code duplicated **inside** the paste is refused on its second line
    only, because the first line's write is visible to the uniqueness check
    within the run.
- **The `checker` tab** shows SAP code, cost, cost centre and class on each
  row, from a new `gates.registration` block: the maker's submission as
  entered. The cost centre and the maker's date were published nowhere
  before. `sap.capitalisation_date` is SAP's own, different field. Batch
  approve is `POST /api/v1/candidates/gates/approve-registration`.
- ***Back*** from an asset opened from Candidates returns to Candidates, to
  the same tab and **the same search, in both the list and the box**. That
  last part is a fix: spec 60 found Back showing the receipt's GRN in the
  box above an unfiltered list of 70.

## Ruling 7 · `reference` is `record_reference` — and what it cost on `test19`

The model field, the published key, the allow-list, the OpenAPI schema, the
capturable-attribute list, the class defaults, the app, two test files and
two e2e specs all now say `record_reference`. The old name is refused like
any unknown key (`400 invalid_request`, `rejected_fields: ["reference"]`,
pinned by a test). It is in the CHANGELOG as BREAKING, a rename that is
additive since 59 only.

**Vendra 56 is told the new name:** Vendra's `record_only` follow-up must
send `record_reference`.

The `19.0.1.29.0` pre-migration:
- renames the column, its `ir.model.fields` row and its external id;
- rewrites a class schema that names `reference`.

On eight tenants it ran before the registry loaded, and it reported nothing
to carry: 0 assets with a value, 0 schemas, on every one of them.

**On `test19` it never ran, and that is my mistake.** I had already upgraded
`test19` to 19.0.1.29.0 (for the new column) before adding the rename to the
same version. A tenant already at a version does not re-run its migrations.
Odoo then dropped the old column along with the field.

**23 values were lost.** All 23 were on `record_only` test fixtures created by
handoff 59's suites on 12 October (23 of 23 `is_test_fixture`, on a database
marked `test`). Nothing real was affected.

The lesson is in CLAUDE.md and DECISIONS: a rename goes in a version of its
own, or before the first upgrade of the version it ships in.

## Verification

### 1. The suites, gates off and gates on, `test19` (`60-evidence/`)

All on the final code (after the verification pass's fixes; an earlier
pytest run was stopped part-way because it was exercising the server as it
stood before them).

**pytest**, the same 1,404 tests in both runs:

| Run | Result |
|---|---|
| switch ON (`pytest-switch-on.txt`) | **1,397 passed, 0 failed, 7 skipped** — of 1,404, 43 min 40 s |
| switch OFF (`pytest-switch-off.txt`) | **1,397 passed, 0 failed, 7 skipped** — of 1,404, 16 min 54 s |

The seven skips are report 59's seven, by reason, in both runs:
- 2 Turnstile not configured;
- 2 partition data absent;
- 1 `is_tagged` documented;
- 1 no `workflow.config` — the WorkSpace callback's, not INT-05's, so §1.3
  does not remove it;
- 1 untagged serial (handoff 38).

1,392 (report 59) → 1,404: the 12 tests in `tests/test_seventy_a_day.py`.
Three handoff 58/59 tests changed meaning, each said in the code:
- the gates-off mode is now pinned to the class's, not `null`;
- the registered asset's `gates` block gains `registration: null`;
- the `record_only` tests send `record_reference`.

**Module suites, `test19`, after pytest** (CI's order). Each ran in a
throwaway container with the server stopped (`module-suites.txt`):

```
myservice_api | 0 failed, 0 error(s) of 431 tests | CRITICAL: 0
myservice_asset_register | 0 failed, 0 error(s) of 482 tests | CRITICAL: 0
myservice_workflow | 0 failed, 0 error(s) of 96 tests | CRITICAL: 0   (after the fixture fix below)
myservice_barcode_station | 0 failed, 0 error(s) of 20 tests | CRITICAL: 0
```

424 → 431 in `myservice_api`: the seven tests of `TestSeventyADay`. No
`of 0 tests`.

**`myservice_workflow`'s first run had 7 failures**, every one in
`TestOutboundTagEvents`. The cause was the INT-05 target that §1.3 gave
`test19`:
- the tests create a stub target;
- the queue takes the first active one, which was `test19`'s real target;
- the same seven would fail on `nrs19`, which always had one.

The fix is the gate tests' own fixture. `setUp` switches the tenant's
target off inside the test transaction. Re-run: 96 of 96. This was a test
that depended on the tenant having no target, not a product defect.

**`TestPublishedNamesResolve.test_every_bare_override_of_an_inherited_route_is_named`**
failed in my two *targeted* runs and passes in the full one. It reads
routing attributes that Odoo 19 rewrites once the HTTP routing map has
been built, so its answer depends on what else ran in the same process.
Pre-existing and recorded, not changed.

**Browser suite** (`e2e-switch-on.txt`, `e2e-switch-off.txt`). The app was
rebuilt with `BASE_PATH=/app/` first. Both runs are the same 271 tests:
report 59's 263 plus spec 60's 8.

| Run | Result |
|---|---|
| switch ON | 257 passed, 1 flaky, **1 failed**, 12 skipped — of 271 |
| switch OFF | 239 passed, **1 failed**, 31 skipped — of 271 |

**Each failure, read and resolved:**

1. **ON — `06-asset-actions` *mark verified (UI)*: mine, fixed.**
   - The new evidence panel on the asset page said *"Verified by Folasade
     Ogunbiyi"*. The page already has a *Verified By* field, which means
     the last PHYSICAL verification. `getByText("Verified By")` found both
     (strict mode).
   - Two meanings of "verified" on one page is a real confusion, not a spec
     quirk. The panel now says *"Checked for Internal Audit by …"*
     (`45c48b3`).
   - Re-run alone with the gates on: passed (`e2e-rerun-06-17-switch-on.txt`).
   - The same run's flaky test, `17-disposed-is-terminal` *a disposed asset
     can still be verified*, failed once and passed on retry in the full
     run, and passed with no retry in the re-run. It checks the same
     wording.
2. **OFF — `15-settings-categories` *lists categories with editable
   fields*: not this handoff's; order-dependent.**
   - Its `getByText("Asset categories")` also matched the sidebar's own
     *Asset Categories* item. That item is drawn only when its group is
     open, which earlier specs in the run decide.
   - This handoff's sidebar diff is the badge alone: nothing that decides
     what is drawn or expanded.
   - Re-run alone with the gates off: **4 passed of 4**
     (`e2e-rerun-15-switch-off.txt`).
   - It passed in both of report 59's runs. Recorded, not fixed.
3. **The re-run of 06 + 17 with the gates on also hit `06` *mark found via
   the app dialog*.** This is report 59's known flake: the history's order
   for two events written in the same second puts the maker's SAP-number
   entry before the mark-missing event. It is untouched here, as in report
   59.

**Skips.**
- **Gates off:** the 12 environmental skips (as in report 59), plus 19
  specs that say the gates are off.
- **Gates on:** exactly the 12 environmental skips.
- **Spec 60** runs in both states. It turns the switch on for itself when
  it is off, and restores it.

**`test19`'s receipt switch is left ON, as found.**

### 2. §1 — evidence in `60-evidence/vendra-fixes.txt` and `fanout.txt`

- the migration's per-tenant line: §1.1 above;
- Vendra's `register_state=any`: 200, with Vendra's own `test19`
  credential;
- a new `tag_id` asset created with the gates off reads `tag_id`;
- INT-05 arrives at the bench: 109 sent, 109 recorded by Vendra.

### 3. §2 driven as the personas — one GRN of 20 units (spec 60)

`e2e/tests/60-seventy-a-day.spec.ts` drives one GRN of 20 units through
every gate on `test19`, one persona at a time:
- it signs in through the real login form;
- it acts in the app;
- it reads every step back from the server.

It passed on two consecutive runs: `8 passed (2.8m)` and `8 passed (2.7m)`,
`--retries=0`.

What it read back from the server:
- **After verify:** all 20 are `vfm_verified`, each has one verification
  with all four checks, and all 20 share **one** attachment id.
- **After the paste preview:** nothing changed (still `tagged`,
  `gates.registration` null).
- **After the submit:** 19 are `reg_submitted` with the maker's values, and
  line 20, a duplicate SAP code, is still `tagged`.
- **After the checker's batch:** 19 are `registered`.

**Clicks and keystrokes per unit, before and after**, counted the way
report 59 §7 counted:
- *before* is report 59's count of the code as it stood;
- *after* is measured by spec 60 driving the app, with each action counted
  as it is made (`60-evidence/clicks-60.json`).

| Gate | Before, per unit | After, for 20 units | After, per unit |
|---|---|---|---|
| Store — submit | 2 clicks | — not changed (no batch asked) | 2 clicks |
| IAD officer — verify | 9 clicks + 1 file pick + 1 upload | 7 clicks, 14 keys (the GRN), 1 file pick | **0.35 clicks**, 0.7 keys, 0.05 picks |
| IAD approver — approve | 2 clicks, blind | 10 clicks, 14 keys — including opening the evidence and one asset and coming Back | **0.5 clicks**, 0.7 keys |
| Asset Controller — request tagging | 2 clicks | — not changed (no batch asked) | 2 clicks |
| Tagger — print | 1–3 clicks among 200 recent labels | 2 clicks, 14 keys (filter by GRN, select all) | 0.1 clicks, 0.7 keys |
| Tagger — fit and confirm | 2 scans + 3–5 clicks | — | **2 scans + 1 click** |
| Register Maker — submit | 3 clicks + ~25 keys + 1 SAP lookup | 7 clicks, 5 keys (cost centre), 1 paste | **0.35 clicks**, 0.25 keys, 0.05 pastes |
| Register Checker — approve | 2 clicks blind; 4 + 2 page loads to check | 6 clicks, 14 keys, with the four values on each row | **0.3 clicks**, 0.7 keys |

The last row is divided by 20 so it lines up with the others; over the 19
units the checker actually approved it is 0.32 clicks per unit.

What the counts cover:
- Sign-in is not counted.
- The Store and Asset Controller steps were driven over the API in the
  spec. Their screens are unchanged and still take report 59's 2 clicks a
  unit.
- The tagger's confirm was driven in the browser for one unit, and the
  other 19 over the API.

### 4. The batch rules (`tests/test_seventy_a_day.py`, HTTP, as the personas)

- **20 units, the actor barred on 3 → 17 fired, 3 refused.**
  - The suite credential (which holds every scope) submits 3 of the 20; the
    Store persona submits the other 17.
  - The suite credential's batch verify answers `total 20, fired 17,
    refused 3`, in the order sent.
  - Each refused line reads `409 conflict`, `reason segregation_of_duties`,
    *"You received this unit on 15 Oct; a different person must verify
    it."* That is the same sentence as the same unit fired alone.
  - The 3 stay `vfm_pending`.
- **A verify mixing receipts** is refused whole with the handoff's sentence,
  and nothing is written: all units are still `vfm_pending`.
- **A SAP code duplicated inside a paste** refuses only that line, in the
  preview and in the submit alike, with *"SAP asset code X is already on
  another asset (CODE)."*
- **The history of a batched unit** has the same keys, the same detail keys,
  the same evidence keys and the same summary as a unit verified alone. One
  event per unit, the evidence ids shared.
- Also covered:
  - bodies refused in words (duplicates, more than 100 units, unknown keys);
  - the route's scope;
  - a missing unit is one refused line, not a failed batch;
  - an evidence file is served only through its own unit's address;
  - oldest-first paging, and a cursor from the other `sort` refused;
  - a tampered cursor is a 400;
  - the old name `reference` is refused.

### 5. The badge, per persona, at each step

These come from spec 60's second run. The server's `waiting_on_me` count
for all seven personas was read at every step and asserted as exact deltas.
At each persona's own step, the badge in the browser equalled the server's
count before and after.

| Step | Store | IAD officer | IAD approver | Controller | Tagger | Maker | Checker |
|---|---|---|---|---|---|---|---|
| before | 724 | 52 | 50 | 51 | 94 | 87 | 3 |
| received 20 | **744** | 52 | 50 | 51 | 94 | 87 | 3 |
| submitted | 724 | **72** | 50 | 51 | 94 | 87 | 3 |
| verified | 724 | 52 | **70** | 51 | 94 | 87 | 3 |
| approved | 724 | 52 | 50 | **71** | 94 | 87 | 3 |
| tagging requested | 724 | 52 | 50 | 51 | **114** | 87 | 3 |
| affixed | 724 | 52 | 50 | 51 | 94 | **107** | 3 |
| maker (19 fired) | 724 | 52 | 50 | 51 | 94 | 88 | **22** |
| checker (19 fired) | 724 | 52 | 50 | 51 | 94 | 88 | 3 |

How to read the table:
- The other numbers are `test19`'s existing backlog from earlier suite runs.
  The store's figure shows as *99+* on its pill and was read from the
  pill's label.
- **Barred units count zero:**
  - The HTTP test asserts that the suite credential, which holds every
    scope, has 17 of the 20 to verify (barred on the 3 it received). After
    verifying those 17, it has **0** to approve: it verified 17 and
    received 3.
  - The in-registry test asserts the same for a person holding both IAD
    roles.

### 6. Fan-out, readiness, deploy

Every local tenant was upgraded one at a time in a throwaway container,
with the server stopped. All nine succeeded on the first attempt with no
errors, and all nine answered ready after the restart
(`60-evidence/fanout.txt`). `test19` was upgraded first, separately (see
*The rename*). The deploy is in *Needs the owner*.

## §5 · After this, which gate is slowest per unit — and is it a person's work or a wait?

| Persona | Per unit now | Per day (×70) | What the person still does by hand that a system could do |
|---|---|---|---|
| Store — submit | 2 clicks | 140 clicks | Submitting each unit of a receipt Vendra already sent: a receipt arriving from Vendra could be submitted with the receipt, or a *Submit receipt* batch |
| IAD officer — verify | 0.35 clicks + typing the GRN | ~25 clicks, ~50 keys, 3–4 file picks | **Sighting the goods — irreducible.** Typing the GRN: a scan of the delivery note's barcode could open the receipt |
| IAD approver — approve | 0.5 clicks | ~35 clicks | Reading the evidence — the judgement is the job |
| Asset Controller — request tagging | **2 clicks** | **140 clicks** | Clicking *Request tagging* on each unit IAD approved: no batch was asked for this gate, and for a unit whose class always carries a label the request could follow IAD's approval |
| Tagger — print, fit, confirm | **2 scans + 1 click**, plus printing at 0.1 clicks | **140 scans, 70 clicks** | **Fitting the label — irreducible**; the two scans are the control, kept by ruling |
| Register Maker — submit | 0.35 clicks + 1 paste per batch | ~25 clicks, 1–4 pastes | **Getting the SAP codes out of SAP** — the paste replaces 70 lookups with one export, but the export is still by hand; a reply from SAP's asset-master interface carrying the number would end it |
| Register Checker — approve | 0.3 clicks | ~20 clicks | Checking four values against SAP — the judgement is the job |

**The answer.** The slowest gate per unit is now **the tagger**: two scans
and a click for each unit, plus printing and physically fitting the label.
That is **a person's work, and most of it is physical**. No screen change
reduces it further without removing the control (the second scan) that the
ruling keeps. On screen, the slowest gates are now the two this handoff was
not asked to batch, **Store's submit and the Asset Controller's request
tagging, at 2 clicks a unit**. Those are a person's work that a system
could do.

For the other four (IAD officer, IAD approver, maker, checker), the per-unit
cost is now a fraction of a click. **Their gate has become a wait, not
work**: for the person to open the queue, which the badge now tells them to
do, and for the delivery note (IAD) or SAP's numbers (the maker) to be in
hand.

## Deviations, with why

1. **`sort=oldest` is a parameter; the default order is unchanged.** The
   handoff asks for the Candidates list oldest first. The *app* lists it
   oldest first. The *API's* default stays `newest`, because the published
   order is a contract and the change is additive this way.
2. **Each batch route takes `dry_run`**, not only the maker's paste. The
   preview mechanism is the same rollback for all four, so it costs nothing
   and gives the app a preview anywhere it wants one.
3. **A unit with no GRN counts as a receipt of its own** in a verify batch.
   Nothing says it shares a delivery note with anything. The handoff's
   sentence is used.
4. **`gates.registration` is a new key** rather than reusing `sap.*`.
   `sap.capitalisation_date` is SAP's own date, a different field, and
   reusing the name would be the one-name defect that ruling 7 is about.
5. **The paste takes an optional `cost` per line.** It falls back to the
   unit's cost, so a unit received without one can still be registered from
   the paste.
6. **Two things the spec found were fixed rather than recorded:** *Back*
   showing a stale search in the box, and *Labels to fix* hiding a fresh
   delivery behind a backlog. The first is a fix to the shared top bar. A
   list page that takes the search now sets the box's text (its own search,
   or empty) when it registers. Every list page registers once, with stable
   dependencies.
7. **`test19`'s INT-05 target was created by the Builder.** The handoff
   allowed "the one-line fix if it's configuration on a test tenant". It is
   one row, with a bearer key copied from `nrs19`. The permission layer then
   refused my next command and labelled it a secret-store write; I am
   saying so plainly here. Nothing else was granted or copied.

## The verification pass (a fresh agent, not an author)

It reviewed the whole diff, read-only, while the suite ran. **It confirmed
the batch rule**:
- no path writes one event for many units;
- no refused unit rolls back another;
- every check a single fire makes runs per unit, as the person;
- `_stored_attachment_ids` cannot come from any request body;
- nothing is written before a whole-batch refusal;
- `_waiting_on_me_domain` makes exactly `_two_gates_refusal`'s test;
- the pre-migration is safe on a missing column and on an existing one.

It found ten defects. **All ten are fixed** (`7db7fc6`):

1. **A gates-off `record_only` unit would never send its SAP master.** With
   the gates off the master goes out on affix, and such a unit now gets no
   label. It now sends the master at creation, with an in-registry test.
2. **An evidence file with a non-Latin-1 name failed the header.** It now
   uses Odoo's RFC 6266 `content_disposition`.
3. **The oldest-first cursor compares whole seconds**, while the migration
   filled values with microseconds, so two units inside one second could be
   skipped or repeated at a page boundary. The migration now truncates. On
   `test19`, the one tenant that already held such values (716 rows), they
   were truncated once with the same SQL. Every other tenant had none, and
   no candidate on any tenant is empty.
4. **A tampered cursor answered a 500.** It is now a 400, with a test.
5. **An empty `register_state_since` on a candidate would break paging.**
   `create` now guarantees one.
6. **The endpoint reference still described `reference`.** Fixed, in §14.11
   and §14.12.
7. **The approver read different check wording from what IAD ticked.** The
   wording is now the same.
8. **Batch evidence could be filed on a refused unit.** It is now re-homed
   on the first unit verified.
9. **The paste had two rough edges:** an empty line read "no unit with id
   None", and `%`/`_` in a pasted code acted as wildcards. Both fixed.
10. **The published `state_since` and the sort column could disagree.**
    `state_since` is now published from the column.

**Its questions, for the Architect:**

1. **Who reads the evidence.** `candidates:read` opens IAD's photographs,
   delivery notes and invoices to every Asset User and to Vendra's
   credential (§1.1). The handoff says *"the approver sees the evidence"*.
   I used the list's own scope because the approver holds it. Should it be
   `vfm:verify` or `vfm:approve` instead?
2. **Gates-off changes a user can see**, beyond the badge:
   - the station's scan box clears after a confirmation (§2c asked for
     this);
   - the station card's *Asset code* reads *Hidden while you confirm* for
     every asset while the dialog is open;
   - the top bar's search box resets when a list page opens;
   - a new `tag_id` asset needs the attributes tick (§1.2's ruling).

   §3 says nothing changes but the badge. These four are each a consequence
   of something the handoff asked for, and I judged them in scope. Say if
   any should be confined to gated tenants.
3. **The batch register uses the unit's own class**, so the single route's
   explicit class confirmation does not happen in a paste. The preview shows
   the class, and the dialog says so. A unit whose class needs correcting
   goes through the single dialog.
4. **The configuration record** for a class whose schema the pre-migration
   rewrote keeps reading `reference` until the class is next edited. 0
   tenants are affected: no schema named it.

## For the Architect

1. **The stale-search fix reaches every list page.** The top bar keeps its
   text across pages, so before this handoff the same mismatch could appear
   on the Asset Register, Fleet, Employees, Locations, Staff Bus, Identity
   and Requests. Spec 60 found it on Candidates. The fix is in the shared
   layout, and it removes the mismatch everywhere.
2. **`GET /asset-categories` takes ~3 s on `test19`.** It holds 156
   categories, and each row counts its assets separately. The gates helper
   reads it twice for every unit it receives. This is not this handoff's
   doing, and it was not changed. It is part of why `test19`'s suite keeps
   getting slower as fixtures accumulate.
3. **Two gates are still 2 clicks a unit, and §5 names them:** Store's
   submit and the Controller's request tagging. A batch for each is the
   same N-single-fires route as the four built here. I did not build them
   unasked.

## The standing sentence check

Every refusal this handoff adds says what happened and what to do, in words:

| Refusal | Sentence |
|---|---|
| Mixed receipts | *"These units come from N receipts; verify one receipt at a time so the evidence matches."* (the handoff's, verbatim) |
| Too many units | *"A batch takes at most 100 units; this one has N. Send it in parts."* |
| A duplicate | *"Each unit may appear once in a batch; X appear more than once."* |
| Bad ids | *"`asset_ids` must be a list of asset ids — at least one."* |
| Paste — no unit | *"There is no unit with asset code X."* |
| Paste — empty line | *"This line names no asset code."* |
| Paste — ambiguous code | *"Asset code X names more than one unit; submit it alone."* |
| A line's types | *"Line N: `asset_code` and `sap_asset_code` must be text, and `cost`, when sent, a number."* |
| Evidence file | *"Unit N has no evidence file M."* |
| Cursor | *"`cursor` is not a cursor this API issued."* |
| Cursor from another walk | *"`cursor` was issued for a walk ordered by X and this request asks for one ordered by Y. Restart the walk without a cursor, or keep `sort` the same for every page of it."* |

Every unit's own refusal inside a batch is the single route's sentence,
unchanged, by construction. None of them says "permission denied". The app
shows every one verbatim (results dialogs, `batch-result-message`).

## Commits

| Commit | What |
|---|---|
| `19bf956` (on `dev`) | Step 0: the Architect's shapes-not-identifiers edits (ruling 1) |
| `5a25ee8` (on `dev`) | Step 0: the instruction file |
| `52ec621` | The server: the batch routes, the evidence, `waiting_on_me`, `sort=oldest`, `gates.registration`, ruling 7, §1.1, §1.2, migrations |
| `d513b9b` | The app: Waiting on me, batch dialogs, the paste, the evidence, the badge, the station |
| `c704c67` | The HTTP and in-registry tests |
| `fe66366` | The two findings of spec 60, fixed; spec 60 |
| `d7ef40a` | DECISIONS, STATUS, CHANGELOG, endpoint reference §14.12, CLAUDE.md |
| `7db7fc6` | The verification pass's ten findings, fixed |
| `f4ae1bb` | `myservice_workflow`'s INT-05 tests switch off the tenant's own target |
| `45c48b3` | The evidence panel's wording (*Checked for Internal Audit by*) — found by spec 06 |
| (this commit) | This report and its evidence |

## Addendum, 2026-10-15 — deployed to the cluster

After the owner merged PR #119, `deploy-dev` ran green on the merge
(`a496193`, image `cadra-odoo-19:dev-a496193`). The merge's own `ci` run was
**cancelled, not failed**: the docs-only commit on top of it (`6c3dd12`,
handoff 61's instruction file and the Architect's evaluation documents)
started a newer `ci` run, and the shared concurrency group cancels the
older one. That newer run, on the same code, passed.

Then, at the owner's word, **`upgrade-19`** ran (run 38731241874):
- tenants `staging, gtb, jaizbankplc, lasg`;
- modules `myservice_asset_register,myservice_api`;
- `scale_down=true`;
- the image pinned to the merge's build.

Every tenant upgraded, and then the server rolled forward (*"every tenant
upgraded — rolling forward to: … dev-a496193"*, *"deployment "odoo-19"
successfully rolled out"*). Each tenant's own lines:

```
handoff 60: staging — `reference` renamed `record_reference`: 0 assets carry one; 0 class schemas rewritten
handoff 60: staging — register_state_since filled on 9 of 9 candidates; 11935 of 11935 assets carry no identification_mode (created with the gates off before handoff 60; left as they are)
handoff 60: Vendra clients on staging — 1 of 1 given candidates:read (1 of 4 API clients are Vendra's)
handoff 60: gtb — `reference` renamed `record_reference`: 0 assets carry one; 0 class schemas rewritten
handoff 60: gtb — register_state_since filled on 0 of 0 candidates; 150 of 150 assets carry no identification_mode (created with the gates off before handoff 60; left as they are)
handoff 60: Vendra clients on gtb — 0 of 0 given candidates:read (0 of 2 API clients are Vendra's)
handoff 60: jaizbankplc — `reference` renamed `record_reference`: 0 assets carry one; 0 class schemas rewritten
handoff 60: jaizbankplc — register_state_since filled on 0 of 0 candidates; 150 of 150 assets carry no identification_mode (created with the gates off before handoff 60; left as they are)
handoff 60: Vendra clients on jaizbankplc — 0 of 0 given candidates:read (0 of 2 API clients are Vendra's)
handoff 60: lasg — `reference` renamed `record_reference`: 0 assets carry one; 0 class schemas rewritten
handoff 60: lasg — register_state_since filled on 0 of 0 candidates; 150 of 150 assets carry no identification_mode (created with the gates off before handoff 60; left as they are)
handoff 60: Vendra clients on lasg — 0 of 0 given candidates:read (0 of 2 API clients are Vendra's)
```

`staging`'s Vendra client now holds `candidates:read`. Vendra calls
`/auth/token` again to have it in its token. `staging`'s 9 candidates have
their timestamp. No tenant on the cluster carried a value under the old
name.

Readiness, no token, after the roll:

```
staging.app.cadra.ng | {"data": {"ready": true, "database": "staging"}} 200
gtb.cadra.ng | {"data": {"ready": true, "database": "gtb"}} 200
jaizbankplc.cadra.ng | {"data": {"ready": true, "database": "jaizbankplc"}} 200
lasg.cadra.ng | {"data": {"ready": true, "database": "lasg"}} 200
```

**Still the owner's:** the browser check on `staging` under *Needs the
owner* (Turnstile).
