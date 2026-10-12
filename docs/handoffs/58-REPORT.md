# Report — Handoff 58: the gates, kept

Branch `feat/the-gates-kept`, from `dev` at `e3e5525` (Step 0: the
instruction file, the evaluation's §8 and the superseded draft committed on
`dev`). PR #116 (`fix/gate-fired-fidelity`, CI green, not yet merged) is
merged INTO this branch so the suite starts from CI-green; merging #116
first or not at all changes nothing.

## The owner's check on `staging` — after the merge and the deploy

Nothing scripted can sign in to the cluster (Turnstile), so this is yours,
in the browser. **Do not turn Turnstile off.**

0. Without signing in: open `https://staging.app.cadra.ng/api/v1/meta/readiness`
   — it must say `{"data": {"ready": true, …}}`. Anything else names the
   module the deploy did not upgrade.
1. Sign in as the **administrator persona** (`docs/api/.personas.cluster.staging`).
2. **Settings → Receipt gates** still reads **On**.
3. Push one unit through all seven steps, each as its persona (the run sheet
   `docs/handoffs/57-DEMO-SCRIPT.md` still holds): Store submits → IAD
   officer verifies → IAD approver approves → Asset Controller requests the
   tag → the tagger confirms the label → Register Maker registers → Register
   Checker approves.
4. Watch the register count (**All Assets**) — it moves **only at the last
   step**, by one.
5. **Settings → Asset Categories**: set one class to **Tag ID**, then receive
   a unit of it (as Store, or from Vendra once Vendra 54 is deployed) with
   description, make, model, colour, material and dimensions and **no
   serial**; at the tagger's step the dialog asks for the label and the
   tick, never a serial.

Then tell the Architect what you saw. The switch stays as it is everywhere:
on for `staging`, off for the rest.

**Needs the owner, otherwise:** the PR merge (the Builder's permission layer
refuses `gh pr merge`), and the deploy (`deploy-dev` → `upgrade-19`, all four
tenants — §7 below).

## In plain words

Handoff 57 built the receipt gates in one night, on the existing asset
record, as a stand-in; the plan was to rebuild them as a separate
"candidate" record. The Architect ruled (evaluation §8) that the stand-in is
good enough to keep — and this handoff made it the real thing:

- The "scaffolding" labels are gone from the code, the screens and the
  current docs.
- **Every test suite now passes with the gates switched ON**, which is how
  NRS will run. Tests that need an asset already on the register now walk
  one through all seven gates as the seven demo people — the same way a real
  unit gets there.
- The five problems 57 left are fixed: refusing the tagger who already did
  another step now looks like every other gate refusal (D3); SAP's answer no
  longer silently overwrites the SAP number the Register Maker typed — a
  different number is flagged as a reconciliation exception naming both
  people (P4); a unit not yet on the register cannot be given a custodian,
  moved, transferred or disposed of, by any route (P5); a tenant whose
  database was not upgraded now SAYS so instead of failing every list with a
  bare error (P8); the docs list every "waiting on" value (D6).
- **Furniture can be received without a serial number** (Section 12): each
  class says whether its units are identified by serial number or by tag and
  attributes; furniture is set to the latter; the tagger confirms a chair by
  its label and a tick saying it matches its description.
- **Some role combinations can no longer be granted** to one person — Store
  with any audit or registration role, Maker with Checker, the two IAD
  roles. Nobody who already holds such a pair loses it; they are listed for
  you to decide. Today that list is empty on every client tenant and on
  `staging`.

What it means: nothing changes on a tenant whose switch is off. On
`staging`, the demo works as before, plus furniture.

## What the handoff assumed and the code did not have

Five claims in the instruction were checked before being built on, and none
held. Each is a `DECISIONS.md` line.

| Claim | What the code had | What was built |
|---|---|---|
| `settings:classes` "already granted to the role" | no such scope anywhere | the scope, granted to the Asset Controller **and** the Asset Manager (so the categories nav item declares one scope) |
| "the existing SAP reconciliation surface" | a computed state and a filter; no discrepancy record | the discrepancy as `data.sap.discrepancy` + the `exception` state + chatter |
| "the configuration record" will show a class or exclusion change | it reads `ir.config_parameter` and nothing else | each change writes a parameter named after it (`cadra.class_identification.<id>`, `cadra.role_exclusion.<id>`) |
| serial uniqueness "already should" ignore empty serials | there is no serial uniqueness in Cadra | uniqueness at the GATED receipt only (a constraint is impossible: `nrs19` has 1,291 shared serials), empty serials never compared |
| "the API's health or readiness answer" | there is none; probes hit `/web/login` | `GET /api/v1/meta/readiness`, no token, and `503 server_misconfigured` from every route |

