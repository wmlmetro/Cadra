# CLAUDE.md — Cadra (myservicenrs)

Guidance for Claude Code and any developer working in this repository. It holds what you need **before and during** your first command. The record of how the project got here lives in the files below — read the ones relevant to what you are about to change, and keep this file current as part of every change.

- **`docs/DECISIONS.md`** — every decision, its reasoning, and the handoff that landed it. Read the entries for the area you are changing.
- **`docs/STATUS.md`** — what is built, with the measurements and evidence behind each item.
- **`docs/ENVIRONMENT-FACTS.md`** — things true of these machines that cost somebody an afternoon. Read it before blaming your code.
- **`docs/DEPLOYMENT.md`** — the `prod` and `dev` profiles, and how a **client** is actually deployed. Rewritten in handoff 20; it says which deployment shape it describes in its first paragraph.
- **`docs/api/EXTERNAL-SURFACES.md`** — every first-party HTTP route *outside* `/api/v1`, who calls it, and whether changing it breaks something.
- **`docs/integrations/INT-10-audit-access.md`** — the audit and value-for-money read-access contract, and which clauses Cadra has closed.
- **Canonical spec** — the PRD and NRS specification under `docs/` (`Cadra_Platform_PRD_v0.4.docx`, `Cadra_at_NRS_Specification_v0.1.docx`). When README and spec disagree, the spec wins.

## Working model — two Claude roles

This project is run by **two cooperating Claude sessions**, the same way its sibling `vendra_network` is:

1. **The Architect (Claude in Cowork/cloud)** — owns the plan, the cross-system specs, this file, and quality control. Writes build instructions, reviews finished work, and holds the integration picture across Cadra, Vendra and SAP. Does not run Odoo.
2. **The Builder (Claude Code in the IDE, this machine)** — executes build instructions: writes code, runs the stack, runs pytest, and handles git. **If you are Claude Code reading this in the IDE, you are the Builder.**

**Handoff protocol** (`docs/handoffs/`):
- The Architect writes numbered instruction files: `docs/handoffs/NN-<slug>.md` — context, steps, acceptance checks, what to report.
- The Builder executes the latest un-reported handoff and writes `docs/handoffs/NN-REPORT.md`: what was run, full test output (not a summary), decisions made and why, deviations from the instructions, open questions, commit hashes.
- **Deviating from a handoff is expected when the handoff is wrong.** Say so in the report with evidence; do not silently comply with a bad instruction, and do not silently improvise around it either.
- **When a handoff asserts that one code path is the only writer of a field, VERIFY IT before building on it.** Handoff 14 said the transfer route was the only writer of `custodian_id`; an exhaustive search found six, including `_WRITABLE_FIELDS`, the Transfers UI, an employee-departure routine and three seed scripts. Recording at the asserted single point would have produced an audit record with invisible holes. **A claim of exclusivity is the Architect's guess unless a search backs it**, and it has now cost two handoffs.
- **Never write "zero have it". Write "zero of how many."** A count of rows carrying a value is meaningless without the count of rows, and a zero taken on its own reads as proof of whatever you already believed. Handoff 31 wrote *"a request's location has never been saved, by anyone"* into nine places on the evidence that `nrs19` had zero requests with a location — **`nrs19` has zero requests**; `cadra19` had eighty and every one of them had a location. The same shape had already produced *"1,146 tracked moves"* (handoff 27, in fact one six-second seeding script) and *"811 `exception` rows"* (handoff 30, every one a fixture). **A denominator is not decoration**: it is what tells a real absence from a table nobody has filled in, and it costs one extra clause. This has now caught three defects in three handoffs and knowing about it has demonstrably not prevented the next one, which is why it is a rule rather than advice. The same instinct as *check the denominator, never the exit code* below, applied to data instead of to a test run.
- The Builder never edits the handoff instruction files or the specs; corrections flow through reports.
- After pushing, notify the Architect: `ListAgents` → `SendMessage` to **`claude-fc [01f312]`**, first line self-contained ("Handoff 01 complete — …"). If it is not listed, skip silently; the Architect polls the repo. The report and commits are the source of truth; the message is only a doorbell.
- **Closing step, every handoff:** after the report is pushed and before notifying the Architect, `git checkout dev && git pull --rebase && git push origin dev`. Leave the working tree on `dev`, current, with nothing local waiting. Never force a rejected push — report it and stop.

### Handoff authoring rules (Architect)

**A handoff must be executable end to end with nothing left for the owner to do by hand.** Every one:

1. **Opens with Step 0 — get to the right state.** Commit the instruction file, merge the previous work, run whatever migration, module upgrade or per-tenant fan-out that merge requires, verify it took, then create the new branch. Never assume the repo or the databases are already where the work needs them.
2. **Ends with the work landed** — committed, pushed, PR opened, report written, Architect notified. "Done" means in the remote, not in the working tree.
3. **Names anything that genuinely needs the owner** in a "Needs the owner" block at the top — a credential, a production deploy, an approval, a business decision — **including the final PR merge: the Builder's permission layer refuses `gh pr merge`, so every handoff ending in a PR is owner-blocked at that step.** Explicit and up front, never discovered halfway through.

If a handoff cannot be completed without a manual step that is not in it, that is a defect in the handoff — say so in the report.

### How the next handoff's instructions get here

The Architect writes `docs/handoffs/NN-<slug>.md` straight into the working tree and makes **no git commit, no push, no fetch and no ref update.** Its sandbox can write a file but cannot unlink one, so every aborted git write leaves a lock file that breaks the next command run here — which has twice cost the owner a debugging round and once left six orphaned files blocking a pull.

