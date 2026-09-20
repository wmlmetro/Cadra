# Report 27 — What has happened to this asset

**Branch:** `feat/asset-history` · **Base:** `dev` at `79a5de0`.

**Needs the owner:** the PR merge, and nothing else. No stored field was added, so there is no migration, no module upgrade and no tenant fan-out — a restart picks it up. One decision is waiting for NRS and the owner and is *not* engineering's: §5.

**The one sentence you asked for, in plain words:** *NRS watched an asset being moved from one location to another, and nothing the system wrote down about that move is protected from being edited or deleted afterwards.* The reassignment to another employee, which they also watched, is protected. Those were recorded by two different mechanisms built to two different standards, and until this handoff no screen showed either.

---

## 1 · §A — what actually has a record

Measured before anything was built: three read-only traces through the code, and SQL against four tenants. "Altered" means through the application.

| What happened | Is there a record with a real time and a real person? | Can it be edited or deleted afterwards, and by whom? | Does it reach back? |
|---|---|---|---|
| **Custodian changed** | **Yes, both.** `nrs.asset.custody`: when, from, to, who moved it, why, `source`. | **No.** Refused to everyone, an administrator using sudo included, and the asset beneath it cannot be deleted. *The refusal is Python — there is no database trigger — and one seed script deletes the table by raw SQL behind an explicit flag.* | To 2026-09-09, when the recorder landed. 674 older links were reconstructed from chatter and say `tracking_backfill`. |
| **Registered** (incl. from Vendra) | **Yes.** `create_date` / `create_uid` — since handoff 08 that is the API client's own user, so a Vendra registration says Vendra. | Not editable. Gone if an asset manager deletes the asset — which only a custody link prevents. | Always. |
| **Tag issued** | Yes — the label row's creation stamp. | The label row is deletable by an asset manager. | Always. |
| **Tag printed · affixed** | Yes, both, stamped from the acting user. | Refused to an ordinary write — but the guard is a context key the *caller* supplies, so a user with write access can set it over XML-RPC. Only the **last** print is kept. | Handoffs 03 and 10. |
| **Disposal approved** | Yes, both. | Not writable over the API — **but both fields are ordinary inputs on the Odoo form**, so an asset manager can rewrite the approver. A rewrite leaves a chatter line. *(I first recorded this as "guarded". It is not — §6.)* | Handoff 23. |
| **Sent to SAP / Tag-Issuing Unit** | Yes. `workflow.dispatch.log`. | Cannot be deleted (no unlink ACL); its delivery fields are editable by a workflow admin. | Handoffs 06 and 07. |
| **Location moved** | **Only sometimes.** A transfer row exists **only** when `POST /move` or a completed Odoo transfer made it. It holds a *date*, not a time, and **no field for who moved it**. Every other way of moving an asset — `PATCH`, the Odoo form, an import — leaves a chatter line and nothing else. | **Yes — edited or deleted by any asset manager, with no trace.** And it is `ondelete='cascade'`: delete the asset and its moves go with it. | `nrs19`: **1,146** tracked location changes, **1** transfer row. `jaizbankplc`: 103 and 103, because those went through `/move`. |
| **Status changed · condition changed** | Yes, both — **in chatter only.** | **Yes.** A `mail.message` can be deleted by anyone with write on the asset, which is the same group that can change the status. | Since the field was tracked. |
| **Verified** | **A date, and whoever saved it — in chatter only.** On the asset itself: one overwritten date. The app's **Verify** button is `PATCH {last_verified_date: today}`; it never calls the method that records a verifier. | Yes. | No record anywhere says a physical check was made. |
| **Disposal carried out** | A date. **No person.** | Tracked. | Handoff 16. |
| **A cost, a SAP field, or a GRN / PO / vendor reference changed** | **No. Nothing.** Overwritten in place. | — | — |
| **Planned maintenance performed** | One overwritten date, no person, no row per visit. | Yes. | — |

**`A mail.message is not evidence; the custody chain is` — and the chain is the only one.** There is no audit-log module installed or vendored. Everything that is not custody is a mutable row, an overwritten column, or chatter.

**Two corrections to the handoff, with evidence.**

