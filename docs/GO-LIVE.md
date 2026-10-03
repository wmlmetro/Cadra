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

**The close-out (2026-09-16) ruled on three of Part II's open items and
accepted several others as they stand.** §7, §11.1 and §8.3 now carry
`[ruled]` decisions rather than questions — **implement them, do not
re-decide them.**

**§10.2's eleven remaining silent-instrument sites and §12's three
judged-and-left findings stay tagged `[open]`, and that is correct: they are
genuinely not fixed.** What the close-out settled is the separate question of
whether to chase them — **it ruled not to, and they are not to be reopened as
decisions.** The two are different things: `[open]` describes the code, the
acceptance describes the argument. Anyone may still fix one; nobody needs to
re-litigate whether it should have been fixed in handoff 26.
`docs/DECISIONS.md` carries the reasoning under *2026-09-16 — close-out*.

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
- **`[ruled]`** — added by the close-out, 2026-09-16. The Architect has
  DECIDED it; it is not yet built. **Implement it, do not re-decide it.** A
  `[ruled]` item is still outstanding work — the tag says the argument is
  over, not that the code exists. `docs/DECISIONS.md` carries the reasoning.

**An item is not ticked because it sounds right.** Everything here carries
either a measurement or the report it came from.

**There are no questions in this register, only decisions to make.** Where
handoff 26 would have asked the Architect something, the options are written
out instead, so whoever picks this up reads a choice rather than a cliffhanger.
**Three of those choices were then made** — §7, §11.1 and §8.3 — and carry
`[ruled]` rather than options. The options they were chosen from are kept
beside each ruling, because a decision whose alternatives are not written
down gets re-argued.

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

## 7 · The three unclassified tenants — `[ruled]` 2026-09-16: mark all three

`cadra19`, `nrs19` and `gtb19` carried no `cadra.database_class`. **Nothing
was unsafe** — absent refuses, so both test suites and both scripts already
declined to touch them. What was missing was a decision, and *unknown* is a
state somebody eventually resolves by guessing.

**The rule when it is genuinely ambiguous is `client`.** A test database
wrongly marked `client` costs somebody an afternoon. A client database
wrongly marked `test` costs a register.

**Ruled by the Architect in the close-out, 2026-09-16 — `nrs19` →
`client`, `cadra19` → `client`, `gtb19` → `test`. Mark all three, including
the safe one.** Unmarked refuses, so nothing is unsafe either way, but **a
database whose class is recorded only in a report is the shape of thing this
programme has spent three handoffs fixing.** The parameter is where the
decision lives; this section is only where it is explained.

#### NEEDS THE OWNER — the three marks are not applied

**The close-out asked the Builder to set these. The permission layer refused
the write**, as it has twice before, so the decision is recorded here and
**the parameter is still absent on all three.** Run these three commands, one
at a time — each loads a registry, and this host does not tolerate two at
once (`docs/ENVIRONMENT-FACTS.md`):

```
docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
  odoo shell -c /etc/odoo/odoo.conf -d nrs19 --no-http \
  --http-port=8099 --gevent-port=8098 <<< \
  "env['ir.config_parameter'].sudo().set_param('cadra.database_class','client'); env.cr.commit()"

docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
  odoo shell -c /etc/odoo/odoo.conf -d cadra19 --no-http \
  --http-port=8099 --gevent-port=8098 <<< \
  "env['ir.config_parameter'].sudo().set_param('cadra.database_class','client'); env.cr.commit()"

docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
  odoo shell -c /etc/odoo/odoo.conf -d gtb19 --no-http \
  --http-port=8099 --gevent-port=8098 <<< \
  "env['ir.config_parameter'].sudo().set_param('cadra.database_class','test'); env.cr.commit()"
```

**Verify with a read that does not go through `get_param`** — the ormcache is
what leaked in handoff 25, and `odoo shell` would read through the same cache
a worker does:

```
for db in cadra19 nrs19 gtb19 test19 nrs lasg gtb jaizbankplc; do
  printf '%-14s ' "$db"
  docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T db \
    psql -U odoo -d "$db" -tAc \
    "SELECT value FROM ir_config_parameter WHERE key='cadra.database_class'"
done
```

**Measured 2026-09-16, before the marks:** `test19` = `test`; `nrs`, `lasg`,
`gtb`, `jaizbankplc` = `client`; **`cadra19`, `nrs19`, `gtb19` = absent.**
That is the state these three commands change, and the five existing marks
confirm the register matches the databases.

#### All three marks weaken a guard. They do not weaken the same one.

**Correction, caught by the close-out's own verification pass.** A first
draft of this block said `gtb19` was the only one of the three that weakens
anything, on the reasoning that `client` and absent both refuse. **That is
true of the test suites and false of the two owner-run scripts**, and it is
wrong in the permissive direction — it tells you the two marks on
client-derived registers are consequence-free when they are the more
consequential two. What each mark actually changes:

| mark | test suites (§ handoff 25) | the two owner-run scripts (§5) |
|---|---|---|
| `gtb19` → `test` | **refuse → ACCEPT.** The suite may now write here. | refuse → accept |
| `nrs19` → `client` | refuse → refuse (no change) | **refuse → ACCEPT** |
| `cadra19` → `client` | refuse → refuse (no change) | **refuse → ACCEPT** |

Both scripts gate on `db_class not in (TEST, CLIENT)` —
`scripts/remove_test_residue.py:164` and `scripts/mark_test_fixtures.py:116`
— so **`client` is allowed on purpose**, because `jaizbankplc` is marked
`client` and is the register they were written for. The consequence nobody
should discover later: once `nrs19` is marked, `remove_test_residue.py` under
`CADRA_APPLY=1` will delete fixture-named rows from **the database holding a
real NRS staff extract and 11,942 assets** — and that script's own comment
(`remove_test_residue.py:155-159`) names `nrs19` as the reason the
absent-refusal exists at all. The ruling stands; marking is still right. **It
is the delete script, not the marks, that now needs the care.**

**`gtb19` was additionally re-verified against the database** on 2026-09-16
rather than taken from §7.3, because it is the mark that opens a database to
the test suite: 156 assets, 6 fixture-named, 61 employees, 149 locations and
company *Guaranty Trust Bank* all match, the sampled employees are the
synthetic alphabetical-by-surname set §7.3 names, and the sampled assets are
the seed script's generic bank equipment. **The live `gtb` is separately
marked `client`**, so the two are not confusable.

### 7.1 · `nrs19` → **`client`** — `[ruled]` 2026-09-16

**Agreed without reservation:** a real NRS staff extract naming serving
officials, and the register another organisation measures against. The
evidence the ruling rests on:

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

### 7.2 · `cadra19` → **`client`** — `[ruled]` 2026-09-16

**The second opinion was asked for and given, and provenance decides it.**
Assets derived from a named architect's drawings, a named consultancy's
completion schedule and a dated FIRS HQ furniture inventory, describing a
real 19-floor building, **are client-derived content whatever the tenant is
used for**. The argument that settles it is the closing one below: `test19`
already exists, is marked, and has a credential pair — **a second test tenant
is a thing to make, not a thing to reclassify.** The evidence:

Measured 2026-09-15: **1,335 assets, 754 locations, 80 requests, 2
employees** (one of them named `Py Test`), **50 fixture-named assets**, 0
custody rows. Company is *Nigeria Revenue Service*.

**The argument for `test`:** it has already been written to by the suite, it
carries a fixture employee, it has no custody chain, and nothing outside this
repository references it — a full-text search found it only in `CLAUDE.md`,
in four frontend comments quoting asset counts, and in one migration comment.

**The argument for `client`, which is why the ruling is `client`:** its
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

### 7.3 · `gtb19` → **`test`** — `[ruled]` 2026-09-16

**Agreed, and it is the only `test` ruling here.** This is the one place
*"when ambiguous, client"* is deliberately **not** applied, because it is not
ambiguous: every category of content is traced to a source and none of it is
client-supplied — synthetic employees, seed-script equipment, and locations
from a JSON file that marks every row as public OpenStreetMap data. **The
caution below about the two GitHub workflows is carried with the mark**, not
resolved by it. The evidence:

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

**One addition §7.3 did not carry, found on re-verification 2026-09-16:**
`gtb19` holds **152 `nrs.asset.custody` rows**, which this section did not
mention and which matter because custody is append-only and marking the
database `test` lets the suite write into it. They are **not a record of
anything real**: all 152 carry `source = 'tracking_backfill'` and all 152
were created on one day, 2026-09-09 — a backfill over the seeded assets, not
a chain of custody anybody handed over. The ruling is unaffected; the count
is recorded so the next reader does not rediscover it as a surprise.

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

**Carried by the Architect, 2026-09-16 (close-out §3).** The correction above
matters outside this repository and has been acted on: *"two unrotated
credentials in git history"* had been in the Architect's own status reporting
for weeks, and **it was wrong in the direction that lets something sit.**
Neither key is set on any tenant and both routes have refused since handoff
17, so there is no live compromised credential to chase — but **Redhubs'
asset-register export and SAP's inbound employee sync have been answering
`Unauthorized` since then, and two external parties are waiting on values
somebody has to generate and hand over.**

**It goes to NRS as a switched-off integration awaiting a credential, not as
a security item** — the two need different people, and filing it as the
second is how it stays unactioned. This section's phrasing stands as written.

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

### 11.1 · One route discards the actor before creating, so its records are never labelled — `[ruled]` 2026-09-16, not yet implemented

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

**The options handoff 26 weighed**, kept because the ruling below refers to
them and because a decision whose alternatives are not written down gets
re-argued:

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

**Ruled by the Architect in the close-out, 2026-09-16. This is a ruling, not
an open question — whoever picks it up implements it, and nobody needs to
re-decide it.**

**Split the two paths rather than choosing one behaviour for both.**

- **On the authenticated route** (`POST /api/v1/home/quick-submit`), **use
  `.sudo()`**. It elevates privileges *and keeps the actor* — that difference
  is the entire reason the actor is being lost here, and keeping it is what
  fixes the defect. `create_uid` then names the real actor instead of
  `__system__`, and `is_test_fixture` derives correctly because there is a
  credential in the environment to read.
- **On the public twin** (`/api/myservice/quick-submit`, `auth='public'`),
  **`with_user(SUPERUSER_ID)` stays exactly as it is.** There is no actor to
  keep, so there is nothing to gain — and **the public path does not change
  at all.**

The reasoning: of the three options above, none was taken whole — splitting
applies option 1 to the authenticated route and option 2 to the public one,
and it is **the only arrangement that fixes the defect without touching
unauthenticated behaviour.** The
objection that blocked the change in handoff 26 — that swapping in `.sudo()`
alters what `env.user` is during a create on a PUBLIC route, decided in a
handoff about test labelling with no test covering it — is answered by not
making that change on the public route at all, rather than by covering it
with a test.

Not folded into the §9.1 pre-envelope refactor: that refactor is a
prerequisite for nothing here, and this is a smaller change than waiting for
it.