**So Step 0 of every handoff begins by committing the instruction file you were given**, on `dev`, before you create your own branch:

```bash
git checkout dev && git pull --ff-only
git add docs/handoffs/NN-<slug>.md
git commit -m "docs: handoff NN — <title>"
git push origin dev
git checkout -b <your-branch>
```

**The owner runs no git commands at any point in the cycle.** Their whole involvement is merging the previous pull request and starting you. A handoff that asks them for a git command is a defect in the handoff. **Merge the previous handoff's PR before the Architect writes the next one**, so the instruction file lands on a base that has stopped moving.

### Parallel execution (Builder)

Work a handoff with **multiple subagents in parallel** when its steps are independent.

- **Partition by file, never by concern.** Two agents must never edit the same file. Split along module/controller boundaries.
- **Serialize anything sharing state**: anything touching the database or the running stack (module upgrade, seeds, migrations), and all `git` operations, run one at a time in the main session.
- **Serialise every `--stop-after-init` run, not only the ones that write.** On this host a second registry load is itself the contended resource: handoff 14 took eight Postgres crash-restarts, four of them with two upgrades running against *different* databases. Different databases do not help — memory is the shared thing, not the registry lock. `docs/ENVIRONMENT-FACTS.md` carries the measurement and the recipe.
- **Fan out freely on read-heavy work** — reading Odoo core for the right hook, tracing how an existing endpoint does something, checking a model's field definitions. This is where parallelism pays.
- **Finish with a fresh verification agent** (not an author) reviewing the diff against the handoff's acceptance criteria and the rules below. Its findings go in the report.
- Give each agent the full contract: this file, the relevant spec section, the exact files it owns, and what to return. Launch independent agents in one message; ~2–5 per handoff.

## Preferences (owner)

- **When a handoff report comes back, explain in plain English what happened first** — what was built, what broke, what it means — before accepting it, ruling on anything, or writing the next handoff. Plain language first, code second — the owner is piecing the whole ecosystem together. Plain terms means plain: no interface numbers doing the work of a sentence, no file paths standing in for an explanation. Then do the usual.
- Plan before building; keep this file current as part of every change, not after the fact.
- Deliverables that matter get committed into the repo, not left in chat.
- **Acting from a cold start proves only the cold start.** A screen is proved by the flow a person actually takes — list, asset, act, back to the list — in ONE session, reading the row in Postgres. Handoff 29's headline fix did not hold in that flow (`refetchOnMount: false`), and its harness could not see it because it loaded every page fresh: it clicked the real button, read the real row, and still missed that the same session's other screens were lying.
- **A document that says how to operate this system is fact-checked against the files it describes whenever a handoff touches the area it covers, and a claim nobody can check is deleted rather than carried.** `docs/DEPLOYMENT.md` was wrong in nearly every claim it made — the image, the entrypoint, the credential it named — because nobody had read it end to end against the compose files since it was written, and a runbook that is confidently wrong is worse than one that is missing.

## What this is, and why the API's shape matters beyond it

**Cadra** — the asset and facilities register for the Nigeria Revenue Service (NRS), built on **Odoo 19** with a versioned REST layer (`/api/v1/*`) in `myservice_api` over the ITSM, asset register, security and FM modules. **Every profile is on 19, and that is asserted rather than assumed:** the base `docker-compose.yml` pins the image, `tests/test_deployment_profile.py` fails if any profile resolves to another major, and CI checks the same fact against the real `docker compose config`. Handoff 20 closed the gap — `prod`, the profile a client is actually deployed with, resolved to `cadra-odoo:15.0-dev` for the whole migration because the base built 15 and only the 19 overlay overrode it — and deleted the Odoo 15 stack files (`docker-compose.dev.yml`, `config/odoo.dev.conf`, `Dockerfile.odoo.dev`, `Dockerfile.odoo.k8s`) so there is nothing left to point at. `CADRA_PROFILE=dev` now means `docker-compose.19.yml`; `dev19` is an alias. **`dist/` is what the migration has left**: the Odoo 15 vendor tree, off every 19 addons path, whose modules `crnd-19/` hand-ports.

Cadra is one of three systems in the NRS integration programme, defined by *"End-to-End Integration Flow — Cadra · Vendra · SAP"* (September 2026). **Vendra** (`Frappe/apps/vendra_network`, Frappe/ERPNext) does digital goods receipt, GRN, classification and inventory; **Cadra** (`wmlmetro/Cadra`, Odoo) owns the asset register, identity, tagging, custody and lifecycle; **SAP** (NRS-owned) holds POs, financial postings, SAP asset codes and payment.

**Interfaces Cadra owns:** INT-03 (Vendra → Cadra, asset-classified receipt hand-off — *inbound to our API*), INT-04/05 (Cadra ↔ Tag-Issuing Unit), INT-06/07 (Cadra ↔ SAP asset master and dual-code reconciliation), INT-09 (lifecycle events → SAP).

**Practical consequence:** `POST /api/v1/assets` is no longer only a UI-adjacent endpoint — it is a contract another system builds against. Changes to `_WRITABLE_FIELDS`, the response envelope, the `condition`/`state` enums, or idempotency behaviour are **breaking changes for Vendra**. Treat them as versioned API changes, and say so in the report when you touch them.

## Stack & environment

- **Runtime: Odoo 19.0** (`cadra-odoo:19.0-dev`, built from `Dockerfile.odoo.19.dev`) · PostgreSQL 13 · Docker Compose · nginx (dev) / Caddy (prod).
- **Bring-up needs BOTH compose files** — the base alone gives the wrong `odoo.conf` and no proxy — **and `ODOO_DBFILTER` decides which tenants are reachable**:
  ```
  ODOO_DBFILTER='^%d$' docker compose -f docker-compose.yml -f docker-compose.19.yml up -d
  ```
  Without the export you get the committed default `^odoo$` — one database on every host, which is what CI wants and almost certainly not what you want locally.