1. **`include=transfers` is not "built, tested and correct" as a history source.** It is built and tested. It is also capped at the last 20, carries no actor and no time, and — per the table — covers a small minority of real location changes. `/history` therefore reads the transfer rows directly and joins them to the chatter row of the move.
2. **"674 rows were backfilled" is an estate figure, not an NRS one.** On `nrs19` the chain holds **1** link. 6,643 of its assets are held by somebody and no link says how — every one assigned at creation on 2026-08-06, a month before the recorder. The chain is not broken; it does not reach back, and the history now says so per asset.

A comment beside the provenance block of `_WRITABLE_FIELDS` says a later change to a GRN reference *"is tracked on the asset's mail.thread"*. **It is not** — none of the six fields carries `tracking=True`. Left as found; it is in GO-LIVE §13.3 for a ruling.

## 2 · What NRS saw that cannot be shown, and why

Everything they watched **can be shown**. What differs is what each line is worth, and the screen now says so on the line.

| They watched | It appears as | Resting on |
|---|---|---|
| Registered from Vendra | *Registered*, naming the Vendra client | the creation stamp |
| Tagged | *Tag issued · printed · affixed* | the label's guarded stamps |
| Assigned, then reassigned | *Custodian changed*, twice, with who moved it and why | **the append-only chain** |
| Moved between locations | *Location moved* | **an editable row** if the app's Move button was used; **a chatter line only** if it was done any other way |

**What cannot be shown at all** is named on every response, under *What Cadra does not record*: a changed cost, a changed SAP field, a changed GRN/PO reference, who carried out a disposal, a maintenance visit, and anything whose record has since been deleted. Their absence from the list is not evidence that they did not happen, and the list says that in words.

## 3 · What the timeline covers, where it begins, what it says when empty

`GET /api/v1/assets/<id>/history` — scope `assets:read`, newest first, `?sort=oldest` to read it forwards (the exact reverse, asserted). Not paged and not capped, for the reason the custody route is exempt. **Newest first because the reader's first question is where the asset is now and how it got there.** Assembled server-side per your ruling, as `nrs.asset.asset_history()`, so the ordering is asserted in-registry with the clock frozen.

- **Every event carries `evidence`** — `append_only`, `system_stamp`, `guarded_record`, `editable_record`, `chatter` — each defined in the response by what somebody can *do* to the record. This is the design decision the handoff did not make and §A forced: an ungraded list would show a deletable note and an append-only link as the same kind of line.
- **A reconstructed row says so**: `reconstructed: true`, and a visible *Reconstructed* pill. **An actor the record does not have is null** — the screen prints *No person recorded*. A transfer row with no chatter line has a null actor even though a `create_uid` was sitting there: that is who *raised* the transfer.
- **Chatter is included, graded as chatter.** Leaving it out would have made the screen cleaner and answered NRS worse — it is the only record of a status change, a verification and most moves. Tracked old/new values only; **message bodies are never published.**
- **One move is one line.** `/move` leaves a transfer row *and* a chatter row; they are joined on the from/to pair within 120 s. A failed join shows two lines — nothing is ever dropped on the strength of it.
- **Where it begins**: the list ends with when custody recording began on this system, and an amber notice when this asset was already held by somebody the chain never saw arrive.
- **Empty says so in words:** *"There is no recorded history for this asset beyond its registration on … That means nothing was recorded, which is not the same as nothing having happened."* The registration is still shown. (The tag minted inside the same `create` does not count as history — otherwise no asset would ever have been empty and the sentence could never have appeared.)

**A false claim on the screen NRS watched, fixed.** The Move dialog said *"Creates an immutable transfer record"*. It does not. The custody dialog said its trail was `mail.thread`; since handoff 14 it is the append-only chain. Both corrected.

**The bug the tests missed.** With 32 tests green, opening the tab showed an asset *changing hands before it was registered*. `create_date` carries microseconds; a custody link's time does not; so anything in the same second as the registration sorted ahead of it (`:44.000` < `:44.730`). That is every asset created already assigned. Fixed by sorting to the whole second with a fixed order inside it; the test was **proved to fail with the fix disabled** — `'custody_changed' != 'registered'` — before it was trusted. *An ordering nobody tests is an ordering that will be wrong* was your sentence; it was also wrong when tested, until somebody looked.

## 4 · Tests — full output is below; the denominators first

In CI's order, against `test19`:

| Suite | Result |
|---|---|
| `pytest tests/` | **861 passed, 8 skipped, 0 failed** |
| In-registry, CI's 11 modules, `--workers=0` | **0 failed, 0 error(s) of 561 tests** |
| Playwright — the four *Audit & Review* specs | **4 passed** |
| Front end — `tsc --noEmit`, `vite build` | clean, built |