**Handoff 26 was right not to change it** inside a handoff about labelling.
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

---

## 13 · The cycle reopened — handoff 27, 2026-09-20

**Part II's opening says there is no 27. There is one, and the sentence is
left as it was written because it was true when written.** Handoff 27 did not
reopen the quality work this register closes; it came out of a live
demonstration to NRS, who opened *Audit & Review* on an asset expecting its
history and found a screen that had never asked for one. What was built is in
`docs/STATUS.md`; what it FOUND is below, because a history endpoint is an
instrument for seeing which events have no record, and it found several.

### 13.1 · Client request: should a location move need an approver? — `[open]`, NRS's and the owner's decision

**Asked by NRS during the demonstration, recorded 2026-09-20.** Having
watched an asset moved between locations on one person's say-so, NRS asked
whether a move should require an approver. **This is a process question, not
a defect, and nothing was built or designed for it.** Whoever takes the
conversation up starts from these facts, each read from the code in handoff 27:

**Who can move an asset today.**

- **Over the API and in the Cadra app:** any credential or login holding
  `assets:write`. For a person, that scope is derived from one Odoo group —
  `group_asset_manager` (`myservice_api/controllers/utils.py`, the scope
  map). The app's **Move** button calls `POST /api/v1/assets/<id>/move`.
- **In Odoo:** `group_asset_manager` only. `group_asset_user` and plain
  employees hold read on `nrs.asset` and nothing else
  (`myservice_asset_register/security/ir.model.access.csv`).
- **There is no second person anywhere on the path.** `POST /move` creates
  its `nrs.asset.transfer` row directly at `state = done` and moves the asset
  in the same request; `approved_by` and `approved_date` stay empty — measured
  2026-09-20, no transfer on `test19` (0 of 18) or on `jaizbankplc` (0 of
  103) has an approver. The single transfer on `nrs19` does: it went through
  the Odoo flow described next. A `PATCH` of `location_id` moves the asset with no transfer row at all.

**What an approval flow would not have to invent.** `nrs.asset.transfer`
already has `draft → approved → done` (plus `rejected`), an **Approve** button
restricted to `group_asset_manager` that stamps `approved_by` and
`approved_date` from the acting user, and a **Complete** step that performs
the move. It is reachable only from the Odoo interface and nothing in the API
or the app uses it. Note that requester and approver would today be drawn
from the SAME group, so "needs an approver" as NRS means it also needs an
answer to *who may not approve their own request* — that is the business
decision, and it is not engineering's.

**What is recorded when an asset is moved today** — see §13.2, which is the
more uncomfortable half of the answer.

### 13.2 · A location move has no durable record — `[landed, keep it that way]` handoff 28; what follows is how it stood

**CLOSED GOING FORWARD by handoff 28.** Every change of `location_id` is now
appended to `nrs.asset.movement` — by `nrs.asset.write`/`create`, underneath
every writer, append-only on the model, `ondelete='restrict'` on the asset.
**It is here, tagged *keep it that way*, because of how easy it is to undo
without noticing:** a new writer that goes round the ORM (raw SQL, `_write`);
an ACL line granting write on the model (the model refuses anyway — that is
why the guard is on the model); a view that shows `location_id` readonly
without `force_save`, which is how the Odoo form came to display a location
it never stored; a foreign key that changes the column by itself, which is
how deleting a location emptied every asset in it with no record at all.
`myservice_asset_register/tests/test_movement_record.py` holds the last
three; `tests/test_recorder_bypass_guard.py` holds the first, by scanning
first-party code for raw SQL against `nrs_asset` that sets a recorded field
and for `_write()`. **Neither can see a writer outside this repository** — a
DBA's query, a restore, another system with database access. The guarantee
is Python, and says so wherever it is published.
**Every move made BEFORE handoff 28 is still exactly as described below.**
Nothing was backfilled — see §13.4 for why that is a decision and not an
omission. **And §13.1's prerequisite is now met:** an approval can be
recorded against something nobody can delete.

**As it stood, in plain words: NRS watched an asset being moved, and nothing
the system wrote down about that move was protected from being edited or
deleted.**

- `POST /move` and a completed transfer write an `nrs.asset.transfer` row.
  `group_asset_manager` holds write AND unlink on it, no record rule narrows
  that, nothing records an edit, and `asset_id` is `ondelete='cascade'` — so
  deleting the asset deletes its moves. It holds `transfer_date` as a DATE;
  the instant survives only as the row's `create_date`.
- Every other writer of `location_id` — `PATCH /assets/<id>`, the Odoo form
  and its building/floor/room onchanges, `asset_import.py` — leaves a
  `mail.message` tracking row and nothing else. Anyone with write on the
  asset can delete that message, which is the same group that can move it.
- **Measured:** `nrs19` holds **1,146** tracked location changes and **1**
  transfer row. `jaizbankplc`: 103 and 103, because there the moves were made
  through `/move`. **Read §13.4 before quoting the first figure: 1,145 of
  those 1,146 are one six-second script on the day the register was loaded,
  not moves.**

Compare custody, which NRS also watched: `nrs.asset.custody` refuses `write`
and `unlink` to everyone including sudo, and refuses deletion of the asset
beneath it. **The fix has the same shape** — record in `nrs.asset.write`,
where every writer of `location_id` passes, append-only — and it is a stored
model and therefore a fan-out across every tenant. It was NOT built in
handoff 27, whose instruction was *"an ordering and a merge, not a new
record"*. The history endpoint grades a move `editable_record` or `chatter`
and never more, so the gap is visible on the screen rather than papered over.
If §13.1 is answered *yes*, this comes first: an approval recorded on a row
an asset manager can delete is not an approval record.

### 13.3 · What else the measurement found — `[open]`

One line each; the evidence is handoff 27's report §A, and INT-10 §2.4 and
§3.2 already carry the field lists.

1. **Verification records a date and, from the app, nobody.** The app's
   **Verify** button is `PATCH {last_verified_date: today}`. `action_verify`
   is the only writer of `last_verified_by` and the app never calls it; the
   field is untracked, and a second verification overwrites the first. The
   history shows each change to the date, graded `chatter`, naming whoever
   saved it. No record anywhere says a physical check was made.
2. **A changed cost, SAP field or GRN/PO/vendor reference leaves nothing.**
   Already in INT-10 §2.4. New here: the comment at `v1_assets.py` beside the
   provenance block of `_WRITABLE_FIELDS` says a later change *"is tracked on
   the asset's mail.thread"*. **It is not** — none of the six carries
   `tracking=True`. The comment is wrong, not the model; it was left for the
   Architect to rule on rather than edited in passing.
3. **`include=transfers` is capped at the last 20 and carries no actor.**
   Handoff 27 described it as *built, tested and correct*. It is built and
   tested. `/history` is uncapped and reads the transfer rows directly, so
   nothing depends on the embed; whether the embed's cap should be said in
   the response, as every other cap now is, is open.
4. **The custody chain's append-only guarantee is Python.** No trigger, no
   constraint. `scripts/nrs_hq_seed.py` deletes from the table by raw SQL
   under `CADRA_SEED_DESTROY_CUSTODY=1`, and says so. The history's
   `append_only` grade states this rather than implying a database guarantee.
5. **6,643 assets on `nrs19` are held by somebody and no link says how** —
   every one assigned at creation on 2026-08-06, before the recorder
   (2026-09-09). Not a defect in the chain; it does not reach back. The
   history says so per asset (`custodian_held_before_first_link`).
6. **`action_mark_retrieved` declares no custody source**, so an employee
   exit clearing a custodian reads `direct`, the same as an Odoo form save.