- **Tenancy is host-based.** With `ODOO_DBFILTER='^%d$'`, `http://localhost:8069` answers *"No database is selected"* and a database is reached as `http://<db>.localhost:8069`. Local databases: `cadra19`, `nrs19`, `gtb19`, `test19` (19-era) and `nrs`, `gtb`, `lasg`, `jaizbankplc` (15-era replicas now served by the 19 container, all at `base = 19.0.1.3`).
- **`odoo` is not a database you can test against**, and `.env.example` names it (`POSTGRES_DB=odoo`, `ODOO_DBFILTER=^odoo$`). It is a genuine 15-era leftover that a 19 worker cannot load, and it fails with an error that names nothing relevant — see `docs/ENVIRONMENT-FACTS.md` for the exact text, which is not what you would guess. The defaults are right for CI, which creates its own single database, and wrong for every command in this file: export `ODOO_DBFILTER='^%d$'` and name a real tenant.
- **Editing a bind-mounted config file breaks its mount.** `./config/odoo.19.conf` is mounted as a *single file*; anything that replaces the inode rather than writing in place (most editors, and every agent file tool) leaves the container with **no `/etc/odoo/odoo.conf` at all** — every `exec … odoo -c` then fails with a confusing `psycopg2.OperationalError` about a unix socket, because the defaults have no `db_host`. `docker compose … up -d --force-recreate odoo` after any config edit.
- **A test will not run against a database that is not marked as a test database.** Since handoff 25, both suites read `cadra.database_class` from the target database and refuse unless it is `test`. **Absent refuses**, so a tenant nobody has classified is refused exactly as a production one is. There is no bypass flag and no override variable — if a database should accept test writes, mark it, and the refusal prints the command. Locally, `test19` is marked `test` and `jaizbankplc`/`nrs`/`lasg`/`gtb` are marked `client` and refuse; `cadra19`/`nrs19`/`gtb19` are unmarked and therefore also refuse. **Ruled in the close-out, 2026-09-16: `nrs19` → `client`, `cadra19` → `client`, `gtb19` → `test`**, on handoff 26's evidence in `docs/GO-LIVE.md` §7 — where the three exact commands are. **The marks are NOT applied yet** (the Builder's permission layer refused the write), so all three still refuse, which is the safe state. **The owner runs them.** **All three marks weaken a guard, and not the same one:** `gtb19` → `test` opens that database to the TEST SUITES, while `nrs19`/`cadra19` → `client` open theirs to the two OWNER-RUN SCRIPTS, which accept `client` on purpose — so `remove_test_residue.py` under `CADRA_APPLY=1` would then delete from `nrs19`, which holds a real NRS staff extract. The live GTB tenant is `gtb`, separately marked `client`.
  ```
  CADRA_API_BASE=http://test19.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q
  ```
  **Run it against `test19`, not `jaizbankplc`.** `jaizbankplc` is a replica of a live client's register and the suite wrote into it for 154 sessions — 88% of its assets are `pytest-*` fixtures. `test19` carries a full credential pair (`docs/api/.creds.test19`) and its client is flagged `is_test_credential`, which the guard also requires: a credential that does not say it is a test credential writes records nobody can identify as fixtures afterwards.

  The venv is `tests/.venv` (Python 3.13) — the repo's own Python, not the container's. `docs/api/smoke_test.py` is the 30-second liveness check. **The skip count is a function of the tenant, not a constant** — on `test19` it is 8 (2 Turnstile, 3 partition-data-absent, 1 no `workflow.config`, 1 no SAP asset number, 1 documented `is_tagged`) — **it was 9 until handoff 27, whose Playwright spec clicked Verify on a `test19` asset and gave the `is_verified` partition test the data it had been skipping for want of; the suite did not change, the tenant did**, with **no admin-scope skips at all**, because that tenant's credential holds `admin`. `docs/ENVIRONMENT-FACTS.md` carries the breakdown. Check the categories, not the count.
- **The browser suite is NOT behind the test-database guard, and its default target is a client's replica.** `e2e/config.ts` falls back to `http://jaizbankplc.localhost:8069`. Name the tenant every time, and rebuild the served bundle first — a plain `npm run build` breaks `/app/`:
  ```
  (cd Frontend/artifacts/nrs-asset-register && BASE_PATH=/app/ npm run build)
  (cd e2e && E2E_ORIGIN=http://test19.localhost:8069 npx playwright test)
  ```
  On `test19` two depreciation specs fail on `dev` as well and four skip (three move specs want two *building* locations); `docs/GO-LIVE.md` §13.5 item 13. Anything beyond those is yours.
- **Run the suites in CI's order: `pytest tests/` FIRST, then the in-registry Odoo suites.** `.github/workflows/ci.yml` runs them that way and the order is load-bearing, not cosmetic — the HTTP suite exercises the API against the registry the previous step left behind, so running the Odoo suites first can leave state that makes a pytest failure reproduce only in CI. Report 16's CI failure is the only way that class gets caught locally.
- **Check the DENOMINATOR, never the exit code.** An Odoo test run whose database died before the test phase reports `0 failed, 0 error(s) of 0 tests` **and exits 0** — a green that executed nothing, indistinguishable from a pass. Both of handoff 14's subagents hit it and one nearly reported it as a pass. **Quote the `of N tests` in every result you report, and treat a collapsed denominator as a failed run.** Grep the output for `of 0 tests` and for `CRITICAL` before believing anything.
- **Module upgrade** after model/view/manifest changes — the running container already binds port 8069, so an in-container upgrade must be given free ports:
  ```
  docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
    odoo -c /etc/odoo/odoo.conf -d <db> -u <module> --stop-after-init \
    --http-port=8099 --gevent-port=8098
  ```
  Then `docker compose … restart odoo` — Python changes are bind-mounted but not hot-reloaded.