And one ruling read literally would have broken a ruling of its own: §5's
"Store (Asset User / Asset Officer)". Every gate role implies Asset User,
and handoff 41 ruled a human tagger holds Asset User beside the Tag-Issuing
Unit — an exclusion on Asset User forbids every gate role to anybody who has
one. **Store is the Asset Officer** (the role that fires the receipt gate).

## §1 · The word comes off

`asset_gates.py` and `v1_gates.py` open with the design, not an apology; the
register filter in `_search` is described as load-bearing (P8) and why. Report
57's title, the `CLAUDE.md` gotcha and the `DECISIONS.md` entry each carry
*kept by handoff 58; see evaluation §8* — appended; the history stands.

**The grep** (case-insensitive `scaffolding|replaced by 58|handoff 58
replaces`, outside `dist/`, `docs/handoffs/5[78]*` and `_superseded/`):
**before, at `e3e5525`: 55 lines. After: 5** —
`handoffs/58-evidence/scaffolding-grep.txt`. **Not zero, deliberately**, and
the handoff's two instructions are why: four of the five are the dated
history the same section says not to rewrite (the `DECISIONS.md` and
`CHANGELOG.md` headings and entry for 2026-10-07 — both now followed by a
*kept by 58* line), and the fifth is a pasted Replit prompt in
`Frontend/attached_assets/` that says *"Start by scaffolding the project"*,
which is not about the gates.

## §2 · Green with the gates on

