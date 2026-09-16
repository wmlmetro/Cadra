# Cadra — go-live ordering

The deployment steps whose **order** matters, and what breaks if they are taken
in the wrong one. This is the Cadra half of the ordering; the Vendra repository
carries its own copy, because a deployment order that breaks another system's
write path is not a Cadra-only fact.

**Part I** (below) is about the **DOKS `cadra-dev` cluster**
(staging.app.cadra.ng and the tenant hostnames). For the Docker Compose
profiles see [DEPLOYMENT.md](DEPLOYMENT.md).

**Part II is not.** It is the programme-wide open-items register added by
handoff 26 — scripts, tenants, credentials and decisions, most of them about
the local estate or about nothing machine-specific at all. Read the two as
separate documents that happen to share a file.

---

## 1 · Every tenant is upgraded at or before the image roll

**Never roll the `odoo-19` image before `upgrade-19` has run for every tenant
database carrying the modules that changed.**

One Odoo process serves every database from one registry. The moment a new
stored field lands in the Python, a tenant that has not been upgraded is broken:
reading the column raises `UndefinedColumn`, and any serialiser that touches it
turns the endpoint into a 500.

This is not hypothetical. Handoff 09 added
`nrs.asset.category.verification_interval_days`, which `_compute_verified` reads
on **every `nrs.asset` create and write** — which is **Vendra's INT-03 write
path**. During that handoff the field landed before the fan-out finished and
`POST /api/v1/assets` 500'd for every call until it did.

```
Actions ▸ upgrade-19          # for every tenant DB, before anything rolls
Actions ▸ deploy-dev (roll_odoo = true)   # or deploy-19
```

`upgrade-19` scales `odoo-19` to 0 for the duration and restores it, and rolls
the image forward itself when every tenant succeeded — or back to the previously
deployed image when one failed, so the pods that come back match the schema they
will read.

---

## 2 · A ConfigMap change does not take effect until `odoo-19` is rolled

`odoo-config-19` reaches the container through a **`subPath` mount**, which
Kubernetes excludes from ConfigMap update propagation — the file inside a
running pod never changes — and the container copies it to `/tmp/odoo.conf` at
startup anyway. `odoo-bootstrap-19` arrives through **`envFrom`**, and a
process's environment is fixed when the process is created.

So `kubectl apply` on either one changes the cluster and changes **nothing that
is running**. `deploy-dev` applies both on every push to `dev` and deliberately
does **not** roll `odoo-19`, because it is `strategy: Recreate` on an RWO
filestore and a roll briefly interrupts every live tenant.

**Since handoff 10 this is loud rather than silent.** `deploy-dev` and
`deploy-19` both end by comparing the running pod against the ConfigMaps they
just applied and **failing the job** when they differ. To clear it:

* re-run **deploy-dev** with `roll_odoo = true`, or
* run **deploy-19** with `run_bootstrap = false`.

Both roll `odoo-19` and both briefly interrupt every live tenant. That
interruption is why it is a deliberate button and not something a push does on
its own.