- **In-registry Odoo tests live in `<module>/tests/`** and run on that same command with `--test-enable --test-tags /<module>` appended — **plus `--workers=0` for any `HttpCase`.** `setUpClass` reads `odoo.service.server.server.httpd.server_port` and `PreforkServer` has no `httpd`, so under the committed `workers = 2` every test in the class errors in setUpClass and the run reports "0 failed". **Pass `--workers=0` on EVERY in-registry run, not only the ones with an `HttpCase`** — without it the run ends at *"Stopping workers gracefully"* and **never prints the `N failed, M error(s) of X tests` line at all**, which is the denominator the rule below tells you to read. Handoff 32 ran `myservice_asset_register` twice, got `411 tests` from `odoo.tests.stats` and no result line either time, and only the third run with `--workers=0` said `0 failed, 0 error(s) of 309 tests`. **`odoo.tests.stats` is not the denominator** — it counts setUpClass and class-level entries; `odoo.tests.result` is.

### Odoo 19 gotcha: `_sql_constraints` is dead

Odoo 19 removed it. `odoo/orm/model_classes.py:162` logs *"Model attribute '_sql_constraints' is no longer supported, please define models.Constraint on the model"* and **creates no constraint** — a uniqueness guarantee declared the old way silently stops existing. **8 declaration sites** were affected — 2 first-party plus 6 in `crnd-19/` — and all are now ported; `docs/constraint-audit.md` is the standing record. Use `models.Constraint("UNIQUE (a, b)", "message")` on 19, keeping the legacy list behind an `_ODOO_MAJOR` guard in our own modules only (the 15 stack still loads them). `dist/` is the Odoo 15 vendor tree and, since handoff 20 retired the 15 stack, is on **no** addons path at all — its `_sql_constraints` are unreached rather than correct, and leaving them alone is right because nothing loads a vendored tree we do not control (see the correction in `docs/constraint-audit.md`). `crnd-19/`/`oca-19/` are 19-only and need no guard. `tests/test_source_guards.py` fails on any unguarded reintroduction in our modules.

### Three records nobody can alter, and what that costs you

`nrs.asset.custody` (who holds it), `nrs.asset.movement` (where it is, handoff 28) and `nrs.asset.event` (what has happened to it — a verification, a change of status with its reason, a change to the GRN, PO or SAP asset number; handoff 30; a change to any of the five warranty fields, handoff 34) are **append-only on the model**: `write` and `unlink` raise unconditionally, `create` refuses unless the recorder's own context flag is set, and all three hold their asset with `ondelete='restrict'`. They are written by `nrs.asset.write` and `nrs.asset.create`, not by any route, because every field they watch has many writers. **All three share ONE guard, `nrs.asset.append.only.mixin` (`models/append_only.py`, imported first) — `create`, `write`, `unlink` and `_resolve_source` — and ONE credential relabel on it in `myservice_api/models/append_only.py` (handoff 31). A fourth append-only record inherits the mixin; it does not copy it. Custody carried a claimable `source` for twelve days because its copy was never fixed when movement's was. What is RULED OUT is merging custody's and movement's ROWS into the event table: their ids and model names are published in the audit contract (`docs/DECISIONS.md`, 2026-09-21) — do not reopen it on aesthetics.** Four consequences that will otherwise cost you an afternoon:

0. **Since handoff 35 there is a FOURTH thing that pins an asset, and it is
   not one of these three.** `nrs.asset.change.request` is a state machine,
   not an append-only row — but `asset_id` is `ondelete='restrict'` and
   `unlink` refuses unconditionally, in EVERY state, a withdrawn request
   included. So an asset somebody once raised a request against cannot be
   deleted either. `scripts/remove_test_residue.py` and
   `scripts/mark_test_fixtures.py` name it alongside the three below.
1. **An asset with a row in any of them cannot be deleted** — and since handoff 28 every asset created at a location has one from birth. A test that needs to delete an asset has to create it nowhere and unassigned, **and must not verify it, change its status, change one of the three references or change its warranty first**: an event is a CHANGE, so creating an asset writes none, but the first of those pins it. `scripts/remove_test_residue.py` and `scripts/mark_test_fixtures.py` refuse on all three by name (and on the fourth above); `scripts/nrs_hq_seed.py` refuses the wipe and offers `CADRA_SEED_DESTROY_CUSTODY=1` and, separately and on purpose, `CADRA_SEED_DESTROY_MOVEMENTS=1` and `CADRA_SEED_DESTROY_EVENTS=1`.
2. **A test cannot backdate or remove a row through the ORM.** Fixtures that need one in the past, or need it absent to simulate the time before the recorder, use raw SQL and say so (`test_snapshot_rollback.py`, `myservice_api/tests/test_asset_history.py`).
3. **Disposed is terminal, and the rule is in the same place** (`nrs.asset._assert_disposed_is_terminal`, handoff 30). A disposed asset cannot change `state`, `location_id` or `custodian_id` through any write to the asset — **and the two doors `write` cannot see are shut separately**: both columns are `ON DELETE SET NULL`, so `generic.location.unlink` and `hr.employee.unlink` refuse to delete a location or an employee that a disposed asset names (archive instead). The verification pass found both by asking whether *"through any door"* was true. A write that NAMES the three fields without changing them is allowed, because the app's edit form re-sends them on every save. There is no context flag round it, on purpose, and no reversal route — that is an open ruling. A test or seed that disposes of an asset and then moves it will now raise. **Since handoff 32 the DATE is guarded too, in the same method**: a disposed asset's `disposal_date` cannot be emptied (correcting it to another day is a proper act and stays), and **only a date arriving in the SAME write as the disposal counts as the caller's** — otherwise `_stamp_disposal` stamps today, overwriting a date PATCHed onto the asset while it was still live. `_stamp_disposal(vals)` takes the write's body as a required positional argument so a second caller has to decide rather than inherit the old behaviour by leaving it out.
4. **The guarantee is Python.** No trigger. A writer that goes round the ORM is not recorded: raw SQL, `_write()`, or the database itself — `nrs_asset.location_id` is `ON DELETE SET NULL`, which is why `generic.location.unlink` records the assets it is about to orphan. **Before adding a writer of `location_id`, `custodian_id`, `state`, `last_verified_date`, one of the three references or a warranty field, ask whether `nrs.asset.write` will see it.** `tests/test_recorder_bypass_guard.py` greps for the raw-SQL ones.