**869 collected** = report 26's 849 (840 + 9) + 10 merged since (PRs #74, #75, the guard fix) + 10 new. **561** in-registry = 524 + 4 (PR #74) + 33 new. No `of 0 tests`, no `CRITICAL`.

**The skip count moved from 9 to 8 during this handoff, and I caused it.** The first full run was 860 passed / 9 skipped — report 26's nine, category for category. My Playwright spec then clicked **Verify** on a `test19` asset, so `?is_verified=true` matches a row for the first time and the partition test that skipped for want of data now runs and passes. Nothing in the suite changed; the tenant did. `CLAUDE.md` says the skip count is a function of the tenant, and this is that. **`test19`'s documented breakdown is now 8, with 3 partition-data-absent rather than 4.**

The e2e spec that was green throughout the period the tab was blank — *"detail tabs switch"* — clicks the tab and never reads it. Two specs now read it.

```
$ CADRA_API_BASE=http://test19.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q -rs
........................................................................ [  8%]
........................................................................ [ 16%]
........................................................................ [ 24%]
........................................................................ [ 33%]
........................................................................ [ 41%]
.......s................................................................ [ 49%]
.......................................................................s [ 57%]
................s.ss.s.................................................. [ 66%]
.................................................s...................... [ 74%]
........................................................................ [ 82%]
........................................................................ [ 91%]
........................................................................ [ 99%]
...ss                                                                    [100%]
SKIPPED [1] tests/test_integrations.py:107: this tenant has no active workflow.config, so the v1 callback refuses 503 and the replay path is unreachable from here
SKIPPED [1] tests/test_query_params.py:119: `is_tagged` published `null` as 'no filter' before this rule existed and keeps it
SKIPPED [1] tests/test_query_params.py:195: no data to partition on this tenant: `is_verified=true` matched 0 rows and `is_verified=false` matched 879.
SKIPPED [1] tests/test_query_params.py:195: no data to partition on this tenant: `has_sap_code=true` matched 0 rows and `has_sap_code=false` matched 879.
SKIPPED [1] tests/test_query_params.py:195: no data to partition on this tenant: `closed=true` matched 0 rows and `closed=false` matched 113.
SKIPPED [1] tests/test_query_params.py:195: no data to partition on this tenant: `is_staff_bus=true` matched 0 rows and `is_staff_bus=false` matched 0.
SKIPPED [1] tests/test_sap_reconciliation.py:324: no asset on this tenant carries a SAP asset number yet
SKIPPED [1] tests/test_turnstile.py:125: Turnstile is not configured on this deployment
SKIPPED [1] tests/test_turnstile.py:140: Turnstile is not configured on this deployment
860 passed, 9 skipped in 74.94s (0:01:14)

# …and again after the verification fixes, with the e2e Verify having run in between:
861 passed, 8 skipped in 77.18s (0:01:17)
# the skip that went: tests/test_query_params.py:195 `is_verified` — see above.

$ odoo -d test19 -u myservice_workflow,myservice_asset_depreciation,myservice_nrs_base,myservice_asset_register,myservice_request_core,myservice_request_fields,myservice_security,myservice_fleet_maintenance,myservice_barcode_station,myservice_api,myservice_identity --test-enable --stop-after-init --workers=0
odoo.tests.stats: myservice_api: 305 tests 28.95s 22594 queries
odoo.tests.stats: myservice_asset_depreciation: 16 tests 0.87s 542 queries
odoo.tests.stats: myservice_asset_register: 192 tests 20.84s 16163 queries
odoo.tests.stats: myservice_barcode_station: 6 tests 4.36s 889 queries
odoo.tests.stats: myservice_dashboard: 13 tests 0.29s 339 queries
odoo.tests.stats: myservice_fleet_maintenance: 21 tests 0.89s 992 queries
odoo.tests.stats: myservice_fm_dashboard: 10 tests 1.53s 1943 queries
odoo.tests.stats: myservice_identity: 20 tests 1.31s 949 queries
odoo.tests.stats: myservice_nrs_base: 10 tests 0.13s 171 queries
odoo.tests.stats: myservice_request_core: 10 tests 0.27s 274 queries
odoo.tests.stats: myservice_request_fields: 15 tests 0.45s 341 queries
odoo.tests.stats: myservice_security: 14 tests 0.34s 314 queries
odoo.tests.stats: myservice_workflow: 105 tests 5.41s 6193 queries
odoo.tests.result: 0 failed, 0 error(s) of 553 tests when loading database 'test19'

# …and again after the verification fixes (+8 tests; myservice_api 305 → 315 on the stats line, every other module unchanged):
odoo.tests.result: 0 failed, 0 error(s) of 561 tests when loading database 'test19'

$ E2E_ORIGIN=http://test19.localhost:8069 npx playwright test tests/06-asset-actions.spec.ts -g "audit & review|detail tabs switch"
  ✓  1 › detail tabs switch (2.2s)
  ✓  2 › audit & review says in words when there is no history (2.0s)
  ✓  3 › audit & review shows a verification, newest first, with what its record is worth (2.3s)
  3 passed (13.4s)
# …and after the verification fixes, with the canned-response spec added:
  ✓  4 › audit & review carries a reconstruction and a blank actor all the way to the screen (2.5s)
  4 passed (17.5s)

# The red-proof, fix DISABLED (`sort_at = at`):
FAIL: TestAssetHistoryOrder.test_nothing_sorts_before_the_registration_it_followed
AssertionError: 'custody_changed' != 'registered'
```