**Settled 2026-09-08.** Handoff 09 set `publisher_warranty_url` in
`k8s/dev/10-configmap-odoo-19.yaml` to stop Odoo's `Publisher: Update
Notification` cron POSTing each tenant's company name, email and phone to
`services.odoo.com` weekly. Both halves are now live in the cluster, done by an
`upgrade-19` run at 06:54 UTC (run `34196778181`):

1. **`publisher_warranty_url`** — `upgrade-19` rolls the image forward at the
   end of its run, so the pod restarted onto the current ConfigMap. Confirmed
   independently by the guard in §2: it read `/etc/odoo/odoo.conf.template` out
   of the running pod and found it identical to the repo's.
2. **The per-tenant cron rows** — `myservice_nrs_base`'s `19.0.1.1.0`
   post-migrate ran on **staging, gtb, jaizbankplc and lasg**, each logging
   *"2 third-party scheduled action(s) deactivated"*.

**`nrs` did not run that migration, and does not need to.** Only 14 modules
load on that database against 77 on the others — our modules are not installed
there — so there is no `myservice_nrs_base` to deactivate anything. It is
covered by layer 1, which is a server-wide config setting and therefore applies
to every database the worker serves, installed modules or not. That is the
division of labour the module's own docstring describes: the config is the
durable half, the cron deactivation is the second layer.

---

## 3 · Turnstile's two halves go together

The sitekey is a **build arg** baked into the frontend bundle
(`VITE_TURNSTILE_SITEKEY`); the secret reaches Odoo through bootstrap
(`CADRA_TURNSTILE_SECRET`). A secret with no sitekey locks everyone out of the
login form. Set both, or neither.

---

## 4 · Provisioning a tenant is not installing modules

`-i` / `-u` never run `scripts/bootstrap.py`, so a database created the
documented way has **no `jwt_secret` and no API client** — `/auth/login` 500s
and no integration can authenticate. Use `deploy-19` with `run_bootstrap = true`
and a `bootstrap_db`, or run the bootstrap explicitly. See
`k8s/dev/MULTI-TENANT.md`.

---

# Part II · The open-items register

**This is where the programme resumes from.** Handoff 26 was the last one;
there is no 27. Contracted core scope was complete at handoff 23, and the
three handoffs after it were about the quality of the record rather than its
scope. What stands between this system and a delivered one is four servers, a
test SAP environment, four answers from the NRS SAP team, a fixed-asset
register extract and some credential rotations. **None of it is code.**

Every item below is tagged:

- **`[open]`** — known, not done, and nobody is currently doing it.
- **`[verified]`** — proved on a real system on a stated date, with the
  evidence beside it. A `[verified]` item can go stale; the date says how
  much to trust it.
- **`[landed, keep it that way]`** — built and working. It is here because
  the easiest way to break it is not to know it exists.

**An item is not ticked because it sounds right.** Everything here carries
either a measurement or the report it came from.

**There are no questions in this register, only decisions to make.** Where
handoff 26 would have asked the Architect something, the options are written
out instead, so whoever picks this up reads a choice rather than a cliffhanger.

---

## 5 · The two owner-run scripts

Both are run by hand, against one tenant, through `odoo shell`. Neither runs
in CI and neither is wired to a deploy. Both refuse a database classified
`production` **and a database carrying no class at all** — an unclassified
database is not a safe one, it is one nobody has thought about.

```
docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
  odoo shell -c /etc/odoo/odoo.conf -d <db> \
  --http-port=8099 --gevent-port=8098 --no-http \
  < scripts/<script>.py
