# CLAUDE.md — Cadra (myservicenrs)

Guidance for Claude Code and any developer working in this repository. It holds what you need **before and during** your first command. The record of how the project got here lives in the files below — read the ones relevant to what you are about to change, and keep this file current as part of every change.

- **`docs/DECISIONS.md`** — every decision, its reasoning, and the handoff that landed it. Read the entries for the area you are changing.
- **`docs/STATUS.md`** — what is built, with the measurements and evidence behind each item.
- **`docs/ENVIRONMENT-FACTS.md`** — things true of these machines that cost somebody an afternoon. Read it before blaming your code.
- **`docs/DEPLOYMENT.md`** — the `prod` and `dev` profiles, and how a tenant is actually deployed.
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

## What this is, and why the API's shape matters beyond it

**Cadra** — the asset and facilities register for the Nigeria Revenue Service (NRS), built on **Odoo 19** with a versioned REST layer (`/api/v1/*`) in `myservice_api` over the ITSM, asset register, security and FM modules. The local stack, CI and the whole cluster are on 19 — every `*.cadra.ng` ingress points at the `odoo-19` service and `k8s/dev/` has no Odoo 15 manifest. **But the `prod` compose profile is still Odoo 15**, and so is the document describing it: `docker-compose.yml` builds `cadra-odoo:15.0-dev` from `FROM odoo:15.0`, only the 19 overlay overrides it, `docker-compose.prod.yml` does not, and `docs/DEPLOYMENT.md` does not mention 19 anywhere. So a client deployed by the documented `prod` route today gets 15. That, `dist/` and `crnd-19/`'s hand-ported modules are what the migration has left.

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
- **Tests need a database with a `docs/api/.creds.<db>` file.** Today that is only `jaizbankplc` (`nrs19` has one, but it holds the demo's two scoped clients, not a `CLIENT_ID`/`CLIENT_SECRET` pair):
  ```
  CADRA_API_BASE=http://jaizbankplc.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q
  ```
  The venv is `tests/.venv` (Python 3.13) — the repo's own Python, not the container's. `docs/api/smoke_test.py` is the 30-second liveness check. The suite skips a batch of admin-scoped and pagination tests its own token cannot reach; `docs/ENVIRONMENT-FACTS.md` carries the expected number, and a healthy run matches it.
- **Run the suites in CI's order: `pytest tests/` FIRST, then the in-registry Odoo suites.** `.github/workflows/ci.yml` runs them that way and the order is load-bearing, not cosmetic — the HTTP suite exercises the API against the registry the previous step left behind, so running the Odoo suites first can leave state that makes a pytest failure reproduce only in CI. Report 16's CI failure is the only way that class gets caught locally.
- **Check the DENOMINATOR, never the exit code.** An Odoo test run whose database died before the test phase reports `0 failed, 0 error(s) of 0 tests` **and exits 0** — a green that executed nothing, indistinguishable from a pass. Both of handoff 14's subagents hit it and one nearly reported it as a pass. **Quote the `of N tests` in every result you report, and treat a collapsed denominator as a failed run.** Grep the output for `of 0 tests` and for `CRITICAL` before believing anything.
- **Module upgrade** after model/view/manifest changes — the running container already binds port 8069, so an in-container upgrade must be given free ports:
  ```
  docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
    odoo -c /etc/odoo/odoo.conf -d <db> -u <module> --stop-after-init \
    --http-port=8099 --gevent-port=8098
  ```
  Then `docker compose … restart odoo` — Python changes are bind-mounted but not hot-reloaded.
- **In-registry Odoo tests live in `<module>/tests/`** and run on that same command with `--test-enable --test-tags /<module>` appended — **plus `--workers=0` for any `HttpCase`.** `setUpClass` reads `odoo.service.server.server.httpd.server_port` and `PreforkServer` has no `httpd`, so under the committed `workers = 2` every test in the class errors in setUpClass and the run reports "0 failed".

### Odoo 19 gotcha: `_sql_constraints` is dead

Odoo 19 removed it. `odoo/orm/model_classes.py:162` logs *"Model attribute '_sql_constraints' is no longer supported, please define models.Constraint on the model"* and **creates no constraint** — a uniqueness guarantee declared the old way silently stops existing. **8 declaration sites** were affected — 2 first-party plus 6 in `crnd-19/` — and all are now ported; `docs/constraint-audit.md` is the standing record. Use `models.Constraint("UNIQUE (a, b)", "message")` on 19, keeping the legacy list behind an `_ODOO_MAJOR` guard in our own modules only (the 15 stack still loads them). `dist/` is the Odoo 15 vendor tree and is **not** on the 19 addons path — its `_sql_constraints` are correct as they stand; `crnd-19/`/`oca-19/` are 19-only and need no guard. `tests/test_source_guards.py` fails on any unguarded reintroduction in our modules.

### Multi-tenancy is a development and demo arrangement, not how a client runs

**Every real client gets its own server and its own single-tenant deployment.** The shared cluster — `nrs19`, `jaizbankplc`, `gtb19`, `cadra19`, `nrs`, `lasg`, `gtb`, `test19` on one registry — exists so one machine can carry development work and demonstrations side by side. It is not the production topology and never was. `docs/DEPLOYMENT.md`'s `prod` profile — one VPS, one domain, Caddy — is the real shape; the Kubernetes cluster is the demo estate. That profile still brings up Odoo 15, which is the open half of the migration, not a leftover file. **This is load-bearing for how you read every measurement in any report.** Three consequences, in order of how easily they mislead:

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
2. **Model is the source of truth, the allow-list is the gate.** A field being on `nrs.asset` does not make it writable; `_WRITABLE_FIELDS` decides. When adding one, add it to the allow-list, the OpenAPI annotation and a test in the same change.
3. **Never let an integration guess.** Unknown fields are currently dropped with a 201 and reported only in `data._warnings.rejected_fields`. Anything that silently degrades — a dropped field, an ignored idempotency key — is a defect even when it returns 200.
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
| 18 | **not started** — the callback that answers twice |

## Backlog — agreed, not yet scheduled

- **The nine pre-envelope routes adopt `@cadra_route`** (`/auth/*`, `/openapi.json`, `/docs`, `/assets/export.csv`, `/integrations/employees/import`, `/brand`). They validate nothing and sit outside the standard envelope — and `/auth/token` is the first endpoint every integration touches. Refactor of the auth surface; after INT-03 is live.
- **Query-parameter validation, API-wide (report 01 V4).** Scoped in report 05: **~26 sites across 5 files** — 13 enum params (`200 []`), **5 boolean params that silently drop the filter and return the UNFILTERED list**, and 8 int params that `except: pass`. The booleans are the dangerous half and should go first: an empty list reads as "no matches", a full list reads as an answer. **There is no primitive to reuse yet** — this item used to cite `utils.py:830`, which is now unrelated code, and the nearest function, `utils._selection_allowed_values`, is error-enrichment that rolls the cursor back and is ruled out on a read path (see `docs/DECISIONS.md`, 2026-09-06). Handoff 05 did the tagging filters only, by hand.
- **Per-session test artefact paths.** Two concurrent pytest sessions clobber each other's report and captures. Cosmetic.

## Decisions

Every product and technical decision, with its date, reasoning and the handoff that landed it: **`docs/DECISIONS.md`**. Read the entries for the area you are about to change before changing it. **Add to it in the same commit as the work** — `[ruled]` by the Architect, `[landed <hash>]` only by the report that confirms it shipped.