## 5 · §D — the approver NRS asked about

Recorded, not built, not designed: `docs/GO-LIVE.md` §13.1, with the date and what was asked. **Who can move an asset today:** anyone in `group_asset_manager`, in Odoo or — because `assets:write` is derived from that one group — over the API and the app. **There is no second person anywhere on the path:** `/move` creates its transfer at `done`, and no transfer on `test19` (0 of 18) or `jaizbankplc` (0 of 103) has an approver. `nrs.asset.transfer` already has `draft → approved → done` with an Approve button that stamps the approver; it is reachable only from Odoo and nothing in the API or app uses it. Requester and approver would today come from the same group, so *"needs an approver"* also needs *"who may not approve their own request"* — which is theirs to answer.

**§13.2 says the uncomfortable half:** if the answer is yes, an append-only record of the move has to come first. An approval recorded on a row an asset manager can delete is not an approval record.

## 6 · Deviations, and what the verification pass found

- **Step 0 as written omitted committing the instruction file**, which `CLAUDE.md` makes the first act of every handoff. Done anyway (`79a5de0`), before branching.
- **`CLAUDE.md` said there is no handoff 27.** Its Backlog paragraph and `GO-LIVE.md` Part II were amended to say the cycle reopened and why, rather than left contradicting the repository.
- **Not built, deliberately:** an append-only location record. It is the real fix for the largest finding here and has the custody recorder's exact shape — but it is a stored model and a fan-out across every tenant, and the instruction was *"an ordering and a merge, not a new record"*. GO-LIVE §13.2.
- **Noted, not touched** (GO-LIVE §13.3): the *Legacy Data* tab prints *"Migrated from FIRS legacy system · March 2024"* on every asset, hardcoded, including ones Vendra registered this month — the same class of defect, one tab along. `RequestDetail.tsx` still prints `"System"` for a message with no author. The app fires six API calls before login and collects six 401s. The e2e file's header still describes Move and Transfer custody as broken in the UI; the code was fixed and the comment was not.

### What the verification pass found

A fresh reviewer — not an author — read the diff against §A–§D and the architecture rules. **No policy breach and nothing wrong with the four honesty requirements in the builder. Two blocking findings, both against me, both fixed.**

**Blocking 1 — I overclaimed, in the module written to prevent overclaiming.** I graded *Disposal approved* `guarded_record` and dropped its chatter rows as "superseded by the guarded columns". They are not guarded: no `write` refuses them and both are inputs on the Odoo form. Their absence from `_WRITABLE_FIELDS` is a fact about one door, and I read it as a fact about the record. **The consequence would have been this:** an asset manager changes who approved a disposal; the history shows the new name, graded *Protected field*, and the only trace of the edit is hidden. I had taken the word "guarded" from a research summary and never opened the model. The false claim had already spread to five documents. Now: the approval is `editable_record`, only the row of the *first* stamping is dropped, every later rewrite is its own event carrying the old and the new name, and `test_a_rewritten_disposal_approver_is_visible` holds it.