```

### 5.1 · `scripts/mark_test_fixtures.py` — `[verified]` on `test19`, `[open]` on `jaizbankplc`

**What it does, in four steps.** Flags the archived `Handoff23 Approver`
credential as a test credential; appends a disclosure to the
`disposal_reason` of every fabricated approved disposal; appends
` [TEST FIXTURE]` to the **name** of every fixture that cannot be removed;
and reports what is left unidentifiable in words rather than as a zero.

**What a run leaves behind.** Records with a changed `disposal_reason` and a
changed `name`. Nothing is deleted, nothing is un-approved, no fixture is
fabricated. It is idempotent — **proved by running it twice on `test19` on
2026-09-15**: the second run reported `marked 0, already marked 20` for
assets and `marked 0, already marked 12` for locations.

**Verified on `test19`, 2026-09-15** — 7 disposals disclosed, 20 assets and
12 locations marked, and the "no such client" case printed out loud rather
than passing silently.

**Open on `jaizbankplc`.** Handoff 24's half of it (the credential and the six
disposals) has already been run there and is confirmed in the database —
`Handoff23 Approver.is_test_credential = t`, all six disposals carrying the
disclosure. The handoff-26 half (the name marks) has **not** been run. What
it would do there, measured with SQL on 2026-09-15:

| | |
|---|---|
| fixture-named assets | 3,894 of 4,164 |
| → assets it would mark (cannot be removed, all reasons) | **115** |
| → of which hold a chain-of-custody row | 99 |
| → of which an approved disposal | 6 |
| → of which a service request points at | 105 (overlapping) |
| fixture-named locations | 368 of 440 |
| → locations it would mark | **17** |

### 5.2 · `scripts/remove_test_residue.py` — `[open]`

**Dry run by default; `CADRA_APPLY=1` is the only way through.** The dry run
MEASURES rather than predicts — every candidate is actually unlinked inside a
savepoint which is then rolled back, so its counts are deletions that really
succeeded. Run it dry, read the refusals, then apply.

**It will never remove:** an asset carrying a chain-of-custody row (the model
refuses `unlink` unconditionally and the FK is `ondelete='restrict'`); an
asset carrying an approved disposal (deleting the record is not a reversal,
it is the same fabrication one step on); anything a real service request
points at (the FK is `set null`, so the delete would succeed while silently
blanking a live request's field); and every custody row `source: test`.

**A defect fixed in handoff 26 that had not yet fired.** Its production
refusal read the database class through `ir.config_parameter.get_param`,
which is `@ormcache`d per worker — the exact call handoff 25 had just
finished proving unsafe, written into this script by the handoff that found
the leak. It now reads the row with SQL through `database_class(env)`. **If
this script has been run by anyone before 2026-09-15, the refusal it passed
was not necessarily reading the database.**

---

## 6 · What can never be identified again — `[verified]` 2026-09-15

**460 service requests on `jaizbankplc` are permanently unidentifiable.**
`request.request.name` is a sequence (`REQ-000692`), not a name the test
suite chooses, so a test-created request has never been distinguishable from
a real one by any rule any script can apply. Of those 460, **0** carry a
self-label.

`is_test_fixture` (handoff 26 §A) closes this **forward only**. It is derived
from the acting credential at creation and cannot be reconstructed for a
record created before it existed, the same way the access record of handoff
24 is not retroactive. Also unidentifiable, on the same tenant and the same
date: **270 assets** carrying no fixture name at all (4,164 total, 3,894
named), and every one of 440 locations, 4,164 tag labels and 14,451 chatter
messages created before the field landed.

The 3,894 that DO carry a fixture name are identifiable **by convention
only** — by a prefix somebody chose to type — which is weaker than the
derived label and is exactly the distinction handoff 26 §D draws between the
name mark and `is_test_fixture`.

**The honest statement to give an auditor:** the register began telling the
truth about itself on 2026-09-15 and says nothing about the day before.

---

## 7 · The three unclassified tenants — `[open]`, with a proposal each

`cadra19`, `nrs19` and `gtb19` carry no `cadra.database_class`. **Nothing is
unsafe today** — absent refuses, so both test suites and both scripts already
decline to touch them. What is missing is a decision, and *unknown* is a
state somebody eventually resolves by guessing.

**The rule when it is genuinely ambiguous is `client`.** A test database
wrongly marked `client` costs somebody an afternoon. A client database
wrongly marked `test` costs a register.

The command is printed by any refused run, and is:

```
docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
  odoo shell -c /etc/odoo/odoo.conf -d <db> --no-http \
  --http-port=8099 --gevent-port=8098 <<< \
  "env['ir.config_parameter'].sudo().set_param('cadra.database_class','<class>'); env.cr.commit()"