**A refusal happens before anything is written.** `err(...)` returns a response; it does NOT roll the transaction back — only an exception does. A route that validates after it has created something leaves that something behind on a 400. Handoff 28 did exactly this on `/move` and left a `done` transfer for a move that never happened.

### A move and a handover need a second person, and the gate is on the model

Since handoff 35, changing `location_id` or `custodian_id` on `nrs.asset`
raises a `UserError` unless somebody has approved it. **This will bite you the
first time you write either field from a script, a shell or a test.** Four
things to know before you do:

1. **The gate is `nrs.asset._assert_change_is_approved`, called from
   `_write_recorded`** — the same place as the disposal guard, under every
   ORM writer. It is NOT in the routes, because the enumeration in report 35
   §A found twelve writers of `location_id` and thirteen of `custodian_id`,
   one of them an editable field on the Odoo form.
2. **A write that NAMES a field without changing it passes.** The app's edit
   form re-sends every field on every save; only a real change is gated.
3. **A caller that is genuinely not a person deciding declares itself:**
   `cadra_approval_exempt='import'|'seed'|'clearance'|'migration'|'test'`.
   **An unrecognised value is no exemption at all.** Five first-party call
   sites, each a row in §A's table — adding one means adding a row to that
   table. `create` is never gated, so a registration (including INT-03 from
   Vendra) is unaffected.
4. **The switch `cadra.approval.required` is read with raw SQL and ABSENT
   MEANS ON**, so every tenant here requires approval unless somebody set it.
   There is no bypass flag and it is deliberately not settable over the API —
   `assets:write`, `approvals:write` and `settings:write` are all one group.
   The refusal prints the command an administrator runs.

**The record is `nrs.asset.change.request`** — who asked, who was asked, who
clicked, when, and what the asset was before. It is not append-only (it has a
state machine) but it is close: `unlink` always refuses, a decided request is
frozen to everything including `sudo()`, and a pending one moves only through
`action_approve` / `action_reject` / `action_withdraw`. Self-approval is
refused in the model, not in the app.

### Multi-tenancy is a development and demo arrangement, not how a client runs

**Every real client gets its own server and its own single-tenant deployment.** The shared cluster — `nrs19`, `jaizbankplc`, `gtb19`, `cadra19`, `nrs`, `lasg`, `gtb`, `test19` on one registry — exists so one machine can carry development work and demonstrations side by side. It is not the production topology and never was. `docs/DEPLOYMENT.md`'s `prod` profile — one VPS, one domain, Caddy — is the real shape; the Kubernetes cluster is the demo estate. **That profile brings up Odoo 19 since handoff 20**, which closed the last open half of the migration outside `dist/`. **This is load-bearing for how you read every measurement in any report.** Three consequences, in order of how easily they mislead:

1. **A per-tenant row count is a fact about a demo, not about an estate.** Numbers from `jaizbankplc` or `nrs19` size a test, they do not size a customer. Say which tenant a number came from and treat it as a fixture unless somebody confirms otherwise.
2. **The fan-out below is a development obligation.** It is real and it must be done here, because one registry does serve every database on this machine. On a client's own server there is one database, so "schema before code" collapses to an ordinary migration and the blast radius of a missed tenant is zero.
3. **Anything justified by "other tenants share this" needs re-reading.** The external record cap was described as a paywall protecting us from partner integrations on a shared cluster; on a single-tenant server its purpose is rate limiting and nothing else. Keeping it is still right. The *reason* changed, and a control whose stated reason has quietly stopped being true is how a future maintainer argues it away.

### Adding a stored field is a multi-tenant migration, not a code change

One Odoo process serves every database from one registry, so the moment a stored field lands in the Python, **every tenant that has not been upgraded is broken** — reads of that column raise `UndefinedColumn`, and any serializer touching it 500s the endpoint. Upgrade **all** databases before the code ships, not just the one you tested on, and on staging/prod the `cadra-upgrade` Job must fan out the same way. `odoo` is correctly absent from the loop: it is 15-era and a 19 worker skips it.

```
for db in cadra19 nrs19 gtb19 test19 nrs lasg gtb jaizbankplc; do
  docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
    odoo -c /etc/odoo/odoo.conf -d $db -u <module> --stop-after-init \
    --http-port=8099 --gevent-port=8098
done
```

## Architecture rules