**Blocking 2 — a false cross-reference.** `DECISIONS.md` said the `RequestDetail.tsx` `"System"` idiom was noted in GO-LIVE §13.3. It was not. It is now (item 9).

**Should-fix, all fixed:** an outbox row was titled *"Sent to an external system"* even when `pending` or `dead` (now *"Event for an external system"*) · a same-day tag scrap sorted at midnight, **before the issue of the tag it scrapped** — the same class as the ordering bug in §3, now using the replacement approval's real instant and approver · the summary sentence counted `chatter + editable_record` as "can be deleted", understating it, since a tag label is deletable too (now counts the one grade nobody can alter) · an unmatched transfer now says its time is when the transfer was *recorded* · the OpenAPI enums were hand-copied and are now read from the model's constants · the INT-10 table omitted two event types · two mutations did not refresh the history (raising a request, generating tags) · a record with no timestamp would have cost an asset its whole history with a 500; it is now omitted and counted in `fidelity.undated_records_omitted` · the honesty rules were untested past the Python, so a Playwright spec now feeds the screen a canned reconstruction, a blank actor, an unknown event type and an unknown grade, and asserts all four render.

**Not fixed, and why:** evidence-grade meanings are hover-only, so nothing on a touch screen (the short label is always visible). `recording_began_at` is the oldest custody row's `create_date`, which on a tenant with no backfilled rows is the first link ever rather than the day the recorder was installed — true to its name, imprecise as "when recording began".

### New exposures to `assets:read` — for your ruling

The history publishes things no existing `assets:read` route did. None is a message body; all are inherent to answering *who*. **(a)** the name of the internal user who made each tracked change, and the historical old/new values of every tracked field, including free-text `disposal_reason` (its current value was already published); **(b)** a transfer's recorder, approver and approval time; **(c)** the creating user of the asset and of each tag; **(d)** outbox reference, event type, status and sender. No tracked field on `nrs.asset` carries `groups=`, so `sudo()` bypasses no field-level restriction. **One crossed a scope boundary and I closed it rather than ask:** a maintenance request's reference, which belongs to `requests:read`. A route cannot see its caller's scopes today (`require_jwt` checks and discards them), so the event says a request was raised, when and by whom, and never which. GO-LIVE §13.3 item 12.

## 7 · Wall-clock and the correction share

**About 50 minutes**, Step 0 commit (19:31) to the last green run (20:21), read off the clock.

**Correction share: about half.** Three corrections, in the order they cost time, and none was found by a test written beforehand:

1. **The ordering bug** (§3) — found by opening the screen after 32 tests were green. ~8 minutes including the red-proof.
2. **The verification pass's findings** (§6) — one overclaim of mine that had reached five documents, nine should-fixes, eight new tests, a second full run of both suites. ~17 minutes. This is the largest share and it is the pass doing its job.
3. **My own build broke the locally served app.** `npm run build` takes `BASE_PATH=/` from `.env.local`, and the dev proxy serves that same `dist/` under `/app/`, so the bundle pointed at asset URLs that 404. `dist/` is gitignored, nothing was committed, and it is rebuilt correctly — but **anyone who runs a plain `npm run build` here silently breaks `http://<tenant>.localhost:8069/app/`**, and nothing says so. That belongs in `ENVIRONMENT-FACTS.md`; I have not added it, because I measured it once and in passing.

**What I would tell the next Builder:** the first §A draft came from three research summaries, and the one claim I did not check against the file — "guarded" — was the one that was wrong.

## Questions

1. **Should location moves get the custody treatment** — an append-only record written in `nrs.asset.write`, where every writer passes? It is a stored model and a full fan-out. I would do it before anything is built on §5.
2. **Should `PATCH` stop accepting `location_id`**, or start writing a transfer row when it does? Today it is the quiet way to move an asset leaving the least behind, and an integration has no way to know that short of reading the changelog.
3. **Should the app's Verify button call `action_verify`** over a real route, so a verification records a verifier? Today it records a date.
4. **The `_WRITABLE_FIELDS` comment** claiming provenance changes are tracked: fix the comment, or make it true by tracking the six fields? The second is a one-line-per-field change with no migration.

## Commits

- `79a5de0` — docs: handoff 27 — what has happened to this asset (the instruction file, on `dev`)
- `a008189` — feat(api): what has happened to this asset — one ordered history, graded by what its record is worth
- this report, in the commit after it