7. **The "guarded" stamps are guarded by a context key the caller
   supplies** — `cadra_tag_capture` (the label's print and affix stamps),
   `cadra_event_dispatch` (the outbox's event fields), `cadra_sap_int07`
   (`sap_code_source`, `sap_synced_at`). Over XML-RPC a user with write on
   the model can set it. This is why `tag_printed`, `tag_affixed` and outbox
   events grade `guarded_record` and not `append_only`. **The disposal
   approval is not guarded at all:** `disposal_approved_by` and
   `disposal_approved_date` have no `write` guard and are inputs on the Odoo
   form; only the API refuses them. The history grades the approval
   `editable_record` and lists any rewrite of the approver.
8. **The `Legacy Data` tab says *"Migrated from FIRS legacy system · March
   2024"* on every asset**, hardcoded in `AssetDetail.tsx`, including the 63
   `nrs19` assets registered from Vendra this month. Same class of defect as
   the blank tab, one tab along; not touched by handoff 27.
9. **`RequestDetail.tsx` prints `"System"` for a message with no author**
   (`m.author?.name ?? "System"`) — an invented actor on a client-facing
   screen. The asset history prints *No person recorded* instead and
   deliberately did not copy the idiom; the request screen still has it.
10. **The app calls six API routes before anyone has logged in** and collects
    six 401s on every cold load (`/locations`, `/identity/employees`,
    `/assets` twice, `/dashboard/map`, `/dashboard/kpis`). Harmless, noisy,
    and it makes a real 401 harder to spot in the console.
11. **`e2e/tests/06-asset-actions.spec.ts` opens by describing Move and
    Transfer custody as broken in the UI.** `moveAsset` and `transferCustody`
    were since fixed to read `res.data.asset`; the header was not.
12. *Moved to §14 — it is an architectural fact, not a to-do.*

### 13.4 · What handoff 28 found — `[open]`, measured 2026-09-20

0. **A caller can label their own custody link.** `nrs.asset.custody.
   _resolve_source` reads the source from the context, and a context is
   something an RPC caller supplies — so anybody able to change a custodian
   can file the link under `test`, or `tracking_backfill`, and have a real
   change of custodian read as an artefact. The custody docstring says the
   label is *"decided from the acting user and never from anything the
   caller sends"*; the credential-derived `test` is, the context-declared
   rest is not. **Closed for `nrs.asset.movement`** in handoff 28 (only
   `api_move`, `api_write`, `transfer` and `direct` may be claimed, and
   `transfer` only with a transfer of the asset's own). **Left open on
   custody**, which handoff 28 did not touch; the same four lines close it.
   Likewise both models' `create` guard is a context flag: what stops a
   hand-written row is that flag AND an ACL granting `create` to nobody.

1. **The 1,146 is a seed, not a scale.** Report 27 measured *1,146 tracked
   location changes against 1 transfer row* on `nrs19` and offered it as the
   size of the problem. It is a true count of rows. **1,145 of them were
   written by Administrator within six seconds** (2026-08-06
   15:34:24–15:34:30), sixteen minutes after the register was loaded, one per
   asset: `FCT → North Central / FCT`, `Lagos → South West / Lagos`. A script
   re-mapping locations onto a hierarchy. The one remaining row is OdooBot's,
   on 2026-09-06. **The structural finding is untouched** — it is proven by
   test that a PATCH left no durable record — but nobody should quote 1,146
   as moves NRS made that went unrecorded. Report 27's author did not look
   inside the number; report 28 did.
2. **A location backfill from chatter — NOT done, by ruling, and the
   measurement argues against it.** It would recover the instant, the
   author, and both locations BY NAME AS THEY READ THEN, for every tracked
   change whose message survives. It would NOT recover: a first placement
   (Odoo writes no tracking row on `create` — 10,439 of `nrs19`'s 11,585
   located assets have no location tracking row of any kind); a reason;
   whether the author was the mover or a script; or anything whose message
   was deleted. **On `nrs19` it would mint 1,145 PERMANENT movement records
   of assets that never moved.** On `jaizbankplc` all 103 rows are matched by
   a transfer row and 45 were written by the test client. Custody's backfill
   was worth it because a custodian change is a person's act; here the
   chatter is mostly data loading, and an append-only table is the wrong
   place to find that out afterwards.
3. **`PATCH {"building_id": …}` moves nothing and says nothing.**
   `building_id`, `floor_id` and `room_id` are in `_WRITABLE_FIELDS`;
   `location_id` is derived from them ONLY by a form onchange, which never
   runs for the API, `load()` or a script. So an integration that sets a
   building leaves `location_id` pointing at the old place, and the movement
   record correctly reports no move. Latent today: three of four measured
   tenants never use those fields, and on `nrs` all 1,272 agree. Either the
   derivation belongs in `write`, or the three fields should not be writable.
4. **Odoo's *Duplicate* fails on every asset.** `asset_tag` is copied and
   then collides with `_check_unique_active`. Pre-existing; found when a test
   tried it. `copy=False` on `asset_tag` would fix it.
5. **Every fixture asset created from now on is permanent.** An asset created
   at a location carries a movement from birth, and the record restricts the
   delete — by design, as custody does. `remove_test_residue.py` and
   `mark_test_fixtures.py` now refuse on it BY NAME; `nrs_hq_seed.py` refuses
   the wipe and offers `CADRA_SEED_DESTROY_MOVEMENTS=1`, deliberately NOT the
   custody flag. The 3,779 removable fixtures report 25 measured on
   `jaizbankplc` predate the recorder and are unaffected.
6. **The e2e suite is outside the database-class guard and defaults to
   `jaizbankplc`.** `pytest` and the in-registry suites refuse a database not
   marked `test`; Playwright does not ask. `E2E_ORIGIN` must be set by hand.
7. **More screens that say what the record does not** — found by the
   front-end pass, NOT fixed (handoff 28 §C named three; these are beside
   them): the top bar prints *"Admin User / Administrator"* for every
   session, so the screen names somebody other than the verifier it now
   records · an untagged asset shows its asset CODE under *"Asset Tag"* ·
   every category is folded into one of three, so a generator reads
   *Furniture & Fittings* · the *Approval Status* pill and the *Cleared → In
   Review → Disposed* stepper are derived from `state` and `is_verified`;
   there is no approval record · the employee screen prints *Permanent*,
   *Male*, *Not Enrolled* and NIN *Verified/Pending* for fields the API never
   sends · *Custodian Match Score* exists only in mock data · *Mark missing*
   promises it is reversible and nothing shown reverses it.

### 13.5 · What handoff 29 found on the asset page and one screen out — `[open]`, acted 2026-09-21

Handoff 29 fixed the status pill, the two browser dialogs, the counts and a
dozen small things (`docs/STATUS.md`). **These it found and LEFT**, each
because it is a decision or a back-end change rather than a repair. Every one
was seen by acting on `test19` and reading the row, not by reading the code.

1. **Mark missing takes no reason, and cannot.** The button sends
   `PATCH {"state": "missing"}`. The model has no field FOR *why*. It has
   three free-text fields — `notes`, `verification_notes`, `disposal_reason` —
   and each means something else; a reason written into one would overwrite
   what it holds and mislabel what was put there. *"Why is this missing"* is the first thing an auditor asks, and
   it needs a field — and, if it is to be evidence, more than a field: a
   `state` change is a chatter line and nothing else. NOT added on the
   front end, because there is nowhere true to put it.
2. **A disposal made from the app is dated by the browser.** `condemnAsset`
   sent `disposal_date` from `new Date().toISOString()` — the UTC date, which
   is YESTERDAY for the first hour of a Lagos day, with a perfectly correct
   clock. Handoff 29 changed it to the browser's LOCAL calendar date, which
   removes that hour for a user in Lagos; it is still the browser's clock and
   not the server's. It cannot simply be dropped: acted, a PATCH of `state: disposed` with no date leaves
   `disposal_date` NULL (the server stamps it only inside `action_condemn`,
   which the API never calls), and the disposals report then raises
   `no_disposal_date` on it. The cure is `POST /assets/<id>/condemn` calling
   `action_condemn`, as `/verify` calls `action_verify`.
3. **A disposal made from the app never has an approver.** The app never
   calls `POST /assets/<id>/approve-disposal`, and no screen offers the step.
   Every condemned asset is a `no_approver` finding. The Condemn dialog now
   SAYS so; nothing yet does anything about it.
4. **On a DISPOSED asset the page still offers Mark verified, Move, Transfer
   and Mark missing** — and *Mark missing* on a disposed asset would overwrite
   `disposed` with `missing`, un-disposing it in the register. Handoff 29
   disabled only the two no-ops (Mark missing on a missing asset, Condemn on a
   disposed one). What a disposed asset may still have done to it is a rule,
   and belongs in the model, not in which buttons are grey.
5. **Every "total" counts missing and disposed assets**, because the back end
   counts `Asset.search_count([])` and `nrs.asset` has no `active` field:
   *Total Assets* on the home dashboard, *Total IT*, the inventory report, the
   barcode station, and the per-category bars on three screens. Handoff 29
   relabelled the asset dashboard's to *On register* and added a *Missing*
   tile so the strip adds up; the others still read as stock.
6. **`_warnings.rejected_fields` is read by nothing.** The API reports every
   field it dropped; the app ignores it. `asset_tag` was the visible case —
   typed, saved, 200, unchanged, silent — and is now read-only. Any other
   field outside the allow-list still fails exactly that way.
7. **Assets with no custodian are shown as held by *"Pool"*.** The register
   list prints `Pool — {department}` for a null custodian. Nothing called
   "Pool" exists in the data.
8. **The register's Status and Category filters work only on rows already
   loaded**, while the count beside them is register-wide. Filter to
   *Cleared* on a 12,000-asset register and you see the Cleared rows among
   the first 200, under a total of 12,000.
9. **The home dashboard prints fixed text as though it were live:** *"All
   systems operational"*, *"7 zones · 38 states · 857 offices"*, and mock
   figures (13,150 assets) while the API loads or if it fails. The asset
   dashboard prints *"NRS Facilities Management · staging.app.cadra.ng"* on
   every tenant, and a *PM Due* card that asserts *"No upcoming PM schedules"*
   for data that has no endpoint.
10. **`is_verified` decays with no write.** It is a stored compute over
    `last_verified_date` and the category's verification window, refreshed by
    cron — so an asset goes from *Cleared* to *Review* without anybody
    touching it. True, and worth knowing before anyone reads *Cleared* as a
    thing somebody did.
11. **The home dashboard's *Review Queue* card promises more than it
    delivers.** Labelled *Active assets not yet verified*, it opens the
    register list UNFILTERED — the list has no server-side filter for it
    (see 8). The count is right; the destination is not the thing counted.
12. **The IT dashboard's condition tiles count across every state.** *Needs
    service* includes missing and disposed assets in poor condition, and that
    page has no *Missing* tile. Its *Verified*/*Unverified* were fixed.
13. **Two depreciation e2e specs fail on `test19`, on `dev` as well as on
    handoff 29's branch** — *"a computed asset charts its value over time"*
    and *"the straight-line switch persists across a reload"*. Established by
    building `dev`'s front end and running them against it; NOT investigated.
14. **On a tenant with `transferred` assets the KPI strip will not add up.**
    Its tiles are Active, Under Repair, Missing and Condemned; the enum has a
    fifth state. None of the eight local tenants holds one. Measured, not
    assumed — and it is a number that will move.

---

## 14 · Architectural facts — not to-dos

Things true of this system's shape that a future change must know about.
They are not defects to be scheduled; they are constraints to design within.

### 14.1 · ~~A route cannot see what its caller is allowed to do~~ — **RETRACTED 2026-09-21. It was false.**

**This section said `require_jwt` checks a token's scopes and *discards them*,
so that no route can see what its caller holds, and that this *"forecloses
per-scope shaping anywhere in this API"*. None of that is true, and it was
registered here as an architectural FACT.**

`myservice_api/controllers/utils.py`, at the end of `require_jwt`:

```python
    _set_request_user(int(uid))
    request.jwt_claims = claims
```

The whole validated token — `scopes`, `uid`, `sub`, `aud`, the limit claims —
is on the request for every handler behind `require_jwt`, on its one success
path, wildcard and `scopes=[]` routes included. Three places already read it: `_limit_claim`
and the frontend-audience check beside it (`utils.py`), `GET /meta/database`
(`v1_meta.py`), and `GET /auth/whoami` (`v1.py`). **A route can shape its
response by scope today, with no change to the authentication path.**

**How a false statement became a registered fact.** Handoff 27's verification
reviewer wrote it in a summary. The Builder searched the code for three
attribute names — `cadra_scopes`, `cadra_claims`, `cadra_token` — found none,
and never opened the function. Report 27 repeated it; the Architect accepted
it and built a ruling on it (handoff 28 §D: *"it belongs in the register as an
architectural fact"*); the Builder registered it. It was found in handoff 29
by reading `whoami` for an unrelated reason. Five handoffs running, the
defect is the same — a claim nobody checked against the file — and this is
its fifth instance, this time about our own code, promoted to a constraint on
future design.

**What it changes.** `GET /assets/<id>/history` withholds a maintenance
request's reference from everybody because it *"could not"* be shown only to
holders of `requests:read`. It can. Withholding it is still SAFE — it
under-publishes — so nothing was exposed; but the stated reason was wrong,
and anything designed around "per-scope shaping is impossible here" should be
re-read. ~~Whether to publish the reference to `requests:read` holders is a
ruling, not a repair: `[open]`.~~ **`[landed]` handoff 30:** ruled, and published
— `detail.reference`, with `detail.reference_withheld` saying when it was not.

## 15 · Handoff 30 — before the fourth twin, 2026-09-21

### 15.1 · What it closed — `[landed, keep it that way]`

Each of these was an `[open]` entry above; the entry is left as it was
written, because how a thing stood is part of the record.

| Entry | Was | Now |
|---|---|---|
| §13.4 item 0 | a caller could file a real change of custody under `test` | custody honours only `api_transfer`, `api_write`, `transfer`, `direct` from the context, as movement does |
| §13.4 item 2 | location backfill, unruled | **ruled: no.** |
| §13.4 item 3 | `PATCH {"building_id": …}` moved nothing and said nothing | the three fields are not writable; sending one is reported |
| §13.5 item 1 | *Mark missing* took no reason, and could not | `POST /assets/<id>/mark-missing`, reason required, kept where nobody can edit it |
| §13.5 item 2 | a disposal made from the app was dated by the browser | `POST /assets/<id>/condemn` — dated by the server, as a Lagos day |
| §13.5 item 4 | a disposed asset could be marked missing, moved, handed over | refused in the model, for every writer; the app does not offer them |
| §13.5 item 6 | `_warnings.rejected_fields` was read by nothing | the app shows it, for every mutation |
| §13.3 *disposal executor* | who carried out a disposal was recorded nowhere | the actor of the `status_changed` event into `disposed` — **from 2026-09-21, not before** |
| §14.1 | a request's reference withheld from everybody | published to a holder of `requests:read` |

### 15.2 · Asked of the Architect — `[open]`

1. **Should custody and movement adopt `nrs.asset.append.only.mixin`?** No
   fields, so no migration, no id changes, no published name changes. It
   would have made §13.4 item 0 impossible. Recommended; not done, because
   it changes two live audit models nobody has ruled on. Report 30 §1.
2. **400, or 200 with a warning, for a field the API does not accept?**
   Recommended: 400 — Vendra's own client already raises on it, *after*
   Cadra has created the asset, and says so. BREAKING; ten routes. Report
   30 §3.
3. **May a DISPOSED asset be verified?** Allowed today, deliberately: a
   disposed asset somebody finds on the premises is an audit finding, and
   refusing to record the sighting would hide it. One line either way.
4. **What a reversal of a disposal should be, if one is ever needed.** Not
   built. Measured need: none — the one asset that ever left `disposed` is
   handoff 29's probe. Report 30 §2 proposes the shape.

### 15.3 · Found, not touched — `[open]`

1. ~~**Deleting an employee silently un-assigns everything they held, and the
   chain of custody records nothing.**~~ **`[landed]` in this handoff**, after
   the verification pass connected it to the terminal rule. `nrs_asset.
   custodian_id` is `ON DELETE SET NULL` (read from `pg_constraint`), so the
   database made the change with no ORM write — the exact twin of the hole
   handoff 28 closed for location. `hr.employee.unlink` now appends the link
   first (`source: direct`, the reason says the employee was deleted) and
   **refuses outright if a disposed asset names the employee**;
   `generic.location.unlink` refuses likewise. Both offer archiving.
2. **`transferred` is a published status with no producer.** Nothing in the
   code writes it; no asset on any of the eight databases carries it — nor
   did any carry `in_repair` before handoff 30's own tests wrote two on
   `test19`. It is published, filterable and selectable in the app's edit
   form. It is report 29 §3's dead-status class; removing a published enum
   value is BREAKING, so it was measured and left.
3. **A disposed asset still assigned to a leaver is flagged for retrieval
   and can never be marked retrieved.** `action_mark_retrieved` clears the
   custodian, which the terminal rule refuses. One button, one asset, a plain
   sentence; nothing automated calls it. The fix belongs in
   `myservice_identity`'s exit flow, which should not flag disposed assets.
4. **Custody can still CLAIM `transfer` through the context without there
   being a transfer.** Movement downgrades that to `direct` unless a transfer
   of the asset's own backs it; custody has no transfer column to check
   against. A claim about process, not about whether the evidence is real —
   far less serious than `test` was — and named rather than left.
5. **The endpoint reference documents neither
   `POST /assets/<id>/approve-disposal` nor the `data.disposal` block.**
   Found by citing two section numbers from memory and then looking for
   them. The route is in the changelog and the OpenAPI document only.
6. **An asset REGISTERED as already disposed has no status event**, by
   design: an event is a change, and the registration is the record. So *who
   carried out the disposal* is unanswerable for such an asset, as it is for
   every disposal made before 2026-09-21.
7. **A verification is still dated by the UTC day, and that date is now
   frozen in an append-only row.** `action_verify` writes `date.today()` and
   the container is UTC, so a check made between 00:00 and 01:00 in Lagos is
   dated the day before — the bug `/condemn` was cured of in this handoff.
   Left, deliberately: `is_verified` is a stored compute whose cron and
   cutoff are UTC on purpose (its docstring says why), and the recorder's
   own "did the actor verify it TODAY" test reads the same clock. Moving one
   without the others files real verifications as `verification_date_set`
   for an hour a night. **The event's `occurred_at` is the exact instant**,
   so the audit question is answerable to the second; it is the asset's own
   date column that is a day out.
8. **The reason is an API and app feature. The Odoo form's *Mark Missing*
   and *Condemn / Dispose* buttons ask for none**, so a `status_changed`
   event made from Odoo carries no reason. It says who and when.
9. **`PATCH {"state": "disposed"}` still disposes, and stamps nothing** — no
   disposal date, no change of condition, no reason. `/condemn` is the door
   that does it properly; it did not close the other one. By precedent
   (PATCH stayed open for location in handoff 28), and the app no longer
   offers it on edit. Whether the MODEL should stamp the date for every
   writer is a ruling: the disposal report's `no_disposal_date` finding, and
   the tests that prove it, rest on the fact that today it does not.
10. **An approved transfer of an asset that is then condemned can never be
   completed** — `action_complete` raises, correctly. It can be rejected.

## 16 · Handoff 31 — one answer per rule, 2026-09-21

### 16.1 · What it closed — `[landed, keep it that way]`

| Entry | Was | Now |
|---|---|---|
| §15.2 item 1 | should custody and movement adopt the mixin? | **ruled yes, done.** One guard, one credential relabel, for all three records. Their ROWS stay where they are — ruled, not to be reopened |
| §15.2 item 2 | 400, or 200 with a warning? | **ruled 400, done**, eleven routes (report 30's ten, plus one that dropped fields without even reporting them), announced in the changelog, the endpoint reference and `INT-10` |
| §15.2 item 3 | may a disposed asset be verified? | **ruled allowed**; the Odoo form, which hid it, now agrees with the model, the API and the app |
| §15.3 item 3 | a leaver's disposed asset could never be retrieved | a disposed asset is not flagged, and does not hold a clearance open |
| §15.3 item 9 | `PATCH {"state": "disposed"}` stamped nothing | the MODEL stamps date and condition for every writer; both `action_condemn` overrides deleted |
| §13.5 item 6, §15.1 | rejected fields shown as a warning | refused; the app says which fields, in words, where it shows any error |
| *(new)* | a found asset recorded no reason | `POST /assets/<id>/mark-found`, reason required |
| *(new, found by the 400)* | **`POST`/`PATCH /requests` dropped a request's location for the life of the route**, `GET /requests` published `location: null` whatever the request held, and `?location_id=` filtered nothing | saved, published, filterable — §16.3 item 1 |

### 16.2 · Asked of NRS — `[open]`, theirs

1. **What does "Transferred" mean?** Published, filterable, selectable in the
   app, and nothing writes it. If an asset can leave NRS's books altogether
   it is a disposal-like act needing an approver and a posting to SAP; if it
   only ever moves between offices, the register already records that and
   the status means nothing. The question as put is report 31 §5. **If it
   means nothing it is removed under handoff 31's announcement.**

### 16.3 · Found — `[open]` unless it says otherwise

1. **`[landed]` — the request location.** The request model's field became
   `generic_location_id` in the move to Odoo 19 and `v1_requests` went on
   asking for `location_id`. **A request raised through the API before
   2026-09-21 has no location** (`jaizbankplc`: 0 of 460). The first
   reading — *the register cannot hold one* — was wrong, was acted on for
   two hours, and was caught by a comment in the front end. **The second
   reading over-corrected** — *never saved, by anyone, and unrecoverable* —
   and was caught by the verification pass running one SELECT: quick-submit,
   the PM scheduler, fleet maintenance and the Odoo form all knew the
   field's real name, and `cadra19`'s 80 requests all have a location,
   which the API read back as `null` until now. **Worth a sweep nobody has done:** every
   OTHER published key in every controller against the model field it
   claims to write, on 19. This one hid for the whole migration behind a
   201; the 400 will now surface the write side of any sibling, but a
   serializer that publishes `null` for a renamed field fails nothing.
   **And the disposal stamp keeps a STALE date:** `disposal_date` is
   writable on a live asset, so one PATCHed with last year's date and
   disposed today is dated last year — *a date the caller sent is respected*
   cannot tell a date sent with the disposal from one sent long before it.
2. **Vendra's own contract document is now wrong.**
   `vendra_network/docs/reference/cadra-api-contract.md` §*"Unknown fields
   are silently swallowed"* says a create with an unaccepted field returns
   201. Nothing of Vendra's breaks — its client turns our 400 into the same
   terminal failure, with a remedy text that is now CORRECT where the old
   one had to be special-cased — but the page misleads. Not our repository;
   a note to send.
3. **`disposal_date` is writable, so a `PATCH {"disposal_date": null}` on a
   disposed asset un-dates it** — the one remaining way to produce a
   `no_disposal_date` finding on a disposal made after 2026-09-21.
4. **The smoke test hardcodes location ids 1 and 2**, which do not exist on
   `test19`: four `404` lines on every run there, exit 0. The pytest suite
   had the same fault and fixed it in handoff 25 (`any_location`).
5. **A screen that PATCHes back the object it GET-ed fails the day the
   serializer gains a read-only key.** `building_id` happened that way in
   handoff 30; the Branding screen was safe only because two shapes happened
   to agree, and now sends an explicit pick. There is no guard against the
   next one.
6. **The Odoo form's Mark Missing, Mark Found and Condemn buttons ask for no
   reason** (§15.3 item 8 stands): the reason is an API and app feature.
7. **The request form's *Assignee* picker writes an EMPLOYEE's id into a
   USER field.** `RequestForm.tsx` searches `/identity/employees` and sends
   the chosen `hr.employee` id as `user_id`, which is `res.users`. The API
   accepts it — it is an integer on the allow-list — so this is a WRONG
   write and not a refused one: the request is assigned to whichever user
   happens to hold that number, or fails on the foreign key. The 400 cannot
   catch it; nothing can but a lookup of users. Found by the front-end pass
   reading the form, acting on nothing. Not touched.
8. **A full page reload inside a query's five-minute stale window restores
   the PERSISTED copy and does not refetch** — so a reload straight after a
   change can show the page as it was before. It made one new browser spec
   flaky and is the front-end author's suspected cause of the long-standing
   failure *"the straight-line switch persists across a reload"* (§13.5 item
   13). A hypothesis; not proven, not touched.
9. **`condition_at_disposal` in the `asset.disposed` event to SAP has never
   carried the condition at disposal.** Disposing sets `condition =
   decommissioned` in the same write the event is built from, so the key has
   read `decommissioned` for every disposal made with the button or
   `/condemn`, and since handoff 31 for a PATCH too. SAP's payload; raised,
   not changed.
10. **Two routes CREATE records from a body and ignore what they do not
   read — the twelfth door, of a different shape.** `POST
   /home/quick-submit` hands the body to a function that takes `**kwargs`:
   send it `request_text` (the sibling route's key) and it raises a request
   with no description, 201. It also swallows a non-integer `service_id` or
   `location_id` with a bare `except: pass` — a KNOWN key silently dropped,
   which is rule 3 verbatim. `POST /integrations/sap/employee-sync` is the
   same shape per employee. Neither filters against an allow-list, so the
   search that found the eleven could not see them — the reason the eleventh
   was missed, again. Not ruled; not touched.
11. **The ACTION routes ignore body keys they do not know** — `/move`,
   `/verify`, `/transfer-custody`, `/mark-missing`, `/mark-found`,
   `/condemn`, `/tag-affixed`, the three request actions. Handoff 31's ruling
   covered routes that take a body of FIELDS; whether these should refuse a
   stray key too is not ruled. `POST …/verify {"verified_by": 7}` answers 200
   and records the caller, which is right — and says nothing about the key.


## 17 · Handoff 32 — the name and the field, 2026-09-22

### 17.1 · What it closed — `[landed, keep it that way]`

| Entry | Was | Now |
|---|---|---|
| §16.3 item 1 | *"worth a sweep nobody has done"* — every published key against the field it claims to write | **done, and kept as a guard.** `myservice_api/tests/test_published_names_resolve.py`, 12 tests, driven by the routing attribute and a parse of every controller so a new route or a new defensive read FAILS rather than being skipped. One write-side mismatch, the known one; 22 read-side guards, all resolving |
| §16.3 item 10 | the twelfth door — two routes that create records from a body they do not filter | **both closed**, same 400 as the other eleven, before anything is written; the SAP feed refuses a whole batch rather than half-creating one |
| *(new, found by the sweep)* | the SAP feed's `status` — published by the schema, the endpoint reference, the demo card and our own test, and **never read by anything** | refused, and all four documents corrected to `employmentStatus` |
| *(new, found by the sweep)* | `POST /home/quick-submit`'s documented example sent four keys the route has never read | corrected; the suite's own test had been sending the same four since it was written |

### 17.2 · Found — `[open]` unless it says otherwise

1. **A key you can write and can never read back.** Four:
   `salvage_rate` (published only as the derived `salvage_value`),
   `verification_notes` (published only in the verify response),
   `mobile`→`mobile_phone` (published by nothing), and — the inverse, and
   the trap beside it — **six asset keys accepted under one name and
   published under another**: `depreciation_method` →
   `financial.depreciation.method`, `depreciation_start_date` →
   `…start_date`, `use_category_policy` → `…uses_category_policy`,
   `model_name` → `model`, `location_id` → `current_location`. A screen that
   GETs an asset, edits it and PATCHes the whole object back is refused on
   every one of those six, with a 400 since handoff 31. This is §16.3 item 5
   with names attached. Renaming a published key is breaking; nothing was
   renamed. **Needs a ruling: publish the missing four (additive, safe), or
   accept the read/write asymmetry and say so once.**
2. **The THIRTEENTH door, and it is unauthenticated.**
   `myservice_identity/controllers/sap_webhook.py` — `POST
   /api/sap/employee-sync`, `auth='none'` — hands the same unvalidated dict
   to `process_sap_payload`, as do `/api/sap/employee-sync/test`, the xlsx
   import job and the SAP import wizard. The accepted-key set now lives on
   the model, so each is a two-line change. **Measured before deciding**:
   `nrs.sap.sync.log.sync_type` records which door each sync came through,
   and across all eight local databases `webhook` is **0 rows**, on every
   one; `api` is 163, all of them on databases this repository's own suites
   write to. So nothing here is evidence of a real SAP feed either way. Left
   alone because it is an unauthenticated external surface and a refusal on
   the door a live upstream may be pointed at is a decision about an outage.
   **Needs a ruling before anything else goes near `myservice_identity`.**
3. **`POST /home/quick-submit` enforces neither of the two keys its schema
   declares required.** An empty body answers 201 and creates a request
   titled *"Quick facilities request"* against the first active type —
   measured, three ways. On the PUBLIC twin that is an unauthenticated way
   to create an empty request; the homepage form enforces both in
   JavaScript and nothing behind it does. Same genre as everything else
   here; belongs in the same ruling as §16.3 item 11.
4. **The guard that forbids field names in user-facing text reaches one
   file.** It is `myservice_api/tests/test_asset_history.py::
   test_the_statements_are_words_not_field_names`, over the asset-history
   statements only. Handoff 32's public-form sentences were held to the same
   rule and pinned by tests of their own, but nothing checks the rest of the
   codebase's user-facing strings. A §A-shaped job; not done.
5. **`tests/test_locations.py::test_list_filtered_by_q` asserted the wrong
   thing and passed for the life of the suite.** `?q=` searches four fields
   — name, description, zone code and the stored city — and the test asserted
   the match was always in the name. It passed because no location on the
   test tenant happened to be in a city called Lagos, until this handoff's
   probe created one. `[landed]` — corrected to assert what the route
   promises. **A test that only passes because of the data it happens to
   meet is a test of the tenant, not of the route**, and there is no guard
   against the next one.

## 18 · Handoff 41 — who has what, 2026-10-01

The first of three on people and access. It adds no way to change anything;
42 is granting and removing, 43 is creating and deactivating. What it found
is here; what it built is in `docs/STATUS.md`.

### 18.1 · What it closed — `[landed, keep it that way]`

- **The three register groups and the Auditor are on the user form**, under
  *NRS Asset Register*, as *Asset Register* (User / Manager), *Tag Issuing*
  and *Audit* — three `res.groups.privilege` records, because on Odoo 19 a
  group with no privilege is shown only under *Extra Rights* and only in
  developer mode. Screenshot: `docs/handoffs/41-evidence/01-user-form-after-privileges.png`.
- **The four `/barcode/*` reads run under sudo** like every other v1 route.
  Until now they read as the token's user, and a person holding Asset User +
  Tag-Issuing Unit got `403 … not allowed to access 'Location'` on *Recent
  tags* from a station every other control of which worked
  (`docs/handoffs/41-evidence/03-station-paired-before-sudo-fix.png`).
- **`GET /api/v1/users`, `/users/<id>`, `/roles`** — admin-scoped reads, and
  the *Users* and *Access changes* pages under a new *Administration* nav
  group, with no control that changes anything.

### 18.2 · Found — `[open]` unless it says otherwise

- **Seven first-party groups are still invisible on the user form** for the
  same reason the three were: `myservice_security.group_security_officer`,
  `group_security_manager`, `group_security_admin`,
  `myservice_staff_bus.group_bus_user`, `group_bus_manager`,
  `myservice_workflow.group_workflow_admin`,
  `myservice_identity.group_identity_manager` — 7 of the 11 first-party
  groups on `test19`, none with a `privilege_id`. Two of them
  (`identity_manager`, `security_officer`, plus `bus_user`) grant API scopes
  through `GROUP_SCOPES`. Each is one `res.groups.privilege` record in its
  own module; not done here because the handoff names three and the Auditor
  is the one widening already taken. `[open]`
- **Nothing in Cadra refuses a privilege escalation through the API.** Odoo
  core has exactly two guards on `group_ids`: the user-type groups are
  disjoint (`_check_disjoint_groups`) and there must remain at least one
  administrator (`_check_at_least_one_administrator`). Writing `group_ids`
  needs the *Access Rights* ACL (`base.group_erp_manager`) — and every v1
  route runs `sudo()`, which does not consult it. So a route that wrote
  `group_ids` tomorrow would let any `admin`-scoped caller grant
  `base.group_system` to anybody, including the credential's own user. For a
  PERSON the `admin` scope is minted only from `base.group_system`, so there
  is nothing left to escalate to; the exposure is an **API credential with
  the `admin` scope**. ~~whose user is deliberately NOT a system
  administrator (`SCOPE_GROUPS` maps `admin` to no group)~~ — **CORRECTED
  2026-10-02 by handoff 42:** `SCOPE_GROUPS` maps `admin` to no group, but
  `scripts/bootstrap.py:509` then grants `base.group_system` to the user of
  every credential holding `admin`, so on every bootstrapped tenant that
  user IS a system administrator (`test19`'s `cadra_client_test_client`
  held *Role / Administrator*). The access record would write the grant
  down and refuse nothing. **`[landed, keep it that way]` handoff 42** —
  the refusal is in the model under every writer (`access_guard.py`), no
  `base.*` group is grantable over the API, and the drive strips the
  credential's user of the group first so the exposure named here is the
  one refused (report 42 §D). Whether bootstrap should grant it at all is
  §19.2.
- **Mail is configured on no tenant.** 0 of 8 local databases have a row in
  `ir_mail_server` (`test19 nrs19 cadra19 gtb19 nrs lasg gtb jaizbankplc`,
  all `outgoing_servers=0`); `mail.catchall.domain` is unset on all 8. The
  staging deploy workflow wires `SMTP_HOST`/`SMTP_USER`/`SMTP_PASS` and a
  `CADRA_EMAIL_RELAY_URL` as optional variables (`.github/workflows/deploy-dev.yml`
  lines 26–29, 172–174) — whether the cluster has them set is the owner's
  to say. So handoff 43 cannot assume an invitation email will be delivered,
  and a design that sets a password has to find a way to hand it over that is
  not a document. `[open]`, decides 43's design.
- **The HTTPS mail relay was dead on Odoo 19 and is not any more — but it
  still has no secret.** `myservice_email_relay` overrode `ir.mail_server.
  connect()`, which 19 renamed `_connect__`; the port changed only the
  manifest version, so on every 19 tenant outbound mail died at *Unable to
  connect to SMTP Server* before the relay was consulted. Fixed 2026-10-02
  (`fix/the-mail-relay-on-19`): the override follows the 19 name, obeys
  `_disable_send()`, posts once per recipient, and its test pins the hook to
  what `mail.mail.send` calls. Proved from the running server on `test19`
  with a wrong secret: the row reads `Email relay returned HTTP 401 /
  Invalid or missing secret`. Installed on 1 of 8 local tenants (`test19`);
  relay parameters set on 0 of 8; the cluster gets both from
  `CADRA_EMAIL_RELAY_URL` / `_SECRET` via bootstrap. **The owner holds the
  secret.** `[open]`, owner — the one thing between 43's invitation email
  and a delivered one. **Found on the first invitation after the merge
  (2026-10-02):** the module was in `.env.example`'s bootstrap list and NOT
  in `k8s/dev/11-configmap-bootstrap-19.yaml`'s, so 0 staging tenants had
  it and the mail went over SMTP (`553 Sender is not allowed to relay
  emails`, Zoho refusing a From that is not the authenticated account).
  The list is fixed for future tenants; existing ones need `upgrade-19`
  with `install_modules=myservice_email_relay` (every tenant), then
  `set-email-relay.yml`, then a roll — the workflow prints the module state
  per tenant so the three steps cannot be done out of order unnoticed.
- **`auth_signup` is installed on all 8 tenants** (`ir_module_module.state =
  installed`), with `auth_signup.invitation_scope = b2c` and
  `auth_signup.reset_password = True` everywhere. Its
  `_create_user_from_template` is a `copy()` of ~~`base.default_user`~~ —
  **CORRECTED 2026-10-02 by handoff 43: on Odoo 19 it copies the PORTAL
  template, `base.template_portal_user_id` (login `portaltemplate`,
  `base.group_portal`); `base.default_user` does not exist on 19.** So 43
  did NOT create people through it — such an account would be a share user
  invisible to `/users`, and the guard refuses `base.group_portal` on an API
  create anyway. `POST /api/v1/users` is a plain `res.users.create` with
  `_default_groups()` ∪ the roles asked, which the recorder's `create` hook
  diffs correctly. `[verified]`, corrected
- **The access record's `group_name` snapshot changed shape on 2026-10-01.**
  `res.groups.full_name` prefixes the privilege, so rows written from now
  on read *Asset Register / Asset Manager* where earlier rows read *Asset
  Manager*. A reader grouping by that column across the boundary sees two
  labels for one group; `group_id` is unchanged. `[verified]`, not a defect.
- **The barcode wrapper fix touched `v1.py` while another agent owned its
  schema block.** Verified after the fact by diff rather than prevented by
  partition — the rule in `CLAUDE.md` was broken and the breach is recorded
  here so it is not repeated. `[verified]`

## 19 · Handoff 42 — the grant, and the refusal, 2026-10-02

### 19.1 · What it closed — `[landed, keep it that way]`

- **No `base.*` group is grantable over the API, and nobody adds a role to
  their own account** — `myservice_api/models/access_guard.py`, under every
  writer of membership, keyed on `request.jwt_claims` (what only our API
  sets). §18.2's escalation finding is closed by it: an `admin`-scoped
  credential asking for `base.group_system` on its own user is refused with
  the model's sentence, driven over HTTP in report 42.
- **`POST /api/v1/users/<id>/roles`** with a dry run that is a real write
  rolled back, and the *Change roles* section on the Users page; the access
  record's row names the person who clicked (actor read back in the spec).
- **11 of 11 first-party groups carry a privilege** on the user form (the
  seven from §18.2 done here).

### 19.2 · Found — `[open]` unless it says otherwise

- **The sign-up door on the cluster is shut, measured.** Anonymous
  `GET /web/signup` → 404 on all four hosts (`staging.app`, `jaizbankplc`,
  `lasg`, `gtb`); login and reset-password → 200. Handoff 43 §0 still owes
  WHY (the parameter's value on the cluster, and what shuts the route), and
  the ruling to set `b2b` deliberately stands. `[verified]`, cause open.
- **`ACCESS_CHANGE_SKIP_KEY` and `ACCESS_CHANGE_SOURCE_KEY` are read and set
  nowhere.** `access_change.py:123-126` says a setter exists "below"; it
  does not. Harmless today (absent means record, with source `direct`), but
  a comment that names a mechanism that does not exist is the kind this
  programme deletes. `[open]`, one-line fix.
- **`myservice_nrs_base/caller_ip.py:49` uses `getattr(request, …)` without
  testing `bool(request)` first.** Outside an HTTP request the proxy RAISES
  `RuntimeError: object is not bound` rather than returning the default, so
  that helper would raise from a cron or a shell. Not reached today.
  `[open]`.
- **`scripts/bootstrap.py:509` makes every admin-scoped credential's user a
  system administrator.** It is what lets such a credential call the
  handful of routes that still read as the user, and it is exactly the
  power ruling 1 says a credential must not reach by itself. The guard
  closes the API route to it; the shell still grants it. For the Architect:
  should bootstrap stop, and what breaks if it does. ~~`[open]`~~ —
  **`[landed]` handoff 44 (§21):** nothing breaks; bootstrap stopped, and
  the grants already made are the owner's to remove with
  `scripts/strip_credential_system_group.py`.
- **The recorder's group-side `write` hook does not watch `implied_by_ids`.**
  Core writes the same relation from the other side; a change through it
  would be an implication change the record misses. The guard refuses it
  over the API; the back office could still make one unrecorded. `[open]`,
  for the recorder.

## 20 · Handoff 43 — the person, and the door, 2026-10-02

The last of three on people. What it built is in `docs/STATUS.md`; what it
found is here.

### 20.1 · What it closed — `[landed, keep it that way]`

- **The front door is shut by code.** `res.users._get_signup_invitation_scope`
  returns `b2b` on every tenant; anonymous `/web/signup` is a 404 whatever
  any row says, and the migration set both rows the Settings screen reads to
  `b2b`. Why it was shut before: §19.2's question, answered — the `website`
  module's per-site field, `b2b` by default, overrides the parameter; the
  parameter's `b2c` (8 of 8 local tenants) had never been read.
- **A person is created, invited, re-invited, deactivated and reactivated
  over the API and from the Users page**, with the letter in the tenant's
  brand on the request's host, and every refusal in words. Proved end to
  end on `test19`: the letter received (Mailpit), the link redeemed, the
  password set, the API signed into with the roles given, the row reading
  `redeemed`.
- **A deactivated account's live token is refused now** (`require_jwt`),
  not at `exp`. Until this handoff a person deactivated at 09:00 kept the
  app until their access token ran out.
- **A deactivated nominee is refused on `/move`, `/transfer-custody` and tag
  replacement.** The picker hid archived users; the gate did not.
- **Odoo's *unregistered users* reminder cron is off** on 8 of 8 (and on a
  fresh install): the third Odoo-branded letter, found by the verification
  pass.
- **An anonymous reset cannot choose its link's host.** The first draft
  took the host from the request for every caller; under `proxy_mode` that
  is `X-Forwarded-Host`, client-supplied where a proxy does not overwrite
  it. Authenticated callers only; the dev proxy sets the header itself.

### 20.2 · Found — `[open]` unless it says otherwise

- **The page the letter leads to is still Odoo's.** `/web/signup?token=…`
  renders *"Sign up login | My Website"* in Odoo's own styling, and so does
  `/web/reset_password`. The LETTER is the organisation's; the first SCREEN
  the person sees is not. The sign-up form is core's QWeb (`auth_signup.signup`,
  `web.login_layout`); rebranding it is a view inheritance in a brand-aware
  module, not done here because the handoff names the email. `[open]`
- **The HTTPS relay discards the plain-text part.** `myservice_email_relay`
  posts `{to_email, to_name, subject, body}` with the first `text/html`
  part only (its manifest says so). The text alternative this handoff
  writes — the one a government mail client that strips HTML would show —
  never reaches a recipient on the cluster. The relay payload has no field
  for it. `[open]`, relay.
- **`web.base.url` lacked its port on 8 of 8 local tenants**
  (`http://<db>.localhost`), because `config/nginx.dev.conf` forwarded
  `Host $host`. Fixed to `$http_host`; the letters no longer read the
  parameter inside a request, but anything else that builds an absolute URL
  from it is wrong on a local tenant until an administrator signs in again.
  `[verified]`, proxy fixed.
- **A pending request whose approver is deactivated is stranded, silently.**
  Measured on `test19` (report 43 §2): request 1426 raised naming
  `h41_manager`, then `h41_manager` deactivated. The queue row publishes
  `approver: {id, name}` and nothing about `active`; `/approvals/approvers`
  no longer lists the person; the requester cannot decide it (self); the
  only way out is another eligible person deciding it (the `admin` person
  rejected it) — and the request cannot be re-nominated, because the model
  refuses every write but a transition. Proposed, for the Architect: publish
  `approver.active` on the queue row and say *"the approver cannot sign in"*
  on the screen; and either allow re-nomination of a PENDING request as a
  recorded act (who changed the nominee, when) or make deactivation refuse
  while the person is the nominee on anything pending (`nrs19`: 1 pending
  request; `test19`: 205 pending of 632). `[open]`, Architect.
- **Deactivating a custodian does nothing to custody, and nothing can see
  it.** Nothing first-party reacts to `res.users.active`; the *Identity
  (clearance)* screen is 20 hard-coded mock rows behind a `MockDataBanner`
  with no route behind it; the real departure routine is SAP-status-driven
  (`hr.employee.action_flag_retrieval` on `exited`, `nrs.asset.action_mark_retrieved`
  clearing `custodian_id` under `cadra_approval_exempt='clearance'`), both
  Odoo-form buttons with no API route. And on the real register custody is
  not tied to accounts at all: `nrs19` links 1 of 11,386 employees to a
  user, and 87 of its 6,646 custodied assets are held by one of its 207
  ARCHIVED employees, 0 of them flagged for retrieval and 0 employees
  `exited`. `test19`: 1 of 88 employees has a user, and 158 of 169
  custodied assets are theirs. NRS's own question (*"use whatever process
  you want to determine how those assets are retrieved"*) is therefore not
  about accounts; it is about the employee record, and the mechanism that
  exists for it is reachable only from the back office. `[open]`, NRS and
  the Architect.
- **§18.2's "`base.default_user`" was wrong on 19** — corrected in place
  above. `[verified]`
- **§19.2's "read and set nowhere" is half right.** `ACCESS_CHANGE_SKIP_KEY`
  IS read (`access_recorder.py:86, 160, 229`) and set nowhere;
  `ACCESS_CHANGE_SOURCE_KEY` is read only in `_record()`, which has no
  callers. Still one-line fixes, still not done here. `[open]`
- **On Odoo 19 `Savepoint.close()` rolls back by default**, so core's own
  `contextlib.closing(cr.savepoint())` around the send in
  `auth_signup._action_reset_password` discards the mail row after SMTP
  has taken the message. Harmless to core (the row is `auto_delete`), fatal
  to a test reading the letter back; `docs/ENVIRONMENT-FACTS.md`. Our
  override uses the context-manager form. `[verified]`
- **`e2e/fixtures/api.ts` declares `twoLocations()` twice** (TS2393 at
  lines 233 and 256). Pre-existing; the e2e tree has no `tsconfig`, so
  nothing checks it. `[open]`, one-line.
- **A re-sent invitation does not revoke the earlier link.** The token's
  payload (`partner id, user ids, login_date, signup_type`) is unchanged by
  a re-send, so both links work until their own expiry; a sign-in or a
  deactivation kills both. Said in §12.6 rather than fixed: revoking would
  need a nonce on the partner, a stored field. `[verified]`
- **The cluster's `nrs` database has never had `myservice_api`.** Read
  through `db-query` after the handoff 43 roll (2026-10-02): base
  19.0.1.3, `auth_signup` installed, `website` NOT installed, first-party
  modules installed = `myservice_email_relay` only, 1 active user, 0 share
  users; no ingress host serves it (`nrs.cadra.ng` does not resolve) and
  `X-Odoo-Database: nrs` on `staging.app.cadra.ng` answers 404 on
  `/web/signup`. So `upgrade-19`'s *"upgrade succeeded: nrs"* has been a
  no-op on every run, and that database's `auth_signup.invitation_scope`
  is still `b2c` with nothing — no website row, no Cadra constant — to
  override it, reachable by nobody today. The local `nrs` and `nrs19` are
  not this database. **`[ruled]` by the owner, 2026-10-02: a leftover.**
  Removed from `upgrade-19`'s default `target_dbs` (now
  `staging,gtb,jaizbankplc,lasg`); dropping the database itself is a
  separate `drop-db` act for the owner, confirm-gated, one database at a
  time.
- **An invitation sent by an integration names the credential as sender**
  (*"this one was sent by Smoke Test (API client)"*). Correct, and odd to
  read; a credential inviting people is not a path NRS will use. `[verified]`

## 21 · Handoff 44 — the credential that is already root, 2026-10-02

### 21.1 · What it closed — `[landed, keep it that way]`

- **An API credential is not a system administrator, and nothing needed it
  to be.** `base.group_system` stripped from `test19`'s `admin` credential
  (with the owner script below) and the credential driven: each of the 37
  calls `44-evidence/drive_credentials.py` makes as that credential answers
  the same status with and without the group (`test19` has no Vendra or
  Tag-Issuing Unit credential; those legs were driven on `boot44`), and the HTTP suite as the stripped credential is
  1,181 passed, 0 failed, 10 skipped of 1,191 — against 1,176 passed, 2
  failed, 12 skipped of 1,190 with it (the two failures were the suite
  outgrowing `test19`, fixed here, §21.2). The two skips that disappear are
  refusals that could not be proved while the credential was root, and
  now are. Neither `scripts/bootstrap.py` nor the `19.0.3.2.0` migration
  grants it any more (two sites, the second found by search, both under a
  source guard); a database
  bootstrapped from nothing (`boot44`) has 0 of 3 credentials holding it,
  and INT-03 (Vendra creates, replays exactly) and INT-05 (the Tag-Issuing
  Unit confirms the label) work end to end, the record naming each.
- **One name per role.** `models/role_names.py`; the guard's refusal, the
  access record, the roster, `/users`, `/roles` and the schema all say
  *System Administrator*.

### 21.2 · Found — `[open]` unless it says otherwise

- **The grants already made are still there.** Locally 3 of 12 API
  credentials hold `base.group_system`: `test_client` on `cadra19`,
  `nrs19` and `test19` — all three the `admin`-scoped smoke credential;
  `test19`'s is now removed. They are exactly the credentials that held
  `admin` when the `19.0.3.2.0` migration ran on 2026-09-07. Vendra's, the Tag-Issuing Unit's and the two
  approver credentials hold it on none. The cluster was NOT measured — the
  Builder's permission layer refuses reads of the cluster's databases. The
  procedure, per database, is `scripts/strip_credential_system_group.py`:
  dry run first (it performs every removal in a savepoint and rolls it
  back, so a refusal shows there and not in the apply), then
  `CADRA_APPLY=1`. Order: any test database, then a demo, then a client's.
  What an operator would see if it went wrong: a `403`/`400` naming an Odoo
  model or group on a call made with that credential — put the group back
  from *Settings › Users* (`cadra_client_<client_id>`) and report the
  route. Note that any future change to `ALL_SCOPES` re-syncs every client
  user's groups wholesale on the next bootstrap, which would remove the
  group silently; running the script first keeps the removal on the
  record with a log. `[open]`, owner.
- **`test19`'s smoke credential lacks `settings:read`/`settings:write`**,
  which a fresh bootstrap gives it (`boot44`). The scopes are re-synced
  only when bootstrap runs, and `test19` has not been re-bootstrapped since
  those scopes were added. Harmless for the suite today (it skips nothing
  for it); named because "the suite's credential holds every scope" is
  assumed in places. `[open]`
- **Two audit-report tests had outgrown `test19`.** The access-changes
  report pages accounts (50 by default) and `test19` holds 61; one test
  compared the whole period's count with one page (198 vs 170), the other
  gave the cursor walk a fixed 60-page budget. Both now walk the report.
  The report was right throughout. `[landed]`
- **The routes of handoffs 41, 42 and 43 are live on the cluster.** An
  unauthenticated `GET /api/v1/roles`, `GET /api/v1/users` and `POST
  /api/v1/users/1/{roles,invite,deactivate}` answer the JSON `401
  unauthorized` envelope on `staging.app.cadra.ng`, `jaizbankplc`, `lasg`
  and `gtb`, where a route that does not exist answers Odoo's HTML 404 on
  the same hosts. So report 42's worry about a cached image does not
  describe today: whatever ran `upgrade-19` last (five successful runs on
  2026-10-02) put the code there. `[verified]`


## 22 · Handoff 45 — the first five minutes, 2026-10-02

### 22.1 · What it closed — `[landed, keep it that way]`

- **The letter's link opens the app**, not Odoo: `/app/accept-invite?token=…`
  and `/app/reset-password?token=…`, the same core token. A letter sent
  before this change (`/web/signup?…token=…`) is redirected to the same page
  with the same token — nobody invited yesterday is stranded.
- **Every state a link can be in is said in words** — outstanding, expired,
  used, cancelled, never valid — with a way forward; `password_rules`
  published and enforced by the server, the refusal shown verbatim.
- ***Forgot password?*** on the sign-in page, answering the same sentence
  whether or not an account matched.
- **The back office is for system administrators.** The interface
  redirects everybody else to the app; no non-administrator's Odoo session
  is served on any `auth='user'` route (`models/backoffice_session.py`); the
  app's own plumbing (`/api/v1`, `/report/barcode`, assets) is untouched.
  The back-office barcode station is therefore an administrator's tool.
- **Odoo's "Security Update: Password Changed" mail** no longer follows the
  password a letter asked for (it did — an Odoo letter with an Odoo link,
  in the middle of the journey).
- **A stranded approval is fixed forward**: `approver.active` on the queue,
  *"— X cannot sign in"* on the screen, and a recorded re-nomination.
- **A deactivation and a reactivation are on the access record and in the
  report**, under every writer of `active`.

### 22.2 · Found — `[open]` unless it says otherwise

- **No password minimum is enforced anywhere.** Odoo 19's `signup()` hashes
  whatever it is given (the empty string included — the app's route refuses
  that one); `auth_password_policy` is installed on 0 of 9 local databases.
  The routes enforce what Odoo would if the module were installed, and
  publish it. Whether Cadra should impose a minimum is a decision.
  `[open]`, Architect.
- **An anonymous reset link is only as right as `web.base.url`.** *Forgot
  password?* is anonymous, and by handoff 43's rule an anonymous request does
  not choose the host a victim's link points at — so the link is built on
  `web.base.url`, which core rewrites when a system administrator signs in on
  the back office. On a database no administrator has signed into it is the
  install default: `boot44`'s first reset letter pointed at
  `http://localhost:8069/app/reset-password?…` (measured, report 45 §B).
  Locally 8 of 8 tenants read `http://<db>.localhost` without the port
  (handoff 43's finding). **On each cluster tenant, read `web.base.url`
  before telling anybody to use *Forgot password?*;** for a client's own
  server, set it (and `web.base.url.freeze`) at deploy. `[open]`, owner.
- **The relay's plain-text part is built and switched off.** The relay
  service is not in this repository; `cadra.email_relay_text_field` names
  the field once its operator confirms one. Until then, on the cluster, a
  letter still has no plain-text part — H.3 is NOT done there. Locally
  (SMTP to Mailpit) the text part is present (report 45 §B). `[open]`, owner.
- **On the cluster the relay ignores our From**, so the new *Sender address*
  changes the sender only where the tenant sends by SMTP. `[open]`, owner,
  with the relay's operator.
- **A tenant with no company address is not refused** — report 43 said it
  was; the From falls back to the sender, then to the RECIPIENT's own
  address. `nrs19` has none (0 of 1 companies). `[verified]`
- **Approval notifications fail to send whenever the person (or credential)
  acting has no email address.** Odoo's chatter mail takes its From from the
  acting user, not the company, and `mail.default.from` is unset on 8 of 8
  local tenants: *"You must either provide a sender address explicitly or
  configure using the combination of `mail.catchall.domain` and
  `mail.default.from`"*, logged on every `/move` the suite's credential
  raised. The request itself is unaffected; the approver's email is not
  sent. Since handoff 35. `[open]`
- **A brand module cannot be installed on a tenant that bootstrap has
  already touched.** `cadra_brand_jaiz` on `boot44` failed:
  `duplicate key value violates unique constraint "ir_config_parameter_key_uniq"
  … (cadra.brand_short_name)` — the module's data file creates rows that
  already exist (empty). The branding API (`PATCH /settings/branding`) is the
  path that works, and is how `boot44` was branded. `[open]`
- ***Forgot password?* answers in about 60 ms for an unknown login and later
  for a real one** (the letter is sent before the answer). The sentence is
  the same; the timing is not. Turnstile, where configured, is the only
  rate limit. `[open]`
- **`test19` holds more accounts than an API credential may read in one
  report** (103 against `EXTERNAL_TOTAL_CAP` = 100, announced in
  `_warnings.truncated`). Four HTTP tests that looked for a fresh person in
  the access report were taught to read the announcement instead, or to act
  on a visible older fixture. `[landed]`
- **System administrators lose the deep link back into the back office**
  after a session expires: an anonymous `auth='user'` page now goes to the
  app, not to `/web/login?redirect=…`. They sign in at `/web/login`. By
  ruling. `[verified]`
- **NRS's 87.** On the local `nrs19` replica, re-counted: **87 of 6,646**
  custodied assets (of 11,951) are held by **59 distinct** archived
  employees (of 207 archived, of 11,386); **0** of the 87 is flagged for
  retrieval, **0** of the 59 is `exited` in SAP — every one still reads SAP
  status `active`. The live tenant was NOT re-counted: the Builder's
  permission layer refuses reads of the cluster's databases. `[open]`,
  owner, before it is quoted.

## 23 · Handoff 46 — everyone sees their own job, 2026-10-03

### 23.1 · What it closed — `[landed, keep it that way]`

- **Six demo personas, one per role and two combinations**, on every
  classified local tenant (`test19`, `boot44`, `nrs`, `lasg`, `gtb`,
  `jaizbankplc`): Halima Danjuma (Store Officer — Asset User), Chukwudi
  Anyanwu (Asset Manager), Nkechi Obiora (Tag-Issuing Unit alone),
  Babatunde Olaniyan (Tagging Officer — Asset User + Tag-Issuing Unit),
  Zainab Garba (Internal Auditor — Auditor), Oluwaseun Ajayi (Systems
  Administrator — system + Asset Manager). Logins `first.last@demo.example`;
  passwords in `docs/api/.personas.<db>` (gitignored, mode 600) and nowhere
  else. Marked three ways — `is_test_fixture` derived from an inert test
  credential, the reserved domain, an `__cadra_demo__` external id — and a
  persona is never an employee.
- **The three commands**, all through one wrapper:
  ```
  scripts/demo_personas.sh <db> seed             # re-runnable; twice changes nothing
  scripts/demo_personas.sh <db> list             # which accounts here are demo accounts
  scripts/demo_personas.sh <db> remove           # dry run: the database's own answer
  scripts/demo_personas.sh <db> remove --apply
  ```
- **What a persona does is labelled too**: an account that is a fixture is
  a test actor (`is_test_fixture` / `source='test'` on what it creates).
- **Every sidebar item declares the scope the server requires; hidden ⇔
  refused**, proved per persona per item by signing in.
- **Landing**: the asset register dashboard, or the best page the person
  can open; `/no-access` says so in words when there is none.
- **Write controls on a page are hidden without their scope**; a settings
  screen reached without `settings:write` shows its values read-only.
- **The dashboard never shows mock numbers to a signed-in person**; it
  showed 13,150 assets to a refused one.

### 23.2 · Found — `[open]` unless it says otherwise

- **At go-live, the personas come off every client tenant.**
  `scripts/demo_personas.sh <db> remove`, read the dry run, then
  `--apply`. A persona named on a move request (requester, approver or
  decider) cannot be deleted and is archived instead — it can no longer sign
  in. `[open]`, owner, at go-live.
- **`cadra19`, `nrs19` and `gtb19` have no personas**: they are still
  unclassified (§7's marks are ruled and not applied), and the seed refuses
  an unclassified database like every writing script. After the owner runs
  §7's three commands, `scripts/demo_personas.sh <db> seed` on each.
  `[open]`, owner.
- **The cluster's personas go on through a workflow** — the local wrapper
  calls `docker compose` and cannot reach it. Once the owner has run it:
  ```
  gh workflow run demo-personas.yml --ref dev \
    -f dbs=staging,gtb,jaizbankplc,lasg -f action=seed -f classify_absent_as=client
  scripts/demo_personas_fetch.sh <run-id>     # on the owner's machine
  ```
  The passwords arrive encrypted and are readable only where
  `docs/api/.personas.key.pem` lives; they land in
  `docs/api/.personas.cluster.<db>`. At go-live: `-f action=remove`, read
  the dry run, then again with `-f apply=true`. `[open]`, owner, to run.
- **Do not create a real person from a persona's session.** A persona is a
  test actor, so an account it creates is labelled `is_test_fixture` for
  good, and everything that person then does is labelled too. The listing
  names any such account (`ACCOUNTS created by them`); the remover does not
  touch it. `[open]`, Architect — whether that is acceptable or the label
  should stop at accounts.
- **The access record keeps the personas' role grants for good** — 14 rows
  per seeded tenant, including a System Administrator grant. Append-only by
  design; the `@demo.example` login on each row says what it was. After
  removal the rows remain. `[open]`, Architect, to accept as written.
- **The roles do not fit the people** — report 46 §E, the evidence measured
  by signing in as each persona:
  - *Asset User cannot change the register.* A Store Officer can register
    nothing, request no move and verify nothing (`POST /assets`, `/move`,
    `/verify` → 403). The smallest role that can is Asset Manager, which
    also approves other people's moves and changes settings, branding,
    depreciation and integrations. There is no role between reading the
    register and running it.
  - *The tagger cannot issue or replace a tag.* Asset User + Tag-Issuing
    Unit confirms a label (`tag-affixed`) but `POST /barcode/generate` and
    `/tags/<id>/request-replacement` need `assets:write`.
  - *`dashboards:read` admits Fleet, Staff Bus, Fleet Roster, Maintenance
    Readiness (and the hidden FM and Security dashboards) to every Asset
    User and Auditor* — the same scope as the asset dashboard's KPIs.
  - *`identity:read` admits the access-change record to every Asset User*
    — the same scope as the employee picker a custodian needs.
  - *The Auditor has reports with no screen*: configuration changes,
    disposals and the asset-register export answer 200 over the API and
    the app has no page for them.
  `[open]`, Architect — a role-model decision, not a string to add.
- **For the per-tenant toggles handoff — screens no current role maps
  onto:** Fleet Command, Fleet, Staff Bus, Fleet Roster, Maintenance
  Readiness, FM Operations and Security Operations (hidden), all on
  `dashboards:read`; Identity (clearance) and Staff Bus read no API at all
  (mock pages, nothing for a server to refuse); the Facility Command Center
  is cross-domain and still carries a hardcoded *All systems operational*
  pill. `[open]`, Architect.
- **Three write routes have no screen**: `POST /assets/<id>/approve-disposal`,
  `POST /home/quick-submit`, `POST /integrations/sap/employee-sync`.
  `[verified]`
- **Tag numbering walked every issued number past 999** — ~11 s per
  registration on `test19`, and one `nrs19` and eight `jaizbankplc` prefixes
  past 999. Fixed (numeric maximum); `[landed, keep it that way]`. Numbers
  above 999 that were never used are no longer back-filled.
- **A local `.env.local` bakes an expired token into the local bundle**
  (`VITE_API_TOKEN`), so a fresh local browser is briefly "signed in" with no
  scopes. Harmless once known; the owner's file. `[verified]`

## 24 · Handoff 48 — what this tenant has, 2026-10-03

### 24.1 · What it closed — `[landed, keep it that way]`

- **Settings → Sidebar**, administrator only: which of the 28 sidebar items
  and 10 groups this tenant shows. A person is drawn an item only when the
  tenant shows it AND their role opens it.
- **It is presentation, not permission, and says so** — first thing on the
  screen, in the API payload (`is_a_permission: false`), and by a guard that
  fails if anything on the server but its own route reads a switch or if the
  app's routes consult one. An item switched off still opens by its address
  and its data comes back. **A tenant that must not have a module needs it
  uninstalled, not switched off.**
- **Everything is on by default**, including any item added later; 0 rows on
  9 of 9 local databases before the first switch.
- **The Sidebar screen and the Settings group cannot be switched off**
  (refused before anything is written; ignored on read if a row says so).
- **Every switch is a row in the configuration-change report**, under its own
  key, naming who last changed it.

### 24.2 · Found — `[open]` unless it says otherwise

- **Screens that have no business in the sidebar for most tenants — not
  "switchable", absent until there is something behind them.** Putting all
  28 items in one list with a default made this plain:
  - **Staff Bus** and **Identity (clearance)** read no API: both render
    built-in sample data (`MockDataBanner`, `mockIdentityRecords`). Default
    on means every new client is shown two screens of invented data. Remove
    them from the sidebar until there is a model behind them.
  - **The fleet line — Fleet Command, Fleet, Fleet Roster, Maintenance
    Readiness** — reads a real model (`fleet.vehicle`), but the real NRS
    register (`nrs19`) holds **0 vehicles**, and on every other local tenant
    every vehicle row came from one superuser load on one day (`cadra19`
    1,609 and `nrs` 1,609; `gtb19`, `gtb`, `lasg`, `jaizbankplc` 30 each;
    `test19` 0). No client has put a vehicle in Cadra. It is the textbook
    case for the tenant switch today, and a question for NRS before it is
    one for engineering: is fleet in scope for any client?
  - **IT Assets Command** is the register filtered to one domain: 69 IT
    assets of 11,951 on `nrs19`, 13 of 1,335 on `cadra19`, 1 of 4,164 on
    `jaizbankplc`, 0 on the other five. A saved filter on *All Assets*, not
    a product line.
  - **The Facility Command Center** (the `/` front door) is cross-domain;
    its hardcoded *All systems operational* pill — an instrument reporting
    something it does not measure — was DELETED by handoff 47 §1b. What a
    real one would take is in report 47.
  - **SAP Sync** is real but empty where it matters: `nrs19` has 11,386 of
    11,386 employees at `never`. It earns its place when the SAP employee
    feed is live, not before.
  `[open]`, Architect.
- **Who changed a switch is the LAST write only** — the configuration report's
  standing limit (handoff 23, `myservice_api/models/audit_configuration.py`): a switch turned off by one person and back on by
  another names only the second. One row per switch keeps that as narrow as
  this storage allows. `[verified]`
- **Other people's sidebars catch up within five minutes or on reload**: the
  sidebar re-reads the switches every five minutes; the administrator's own
  sidebar changes at once. Presentation, so not a gap. `[verified]`
- **A frontend rolled out ahead of its backend shows everything**: the
  sidebar treats an unreadable answer (a 404 from an Odoo without the route)
  as nothing hidden, and the Sidebar screen shows the error. On the cluster a
  push rolls the frontend only; the route needs `myservice_api` 19.0.3.20.0
  loaded (the `cadra-upgrade` Job). `[open]`, owner, at the next cluster
  upgrade.



## 25 · Handoff 47 — a role is a job, 2026-10-03

- **The role model now fits the people** — the two coarse scopes split
  (`access:read` out of `identity:read`, `operations:read` out of
  `dashboards:read`), tag issuance and replacement on `tagging:write`, and
  the **Asset Officer** between Asset User and Asset Manager. Rulings and
  consequences in `docs/DECISIONS.md` (2026-10-03, handoff 47); breaking
  changes announced in `docs/api/CHANGELOG.md`. `[landed, keep it that way]`
- **NRS is owed a real clearance screen.** Handoff 47 §1b removed *Identity
  (clearance)* from the sidebar because it rendered sample data built into
  the app — but NRS asked for the screen by name: their offboarding
  question (*"whatever process you want to determine how those assets are
  retrieved"*) is what it pretended to answer. The mechanism already exists
  in the back office (report 43 §G.2: a leaver's clearance list, disposed
  assets excluded since handoff 31). Owed, not dropped. `[open]`, Architect
  — a build, after the Auditor's screens.
- **Staff Bus left the sidebar with it** (same ruling, same reason: mock
  data, default-on). Both keys are retired in `SIDEBAR_RETIRED` and never
  come back under the same name; both routes still serve by address.
  `[landed, keep it that way]`
- **The Auditor's four reports still have no screen** — configuration
  changes, disposals, the register snapshot, the export all answer the
  auditor 200 over the API and the app draws no page for any of them
  (report 46 §E.6). Explicitly NOT ruled in handoff 47: it is the next
  build, and the auditor's demo. `[open]`, Architect.
- **Existing credentials provisioned under the old scopes** need their rows
  touched where they relied on a split or moved scope: a non-admin
  credential holding `identity:read` to read `/reports/access-changes` now
  needs `access:read`; one holding `dashboards:read` for the fleet/FM/
  security endpoints now needs `operations:read`; one holding `assets:write`
  to mint or replace labels now needs `tagging:write`. Per-tenant counts of
  who is actually affected are in report 47 §counts. `[open]`, owner, before
  the next demo that uses a non-admin credential on those routes.