1. **The API is a contract.** Every `@cadra_route` returns the PRD §10.7 envelope via `ok()` / `err()` — never raw dicts. Additive changes are safe; changing or removing a field, an enum value or an error code is breaking, and Vendra is downstream.
2. **Model is the source of truth, the allow-list is the gate.** A field being on `nrs.asset` does not make it writable; `_WRITABLE_FIELDS` decides. When adding one, add it to the allow-list, the OpenAPI annotation and a test in the same change. **A DERIVED field is the exception that proves it**: `is_test_fixture` (`myservice_api/models/test_fixture.py`) is published and read-only — stamped from the acting credential at creation, overwritten rather than defaulted, refused by `write()` unconditionally, and in no allow-list. `tests/test_source_guards.py` fails if it is ever added to one, and fails if a model any first-party path can create carries no self-label at all.
3. **Never let an integration guess.** A body field a route does not accept is REFUSED — `400 invalid_request`, `details.rejected_fields` and `details.writable`, and nothing is written, the accepted fields beside it included (`refuse_unwritable`, handoff 31). Until then it was dropped with a 2xx and named in `data._warnings.rejected_fields`, which for most of this API's life nothing read: that is how a category's depreciation method came to be unchangeable from its own settings screen, and how `POST /requests` dropped a request's location for the life of the route. **Two traps this leaves, both of which have already bitten:** a screen that PATCHes back the object it GET-ed now fails the day the serializer gains a read-only key — send an explicit pick; and **a published key and the model field behind it can stop agreeing without anything failing** — the request model's location became `generic_location_id` in the move to Odoo 19, `v1_requests` went on asking the model for `location_id`, and the key was dropped with a 201 for the life of the API. When a field is refused or comes back `null`, read `ir_model_fields` before concluding the register cannot hold it: the first reading here was exactly that, and the app's picker was removed on it before the API was fixed instead. Anything that silently degrades — a dropped field, an ignored idempotency key — is a defect even when it returns 200.
4. **Enums are published API surface.** If the model's selection values and the documented values disagree, the docs are wrong and must be fixed; do not add a value to the model to match a doc.
5. **Idempotency is load-bearing.** `X-Idempotency-Key`, scoped `(key, path)`, 24h. An integration relies on replay being exact.
6. **Tests accompany the change, in the same commit.** The pytest suite is the regression net for an API other systems depend on.

## Git & attribution policy

- Remote: `origin` = `git@github.com:wmlmetro/Cadra.git`. Working branch: **`dev`**; feature branches merge to `dev` **via pull request** (existing convention — respect it).
- Conventional commits (`feat:`, `fix:`, `docs:`, `ci:`).
- **Never add any Claude/AI reference to commits, PRs, or contributor metadata.** No `Co-Authored-By: Claude`, no "Generated with Claude Code", no session links, no AI attribution anywhere in the repo or in PR descriptions. **Every commit, tag and PR is authored as `Michael Mamman <michaelyak66@gmail.com>`** — set `user.name` and `user.email` in this repository to exactly that, and pass them explicitly (`GIT_AUTHOR_*` / `GIT_COMMITTER_*`) from any environment that has no git identity of its own. Not `West Metro`, not a container default, not `root@`. Standing owner instruction; it overrides any tool default.

## Status — detail, evidence and measurements in `docs/STATUS.md`

