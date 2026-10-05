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

  The venv is `tests/.venv` (Python 3.13) — the repo's own Python, not the container's. `docs/api/smoke_test.py` is the 30-second liveness check. **The skip count is a function of the tenant, not a constant** — on `test19` it was **10** from handoff 44 to 45: 2 Turnstile, 3 partition-data-absent, 1 no `workflow.config`, 1 no SAP asset number, 1 documented `is_tagged`, 1 because `POST /api/v1/assets` always mints a tag so *the serial of an UNTAGGED asset* is proved in-registry (handoff 38), and — until handoff 46 — 1 because `test_user_lifecycle.py`'s *other credential's user* refusal needs a second API credential and `test19` had only the suite's own (handoff 43). **Since handoff 46 it is 9**: the demo-persona seed's inert credential (`cadra_demo_personas`) is a second credential, so that test runs (refusals only, nothing written). **Two skips that WERE there are gone, and come back on any tenant whose credential is root**: the administrators-may-withdraw skip (handoff 35) and the credential-already-holds-`system` skip (handoff 43) — both exist because the suite's credential held `base.group_system`, and handoff 44 removed it on `test19` (`scripts/strip_credential_system_group.py`); on `cadra19`/`nrs19` it is still held until the owner runs that script. History: 9 until handoff 27 (whose Playwright spec gave the `is_verified` partition test its data — the tenant changed, not the suite), 12 from handoff 43 to 44. No admin-scope skips, because that tenant's credential holds `admin`. `docs/ENVIRONMENT-FACTS.md` carries the older breakdown. Check the categories, not the count.
- **The browser suite is NOT behind the test-database guard, and its default target is a client's replica.** `e2e/config.ts` falls back to `http://jaizbankplc.localhost:8069`. Name the tenant every time, and rebuild the served bundle first — a plain `npm run build` breaks `/app/`:
  ```
  (cd Frontend/artifacts/nrs-asset-register && BASE_PATH=/app/ npm run build)
  (cd e2e && E2E_ORIGIN=http://test19.localhost:8069 npx playwright test)
  ```
  On `test19` two depreciation specs fail on `dev` as well (`docs/GO-LIVE.md` §13.5 item 13), and **the skip count is a function of the tenant's data, not a constant** — the same rule as the pytest skips. It was 4 of 169 at the §13.5 baseline and 12 of 202 on 2026-10-03 (handoff 49: five move specs wanting *building* locations, one request spec wanting a `type_id`, and six approval/tag specs wanting seed state; named one by one in `docs/handoffs/49-evidence/suite-results.txt`). Check the categories, not the count. Anything beyond those is yours.
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

### Odoo 19 gotcha: `ir.mail_server.connect()` is `_connect__`

`mail.mail.send()` opens one SMTP session per batch through
`ir.mail_server._connect__` (19) — it was `connect` on 15 — and hands it to
`send_email()`. `myservice_email_relay`, the HTTPS bridge for clusters that
block SMTP egress, overrides the opener to skip the socket; its 15-era
override of `connect` was carried onto 19 with only its version changed and
was dead code for the life of the 19 stack, so every outbound mail died at
*Unable to connect to SMTP Server* before the relay was consulted
(`docs/DECISIONS.md`, 2026-10-02). The override is on `_connect__` now and
`myservice_email_relay/tests/test_relay.py` reads core's source to assert the
name still matches. **A method you override is a name the framework owns;
after an upgrade, grep core for it before trusting the override.** The relay
is live on no tenant until `cadra.email_relay_url` AND
`cadra.email_relay_secret` are set (the relay refuses a missing secret);
`set_param(key, "")` on 19 stores an empty string rather than deleting the
row.

### Odoo 19 gotcha: a group reaches the user form through `res.groups.privilege`, not `category_id`

`res.groups` has no `category_id` on 19. The user form's widget renders one
SELECTION per `res.groups.privilege` — its groups as mutually exclusive
options under a "No" placeholder — grouped by the privilege's category, and
**a group with no privilege is shown only under *Extra Rights*, and only in
developer mode** (`res_user_group_ids_field.js`). That is why the three
register groups and the Auditor were invisible for the life of the module
and assignable only from the Groups menu in debug (handoff 41). The fix is
a privilege record per CHOICE, not per category: *Asset Register* holds
Asset User and Asset Manager (one choice, Manager implies User), *Tag
Issuing* holds the Tag-Issuing Unit alone and *Audit* the Auditor alone,
because a group sharing a privilege with another cannot be held WITH it —
and a human tagger holds Asset User + Tag-Issuing Unit. A privilege creates
no implication and no access rule. **Handoff 42 gave the other seven theirs — 11 of 11
first-party groups now have one**; a new group needs one or it is invisible. Side effect: `full_name` prefixes the privilege, so the access
record's `group_name` snapshot reads *Asset Register / Asset Manager* from
2026-10-01 and *Asset Manager* before.

