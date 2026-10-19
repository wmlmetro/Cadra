# Report — Handoff 63b: the faster loop

Branch `chore/the-faster-loop`, from `dev` at `8e00385` (handoff 63, PR
#122, merged). No module version changed: Python only, and a tag-number
sequence that creates itself per prefix on first use.

## Needs the owner

1. **The PR merge.** The Builder's permission layer refuses `gh pr merge`.
2. **The deploy:** `deploy-dev`, then roll the Odoo backend (`deploy-19`,
   or `upgrade-19` as for report 62 — no schema change, no module to
   upgrade). Three things change for a live tenant: the configuration
   report's day (announced), the tag-number mint, and the category save.
3. **`test19`'s `NRS-FURN-018`** (GO-LIVE §32.4): two of Vendra's chairs,
   assets 106911 and 106912, carry it — the 69th number active on two
   assets of `test19`'s 21,121 active labels. Listed, not renumbered:
   which chair keeps it is a person's choice (the station's *Replace tag*).

## In plain words

Every handoff was spending most of its hours waiting for tests on a test
database that grows each week, and repeating on a laptop what CI already
does. Three changes fix the loop. **CI now proves both settings of the
receipt gates on every push**, side by side, in the same 13 minutes one
setting took. **A clean test database can be made in about five seconds**
(`test19f`, copied from a template), so the suite runs on the same small,
known database every time: 9 minutes instead of 15 with the gates off, 15
instead of 25 with them on. **Running tests in parallel was tried and does
not work yet**: the tests share one database's state.

Two real defects were fixed on the way. **Two receipts arriving at the same
moment could get the same tag number** — Vendra saw it with two chairs; the
number now comes from a counter the database guarantees never repeats, and
the rare clash left gets a clear "try again" answer. **The settings-change
report used a London-style day**, so for an hour after midnight a change
just made was missing from "today"; it now uses the Lagos day like
everything else. A slow screen got faster: saving a category's
depreciation policy on 19,000 assets went from 13–21 seconds to under 10.

## What was built

- **§1 — CI, both switch states** (`ci.yml`): `bootstrap-and-test` is a
  matrix `gates: [off, on]`; each leg writes `cadra.receipt.gated` after
  the personas and checks it. CI also seeds the fixtures below.