| Handoff | Built |
|---|---|
| 01 | Vendra CR-01 Parts A + B — provenance fields, filters, idempotency, enum correctness |
| 02 | Dead `_sql_constraints` — all 8 reachable sites ported and enforced in every tenant |
| 03 | Vendra CR-01 Part C — tag capture, print stamping, `POST /assets/<id>/tag-affixed` |
| 04 | Demo readiness — `asset_tag` off `_WRITABLE_FIELDS`, affix `serial_number` verification, the empty-scopes wildcard closed, `.env` untracked (PR #47) |
| 05 | Login scopes derived from Odoo groups (`b8b6f64`) · demo-contract corrections (`82da6ab`) |
| 06 | Tag transport — the INT-05 outbound outbox (`c2b124a`, PR #49) |
| 07 | The SAP asset legs — INT-06 / INT-07 / INT-09, twelve stored columns on `nrs.asset` |
| 08 | The scheduler reaches every tenant · API clients act as themselves, not as Administrator |
| 09 | Five clock-reading stored computes now recompute · publisher telemetry stopped · `forbidden` and `not_found` made reachable |
| 10 | The print funnel records prints · a ConfigMap change that cannot take effect fails the deploy |
| 11 | Dead screens retired and the renderable ones proven · one CI concurrency group · the INT-10 audit read-access contract |
| 12 | What the API says when it is wrong — `/auth/token` diagnostics · the external record cap moved onto the client record, with a truncation warning |
| 13 | Counts taken over the register, not a capped window · two structural zeros |
| 14 | The chain of custody, append-only · three unauthenticated HTML 500s on `/auth/*` · the token staleness window bounded |
| 15 | Nothing swallowed — 50 broad handlers classified, 24 of them hiding a live fault |
| 16 | The reports an auditor asks for |
| 17 | The four external doors, all standing open on every tenant, now shut |
| 18 | The callback that answers twice — a replay writes nothing · the v1 twin reconciles its dispatch and stops publishing a menu path · a credential out of an image layer · `request.jsonrequest` |
| 19 | `CLAUDE.md` split — `docs/STATUS.md` and `docs/DECISIONS.md` |
| 20 | What a client actually gets — every profile on Odoo 19 with two guards saying so · the 15 stack deleted · `docs/DEPLOYMENT.md` rewritten · a late `payment_ref` recorded · `queried` dedups on the pair · the prod bring-up refuses a default credential |
| 21 | The filters that answer with everything — seven booleans, thirteen enums and nineteen foreign keys refuse what they cannot read · a pure validator at the door · `.gitlab-ci.yml` deleted · a newline-bearing credential refused |
| 22 | The front end that lies to its own users — seven enum sets read from the model, not declared · `GET /api/v1/meta/enums` · a drift guard proved to fail first · a corrupt cursor is a 400 (BREAKING) · `?has_coordinates=false` stops answering zero · two partition tests that never ran |
| 23 | **The last two audit reports — §13.4's five are complete.** The access log that does not exist, said in the response with the six places it could have been · the configuration log's 22 recoverable keys, credentials redacted by key name · the `Auditor` group, proved by acting · a disposal approved by whoever called · the CI series guard reads the file it was written for, after its first fix exempted `ODOO_VERSION: '15.0'` |
| 24 | The record starts now — group membership is an append-only fact with the actor and the instant it begins · the writer list corrected in three places (implication writes NO membership rows on 19) · what a test run writes into a client's register · `finance_viewer` ruled a sentence, not a group |
| 25 | **Where the tests are allowed to write.** A test refuses any database not marked `cadra.database_class = test`, absent included — both suites, no bypass flag, CI stamped rather than exempted · the guard read through an ormcache and leaked 24 writing tests onto an unmarked database before it was made to read the row · a fixture can no longer mint a credential that lies about itself · the residue script, dry-run and trial-deleted, 3,779 of 3,894 removable and 115 refused · `fmDomain` gets its own name and row · `allowed_values` on three refusals (`allowed` DEPRECATED) · `workflow_payment_ref` published |
| 26 | **A fixture says so on its face — and the last handoff.** `is_test_fixture` derived from the acting credential onto 14 models, unsettable and unclearable · a guard that fails on any creatable model with no self-label · 24 silent instruments found, 13 fixed including the production refusal that read through the ormcache · the three tenants measured and proposed · the open-items register in `docs/GO-LIVE.md` Part II |
| 27 | **What has happened to this asset — the cycle reopened by a client, not by polish.** NRS opened *Audit & Review* expecting an asset's history and the screen had never asked for one · `GET /assets/<id>/history`, one ordered list merged server-side from seven sources, newest first · every event graded by what somebody can DO to its record, because only a change of custodian has one nobody can alter · **a location move has no durable record** (`nrs19`: 1,146 tracked moves, 1 transfer row) · reconstructed rows say so, a blank actor stays blank, what is never recorded is named on every response, and an empty history says so in words · an ordering bug 32 passing tests missed, found by opening the screen · the Move dialog stopped calling an editable row "immutable" |
| 28 | **Where a thing has been — location gets the custody treatment.** `nrs.asset.movement`, append-only, written in `nrs.asset.write`/`create` underneath every writer of `location_id`; PATCH stays open and writes no transfer, because a move is not always a transfer · two writers that were not in the Python: deleting a location (`ON DELETE SET NULL`, cascading from a parent) and the Odoo form, which had never saved the location it displayed · `POST /assets/<id>/verify` records WHO verified · six provenance fields and the verifier tracked, with the instant tracking began stamped per database (by migration on an upgrade, by `post_init_hook` on a fresh install) so the register snapshot does not claim a history they lack · three screens stopped saying what the record does not · **report 27's "1,146 moves" is one six-second seeding script**, found by asking what a backfill would recover · a refused `/move` left a `done` transfer behind, found by fact-checking a doc |
| 29 | **Every control on the asset page — proved by clicking it and reading the row.** A missing or disposed asset rendered as a green *Cleared*, on every screen, from one shared function; one status slot now shows lifecycle when it is anything but active · three unreachable statuses measured dead and deleted · the browser's two `confirm()` dialogs replaced, and *Mark missing* given no reason because the API has nowhere to put one · Condemn sets the condition as well as the state · counts stopped folding missing and disposed assets into stock (`nrs19` reported *Verified: 1* — the missing one) · a dead bell, a hardcoded user name and four dead tabs removed · the persisted cache versioned so the fix cannot be outlived by a browser · **RETRACTED: `require_jwt` does set `request.jwt_claims`** — the "architectural fact" of handoff 28 was false · the snapshot's *today* made a Lagos day, found at 00:50 |
| 30 | **Before the fourth twin — what has happened to an asset, recorded so nobody can alter it.** Asked whether a third, fourth and fifth copy of custody was a design or an accident: ONE model, `nrs.asset.event`, for every verification, every change of status with its reason, and a change to the GRN, PO or SAP asset number — the guard written once as a mixin, custody and movement left where they are because their ids and names are PUBLISHED and a migration is a rewrite of the two tables whose value is that nobody rewrites them · **disposed is terminal, in the model** — two doors were open, not one: a completed transfer un-disposed whatever it was completed on · un-disposing refused outright on a measurement: the only asset that ever left `disposed` is handoff 29's own probe · `POST …/mark-missing` and `POST …/condemn`, a reason required on both · **`/condemn` as specified would have MOVED the one-hour-a-night bug onto the server** — every API credential's user has no timezone, so `context_today` is UTC; it stamps a Lagos day · `building_id`/`floor_id`/`room_id` not writable (BREAKING) — the one live sender was our own edit form, echoing fields it had no input for · the app shows `_warnings` for every write, and on that day found that **a category's depreciation method could never be changed from its settings screen** · `exception` wired as a review status: 811 rows, every one a fixture, the control live with an opening balance of zero · a refused `/move` no longer burns a transfer reference, proved to fail first |
| 31 | **One answer per rule.** The append-only guard written ONCE — custody and movement adopt `nrs.asset.append.only.mixin`, and their ROWS deliberately stay where they are because their ids are published in the contract an auditor reads · **a body field a route does not accept is a 400 and NOTHING is written**, eleven routes, announced — report 30's ten plus one that dropped fields without even reporting them · the MODEL stamps a disposal's date and condition for every writer · `POST /assets/<id>/mark-found`, a reason required · a disposed asset is not on a leaver's clearance list · **and the 400 uncovered that `POST`/`PATCH /requests` had dropped a request's location for the life of the route** — the model's field became `generic_location_id` on 19 and the API went on asking for `location_id`; both of the first two readings of it were wrong, the second written into nine places on a count with no denominator |
| 32 | **The name and the field — the sweep, kept as a guard.** Every published key in the API against the model field it claims to write, both directions, driven by the routing attribute and a parse of every controller so a new route or a new defensive read FAILS rather than being skipped (`myservice_api/tests/test_published_names_resolve.py`) · **its first draft could not see the helper it was written about** — `_location_field` spells its check with a loop variable — caught by the table's own staleness check · the twelfth door and the thirteenth: `POST /home/quick-submit` and `POST /integrations/sap/employee-sync` refuse a key they do not read, a batch refused whole, and quick-submit refuses an id it cannot resolve instead of swallowing it · **`status` on the SAP feed was published by the schema, the endpoint reference, the demo card and our own test, and never read by anything** — the third instance of a published name and the thing underneath answering to another · quick-submit's documented example sent four keys the route has never read · a disposal's date cannot be taken off, and only a date sent WITH the disposal is the caller's · four keys you can write and never read back, named not fixed · three audit-report tests that had begun failing because `test19` crossed the record cap on one date |
| 35 | **Nobody moves an asset alone — the second thing NRS asked for.** A move or a custody change becomes a REQUEST, and the rule sits in `nrs.asset.write` under all **twelve** writers of `location_id` and **thirteen** of `custodian_id`, not in the two routes the app calls — the enumeration was done before the code because the last two guesses at this list were both wrong · `nrs.asset.change.request`, ONE model for both, because *what is waiting on me* is one question · `nrs.asset.transfer` NOT reused and measured to be safe to leave: all 267 rows on all EIGHT tenants are `done`, nothing in `draft`, and `approved_by` is set on 1 of them — it becomes the RESULT of an approval instead, carrying the real approver · nothing written to the asset on request; the append-only rows appear on approval, from the same recorders as every other writer · who is ASKED and who CLICKED are two columns · self-approval refused in the model, under `sudo()` and as SUPERUSER · a request records what the asset WAS and cannot be approved once that stopped being true · one pending request per asset, by partial unique index · `cadra.approval.required` read with raw SQL, absent means ON, read-only over the API because the people it constrains hold `settings:write` · BREAKING: `/move` and `/transfer-custody` stop moving the asset and require `approver_id` |
| 34 | **Warranty — client scope from a demonstration, and the first handoff that spans both repositories.** Cadra goes first: **`myservice_api` 19.0.3.12.0 accepts the keys**, and `openapi.json` says so for Vendra to read, because since handoff 31 a Vendra sending them to an older Cadra would dead-letter every receipt · a duration and a start date, the expiry DERIVED from them and a contradicting one refused, `basis` published beside the date · who honours it as a name, and the certificate number · three states — *no warranty recorded* is the honest third and, measured, 100% of every real tenant — on a Lagos day, and an *expiring soon* window named on the screen · a change is an append-only `warranty_changed` event; a create writes none · a warranty moves nothing about the asset's state, condition or counts · the published block uses the writable names, so a block read can be sent back unchanged (an edited duration goes without the expiry it replaces) · the verification pass found a multi-asset save that would have told SAP of each disposal twice, proved to fail first |

## Backlog — see `docs/GO-LIVE.md` Part II

**Handoff 26 closed the programme's own quality work, and said there would
be no 27. There is one: it came out of a live demonstration to NRS, not out
of the register below, and it is the only kind of thing that reopens the
cycle — a client asking for something the system does not do.** What it
built is in the table above; what it FOUND — chiefly that a location move
has no durable record, and the approver NRS asked about — is
`docs/GO-LIVE.md` §13. Everything else outstanding —
the two owner-run scripts, the three unclassified tenants with a proposed
class and its evidence, the credentials, the nine pre-envelope routes, the
silent-instrument sites that were found and not fixed, and the questions that
belong to NRS rather than to engineering — is in the **open-items register at
`docs/GO-LIVE.md` Part II**, one entry each, tagged `[open]` / `[verified]` /
`[landed, keep it that way]`, each carrying its evidence and the report it
came from. **That file is where the programme resumes from; this list is not
maintained in parallel.**

**The close-out (2026-09-16) settled three of those entries and closed four.**
`docs/GO-LIVE.md` §7 (the three tenants), §11.1 (the quick-submit actor) and
§8.3 (the two cutover credentials) now carry `[ruled]` decisions rather than
questions — **implement them, do not re-decide them** — and §10.2's eleven
remaining silent-instrument sites and §12's three judged-and-left findings
are accepted as they stand and are not to be reopened. The reasoning for all
of it is in `docs/DECISIONS.md` under *2026-09-16 — close-out*.

The one thing to read first if you read nothing else: **`admin` / `admin` is
accepted on all eight local tenants** (verified 2026-09-15, §8.1), and the
same bootstrap provisions the cluster.

## Decisions

Every product and technical decision, with its date, reasoning and the handoff that landed it: **`docs/DECISIONS.md`**. Read the entries for the area you are about to change before changing it. **Add to it in the same commit as the work** — `[ruled]` by the Architect, `[landed <hash>]` only by the report that confirms it shipped.