**A human in the Tag-Issuing Unit also holds Asset User.** The group grants
`tagging:write` and nothing else, which is complete for the API credential
it was built for and leaves a person refused at the SCOPE gate on every
station read (`assets:read`) — no access rule can grant a scope, so an
`ir.model.access` row was the option that lost (`docs/DECISIONS.md`,
2026-10-01). The four `/barcode/*` wrappers in `v1.py` now delegate under
sudo like every other route (`_delegate_reads_as_superuser`); until then
they read as the token's user, and a paired tagger got `403 … 'Location'`
on *Recent tags*.

### Odoo 19 gotcha: the sign-up door is decided by the `website` row, and now by a constant

`auth_signup.invitation_scope` is NOT what decides whether a stranger can
create an account on a tenant with `website` installed: the `website`
module overrides `res.users._get_signup_invitation_scope` with its own
per-site field `website.auth_signup_uninvited`, default `b2b`. That is why
every tenant said `b2c` and answered 404. Since handoff 43 the method
returns `b2b` as a constant in `myservice_api/models/invitation.py` — the
owner's ruling — so no row and no Settings click opens it; a token in the
URL (the invitation's link) still works. **Three more things in that file
you will hit:** `_action_reset_password` is overridden wholesale (the
letters are the tenant's — do not edit `auth_signup.set_password_email`,
it is no longer sent); `res.partner._get_signup_url_for_action` puts the
link on the bound REQUEST's host when the caller is AUTHENTICATED, not
`web.base.url` (which any administrator login rewrites) — anonymous
`/web/reset_password` keeps core's base, because under `proxy_mode` the
request host is `X-Forwarded-Host`; and **`Savepoint.close()` rolls back on 19**
(`sql_db.py:118`), so `contextlib.closing(cr.savepoint())` — core's own
pattern there — undoes what it wraps. Use `with cr.savepoint():`. Creating
a person over the API is a plain `res.users.create` with
`_default_groups()` ∪ the roles asked, because on 19 the sign-up template
is the PORTAL user (`base.template_portal_user_id`), not `base.default_user`.

### The back office is for system administrators — and that includes your tests

Since handoff 45 nobody who is not a system administrator can USE an Odoo
session. **This will bite the first in-registry test you write that signs a
non-administrator in with `self.authenticate(...)` and calls an `auth='user'`
route** — `/barcode/*` JSON, `/web/dataset/call_kw`, `/report/pdf`, `/my`:
`models/backoffice_session.py` ends that session in `ir.http._authenticate`
before the route runs (an `http` route answers a redirect to `/app/`, JSON-RPC
answers *Session expired*). `controllers/backoffice.py` shuts the doors a
person walks through: `/web`, `/odoo`, `/odoo/<path>` → `/app/`; a
non-administrator signing in on `/web/login` → `/app/`; GET and POST of
`/web/signup` and `/web/reset_password` → the app's pages, same token. What
is untouched, by measurement (report 45 §B): `auth='none'` (every `/api/v1`
route — the app holds a bearer token and no Odoo session), `auth='public'`
(`/report/barcode`, the QR on a label — the ONE non-API Odoo path the app
requests — assets, images, `/web/login` itself, which the k8s probes GET).
The back-office barcode station is therefore an administrator's tool; its two
test files run as one. **The letter's link is the app's**
(`/app/accept-invite?token=…`, `/app/reset-password?token=…` — only the
token), redeemed by `controllers/v1_signup.py`, which signs the person in
with `/auth/login`'s own payload. **An anonymous reset link is built on
`web.base.url`** (handoff 43's rule), which core rewrites when an
administrator signs in on the back office and which is the install default on
a database nobody has — `docs/GO-LIVE.md` §22.2.

**`test19` holds more accounts than an API credential may read in one report**
(103 against `EXTERNAL_TOTAL_CAP` = 100, announced in the top-level
`_warnings.truncated`). A person a test creates NOW has the highest id and is
the one cut off; a test looking for it in `/reports/access-changes` must read
the truncation or act on an older visible fixture (four already do).

### Demo personas, and why a fixture account labels what it does

Since handoff 46 every classified local tenant carries six invented people
on `@demo.example` (`docs/api/.personas.<db>` holds the passwords;
`scripts/demo_personas.sh <db> list` says which accounts they are). **Two
things will surprise you.** First, `myservice.api.client._is_test_credential_user`
now answers yes for any account whose partner is `is_test_fixture` — so
anything a persona, or an officer a suite invited through `POST /users`,
creates is labelled a fixture and its append-only rows read `source='test'`.
That is deliberate: an invented officer's verification is not history.
Second, a persona named on a move request cannot be deleted (the request
holds requester, approver and decider with `ondelete='restrict'`), so the
remover ARCHIVES it — run the dry run first; it is the database's own answer.
The seed refuses an unclassified database and `production`; the remover
accepts `production`, because at go-live these come off. **On the cluster**
the same scripts run through `.github/workflows/demo-personas.yml`; the
passwords leave the runner only encrypted to a key whose private half is on
the owner's machine (`scripts/demo_personas_fetch.sh <run-id>` decrypts them
into `docs/api/.personas.cluster.<db>`). The four cluster tenants are
`client` by the owner's ruling of 2026-10-03.

**A sidebar item is drawn on two conditions since handoff 48: the TENANT
shows it (Settings → Sidebar, `cadra.sidebar.*` parameters) AND the person's
scopes open it.** The first is presentation only — nothing but
`controllers/v1_sidebar.py` may read a switch and `App.tsx` may not route on
one (`tests/test_sidebar_catalog.py`). **A new nav item needs a `key`, the
same key in `SIDEBAR_GROUPS`, and never a key that was published before**;
renaming or re-scoping an item never touches its key.

**A sidebar item declares the scope the SERVER requires for what the page is
for** (`lib/navigation.ts`, `scope` required, all-of), and the landing page
is computed from the same table. Hidden must mean refused:
`e2e/tests/46-…` signs in as each persona and fails if an item is drawn for
somebody the server refuses or hidden from somebody it answers. Where a
scope admits a page that is not the role's job, that is a role-model
finding for the Architect — do not invent a scope to hide it.

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
   There is no bypass flag and it is deliberately not settable over the API.
   (Until handoff 47 the stated reason was that `assets:write`,
   `approvals:write` and `settings:write` were all one group; the Asset
   Officer now holds `assets:write` without the other two, which makes the
   switch's unreachability over the API more load-bearing, not less.)
   The refusal prints the command an administrator runs.

**Since handoff 38 a TAG REPLACEMENT is two-person as well, and it is NOT
on that model.** `nrs.asset.tag.label` has its own `active → pending →
scrapped` state machine, completed with the same conventions: `approver_id`
named at request, the decider from the token, self-approval refused in
`_may_decide` (which reads the change request's `APPROVER_GROUP`, so there is
one answer to "who is an approver"), a reason required to ask and to reject,
and nine stamp fields refused by `write` without `cadra_tag_replacement`. The
change request was not reused because its one-pending-per-asset index would
make a pending label block a move. **Two consequences:** the Odoo form's
*Request Replacement* button now refuses until `replacement_reason` and
`approver_id` are typed on the record, and the legacy back-office station's
one-click *Replace* refuses outright — the SPA's barcode station is the path
that works. A pending tag's NUMBER does not resolve on the scan box (on
purpose, unchanged); its asset code and serial do, and name the pending label.

**Since handoff 39 the station is also where a label is CONFIRMED on the
asset.** `POST /assets/<id>/tag-affixed` had been the only way an asset
becomes `is_tagged` since handoff 03, and nothing in the app called it. The
card's *Confirm affixed* opens a dialog that **never hands the expected
number over** — no default, no suggestion, the card's line replaced, the
scan box emptied and the page blurred behind it — because the check is only
evidence if the number comes off the physical label. **The one place it
does appear is the server's wrong-tag refusal, shown verbatim by
instruction; that tension is open for the Architect (`docs/DECISIONS.md`,
2026-10-01).** A repeat is told from a first by reading the `tagging` block
before posting, not by a clock. If you add a place on that page that prints
a tag number, it has to be inside the blurred root while that dialog is
open; the Playwright spec (`e2e/tests/39-…`) asserts the dialog's markup at
open and the scan box, not the blur. **Since handoff 40 the dialog's tag and
serial fields carry the station's own Type / Camera toggle** (the station's
`BarcodeScanner`, reused unchanged, one field at a time, default Type) — and
**a camera detection FILLS the field and does not submit**, where the
handheld's Enter does: a trigger pull is a deliberate act, a camera reads
whatever passes the lens. The dialog became a column whose form scrolls
between a fixed header and footer because the preview pushed *Confirm* off a
720px viewport. The spec (`e2e/tests/40-…`) shows the browser a real label
through Chromium's fake capture device; `docs/ENVIRONMENT-FACTS.md` has the
recipe and its one race.

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
7. **An API credential's power is its scopes, never its groups.** Its `res.users` holds exactly `utils.groups_for_scopes(scopes)` — `base.group_user` plus the `SCOPE_GROUPS` rows — and **never `base.group_system`, `admin` scope included**: a system administrator can run arbitrary server actions, which makes every rule in the model advisory for whoever holds it. `scripts/bootstrap.py` and the `19.0.3.2.0` migration both granted it until handoff 44, and a source guard now fails on either shape; driven without it, nothing the credential's scopes promise broke (report 44 §A). A credential that needs more needs a scope and a `SCOPE_GROUPS` row in a commit, not a group added by hand — the next scope edit erases those anyway (`docs/DECISIONS.md`, 2026-10-02).

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
| 38 | **Before the demo — two things we said in the room, made true.** A scanned SERIAL finds its asset: both lookup routes documented *"tag, asset code, or serial number"* since June and searched the first two; resolution is now tag → code → serial (0 collisions on 8 tenants, the order is for determinism), the serial compared stripped and case-insensitively and EXACTLY, a serial on more than one asset (`nrs19`: 1,291 of them, `PROBOOK` ×94) a miss that says how many, and `matched_by` on every hit · a faded tag is REPLACED by two people on the tag model's own state machine: `POST /tags/<id>/request-replacement` (reason, notes, `approver_id`), `/approve-replacement`, `/reject-replacement` (reason required), a pending queue, and the station's *Replace tag* / *Approve* / *Reject* — proved in one browser session, old number scrapped and existing exactly once, new number minted, chain and reason on the row · the page's "no match" panel had never rendered (a miss is a 404) · **IR number format NOT built, measured instead**: NRS's real IR numbers are on `nrs19` in a studio column `x_ir_number` (11,385 of 11,386, all digits, 5 or 8 long, none with an `O`) and the field Cadra reads is empty there; 0 of 193 IR numbers on the other tenants are anything but seeds and fixtures |
| 39 | **The tagger confirms.** The one control the integration lacked a person for: *Confirm affixed* on the station's card, a dialog the tagger scans the physical label INTO, the server's refusal rendered verbatim (*Scanned tag X does not match the tag issued for this asset (Y)…*), a repeat said as *already confirmed on <date>* with the original record untouched, the affixed state shown instead of the button afterwards · the expected number never handed over — and the first screenshot showed it in the scan box behind the overlay, so the card's line, the scan box and the whole page are blurred while the dialog is open; the one place it appears is the verbatim wrong-tag refusal, open for the Architect · the serial field offered only when the record has one to check · a scrapped label in hand is refused as a mismatch naming the tag NOW issued, the model's own scrapped sentence being unreachable through the route · no Python changed |
| 40 | **The camera in the dialog.** The station offers Type / Camera to FIND an asset and report 39's dialog offered only typing to CONFIRM it — on the phone a tagger at a state office will actually hold, the one step where typing is worst. The same toggle on the dialog's tag field and its serial field, the station's `BarcodeScanner` reused unchanged, default Type, never auto-selected · **a detection fills the field and does not submit** (a trigger pull is deliberate, a camera reads the room), the toggle flips back to Type and the cursor returns to the field · the handheld path proved unchanged: auto-focus, Enter submits · a submit or a close with the camera open stops it, every stream ever opened read `ended` · the no-leak rule unchanged, asserted on the dialog's markup with the camera running · **found by the spec's first run: the preview pushed *Confirm* off a 720px viewport**; a sticky footer floated over the form, so the dialog is now a fixed header and footer with the form scrolling between · proved with a REAL decode — Chromium's fake capture device fed the label Cadra prints, decoded by the platform's `BarcodeDetector` · no Python changed · the first real use prompts for camera permission |
| 42 | **The grant, and the refusal — the write, with the line it cannot cross put in the model first.** `myservice_api/models/access_guard.py` under every writer of membership: no `base.*` group grantable over the API (only Asset User, Asset Manager, Tag-Issuing Unit, Auditor), nobody adds a role to their own account, groups neither created, deleted nor re-meant, accounts not deleted — keyed on `request.jwt_claims`, the one thing only our API sets, so bootstrap, upgrades, the back office and `auth_signup` are untouched and nothing is switched off to install · diff-then-raise like the recorder; a refusal rolls the recorder's rows back (the id gaps in the record are the proof) · `POST /users/<id>/roles` with a dry run that is a real write in a savepoint, rolled back, so the preview shows the effective roles Odoo computes and a refusal before Apply · the *Change roles* section on the Users page, the refusal verbatim · the actor on the row is the person who clicked · **bootstrap grants `base.group_system` to every admin-scoped credential's user**, so report 41's "deliberately not a system administrator" was false on bootstrapped tenants · 11 of 11 first-party groups on the user form · the cluster's sign-up door measured shut (anonymous `/web/signup` → 404 ×4) — `docs/GO-LIVE.md` §19 |
| 43 | **The person, and the door.** The sign-up door shut BY CODE (`_get_signup_invitation_scope` → `b2b`; the `website` module's `b2b` default had been overriding the parameter's `b2c` on 8 of 8 tenants, which is why 42 found it shut) · `POST /users` creates a person with roles and sends the letter in ONE savepoint, `/users/<id>/invite`, `/deactivate`, `/reactivate`, every refusal in words · the invitation and reset letters are the TENANT's (`res.users._action_reset_password` overridden — the one method every path ends in — rendering `cadra.brand_*`, the company's name, a link on the REQUEST's host, no Odoo), received in a real inbox, redeemed, the roles proved by signing in · a deactivated account's live token refused NOW · an archived nominee refused on `/move` · `invitation` on every user row · measured and left: a stranded request names a deactivated approver with no sign of it, and custody is not tied to accounts (`nrs19`: 1 of 11,386 employees has a user) |
| 45 | **The first five minutes — Odoo invisible to everybody who is not a developer.** The letter opens the APP's page with core's own token (old `/web/signup` links redirected, same token, nobody stranded), every dead link said in words (expired told from never-valid by reading the token's own expiry), the password rules Odoo enforces — almost none, measured: `auth_password_policy` on 0 of 9 — published and refused in words, *Forgot password?* answering the same sentence either way · the back office shut by controller AND by session (`ir.http._authenticate`), the verification pass having held a non-administrator's session through JSON-RPC and `/my` · the app's only non-API Odoo request measured by driving it: `/report/barcode`, a label printed as a non-administrator · Odoo's own "Password Changed" mail suppressed on the letter's path · a stranded approval re-pointed, recorded (`nrs.asset.change.request.renomination`, the fourth append-only record) · deactivation and reactivation on the access record and the report, ordered causally within a second · sender address on the branding screen; the relay's plain-text part built and switched off pending its operator · found: an anonymous reset link is only as right as `web.base.url`; approval notifications fail for an actor with no email; a brand module will not install after bootstrap |
| 44 | **The credential that is already root.** `base.group_system` stripped from `test19`'s `admin` credential and the whole HTTP suite driven as it: **nothing broke** — 1,181 of 1,191 passed, 0 failed, and the two skips that waited for a credential that was not root now RUN (somebody else's request cannot be withdrawn; `system` cannot be granted to its own user) · every credential leg answers the same status with and without the group · `bootstrap.py` AND the `19.0.3.2.0` migration stop granting it (the second found by search, not named by the handoff; a guard for both) · the employee xlsx import driven too, its worker runs as root; `scripts/strip_credential_system_group.py` takes it off, dry-run by default, owner-run (3 of 12 local credentials held it; Vendra's and the Tag-Issuing Unit's never did) · what an API credential is entitled to, written down · one name per role, the alias in the model, a guard against a second table · the routes of 41–43 measured live on 4 of 4 cluster hosts · two audit tests that `test19` outgrew (61 accounts on a 50-row page) |
| 41 | **Who has what — the first of three on people, and it changes nothing.** The three register groups and the Auditor on the user form through `res.groups.privilege` (19 has no `category_id`; a privilege is a single choice, so the Tag-Issuing Unit gets its own to stay pairable) · driven as a person holding ONLY the Tag-Issuing Unit: every station read refused at the scope gate, verbatim in the report; the pairing with Asset User documented and the ACL row ruled out · the paired tagger found the four `/barcode/*` wrappers reading as the token's user (`403 … 'Location'` on *Recent tags*), now sudo like every other route · `GET /users`, `/users/<id>`, `/roles` — `roles_direct` and `roles_effective` as two keys, scopes derived from `GROUP_SCOPES` and recomputed by the suite · *Users* and *Access changes* under a new *Administration* nav group, no control that changes anything · nothing in Cadra refuses a privilege escalation over the API, mail on 0 of 8 tenants, `auth_signup` on 8 of 8 — `docs/GO-LIVE.md` §18 |
| 34 | **Warranty — client scope from a demonstration, and the first handoff that spans both repositories.** Cadra goes first: **`myservice_api` 19.0.3.12.0 accepts the keys**, and `openapi.json` says so for Vendra to read, because since handoff 31 a Vendra sending them to an older Cadra would dead-letter every receipt · a duration and a start date, the expiry DERIVED from them and a contradicting one refused, `basis` published beside the date · who honours it as a name, and the certificate number · three states — *no warranty recorded* is the honest third and, measured, 100% of every real tenant — on a Lagos day, and an *expiring soon* window named on the screen · a change is an append-only `warranty_changed` event; a create writes none · a warranty moves nothing about the asset's state, condition or counts · the published block uses the writable names, so a block read can be sent back unchanged (an edited duration goes without the expiry it replaces) · the verification pass found a multi-asset save that would have told SAP of each disposal twice, proved to fail first |
| 46 | **Everyone sees their own job.** Six demo personas — Store Officer, Asset Manager, Tag-Issuing Unit alone, Tagging Officer (Asset User + TIU), Internal Auditor, Systems Administrator — on every classified local tenant, seeded twice (second run changes nothing), marked by the `is_test_fixture` DERIVATION (created by an inert test credential), the `demo.example` domain and an `__cadra_demo__` external id; never an employee; listed, and removed (archived where a move request names them) by one wrapper, `scripts/demo_personas.sh` · **an account that is a fixture is a test ACTOR** — what a persona does on a client's register is labelled too · the handoff's own example name was four real `nrs19` employees; the seed refuses a name the tenant's staff or contacts carry · every sidebar item declares the scope the server requires, proved per persona per item: drawn ⇒ answered, hidden ⇒ 403 · landing on `/assets`, or `/no-access` in words · in-page write controls hidden without their scope · the dashboard stopped showing a refused person 13,150 mock assets · **the roles do not fit the people**: Asset User cannot register, move or verify; the tagger cannot issue or replace a tag; `dashboards:read` admits Fleet and Staff Bus to everybody — `docs/GO-LIVE.md` §23 · found on the way: **every registration walked every tag number past 999 under its prefix** (a text sort put `999` above `8305`) — ~11 s per `POST /assets` on `test19`, 0.2 s now, and one `nrs19` and eight `jaizbankplc` prefixes were paying it |
| 48 | **What this tenant has.** Settings → Sidebar: per-tenant switches for the sidebar's 28 items and 10 groups, a group a master switch, everything on by default · an item is drawn when the TENANT shows it AND the PERSON's scopes open it · **presentation, not permission** — said first on the screen, `is_a_permission: false` in the payload, and a guard that fails if anything but its own route reads a switch; a hidden item's address typed still returns its data (`test19` and `boot44`, as administrator and Store Officer) · keyed on declared literals, never label/path/scope, so 47's scope changes cannot switch anything back on · one config parameter per switch, so each is a row in the configuration-change report · the Sidebar screen and its group cannot be switched off · found: Staff Bus and Identity are sample data, and the real NRS register has 0 vehicles — `docs/GO-LIVE.md` §24.2 |
| 37 | **The doors, and the two red tests nobody named — written before 38, run after 48.** The naming convention ruled: one name per field, published and writable; an old published name survives only as a read-only OUTPUT alias, never an accepted input (33 §B2 unblocked, not executed) · the identity door ruled for retirement — SAP gets `POST /api/v1/integrations/sap/employee-sync`; the census re-taken before being quoted (0 `webhook` rows OF 287, all eight tenants, 2026-10-03; the old figure had moved 163 → 179 → 286) and the secret set on 0 of 8, provisioned by nothing · driven side by side: **the old door cannot create or update an employee on Odoo 19 at all** (`hr_version.last_modified_uid` NOT NULL vs `auth='none'`'s userless environment — error rows under `success: true` for the life of the 19 stack), and its documented list shape dies in the JSON-RPC dispatcher · the unvalidated dict closed ON THE MODEL for all six callers (the CSV wizard passed unknown spreadsheet columns straight through) · quick-submit's schema-`required` pair enforced, the first-active-type fallback and placeholder title deleted (BREAKING, announced) · **the two red tests were the product and they were red ONE HOUR A NIGHT**: the register stamps a disposal with the Lagos day, the depreciation module measured today in UTC, so 23:00–24:00 UTC a fresh disposal read `fully_depreciated` — reports 31, 32 and 34 ran it green (775/796/820-test denominators — which the frozen clock proves can only happen outside the window), report 35 never ran this module's suite, and report 36's session brushed midnight Lagos and was the first inside it; one definition of the day on both sides now, pinned by a frozen-clock test proved to fail first |
| 49 | **The auditor's own screens.** Four reads the server answered for weeks with no page asking, now pages in the Audit group, no route changed: Configuration changes (`settings:read`), Disposals, Register snapshot and Export (`assets:read` — drawn for every Asset User too, the server's own gate; role-model finding, GO-LIVE §26) · the export downloads `export.csv` with the bearer token (`apiGetRaw`), size before the click, preparing during, rows/bytes/seconds after — `nrs19` 11,951 rows in 1.2 s, file = screen = register · §4 answered with no new endpoint: the snapshot's departed-custodians card from `/identity/employees?active=false` (87 assets / 59 people / 0 flagged on `nrs19`, denominator always shown, measured NOW and says so) · the snapshot deliberately filterless (route filters select on TODAY's values) · empty states proven with a measured-empty period — 1990, because every tenant's fixtures backdate disposals to exactly 2020-01-01 · found: a null `book_value` white-screened the app — no error boundary (GO-LIVE §26) · spec 49 4/4 on `test19` and `boot44`; published sidebar keys 26 → 30 |
| 50 | **The consequences.** Taking a copy of the register is its own permission: `export:read`, both export routes, granted by exactly the Auditor (BREAKING; named `:read` so the Auditor-is-read-only pin holds) · any render error is a sentence — `RouteErrorBoundary` inside the shell, keyed on location, proved by a deliberate throw with the sidebar alive · the attribution rule made mechanical: a commit-msg hook + a CI job over NEW commits only refuse the trailer (reports 37 and 49 both shipped it; 206 of 209 historical commits stay as ruled) · GO-LIVE §25's hole closed: `/dashboard/map` sends `locations` only, the plate-and-driver rows moved to `GET /fleet/map` under `operations:read` (0 geocoded vehicles of 3,338 on nine tenants — the shape leaked, never yet a row), `recent_requests` deleted unread · §2.2 re-counted: 8 active non-admin credentials hold `assets:read`; the 47 leftovers confirmed, still owner-ruled · the two red browser specs named with their first recorded failure texts — neither is 37's defect (a spec-fixture defect; the persisted-cache hypothesis matched point for point) · handoff 33's remainder landed: `salvage_rate` + `verification_notes` published (write-only waivers removed so the guard enforces them), `mobile` dropped from the sync for all six callers (0 of 15,780 employees, 0 of 321 payloads), the census widened to every first-party `controllers/*.py` (73 body routes of 142 declarations, two-way), the words guard's two string classes separated and drawn over five report endpoints |
| 51 | **The queue and the refusal — the last Cadra handoff before the demo.** `GET /api/v1/tags/replacements` (`assets:read`): every replacement request, decided ones included — `state` on the label's own lifecycle, `waiting_on_me`, `raised_by_me`; `pending-replacements` stays pending-only by its published name · `/approvals` shows tag replacements beside movement requests, two sections under the same tabs, each with its own query, honest count and empty sentence; driven as requester (no decide control, the you-asked sentence), named approver (waiting → approve → replaced) and auditor (no control), plus the tagging-only 403 naming `assets:read` · **a refused affix leaves an append-only `affix_refused` event** — written on its OWN cursor because the decorator's rollback unwinds the request's (both placements measured: the same-cursor row reaches the DB on flush and vanishes on rollback; the own-cursor row survives the real 400 into a separate read); refusal text byte-identical; the wrong-then-right sequence reads in order with the gap visible · spec 13 fixed (first CHARTABLE asset; loud skip), **spec 14's persisted-cache hypothesis CONFIRMED by its first mid-test dump** (the failing attempt restored a pre-click payload the 1 s write throttle had preserved and never refetched it; the passing retry had no persisted entry and fetched fresh) · the two withdrawn rulings recorded in `docs/retired-screens.md` · §4's page-load check caught `ITAssetsCommand` crashing on every tenant WITH an IT category (a hook below three early returns — React 310); one hook moved, 150 pins render · found and named: the approvals badge counts none of 194 pending replacements; the station panel truncates at 100 silently; the IT category regex matches the "it" in *Furniture* |
| 52 | **The Builder's list — six findings from report 51 §9, made the work.** The approvals badge sums BOTH queues (movement + pending tag replacements; nothing drawn when either total is missing) · the station panel ends with the truth: *showing the 100 most recent — N more on the Approvals page*, N from `total_estimate` · the IT dashboard matches `\b(IT|computer|laptop|server)\b` and prints *Showing: <category> (N assets)* — `domain`/`code` measured and lost (seed-only; jaiz's real "IT Equipment" carries neither); before/after on `jaizbankplc`: *21 Furniture records* → *Showing: IT Equipment (21 assets)* · the scrapped and serial-mismatch refusals recorded with `reason` in the payload and a sentence each — the err-path placement MEASURED: a same-cursor write survives there (no exception, no rollback), shared own-cursor recorder shipped anyway · **the cache ruling: restored data is never fresh** — `onSuccess` invalidates everything on restore, paint unchanged (~0.4 s), burst +15/+3/+3 calls on three screens; spec 14 green ×3 with instrumentation kept, after its own race was found (the reload ABORTED the in-flight PATCH and the old green was the restored sketch of a write the server never got — the spec now awaits the PATCH response) · two guards red-once-then-green: the SPA's scope maps vs `utils.py`'s 19 (SCOPE carried 17), the endpoint reference's index vs a static census (64 rows of 115 → 115) |
| 54 | **Every time — the scanner's engine.** The camera's decoder is BUNDLED (`zxing-wasm` behind `scanEngine.ts`) and is THE engine on every device — the platform `BarcodeDetector`, which existed on some phones and not others and honoured an unchecked subset of the formats asked for, is gone, not demoted · 13 formats, the reticle decoded first and true, ~10 fps, 1D accepted on two agreeing decodes and 2D on one (`scanDecision.ts`, pure, unit-driven), two values in frame a tap-to-choose, never a guess · silence ends at 4 s and offers typing at 10 s with the camera left running · zoom where the hardware has it, a camera picker when there are several (the demo Mac's fixed-focus built-in vs a Continuity Camera), granted `getSettings()` printed on the preview · `onDetected(value, format)`; the affix route accepts `scanned_format`/`serial_format` (enum, refused outside it, nothing written) and the `affix_refused` event records the symbology beside the refused value — a successful affix stores nothing new · the corpus: 408 offline decodes through the same wasm, Cadra's labels from the REAL renderer at template metrics, N of M everywhere, committed baseline · **found: the small/standard labels' Code 128 is ≈5 mil/module — below any camera's floor (0 of 24 each); the QR reads on every size; template question open** · §6c's real-device table owner-blocked (no "Needs the owner" block named it — handoff defect) · wasm lazy, boot path unchanged (2,076→3,060 KB all in lazy assets) |
| 47 | **A role is a job.** `identity:read` and `dashboards:read` each split in two — `access:read` (the access record, the Auditor's) and `operations:read` (fleet/staff bus/FM/security; the sidebar group key `operations` is a different namespace, on purpose) · tag minting and replacement moved to `tagging:write` (BREAKING — a manager no longer prints labels; the unit's scope covers its job) · **the Asset Officer**: Asset User's reads + `assets:write`, implied by Manager, grantable (the named fifth entry handoff 42 demanded), published as `asset_officer` · `SCOPE_GROUPS[assets:write]` → Officer, so Vendra's credential reads as what it does · Staff Bus and Identity (clearance) out of the sidebar (keys retired, routes serve, clearance OWED to NRS — `docs/GO-LIVE.md` §25) · the hardcoded *All systems operational* pill deleted |

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