- **§2 — `scripts/fresh_test_tenant.sh <tenant> [--rebuild-template]`.**
  Restores `test19f` (or `test19`) from `cadra_test_template` with
  `CREATE DATABASE … TEMPLATE`, copies the filestore, points
  `web.base.url` at the tenant, copies creds and personas. The template is
  built the way CI builds its database (`.env.example`'s module list,
  `bootstrap.py` core seed, class `test`, personas) plus
  `scripts/seed_test_template_fixtures.py` — the `h41_*` accounts, two
  employees, the Mailpit row — which `test19` carries and a fresh database
  does not (24 of the first `test19f`'s 37 skips). It is marked
  `IS_TEMPLATE … ALLOW_CONNECTIONS false`, so Odoo's scheduler never sees
  it. Refuses a tenant off the allow-list (`nrs19`, client replicas and
  `staging` by name), an existing database not marked `test`, a remote
  `DOCKER_HOST`. **The suites use `test19f` from now on:** faster, and a run
  does not depend on what earlier runs left. `test19` stays as it is.
- **§3a — xdist: not adopted.** `-n 4` on a fresh `test19f`: 30 failed, 2
  errors. The first five: `test_raising_a_move_request_writes_nothing_to_the_asset`,
  `test_a_body_that_names_who_decided_is_refused[state]`,
  `test_an_asset_code_beats_a_serial_that_reads_the_same`,
  `test_cannot_delete_a_category_that_holds_assets`,
  `test_a_custody_transfer_is_an_append_only_event`. Causes: the tag race
  below (10 × 409), whole-register counts (`115 == 110`), and one test
  flipping the tenant-wide gates switch under the others ("0 of 1 serial
  numbers captured"). Stopped there; no test rewritten. The report hook now
  collects in `pytest_runtest_logreport`, so `-n` would still write it.
- **§3b — the category save.** 63 had halved it; the test still took 29.8 s
  of its 30 s timeout. Profiled on `test19`'s 19,042 (rolled back): the
  depreciation module's `write` restated the class AND the route did again,
  and each restatement built every schedule twice (value, end date) —
  76,168 builds. The route's second call is gone; `engine.summary_at`
  builds once, pinned equal to the two old calls over 38,400 policies.
  Mail tracking of the policy fields (3.7 s) is kept: it is the history.
- **§3c — the Lagos day** (`audit_configuration.lagos_days_in_utc`).
  BEHAVIOUR CHANGE in the CHANGELOG. The four HTTP tests ask
  `conftest.lagos_today()` instead of the machine's date (CI's is UTC — it
  would have moved the failing hour, not removed it); spec 59 likewise.
- **§3b amended — the tag race.** `max(number) + 1` read through each
  request's REPEATABLE READ snapshot; a lock cannot fix a snapshot taken
  before it. Now a Postgres sequence per prefix, created on first use under
  an advisory lock, started at the highest issued number, lifted past a
  number issued around it. The collision left answers
  `409 tag_number_taken`, `details.retryable: true` (new code, CHANGELOG,
  endpoint reference); every other unique violation stays `409 conflict`.
- **Step 0 / found:** handoff 63's own CI was red — 1 error of 1,264 in
  `test_a_number_already_active_on_a_second_asset_is_not_reprinted`, which a
  fresh database's new index broke; fixed in this branch's first commit.

## The numbers

| | Before | After |
|---|---|---|
| Full pytest, gates off (local) | `test19`: 1,491 passed, 7 skipped of 1,498, **14 m 42 s** | `test19f`: 1,488 passed, 10 skipped of 1,498, **9 m 06 s** |
| Full pytest, gates on (local) | `test19` (report 63): 1,486 passed, 5 failed, 7 skipped, **24 m 36 s** | `test19f`: 1,488 passed, 10 skipped of 1,498, **15 m 05 s** |
| CI, both jobs (wall clock) | one job, gates off: **12 m 46 s** (run 39183282828) | two legs in parallel: **13 m 04 s** (off) and **14 m 55 s** (on), run 39217153227 on HEAD; 12 m 55 s each on run 39209513059 |
| Category policy save (`test19`, 19,042 assets, HTTP) | save 13.2 s, restore 20.6 s; the test 29.8 s | save 9.7 s, restore 9.7 s; the test 19.8 s |
| Fresh test tenant, restore time | — | **4.0–8.4 s** (template rebuild 145–153 s) |

`test19`: 23,024 assets, 332 MB, largest class Generator 20,680 (2026-10-19).
`test19f`: 0 assets, 52 MB. Skips on `test19f` (10): `test19`'s seven
categories, plus `has_deadline` and a second page of requests (no data), and
the suite's credential already holding `auditor`. CI's skips 39 → 16 of 1,498.

Tag race, `tests/test_tag_number_race.py` (20 concurrent receipts, one
prefix): old code 2 and 7 of 20 refused `409`; new code 20 distinct numbers,
6 of 6 runs. In-registry on `test19f`: `myservice_api` (the three boundary
classes) 0 failed of 21; `myservice_asset_depreciation` 0 failed of 17;
`myservice_asset_register` 0 failed, 0 errors of 503 (report 63's denominator). Final full local run (gates off, fresh
`test19f`, `ee98fbe`): **1,489 passed, 10 skipped of 1,499, 9 m 42 s**
(`63b-evidence/final-pytest-gates-off-test19f.txt`). **CI on HEAD** (`ee98fbe`, run [39217153227](https://github.com/wmlmetro/Cadra/actions/runs/39217153227)): green — off 1,483 passed, 16 skipped of 1,499 in 2 m 30 s; on the same in 4 m 10 s; modules 0 failed, 0 errors of 1,268 in both.

**The documented end-of-handoff command** (CLAUDE.md, Speed rule 3):
```
scripts/fresh_test_tenant.sh test19f
CADRA_API_BASE=http://test19f.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q
```
~9 min gates off, ~15 min gates on (switch set on `test19f` first) — then
cite CI's two legs for the other state and the module suites.

## Deviations and questions

1. **Step 0's CLAUDE.md commit was already done** (report 63, `b0de011`).
2. **The handoff was amended mid-run** (07:27): 3 h budget, the tag race.
   Committed as given (`90b3686`).
3. **I handed `test19` back to the Vendra Builder** at 07:03, at its
   session's request: my before-run had turned its gates off, which is why
   its receipts came back `registered`. Everything after ran on `test19f`,
   except the category profile, done after it confirmed it was finished.
   The permission layer refused a dump-copy of `test19` while it was busy.
4. **CI now seeds the `test19` fixtures too** — not asked; 23 more tests run
   in CI. It writes the Mailpit row there as well, harmless (no Mailpit).
5. **For the Architect:** (a) `GET /reports/access-changes` still bounds UTC
   days — the same shape, not changed. (b) The gates-on CI leg proves the
   asset-code race only; the tag sequence is proved by the gates-off leg.
   (c) the endpoint reference lists `unprocessable` (422), which
   `utils.py` does not define — found, not changed.
6. **Verification pass** (fresh agent, read-only): one defect in my first
   draft — the sequence draw always called `setval`, which could wind the
   sequence back between another request's `nextval` and its own; fixed
   (`setval` only to lift), race rerun 3/3. Also fixed: a stale skip count
   in ENVIRONMENT-FACTS, spec 59's UTC dates, two wording nits. It found
   nothing in the CI YAML, the Lagos edges, the depreciation equivalence or
   the error-code mapping. My own find while proving it: a restored tenant
   kept the template's `web.base.url = http://localhost:8099`, and an
   in-registry PDF render hung 20 min on it; the restore now sets it.
7. **CI caught one of mine:** run 39214029304 (`29a34f9`) — 1 failed,
   1,482 passed, 16 skipped of 1,499 in both legs:
   `test_every_catch_all_says_what_it_is_hiding`, the new engine test's
   `except Exception` without its marker. Fixed in `ee98fbe`. I had run
   only the module suite for that file, not the source guards — the
   rule-2 shortcut's cost, paid in one CI cycle.

## Where the time went

Wall clock 06:46 → ~08:55 Lagos, about 2 h 10 m of the 3 h budget;
phases overlap because the long runs went in the background.

- build (CI matrix, script and template, the Lagos day, category save, tag
  race, docs): 06:46–08:08, ~80 min of it hands-on;
- tests: before-run on `test19` 06:46–07:01; `test19f` runs (serial,
  xdist, gates on) 07:10–07:53; module suites and race runs 07:55–08:36;
  final run 08:37–08:47 — ~75 min of runs, most of it beside other work;
- verification pass: 08:08–08:14, its fixes and re-proof 08:14–08:36;
- report: 08:31–08:55.