**One helper per suite**, named in `DECISIONS.md`: `tests/gates.py` (pytest)
and `e2e/fixtures/gates.ts` (browser) — `receive`, `on_the_register`,
`ready_to_affix`. With the switch on they walk the unit through the seven
gates **as the seven demo personas, over HTTP** — the no-two-gates rule makes
one credential unable to; with it off they do nothing. Receipt-path tests are
parametrised over both switch states (`receipt_switch` fixture, which puts
the tenant's own value back). No test was deleted, skipped or loosened; one
first draft of mine DID return early and skip three assertions under the
switch, and was rewritten so both branches end in the same assertions.

**pytest, `test19`** (`handoffs/58-evidence/`):

| Run | Result | Denominator |
|---|---|---|
| Baseline before any change, switch ON | 87 failed, 1,235 passed, 9 skipped | 1,331 |
| Final, switch OFF (`pytest-switch-off.txt`) | **1,350 passed, 0 failed, 7 skipped** | 1,357 |
| Final, switch ON (`pytest-switch-on.txt`) | **1,350 passed, 0 failed, 7 skipped** | 1,357 |

The 1,331 → 1,357 difference (26) is what this handoff added: 20 tests in
`tests/test_gates_kept.py`, the D6 guard, and receipt-path tests
parametrised over both switch states (each now two cases) — the same 1,357
in both final runs. Skips, both runs: 2 Turnstile not configured, 2 partition-data-absent,
1 `is_tagged` documented, 1 no `workflow.config`, 1 untagged-serial
(handoff 38) — the 7 report 57 had.
The switch-OFF run was taken twice: the first (`pytest-switch-off-run1.txt`)
was 1 failed of 1,357 — `test_every_catch_all_says_what_it_is_hiding`, the
handoff-15 guard catching the broad `except` I put round the SAP
discrepancy's chatter post without its `catch-all:` classification. Marked
(`reported`, and why), then the whole suite run again: the line above. The
switch-ON final run was 28 minutes; before this handoff the suite took 9½ —
the difference is ~80 units walked through seven gates each.

**Module suites, `test19`, `--workers=0`, after pytest** (CI's order):
`myservice_api` **0 failed, 0 error(s) of 414 tests** ·
`myservice_asset_register` **0 failed, 0 error(s) of 482 tests** ·
`myservice_workflow` **0 failed, 0 error(s) of 96 tests** — no `of 0 tests`,
no `CRITICAL` (`module-suites.txt`). The first run was 4 failed + 3 errors of
412 and 1 failed of 482: guard tables meeting the new names, 57's rule-1
tests meeting rule 2, and the snapshot guard meeting three tracked fields —
each resolved as described under §2.

**Browser suite, `test19`** (`e2e-switch-off.txt`, `e2e-switch-on.txt`):

| Run | Result |
|---|---|
| switch OFF | 229 passed, 0 failed, 24 skipped — of 253 |
| switch ON | 241 passed, 0 failed, 12 skipped — of 253 |

Same 253 tests. The 12 extra skips with the switch off are spec 57's twelve,
each saying the gates are off (named in
`e2e-switch-off-spec57-skips.txt`). The 12 in both runs: 8 need the service
credential (`E2E_CLIENT_ID` unset), 3 need building locations `test19` does
not have, 1 needs a request `type_id` — report 49's categories. The two
depreciation specs GO-LIVE §13.5 lists as red on `test19` passed in both
runs, first attempt. After the asset form gained its three Section 12 inputs
(below), specs 05 and 19 — the two that drive that form — were re-run: 8 of
8 with the switch on, 8 of 8 off.

**Tests whose meaning changed under the switch** — every one is a premise
the gates make false, not an assertion relaxed:

- `test_user_roles.py` (grant/record/revert) and spec 42 grant the Asset
  Manager the **Auditor**, not the Tag-Issuing Unit: Manager implies
  Officer, and Officer × TIU is now a forbidden pair.
- Spec 45: the invited tagger is **Asset User + TIU** (handoff 41's ruled
  human tagger), not Manager + TIU.
- `test_audit_reports.py` SAP coverage (two tests): with the gates on every
  registered unit carries the SAP code its maker typed, so the period can be
  `complete`; the expectation is read off the fixture's own rows, both ways.
- `test_asset_events_api.py::…registered_as_already_disposed…`:
  parametrised; ON, a receipt cannot arrive disposed (P5) — refused 409.
- Disposal fixtures (`test_audit_reports`, `test_audit_logs`,
  `test_rejected_fields_are_refused`): with the gates on the unit is
  registered and THEN disposed (`gates.disposed_on_the_register`).
- `test_barcode.py` (2) and spec 38: the asset-code scan resolves *by tag*
  when the gates are on, because the label IS the asset code (ruling 4.3).
- `test_tag_replacement.py`: a pending or old label is found by code.
- `test_asset_history.py`: counts relative to the history after the walk.
- `test_sap_reconciliation.py`, `test_tagging.py` filters: ask
  `register_state=any`, so a candidate is in the population.
- Spec 06 "no history": the unit as received (a registered gated unit
  always has gate history). Spec 19: a receipt cannot carry a custodian —
  asserted refused instead. Specs 05/19: a serial class, typed serial.
- Spec 46: the `/settings/categories` probe is `PATCH /asset-categories/0`
  (the item now declares `settings:classes`). Spec 48: the Store Officer
  example item is `receipt_gate` — stale since 57's persona change.
- In-registry: 57's three rule-1 tests switch off the ONE exclusion they
  need inside their transaction — rule 1 still holds when an owner has
  switched rule 2 off; `test_asset_officer_role`'s receipt carries a serial.

## §3 · The findings 57 left open — driven over HTTP on `test19`

Each is a test in `tests/test_gates_kept.py` (HTTP) and/or
`myservice_api/tests/test_gates_kept.py` (in-registry), green in the runs
above; answers as served:

- **D3** — `test_a_two_gates_refusal_at_affix_is_a_409`: the suite submits a
  unit, the personas walk it to `tag_issued`, the suite affixes →
  **409 `conflict`**, `details.reason = "segregation_of_duties"`,
  `details.earlier.gate = "receipt"`, *"You received this unit on 12 Oct; a
  different person must tag it."* In the browser: spec 57 (b), the sentence
  verbatim in `affix-refusal`. CHANGELOG: BREAKING (status), affix only.
- **P4** — in-registry (SAP's answer cannot be driven over HTTP on a tenant
  with no SAP): same number → `code_source = confirmed`, nothing else moves;
  different → the maker's number kept, `sap_returned_asset_number` set,
  `reconciliation_state = exception`, `sap.discrepancy` names both numbers,
  the maker and the checker (from the gate events); correcting the entered
  number to SAP's closes it.
- **P5** — `test_every_writer_refuses_a_candidate`, every writer over HTTP,
  each **409 `not_on_the_register`** with *"This unit is not on the register
  yet (waiting on Store); …"*: `PATCH custodian_id` (*a custodian can be
  assigned once it is registered*), `PATCH location_id` (*moved*), `PATCH
  state=disposed` (*disposed of*), `POST /move`, `POST /transfer-custody`,
  `POST /condemn`, `POST /assets` with `custodian_id`, `POST /assets` with
  `state: disposed`. In-registry: a change request and an `nrs.asset.transfer`
  raised against a candidate are refused at creation (*transferred*); the
  approval of a request and every ORM writer meet the guard in
  `_write_recorded`; clearing passes; a registered asset is untouched.
- **P8** — on a throwaway copy of `test19` (`p8probe58`, the column
  dropped, then the database dropped): `GET /meta/readiness` → **503**
  *"…1 column(s) missing, first nrs_asset.register_state. Upgrade
  myservice_asset_register on p8probe58…"*; `GET /assets` with a token →
  **503 `server_misconfigured`** naming the column, where it was a bare 500;
  `test19` itself → 200 ready (`p8-throwaway-copy.txt`). Placed where it
  costs least: one `except` in `cadra_route`, one unauthenticated route.
- **D6** — the reference already listed seven `waiting_on` values (the only
  six-value list is handoff 57's instruction file, which I do not edit); now
  pinned by `test_the_reference_lists_every_waiting_on_value_it_serves`.
- **P1, D5, INT-05** — a `DECISIONS.md` line each, no code.

## §4 · Section 12

All driven in `tests/test_gates_kept.py` with the switch on:

- a `tag_id` unit (Office Furniture, attributes, **no serial**) through all
  seven gates; the affix refused 400 without the tick, then taken with it;
  the affix event records `check = label_and_attributes`. In the browser:
  spec 57 (a) — the tagger in the Confirm-affixed dialog sees no serial
  field, the tick reads *"The item matches: <name>, Ergo, Black"*, Confirm
  stays disabled until ticked, the expected number never in the markup;
- missing colour → 400, `details.missing_fields = ["colour"]`, *"…must
  arrive with its colour (`colour`)."*;
- a `serial` unit with no serial → *"Generator: 0 of 1 serial numbers
  captured. Capture one serial number per accepted unit."*;
- `pool` → *"Pool identification is not built yet (Addendum A Phase E)."*;
- the class changed to `serial` with a chair already received: the chair
  keeps `tag_id` and is affixed on label + tick; a NEW chair needs a serial
  (AD-31);
- two chairs with no serial both accepted; a serial already on the register
  refused, compared stripped and case-insensitively;
- the Asset Controller (`settings:classes`) changes a class's mode (200),
  is refused a rename (403 naming `settings:write`); the Store Officer is
  refused 403; the change is on the configuration record as
  `cadra.class_identification.<id>`.

The migration's line per tenant is in §7. Vendra 54 reads the two category
fields; Vendra already refuses a captured line without make and model, so
the default serial schema cannot dead-letter a Vendra receipt.

## §5 · Rule 2 — the role-exclusion table

**Measured before the seed** (`conflicting-grants-before-seed.txt`; SQL
committed beside it): 0 of 3 (`cadra19`), 0 of 5 (`nrs19`), 0 of 9
(`gtb19`), 0 of 8 (`nrs`), 0 of 15 (`lasg`), 0 of 15 (`gtb`), 0 of 21
(`jaizbankplc`); **16 of 665 (`test19`) and 10 of 37 (`boot44`), every one an
INACTIVE e2e fixture holding Officer + Tag-Issuing Unit** (spec 45's old
tagger). The cluster, through the read-only `db-query` workflow: **0 of 17
on `staging`, 0 of 15 on `gtb`, `jaizbankplc` and `lasg`.** The personas the
handoff named (Halima, Babatunde, Chukwudi, Oluwaseun) hold no pair. Nothing
was revoked.

Driven: every seeded exclusion refused at grant over the API, preview and
apply, naming both roles and the reason (`test_every_seeded_exclusion_
refuses_the_grant`); on the Users page, spec 58 — the preview's 403 verbatim
in `roles-refusal`, Apply disabled, nothing written; one exclusion toggled
off on Settings → Role exclusions, the grant applied, the configuration
record showing `cadra.role_exclusion.<id>` = `off; Register Maker × Register
Checker; …`; toggled back on, the person listed under *Conflicting grants*,
roles kept. The one real bug the run found: a switched-off exclusion went on
refusing, because the Users route reads people with `active_test=False` and
the guard inherited it — fixed by naming `active` in the domain.

## Verification pass (a fresh agent, not an author)

Found and **fixed**, each with a test: rule 2 would have refused a brand-new
API credential (a fresh database's `bootstrap.py` would have failed);
`PATCH /asset-categories/<id>` checked its scope after existence and was
published in `openapi.json` as needing no token; **a receipt could arrive
`state: disposed`** and be walked to the register, sending SAP a master for a
write-off; a SAP discrepancy could never close; the discrepancy's chatter
post could escape the INT-06 drain; a mode-only category change re-derived
depreciation for the whole class; a non-string role key was a 500; a repeat
affix of a `tag_id` unit was not idempotent; a test fixture pinned a class's
default schema (`class_attributes_schema: null` now resets it). The CHANGELOG
and §14.8 overclaimed what approving an old request answers — corrected.

**Left, with reasons** (`DECISIONS.md`): a back-office group-IMPLICATION edit
is not judged by rule 2; the SAP discrepancy is fields + chatter, not an
append-only event; INT-09 lifecycle events of a unit in discrepancy carry
the maker's number; a back-office *Duplicate* of a candidate yields a
registered asset (pre-existing from 57); the readiness answer has no `meta`
block. The middle three are GO-LIVE §29 item 14.

Found by the browser run and **fixed**: the *Create person* dialog's Create
button sat off a 720px screen once there were ten roles (spec 43); the asset
form had no colour/material/dimensions inputs, so a furniture unit could not
be received in the app at all.

## §7 · Fan-out and deploy

Every local tenant, serially, `-u myservice_asset_register,myservice_api,
myservice_workflow`, then a restart; the migration's own line, readiness
and the seed (`fanout.txt`):

```
cadra19 | handoff 58: identification mode on cadra19 — 2 of 28 classes tag_id (Furniture & Fittings, Office Furniture), the rest serial  | errors: 0
nrs19 | handoff 58: identification mode on nrs19 — 1 of 22 classes tag_id (Office Furniture), the rest serial  | errors: 0
gtb19 | handoff 58: identification mode on gtb19 — 2 of 29 classes tag_id (Furniture, Office Furniture), the rest serial  | errors: 0
test19 | (no migration line — already at 19.0.1.27.0) | errors: 0
nrs | handoff 58: identification mode on nrs — 2 of 28 classes tag_id (Furniture & Fittings, Office Furniture), the rest serial  | errors: 0
lasg | handoff 58: identification mode on lasg — 1 of 29 classes tag_id (Office Furniture), the rest serial  | errors: 0
gtb | handoff 58: identification mode on gtb — 2 of 29 classes tag_id (Furniture, Office Furniture), the rest serial  | errors: 0
jaizbankplc | handoff 58: identification mode on jaizbankplc — 2 of 29 classes tag_id (Furniture, Office Furniture), the rest serial  | errors: 0
boot44 | handoff 58: identification mode on boot44 — 1 of 22 classes tag_id (Office Furniture), the rest serial  | errors: 0
test19 | handoff 58: identification mode on test19 — 1 of 129 classes tag_id (Office Furniture), the rest serial (its first upgrade, 09:44Z) | errors: 0

# after the restart: readiness (no token) and the seeded exclusions, per tenant
cadra19 | readiness: {"data": {"ready": true, "database": "cadra19"}} 200 | exclusions active: 8 of 8
nrs19 | readiness: {"data": {"ready": true, "database": "nrs19"}} 200 | exclusions active: 8 of 8
gtb19 | readiness: {"data": {"ready": true, "database": "gtb19"}} 200 | exclusions active: 8 of 8
test19 | readiness: {"data": {"ready": true, "database": "test19"}} 200 | exclusions active: 8 of 8
nrs | readiness: {"data": {"ready": true, "database": "nrs"}} 200 | exclusions active: 8 of 8
lasg | readiness: {"data": {"ready": true, "database": "lasg"}} 200 | exclusions active: 8 of 8
gtb | readiness: {"data": {"ready": true, "database": "gtb"}} 200 | exclusions active: 8 of 8
jaizbankplc | readiness: {"data": {"ready": true, "database": "jaizbankplc"}} 200 | exclusions active: 8 of 8
boot44 | readiness: {"data": {"ready": true, "database": "boot44"}} 200 | exclusions active: 8 of 8
```

**The deploy, for the owner, after the merge** (as report 57's addendum):
1. Merge this PR → **`deploy-dev`** builds and pins the backend and frontend
   images.
2. **`upgrade-19`**, all four tenants (`staging, gtb, jaizbankplc, lasg`),
   modules `myservice_asset_register,myservice_api,myservice_workflow`,
   `scale_down=true` — the migration prints, per tenant, *"N of M classes
   tag_id (…), the rest serial"*; the role-exclusion table is seeded.
   **Mandatory before traffic**: the register filter reads a column every
   asset search uses (P8).
3. Then the check at the top of this report — `/api/v1/meta/readiness` first.
The demo personas need nothing new (no new persona).

## §9 · What stands between this and switching it on for NRS in production

`docs/GO-LIVE.md` §29 is the checklist — fourteen items, each with an owner.
In short: **(1)** named people for every gate (NRS) — seven distinct people
or the chain cannot finish; **(2)** the class list, serial or `tag_id`, and
each class's mandatory attributes (NRS decides, us to set); **(3)** Vendra 54
deployed before a furniture receipt (us); **(4)** the conflicting grants,
re-measured on the production tenant on the day (owner decides); **(5)**
INT-06 against the real SAP endpoint — never yet done — including mode D2
and the SAP asset-class mapping, blank today, which makes SAP reject the
master (SAP, NRS, us); **(6)** an in-flight candidate when the switch is
turned off: **nothing happens to it** — measured
(`test_turning_the_switch_off_leaves_an_in_flight_unit_in_the_chain`): it
stays a candidate, hidden, and its remaining gates still fire; there is no
"release all", by design; **(7)** who may turn the gates off (today the
Asset Manager can); **(8)** legacy placeholder serials that a receipt would
collide with; **(9)** a rejected unit has no way back (A3); **(10)** nobody
is notified a unit waits on them (Section 7); **(11)** the label's Code 128
on small labels; **(12)** the deployed check after every deploy (owner,
Turnstile); **(13)** demo personas off the production tenant; **(14)** the
verification pass's three follow-ups.

## Deviations, with why

1. **Five handoff assumptions did not hold** — table at the top; each built
   around and recorded.
2. **Store = Asset Officer** in the exclusion table, not Asset User (above).
3. **Rule 2 applies to every writer, not only the API**, with credentials'
   users and module install/upgrade outside it — a combination of roles is
   wrong whoever grants it.
4. **The readiness route is unauthenticated** — the person who needs it is
   checking a deploy and nothing scripted can sign in on the cluster.
5. **The asset now publishes four additive keys** (`colour`, `material`,
   `dimensions`, `identification_mode`) beyond §7's "only the category
   fields": a key the API accepts must be readable back
   (`test_published_names_resolve`). Null on every pre-existing record; the
   switch-off suite proves nothing else moved.
6. **PR #116 merged into this branch**, not waited for — CI-green, owner-
   blocked at the merge; it is the reason CI was red on `dev`.

## Not done — and why

- **The deployed check on `staging`** — the owner's (Turnstile), top of
  this report. **Not done by design:** Turnstile stays on everywhere; the
  switch is unchanged on every tenant (on for `staging`, off for the rest).
- **Needs the owner:** the PR merge, the deploy (`deploy-dev`, `upgrade-19`).

## Commits

| Commit | What |
|---|---|
| `e3e5525` (on `dev`) | Step 0: the instruction file, evaluation §8, the superseded draft |
| `f4442ec` | PR #116 (`fix/gate-fired-fidelity`) merged in — CI-green, not yet merged to `dev` |
| `dea6201` | the server: D3, P4, P5, P8, Section 12, rule 2, the labels off |
| `33961f4` | the app: categories, the tag_id affix, Role exclusions, the asset form, the Create-person dialog |
| `2cf57c3` | the suites green with the gates on; the new tests; specs 57 and 58 |
| (this commit) | decisions, CHANGELOG, endpoint reference, CLAUDE.md, STATUS, GO-LIVE §29, this report and its evidence |

## The standing sentence check

Every refusal this handoff adds says what happened and what to do, in words,
naming the thing — the class, the field, the earlier act and its date, the
person a unit waits on, both roles and the reason, the module to upgrade —
and none says "permission denied" (asserted in `test_a_two_gates_refusal_at_
affix_is_a_409`, spec 57 (b), and the handoff-50 words guard in the module
suite, green). Two sentences are deliberately someone else's: the
missing-serial refusal is Vendra's own, so a storekeeper reads one sentence
in both systems; the Phase E sentence is the handoff's, verbatim.