```

### 7.1 · `nrs19` → **`client`.** Confidence: high.

Measured 2026-09-15: **11,942 assets, 11,386 employees, 1,154 locations, 0
fixture-named records.** The employee list is a real NRS staff extract — it
names actual serving NRS officials, including the Executive Chairman — and it
was loaded from client-supplied CSVs that are **in this repository** at
`docs/seed/NRS_all_csvs/` (`employee_master.csv`,
`IMPORT_ALL_ICT_nrs_asset.csv`, `IMPORT_fleet_nrs_asset.csv`). 11,878 of the
assets landed on one day, 2026-08-06, which is the ETL.

**It is also the tenant Vendra's integration work measures against**:
`docs/api/.creds.nrs19` holds the two counterparty credentials, `Tag-Issuing
Unit` (INT-05) and `Vendra (INT-03)`, and its own header calls it *"the
working tenant for integration and demo work"*. Marking this `test` would
point the writing test suite at real NRS personal data and at the register
another organisation is building against.

### 7.2 · `cadra19` → **`client`.** Confidence: medium — this is the one worth a second opinion.

Measured 2026-09-15: **1,335 assets, 754 locations, 80 requests, 2
employees** (one of them named `Py Test`), **50 fixture-named assets**, 0
custody rows. Company is *Nigeria Revenue Service*.

**The argument for `test`:** it has already been written to by the suite, it
carries a fixture employee, it has no custody chain, and nothing outside this
repository references it — a full-text search found it only in `CLAUDE.md`,
in four frontend comments quoting asset counts, and in one migration comment.

**The argument for `client`, which is why the proposal is `client`:** its
seeded assets (1,285 of the 1,335 carry no fixture name) come from
`scripts/nrs_hq_seed.py`, whose own header
names its sources as **real client documents** — Baron Architecture drawings
A400–A485, the Unecon Associates M&E completion schedule, and the *FIRS HQ
Furniture Inventory* dated 11/02/2026 — mapped to a real 19-floor, 232-room
building. That is client-derived content describing a real building, not
invented data, and the asset serials (`Dell Latitude 5450 (KILL203659-3)`)
read as real.

**If somebody wants a second local test tenant, the right move is to make
one**, not to reclassify this. `test19` already exists, is marked, and has a
credential pair.

### 7.3 · `gtb19` → **`test`.** Confidence: medium-high, and it is the only `test` proposal here.

Measured 2026-09-15: **156 assets, all created on 2026-08-06**, 149
locations, 61 employees, and **6 fixture-named assets already in it**
(`pytest-asset-*`, `idem-asset-pytest-*`) — the suite has already written
here.

Every category of its content is reproducible and none of it is client-supplied:

- the 156 assets are generic bank equipment from `scripts/gtb_data_seed.py`
  (`NCR SelfServ 22 ATM`, `Perkins 100KVA Diesel Generator`);
- the 61 employees are synthetic (`Amaka Adeyemi`, `Emeka Afolabi`, `Zainab
  Balogun`, `Musa Chukwu` — generated, alphabetical by surname);
- the 122 branch locations come from `scripts/gtb_locations.json`, which
  marks every row `"source": "OSM (real)"` — **public OpenStreetMap data**,
  not a client extract.

**The real GTB tenant is `gtb`, which is already marked `client`.**
`k8s/dev/60-ingress.yaml:82` records that the live database *"was renamed
from the seeded `gtb19`"*, and `k8s/dev/11-configmap-bootstrap-19.yaml:7`
describes `gtb19` as a database bootstrap was **validated against**. That is
a test database by construction.

**The one caution:** the name `gtb19` is also used by
`.github/workflows/deploy-19.yml` and `tenant-cutover-19.yml` as an example
`bootstrap_db` on the DOKS cluster. Those are a **different database on a
different machine**; classifying the local one says nothing about the cluster
one, which needs its own mark.

---

## 8 · Credentials — `[open]`, all of them

### 8.1 · `admin` / `admin` is accepted on every local tenant — `[verified]` 2026-09-15

Tested through `/web/session/authenticate` against all eight local databases
— `cadra19`, `nrs19`, `gtb19`, `test19`, `nrs`, `lasg`, `gtb`,
`jaizbankplc`. **All eight accepted `admin` with the password `admin`** and
returned a uid.

These are local replicas, and that is not the reassuring reading of it: the
same `scripts/bootstrap.sh` provisions the cluster, so this is a statement
about **what bootstrap leaves behind**, not about this laptop. `nrs19` in
particular holds a real NRS staff extract behind that password.

**Before any environment an NRS user can reach, every tenant's `admin`
password is set to something nobody has typed into a terminal.** There is no
code change here; it is an operational act, per tenant, and it is the first
item on this list for a reason.

### 8.2 · The `ODOO_ADMIN_PASSWORD` Secret — `[landed, keep it that way]`

Handoff 18 took `ODOO_ADMIN_PW=admin` out of `Dockerfile.nrs-import`'s image
layer, where `docker history` printed it to anyone with registry access. The
entrypoint now refuses and names the Secret
(`scripts/nrs_import_entrypoint.sh:29`), the Job reads
`cadra-odoo/ODOO_ADMIN_PASSWORD` (`k8s/dev/71-nrs-import-job.yaml:73`), and
`nrs-import.yml` pre-checks the key so a missing `secretKeyRef` fails loudly
instead of leaving the pod in `CreateContainerConfigError` with no logs.

**Keep it that way**: the guard that stops it coming back is
`tests/test_source_guards.py`'s credential readers, which grew a `pw` pattern
in handoff 18 because `ODOO_ADMIN_PW` had matched nothing.

### 8.3 · The two live-cutover credentials — `[verified]` 2026-09-15, and open in a different way than it reads

Named in report 17 §3 and carried as unrotated by reports 18, 20 and 21.
Both literals entered git history at `a4b505a` and **cannot be removed from
it**:

| parameter | what it guards | held by |
|---|---|---|
| `myservice_identity.redhubs_api_key` | `POST /api/myservice/assets/export` and the CSV twin — **a full dump of the asset register** | Redhubs |
| `myservice_identity.sap_webhook_secret` | `POST /api/sap/employee-sync` — **inbound employee create/update** | SAP SuccessFactors / the NRS SAP team |

The burnt literals themselves are **deliberately not reproduced here.**
`tests/test_source_guards.py::test_the_compromised_literals_are_gone_from_first_party_source`
refuses any file in this repository that resolves to either value, and it
**failed this handoff's own test run** when the first draft of this section
pasted them into the table. The guard is right: they are in git history and
nothing should make them easier to find. Report 17 §3 names them if you need
to recognise one.

**Measured on 2026-09-15: NEITHER PARAMETER IS SET ON ANY OF THE EIGHT LOCAL
TENANTS.** So the state is not "a compromised key is live in a database" —
handoff 17 took the literals out of the source and the routes have refused
ever since.

**What is actually open is the other half of the cutover: nobody has issued
replacements.** Until an operator sets each parameter per tenant and gives
the new value to Redhubs and to the NRS SAP team, **both integrations are
down, answering `Unauthorized`** — which is the intended, announced behaviour
and is also a thing somebody is presumably waiting on. Each rotates in
exactly one place per tenant; report 17 verified independently that the
literals appear in no ConfigMap, Secret, `.env`, seed script, compose file or
workflow.

**Do not re-use the old values.** They are retrievable from git by anyone who
can read the repository.

### 8.4 · `.env` in git history — `[open]`

`.env` was tracked *and* gitignored until 2026-09-05 (handoff 04), so a real
dev client secret sat one `git add .` from a commit and **is in the history**.
Rotating it is not free: Vendra's `site_config` holds that secret, so
rotating without updating Vendra breaks INT-03. The two must move together.

**Git history is not fixed by a later commit.** Anything that was ever
committed stays retrievable; rotation is the only remedy.

---

## 9 · API and platform items carried forward — `[open]`

### 9.1 · The nine pre-envelope routes

`/auth/*`, `/openapi.json`, `/docs`, `/assets/export.csv`,
`/integrations/employees/import` and `/brand` do not use `@cadra_route`.
They validate nothing and sit outside the PRD §10.7 envelope — and
`/auth/token` is the first endpoint every integration touches.

**This now blocks something concrete.** Report 25 could not make the test
suite refuse *before writing anything*: classifying the target database needs
a bearer token, `POST /auth/token` creates a refresh-token row, and
`cadra_endpoint` has no public mode. One row lands in the target database
before the refusal prints. Closing that needs an unauthenticated
classification route, which is this refactor's territory.

### 9.2 · The CI-series guard does not catch the file it was written to delete

`tests/test_deployment_profile.py:315` skips any line without `odoo` in it,
and the deleted `.gitlab-ci.yml`'s pin was `SERIES_BRANCH: '15.0'` — no
`odoo` on that line.

**Report 25 §4 states this was closed in handoff 23** (the `odoo`-on-the-line
requirement replaced by an allow-list of the two non-Odoo `<major>.0` shapes,
with a mutation proof reading `tests/fixtures/retired-gitlab-ci.yml` byte for
byte). **`CLAUDE.md`'s backlog still lists it as open.** One of the two is
stale; the evidence favours report 25. **Read the guard before trusting
either.**

### 9.3 · Per-session test artefact paths

Two concurrent pytest sessions clobber each other's report and captures
(`docs/api/test-report.md`, `docs/api/test-responses/`). Cosmetic, and it has
never yet cost anything.

### 9.4 · `Finance Officer` / `finance_viewer` — `[landed]` as a ruling, not as code

Ruled in handoff 24: it is `group_auditor` under another name and will not be
built as a second group. **There is no field-level access control anywhere in
Cadra** — no `groups=` on any field in any first-party module,
`serialize_asset` takes no scope argument, and every route runs `sudo()`, so
an Odoo group cannot subtract a field. The finest cut available is
route × scope, and financial fields are not a route.

A `finance_viewer` built today would be `group_auditor` minus three
NON-financial scopes — a narrower auditor, not a finance role. The
deliverable is the paragraph in `INT-10 §4.3`, which exists.

**Separately, and not the same question:** specification §3.4/§3.5 cast
Finance as a disposal **approver**, which is `approvals:write`. Nobody has
built or refused that.

### 9.5 · The retroactive access question — **NRS's decision, not a backlog item**

Handoff 23 established that **no access-change history exists** and that
nothing about it can be made retroactive: `res_groups_users_rel` is `(gid,
uid)` with no timestamp and no actor, `group_ids` carries no tracking,
`mail_tracking_value` holds 0 rows on `res.users` / `res.groups` on all eight
tenants, and `ir_logging` holds 0 rows on all eight.

The three options and the recommendation are written out in
`docs/integrations/INT-10-audit-access.md` §2.10b. The recommended one is
`tracking=True` on a `res.users` override of `group_ids`, whose real work is
the many2many tracking-value reader rather than the declaration.

**Whichever is chosen, the record begins the day it is built.** That is a
decision for NRS about what they need, not an engineering backlog item, and
it should be put to them in those terms.

---

## 10 · The silent-instrument sweep — what was fixed and what was not

Handoff 26 §B swept `scripts/` and every maintenance path for one shape: **a
step that operates on a named thing, finds no such thing, and treats zero as
done.** It found **24 distinct sites**. **Thirteen were fixed** and one more was
documented in place; the remaining eleven are recorded
here because they are real and none of them is urgent.

### 10.1 · Fixed in handoff 26 — `[landed, keep it that way]`

| site | what it did |
|---|---|
| `remove_test_residue.py` | production refusal read through the ormcached `get_param` — the one guard between `CADRA_APPLY=1` and a real register |
| `bootstrap.py` ×2 | archived API client invisible to `search()` → a SECOND row with the same `client_id`, reported as a success |
| `bootstrap.py` | downgrade interlock read through the same ormcache |
| `bootstrap.py` | archived `ir.mail_server` → duplicate (`active` confirmed at core `ir_mail_server.py:197`, not assumed) |
| `bootstrap.sh` | a FAILED psql measurement became a confident *"fresh DB"* and ran `odoo -i` against a populated database |
| `audit_report_fingerprint.sh` | discarded psql's stderr, so a stopped container and a genuinely absent table printed identically — a proof instrument that proved "nothing was written" by measuring nothing |
| `seed_asset_costs.py` | refusal gated on a database **NAME** allowlist that did not contain `jaizbankplc`; now gates on the class, and a refusal exits 1 instead of 0 (the k8s Job was reporting **Succeeded** for a run that did nothing) |
| `nrs_hq_seed_v4.py` ×3 | printed `ERROR … not found` and carried on, matching unrelated top-level locations; summary printed GLOBAL counts so a run that tagged nothing showed a previous run's numbers; an `else: pass` under a comment describing a fallback nobody wrote |
| `mark_test_fixtures.py` | `('name','like','H23%')` — Odoo wraps `like` in `%…%`, so a real `PUMP-H23-4` would have been disclosed as a fixture |
| the three brand seeds ×2 | a `✓` printed over three zeros when the asset-code sequence was missing; `custodians wired: 3998` printed for facility matching that had fallen through entirely |

### 10.2 · Found, not fixed — `[open]`

None is urgent and all are recorded with file and line in report 26. The
shape they share: a summary that measures **the world rather than the run**,
or a `search()` that asks "does this exist" without `active_test=False`.

- `backfill_external_ids.py` ×3 — archived rows invisible to XML-RPC
  `search_read`, so the printed prediction *"will be CREATED"* is right about
  the outcome and wrong about the reason, leaving the operator no reason to look.
- `nrs_hq_seed.py`'s `get_or_create` (7 call sites) and
  `load_{gtb,jaiz,lasg}_locations.py` — same archived-record shape; the line
  that would tell you something went wrong reports the duplicate as a success.
- `migrate_nrs_locations.py` — a glob that matches no CSV prints
  `0 categories, 0 sub-categories` and continues, run unattended by
  `nrs_import_entrypoint.sh`.
- `fleet_location_matcher.py` — a `.get(tag, [])` default silently degrades
  match quality estate-wide, and the final report is a global count.
- `seed_nrs_assets.py` — per-file `!` warnings but no "0 of 6 loaded"
  aggregate, then `Done.`
- `bootstrap.sh` — `odoo shell <<< exec(...)` swallows the exit code, so an
  uncaught exception in `bootstrap.py` prints a traceback and still exits 0.
  The refusal text is visible in the tail that gets dumped; the exit status
  is not. **Worth a ruling**: turning that warning into an abort would stop
  prod deploys for reasons nobody has enumerated.

### 10.3 · The guard that makes it a property — `[landed, keep it that way]`

`tests/test_fixture_patterns_agree.py` fails if the two fixture scripts
disagree about what a fixture name looks like, and fails on any unanchored
`like` against a record name in either. A deliberate substring match is still
written `=like` with its own explicit `%` wildcards, so the intent is in the
code rather than in the reader's memory of Odoo's defaults.

---

## 11 · The fixture label itself — `[landed, keep it that way]`

`is_test_fixture` (handoff 26 §A) is stamped onto 14 models from the acting
credential at creation. **The three things that make it a derivation rather
than a convention, and that a future change could quietly remove:**

1. `create()` **overwrites** whatever arrived in `vals`. A caller cannot
   declare itself real or slander a real record.
2. `write()` refuses to move it, **unconditionally** — there is no superuser
   branch, because a superuser branch is what an `odoo shell` one-liner uses.
3. It is in no `_WRITABLE_FIELDS`, and
   `test_the_derived_label_is_not_writable_over_the_api` fails if it is added
   to one.

`tests/test_source_guards.py::test_every_model_a_first_party_path_creates_is_classified`
enumerates every model any first-party path can create and fails on one that
is neither labelled, nor labelled by its own older mechanism
(`nrs.asset.custody.source`), nor exempted **with a written reason**. A model
added next year turns the suite red on the day it is added.

**Adding a model to the mixin is a multi-tenant migration**, not a code
change: a stored field on an un-upgraded tenant raises `UndefinedColumn` on
every read. All eight local tenants were upgraded and verified at 14 columns
each on 2026-09-15; on the cluster the `cadra-upgrade` Job must fan out the
same way — see §1 of this file.

### 11.1 · One route discards the actor before creating, so its records are never labelled — `[open]`

`myservice_website_theme/controllers/api.py:198`:

```python
req = env['request.request'].with_user(SUPERUSER_ID).create(vals)
```

`with_user(SUPERUSER_ID)` **replaces** the acting user; `.sudo()` would have
elevated privileges while keeping it. So a service request created through
`POST /api/v1/home/quick-submit` — which IS authenticated, by a credential —
is written as `__system__`, and `is_test_fixture` correctly derives `False`
because there is no credential in the environment to read.

**Measured on `test19`, 2026-09-15.** Stated as an invariant rather than a
count, because the counts climb with every suite run and a snapshot goes
stale between two readings of this page:

- **every record created through a CREDENTIAL after the field landed is
  labelled** — assets, locations, tag labels and transfers, 100%, no
  exceptions;
- **every unlabelled record has `create_uid = __system__`**, and they are
  service requests, their request events, and the chatter hanging off them.

Both halves were re-checked after several further suite runs and both still
held. It is the only `with_user(SUPERUSER_ID)` in any first-party module.

**Not changed, deliberately.** The same handler serves the `auth='public'`
twin at `/api/myservice/quick-submit`, where the acting user is the public
user rather than a credential, so swapping in `.sudo()` changes what
`env.user` is during a create on a PUBLIC route — a behavioural change to an
unauthenticated path, made in a handoff about test labelling, with no test
covering what depends on it.

**The decision to make.** Three options:

1. **Swap `with_user(SUPERUSER_ID)` for `.sudo()`.** Smallest change, and it
   improves the audit trail generally — `create_uid` would name the real
   actor instead of `__system__` on every request filed through the
   homepage. Needs a test on the public path first, covering whatever reads
   `env.user` inside `request.request.create`.
2. **Leave it, and accept that homepage-filed requests are unlabelled.**
   Defensible: the record genuinely was created by the system user. The cost
   is that the ONE public write path is the one whose output cannot be
   identified, and report 24 measured the public dropdown as 84% fixtures.
3. **Fold it into the pre-envelope-routes refactor** (§9.1), which is already
   going to touch how these routes establish identity.

**This is a pre-existing audit-trail defect that handoff 26 exposed rather
than introduced** — the actor was being discarded long before there was a
label to lose.

---

## 12 · Three things the verification pass found that were left as they are

Each is a real behaviour change or a latent divergence that handoff 26
introduced or exposed and chose not to chase. None is urgent; all three are
here so nobody rediscovers them from a symptom.

### 12.1 · `bootstrap.py`'s archived-client refusal stops the whole bootstrap — `[open]`

`_find_api_client` now raises when it finds an archived client with the
`client_id` it was about to create, instead of silently creating a duplicate
row and printing a success line. That is the right refusal.

**What its docstring does not say is the blast radius.** It raises from
`ensure_test_client` / `_ensure_scoped_client`, inside `main()`'s outer `try`,
which **re-raises** — so re-bootstrapping a tenant whose credential somebody
deliberately revoked by archiving now also skips the mail-server step, the
seeds and the credential capture. It used to finish, wrongly. It now finishes
nothing, loudly.

Probably the right trade — a revoked credential is a decision a deploy script
must not paper over — but it is a behavioural change on the production path
that nothing records. **If it bites, the remedy already exists:**
`CADRA_REACTIVATE_ARCHIVED_CLIENT=<client_id>` names the specific credential
to revive.

### 12.2 · The brand seeds' new `RuntimeError` aborts the whole seed file — `[open]`

`fix_asset_codes_and_tags(env)` is the **first** module-level call in each of
`gtb_data_seed.py` / `jaiz_data_seed.py` / `lasg_data_seed.py`;
`seed_employees`, `wire_assets` and `wire_fleet` follow it. A missing
`nrs.asset` sequence used to fall through silently and let branches,
employees and fleet seed anyway. It now raises, and **none of them run**.

Contained: `run_seeds` catches it (`bootstrap.py`), so it degrades to one
`✗ <tenant> Demo Data failed` line and provisioning continues to the next
seed. Loud beats silent — but "one step failed" became "no step ran", and
that scope change is recorded nowhere else.

### 12.3 · The two fixture scripts still diverge in two ways the parity guard does not cover — `[open]`

`tests/test_fixture_patterns_agree.py` compares the NAME PATTERNS and the
anchoring. Two behavioural disagreements sit outside it:

1. **`active_test`.** `mark_test_fixtures.py` searches locations with
   `with_context(active_test=False)`; `remove_test_residue.py` uses a plain
   `search()`. So the marking script marks archived fixture locations the
   removal script never even considers.
2. **`_asset_stays` does not know about the database's own refusals.**
   `remove_test_residue.py` builds `removable_asset_ids` from assets that
   passed the rules **and survived a trial `unlink`** — report 25 measured 96
   locations failing on a foreign key no reading of the model files predicted.
   `mark_test_fixtures.py`'s `_asset_stays` knows only the three declared
   rules. An asset that passes all three and is then refused by the DATABASE
   stays in the register, and the location holding it would go unmarked.

**On `jaizbankplc` today the two agree exactly** — the marking script's
selection reproduces the removal script's 17 refused locations, verified in
SQL. The divergence is latent, and it is the kind that appears on a different
tenant rather than on this one.

**Why it was not fixed:** the honest fix is for the marking script to perform
the same trial-unlink measurement the removal script does, which means a
marking script that attempts deletions. That is a bigger change than §D asked
for, on a script the owner runs against a client's register.
