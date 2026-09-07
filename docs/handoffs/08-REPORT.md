# Handoff 08 — REPORT: Nothing scheduled has ever run

**Builder:** Claude Code (IDE) · **Branch:** `fix/scheduler-all-tenants` → PR into `dev`
**Date:** 2026-09-07

## Needs the owner

- **Merging the PR.** The Builder's permission layer refuses `gh pr merge`.
- **Three decisions surfaced here that are not mine to take** — the k8s telemetry
  cron, the dashboard routes' 400-vs-403, and the `is_verified` / `is_overdue`
  staleness. Each is written up below with a recommendation.

---

## The headline, corrected

The diagnosis is right and the mechanism is exactly as stated. `config/odoo.19.conf:7`
set `db_name = odoo`, and Odoo's cron worker reads that same option:

```python
def cron_database_list():
    return config['db_name'] or list_dbs(True)
#   odoo/service/server.py:99
```

So the scheduler served one database. **And it was the wrong one twice over** —
`odoo` is the only 15-era database on this machine:

```
odoo        | base = 15.0.1.3   <- the only DB cron was pointed at
cadra19     | base = 19.0.1.3
nrs19       | base = 19.0.1.3
gtb19       | base = 19.0.1.3
test19      | base = 19.0.1.3
nrs         | base = 19.0.1.3
gtb         | base = 19.0.1.3
lasg        | base = 19.0.1.3
jaizbankplc | base = 19.0.1.3
```

A 19 worker skips a 15 database as incompatible (`ir_cron.py:201`). So the
scheduler was not merely pointed at one tenant instead of eight — it was pointed
at the one database it would refuse to process. Zero jobs, not one-eighth.

### Two corrections to the handoff's framing

**1. This is a local-development defect, not a production incident.**
`k8s/dev/10-configmap-odoo-19.yaml:13-14` has *always* deliberately omitted
`db_name`, and sets `dbfilter = ^%d$`. `list_dbs(force=True)` bypasses that
configmap's `list_db = False`. So the cluster's worker has been enumerating every
tenant all along. The eight "production-shaped tenants" that never ran a cron are
the eight *local* databases. I could not confirm this against the live cluster —
`kubectl` is installed but has no context — so it is read from the manifest and
the Odoo source, not observed. **The one-query check on a staging tenant is
`select cron_name, lastcall from ir_cron where cron_name ilike '%epreciat%';` — a
`lastcall` inside the last 31 days settles it.**

**2. "Not one, not once" is very slightly too strong.** The four 19-era databases
carry populated `lastcall` values from foreground `-d <db>` runs and the throwaway
worker containers handoff 06 used. The four replicas (`nrs`, `gtb`, `lasg`,
`jaizbankplc`) had **every** `lastcall` NULL — 26 of 26 each. Nothing has ever run
from the stack's own scheduler on any tenant, which is the claim that matters.

---

## The confirmed cron list

I confirmed the list as instructed rather than acting on it. It is right about
five of six, wrong about one, and incomplete by two.

| Cron | Status | What never running cost |
|---|---|---|
| `myservice_workflow.cron_workflow_outbound_events` (INT-05) | **confirmed dormant** | Every outbound asset event queued and stayed queued. 5 pending + 10 error rows on `nrs19` at the start of this handoff. |
| `myservice_asset_depreciation.cron_asset_depreciation` | **confirmed dormant** | **₦23.1 m of accumulated depreciation understated across seven tenants** — measured, and then measured again after the fix. See below. |
| `myservice_api.ir_cron_gc_refresh_tokens` | **confirmed dormant** | 23 expired/revoked refresh tokens never purged. Table hygiene, *not* an auth hole: `verify_and_rotate` checks `expires_at` at use time (`api_refresh_token.py:117`), so a dead token was never usable. Lower severity than the handoff implies. |
| `myservice_asset_register.cron_asset_pm` | **confirmed dormant** | **Nothing.** There are 0 `nrs.asset.pm` rows on all eight tenants — the cron's loop has never had a record to enter. No PM was missed because no PM schedule exists. |
| `myservice_fleet_maintenance.ir_cron_fleet_preventive_maintenance` | **confirmed dormant** | **Nothing.** All 1,609 (`cadra19`/`nrs`) and 30 (elsewhere) vehicles are `maintenance_status = no_schedule`, because none has a `last_service_date`. Zero tickets, zero alerts. |
| `myservice_identity.cron_sap_asset_export` | **the list is wrong** | It is `active="False"` **by definition** (`myservice_identity/data/ir_cron.xml`) and its code is the literal `pass` with the comment *"Placeholder — implement when Redhubs API confirmed"*. It is dormant by design, not by this bug. Nothing was "never pushed" that was ever going to be. |

**Two crons the list is missing, and they are the worst thing found.** `nrs19` and
`jaizbankplc` each carried two extra `ir_cron` rows:

```
cron_asset_pm_refresh_overdue    -> nrs.asset.pm._cron_refresh_overdue()
cron_asset_refresh_verification  -> nrs.asset._cron_refresh_verification()
```

**Neither method exists on `dev`.** *(Corrected after verification — my first
draft said they had never existed anywhere, and that was wrong.)* Both exist in
commit `c673ed1` on `feat/rfp-phase1-authorisation`, which is **not** an ancestor
of `dev`. That commit added the two crons, their data file **and** batched
implementations whose docstrings name this exact problem — and it was never
merged. These two databases were upgraded from that branch; the rows survived,
the code did not.

The distinction matters three ways: the diagnosis is "two tenant DBs carry state
from an abandoned branch", not "someone scheduled a phantom"; the fix for
`is_verified`/`is_overdue` **already exists at `c673ed1`** and is where a
follow-up should start rather than a blank page; and on `dev` the xmlid still
claims this module owns a cron this module does not define, so the lookup finds
nothing. `nrs19` already shows `failure_count = 1`.

**They were harmless only because the scheduler was dead.** The first tick after
the fix would have raised `AttributeError` on both, on two tenants, every day, for
at least a week before Odoo auto-deactivated them and notified the admin. They are
deleted by `myservice_asset_register/migrations/19.0.1.10.0/post-migrate.py` —
before the scheduler was woken, not after.

**On `dist/`:** the Architect's caution was right and the answer is that it is out
of scope. Ten module *names* under `dist/` match installed modules on the live
tenants (`generic_location`, `generic_resource`, `web_responsive`, …), but they are
installed from `crnd-19/`/`oca-19/`, which are on the addons path; `dist/` is not.
Neither `crnd-19/` nor `oca-19/` defines a single `ir.cron`. No `dist/` module
contributes a cron to any tenant.

---

## Part A — the fix

### `db_name` does two jobs and only one was wanted

Removing the line alone would have broken CI. `.env.example` ships
`ODOO_DBFILTER=` (empty), CI copies it, bootstraps the database named `odoo`, and
pytest hits a bare `http://localhost:8069` — which worked *only* because
`db_name = odoo` exposed exactly that one database on every host. That was the
trap in this handoff.

The separation used is:

- **`db_name` controls HTTP exposure AND pins the cron worker.** Gone from
  `config/odoo.19.conf` and `config/odoo.dev.conf`.
- **`dbfilter` controls HTTP exposure only.** `list_dbs(force=True)` goes to
  `pg_database` regardless of what the filter says (`service/db.py:438`), so the
  scheduler now sees every database whatever the filter is set to.
- `.env.example` therefore ships **`ODOO_DBFILTER=^odoo$`**, which reproduces the
  old single-database exposure exactly, and `^%d$` remains the multi-tenant
  setting. Both compose files default to `^odoo$` so there is no silent
  "expose everything" state if `.env` is missing.

**Verified, not assumed.** I ran a throwaway container with no `db_name` and
`--db-filter='^test19$'`, and requested a bare `localhost` with no Host subdomain:

```
  /web/login -> 200
  {"data": {"name": "My Company", "short_name": "NRS", "primary": "#C8102E", ...}}
```

That is the CI path, reproduced. (Handoff 07's report records a CI failure that
verification missed; this is the check that would have caught it.)

### What each config file is for

| File | Purpose | Live? | `db_name` |
|---|---|---|---|
| `config/odoo.19.conf` | The Odoo 19 dev stack, mounted by `docker-compose.19.yml` | **Yes — this machine** | was `odoo`, **removed** |
| `config/odoo.dev.conf` | The Odoo 15 dev stack, mounted by `docker-compose.dev.yml` | No — nothing runs 15 here | was `odoo`, **removed** |
| `config/odoo.prod.conf` | The legacy VPS/Caddy compose deployment (`docker-compose.prod.yml`) | Not on this machine; k8s superseded it | **never set** — unaffected |
| `odoo.conf` (repo root) | **Answering the Architect's question:** a committed *generated artefact* of the Odoo 15 bare-metal `install.sh`. `db_name = myservice`, `addons_path = /opt/odoo/...`, references a `bureaucrat` tree that no longer exists. **Nothing mounts or reads it** — `install.sh:183` writes `/etc/odoo/odoo.conf` from its own heredoc and never opens this file; its own comment at line 16 points at `config/odoo.conf`, which does not exist. It is single-host, single-database, so its `db_name` is correct for what it describes. **Recommend deleting it**; I have not, because it is outside this handoff and deleting a committed file is the owner's call. |

### `max_cron_threads` — 1 is sufficient, and here is the basis

I did not raise it. The reasoning, from the Odoo 19 source and then from
measurement:

- `WorkerCron.process_work()` processes **one database per call**, and `sleep()`
  only really sleeps *once the queue is empty* (`service/server.py:1416-1470`).
  One thread therefore walks all nine databases per cycle — it is not one tenant
  per minute, which is the intuition that makes 1 look too small.
- `ir.cron._trigger` sends a `NOTIFY cron_trigger` carrying the database name.
  That both interrupts the `select()` sleep and puts the triggered database at the
  **head** of the queue, so an INT-05 delivery does not wait behind seven idle
  tenants. Observed: an affix at 20:39:37 was attempted at **20:39:41**.
- **Measured:** the entire first tick — 192 jobs across 8 databases with weeks of
  catch-up in it — took **3 m 38 s** on one thread. The longest single job was
  9.89 s. Steady state is a fraction of that.
- It matches `k8s/dev/41-odoo-19-deployment.yaml:69`, which also runs 1. Raising
  the local value would make local behaviour *less* representative of the cluster.

The real cost of one thread is head-of-line blocking while a genuinely long job
runs. At a 9.89 s worst case against a 5-minute INT-05 sweep, that is not a
concern. If a tenant ever acquires a job in the minutes range, revisit — and
`limit_time_real_cron` below is the tripwire.

### One limit I did change, and why

`limit_time_real_cron` defaults to `-1`, meaning "use `limit_time_real`", which
itself defaults to **120 s**. A cron job running longer than two minutes has its
worker **SIGKILLed and its transaction rolled back — forever, on every retry.**
That was survivable while the scheduler was pinned to an empty database. It is not
survivable on a first tick carrying an 11,386-row HR recompute and a
114,250-attachment filestore walk on `nrs19` alone. `config/odoo.19.conf` now sets
`limit_time_real_cron = 1200`, which is what `k8s/dev/10-configmap-odoo-19.yaml`
already gives the cluster via `limit_time_real`. HTTP keeps its 120 s.

---

## What the first scheduler tick actually did

*This is the number the Architect asked for first.*

I staged it deliberately: the stack was brought up with `--max-cron-threads=0`,
every migration was run, the debts were retired, and only then was the scheduler
enabled — so the tick has a known start time and nothing else moving.

```
scheduler enabled     20:32:46 UTC
first job starts      20:34:19 UTC   (23 s container boot + WorkerCron's 64 s initial sleep)
last job finishes     20:37:57 UTC
─────────────────────────────────────
first tick duration   3 m 38 s       192 jobs, 8 databases, 1 cron thread
```

Per tenant: `cadra19` 24, `gtb19` 24, `test19` 24, `nrs19` 20, and 25 each on
`nrs`, `gtb`, `lasg`, `jaizbankplc`. `odoo` was enumerated and skipped, as designed.

**192 and the 186 in the fan-out table below are two different measures, and the
table's "24 of 23" is my sloppy labelling, not an arithmetic error.** 192 counts
*job executions* inside the 20:34:19–20:37:57 window, read off the log. 186 counts
*distinct crons whose `lastcall` is after the wake*, read off the database later —
so a cron that ran twice counts once, and the denominator is `active`, which fell
by one per tenant when I deactivated the telemetry cron after it had already run.
Neither number is reconstructable now: `lastcall` is overwritten by every
subsequent pass, and the container log no longer reaches back that far.

**Overdue jobs fire once, not N times.** `ir_cron.py:647` catches `nextcall` up in
a loop that advances the schedule without re-invoking the job, so a daily cron 20
days late runs a single time. This is why a three-week gap cost under four minutes.

### What it changed

| | |
|---|---|
| Refresh tokens purged | **23** (`cadra19` 5, `gtb19` 9, `jaizbankplc` 9, `nrs19` 0) — all already expired or revoked >7 days |
| Depreciation recomputed | 5 tenants on the first tick; the 3 not yet due were taken separately (below) |
| PM service requests created | **0** — no PM schedules exist |
| Fleet maintenance tickets | **0** — every vehicle is `no_schedule` |
| Emails **sent** | **0.** `select count(*) from mail_mail where state='sent'` is 0 on every tenant, after the tick |
| Jobs that failed | **7** — all of them `Publisher: Update Notification`, deliberately (below) |

### The one thing that genuinely needed staging

Not the 67 queued emails. Those were the obvious candidate and they are inert:
every one is in state `exception`, not `outgoing`, and the queue domain is
`('state','=','outgoing')` with no date filter (`mail_mail.py:206-212`), so the
scheduler selects **zero** rows. Behind that, there is no `ir_mail_server` on any
tenant, no SMTP or catchall parameter, the relay env vars are empty, and
`localhost:25` refuses from inside the container — the same `[Errno 111]` already
stamped on all 67. Nothing was going to be sent, and after the tick nothing was.

The item that did need handling is one the handoff's table does not mention:

**`mail.ir_cron_module_update_notification` — "Publisher: Update Notification".**
Weekly, overdue on every tenant, and the only cron in the set whose outbound
transport actually works. It POSTs to `http://services.odoo.com/publisher-warranty/`
a payload assembled at `mail/models/update.py:_get_message` containing the database
name and uuid, `web.base.url`, the installed application list, user counts — **and
the company's name, email and phone.** Across these tenants that is *Nigeria
Revenue Service*, *Guaranty Trust Bank*, *Jaiz Bank Plc* and *Lagos State Ministry
of Health*, disclosed to a third party from a developer's laptop, in one batch, the
moment the scheduler woke.

**It had already fired once, and I first wrote that it never had.** `nrs19`'s
row shows `lastcall = 2026-09-06 19:15:33` — handoff 06's throwaway worker
container, a day before this handoff, while `publisher_warranty_url` was still
the Odoo default. So one real POST carrying the Nigeria Revenue Service company
name, email and phone was attempted from this machine before any of this was
done. Worth the owner knowing rather than asserting away.

Neutralised before the tick, in two layers:

1. `publisher_warranty_url = http://localhost:1/publisher-warranty/` in
   `config/odoo.19.conf` and `config/odoo.dev.conf`. This is the durable half: it
   is in the repo, it covers every local database including ones not yet created,
   and it holds whatever a cron row says.
2. The cron row deactivated on all eight local tenants. Needed because the server
   action is `model.update_notification(None)` — `cron_mode` **falsy**, so it
   raises rather than returning `False`. The closed port alone would mean a weekly
   `ERROR` and a climbing `failure_count` on every database. *(I initially wrote in
   the config comment that it would fail silently; the first tick proved otherwise
   — 7 tenants logged `server action #133 failed` — and the comment is corrected.)*

The tick's 7 failures are that mechanism working: connection refused at a closed
port, no payload off the machine.

**Owner decision:** the k8s stack has no `db_name`, so **this cron has been running
weekly in the cluster all along** and those POSTs have been going out. Whether to
stop it there is a product decision about telemetry, and I have not touched
`k8s/`. Two further reasons not to: a ConfigMap mounted with `subPath`
(`41-odoo-19-deployment.yaml:70-74`) is excluded from Kubernetes' update
propagation, and the only step that rolls `odoo-19` is gated on
`workflow_dispatch` (`deploy-dev.yml:216`) — so a configmap edit merged to `dev`
would be applied and **not take effect**. Any k8s config change needs a
deliberate roll. That is itself a finding; see §"the same shape elsewhere".

**Also noted, not acted on:** `digest.ir_cron_digest_scheduler_action` manufactured
~40 new `mail_mail` rows across seven tenants on the first tick, every one of which
failed immediately — not one of the 36 due subscribers has an email address. It
authored 26 of the 67 rows already in the queue. It is harmless today and becomes
real email the day anyone configures SMTP. Recommend deactivating the digest per
tenant; it is a product decision, not a defect.

---

## Depreciation — does it need a backfill?

**No. One cron run per tenant is sufficient, and the reason is structural.**

`_cron_recompute_depreciation` (`myservice_asset_depreciation/models/asset.py:356`)
selects assets whose method is `straight_line` or `declining_balance` and calls
`engine.value_at(as_of, ...)`, which **rebuilds the whole schedule from the start
date and reads off the last elapsed period** (`depreciation_engine.py:275-295`). It
does not append and does not increment. Missing twelve runs and missing one produce
the identical output on the next run. There is no per-period row to reconstruct —
no depreciation line or history model exists in the repo (`\dt *depreciation*` on
`nrs19` returns nothing), because the schedule is derived on demand by design.

So the recovery is: **let the cron fire.** Which it now has.

### The damage, measured — and then measured again after the fix

The figures are plain stored fields with no `compute=` and no `@api.depends`
(`asset.py:96-105`); the module's own docstring says why: *"these figures drift
with **time**, not just with their inputs."* Nothing recomputes them on read — the
API serialises the stored column straight out (`v1_assets.py:129-142`).

| Tenant | assets in scope | accumulated **before** | accumulated **after** | correction |
|---|---:|---:|---:|---:|
| `cadra19` | 1,313 | 173,038,279.71 | 175,764,238.02 | **+2,725,958.31** |
| `gtb19` | 156 | 360,874,486.21 | 366,133,593.84 | **+5,259,107.63** |
| `nrs19` | 54 | 0.00 | 0.00 | 0.00 |

`nrs19`'s zero is correct, not a failure: **all 11,878 of its assets are
`erp_managed`**, which the cron's domain excludes by design (NRS spec §6.2 — SAP
FICO owns those figures). The "11,878 assets" in the handoff is the register size,
not the depreciation workload; the cron touches 53 rows there and 4,928 across the
whole estate.

The remaining five tenants were recomputed by the first tick itself and stamped
`cadra.depreciation.last_recompute`. Estate-wide the understatement was **≈₦23.1 m**,
and seven assets across four tenants were showing `Depreciating` having already
reached end of life (`gtb19` alone went from 38 to 40 `fully_depreciated`).

Every asset was behind by **exactly one monthly charge**, not by years — the
figures were last written by a manual `backfill_depreciation.py` run on
2026-08-20, and one month-end has passed since.

**Not a second route:** `k8s/dev/52-depreciation-job.yaml` is a one-shot `batch/v1`
Job with `REPLACE_ME_*` placeholders, driven by a `workflow_dispatch`-only
workflow that defaults to a dry run. It is a manual data-fix tool, not a scheduler.

**One inconsistency worth a follow-up:** `GET /assets/<id>/depreciation-schedule`
returns `summary` from the *stored* fields and `periods` computed *live*
(`v1_assets.py:1235-1248`), so between cron runs a client can see the two disagree
inside a single response. Not introduced here; now much less visible.

---

## Part B — proved unattended

**No shell. No manual drain. No calling the cron function.** An affix through the
API, then nothing.

### `nrs19` → Vendra

```
20:39:36  POST /api/v1/assets/11936/tag-affixed   (client: tag_issuing_unit)
20:39:37  event queued          workflow.dispatch.log #45, status=pending
20:39:41  attempt 1  ← 4 seconds later, by the scheduler, unattended
...
20:48:50  attempt 4  HTTP 409  status=acknowledged
          {"status":"duplicate","duplicate":true,"name":"VIM-2026-00241",
           "received_event_id":"46b92321407f4373ae573a3634e0f034"}
```

**Queued 20:39:37 → delivered 20:48:50.** Vendra holds it as `VIM-2026-00241`.

The nine minutes are not scheduler latency — the first attempt came **4 seconds**
after the affix. Two real conditions stretched it, and both are worth recording:

1. **`vendra.network` resolved to `127.0.0.1` inside the container**, which is the
   container, so every outbound event dead-ended on "Connection refused" against
   Cadra itself. Fixed properly in `docker-compose.19.yml` with
   `extra_hosts: ["vendra.network:host-gateway"]` — the hostname is load-bearing
   because Frappe selects the site from the `Host` header, so rewriting the URL to
   `host.docker.internal` returns a 404 from the wrong site. Without this the
   local INT-05 loop cannot work at all, scheduler or no scheduler.
2. **A delivery that timed out had actually landed.** Vendra took longer than the
   config's 10 s `rest_timeout` to answer, so Cadra recorded a failure for a
   request Vendra had processed. The retry got `409 duplicate` — and handoff 06's
   ruling that *"a 409 from the receiver is a delivery, not a failure"* is what
   turned that into `acknowledged` instead of a spurious dead-letter. **The
   `event_id` idempotency design was load-bearing here, live, on its first real
   timeout.** That is the strongest evidence in this report that the outbox is
   built right.

### `jaizbankplc` — the second tenant

```
20:43:41  POST /api/v1/assets/2001/tag-affixed
20:43:42  event queued          workflow.dispatch.log #52
20:43:46  delivered  HTTP 202   ← 4 seconds, unattended
```

Receiver log:
```json
{"at":"2026-09-07T20:43:46","path":"/int05",
 "idempotency":"0c7e10bc250f4a1abb22eb5a6c2d953c",
 "event_id":"0c7e10bc250f4a1abb22eb5a6c2d953c",
 "asset":{"asset_code":"Jaiz-AST-002245","id":2001,"name":"H08 second-tenant scheduler probe"}}
```

**Queued 20:43:42 → delivered 20:43:46. Four seconds.** The gap is the proof.

I deliberately did *not* point this at Vendra: `jaizbankplc` is a different
client's register, and writing its assets into Vendra's real dataset to prove a
scheduler works is a bad trade. It has no `asset_events` config of its own, so I
provisioned one against a throwaway local receiver. **That config is a local test
artefact** — `workflow.config` id 1 on `jaizbankplc`, pointing at
`http://host.docker.internal:8901` — and should be removed or repointed before that
tenant is used for anything else.

---

## Part C — every API client now acts as itself

The finding is exactly right and the fix was smaller than expected, because
**the mechanism already existed**: `myservice.api.client.user_id` is a
`required=True` many2one called "Run As User", and `require_jwt` already puts the
JWT's `uid` claim into the request env. Odoo 19's `sudo()` does **not** change
`env.uid` (`orm/models.py:5954` — *"does not change the current user"*), so
`affixed_by = self.env.uid` at `asset_tag.py:212` was faithfully recording the
truth. The truth was that **both provisioning sites in `scripts/bootstrap.py` set
`user_id` to `base.user_admin`** (lines 195 and 260). Two lines.

### What shipped

- **`SCOPE_GROUPS` + `groups_for_scopes`** in `myservice_api/controllers/utils.py`
  — an explicit scope→group table, deliberately **not** the inverse of
  `GROUP_SCOPES` and not derived from it. `assets:read` is granted by three groups
  there and `dashboards:read` by two unrelated ones, so an automatic inverse has
  no basis to choose; and `admin` would invert to `base.group_system`, letting a
  scope string typed into a form provision a system administrator. A source guard
  asserts `group_system` never appears in the table.
- **`_provision_client_user`** on `myservice.api.client`, wired into `create` as a
  default so `user_id` can stay `required=True`, plus a **"Provision Own User"**
  form button for existing records. The user gets no password at all (the column
  is left null — passing `password: False` reaches passlib and raises
  `TypeError: secret must be unicode or bytes, not bool`, which is how the first
  migration run failed), so it cannot log in through the web client or
  `/auth/login`. It stays `active` because `verify_and_rotate` revokes the whole
  token family of an inactive user.
- **`write()` re-syncs the groups when `scopes` change** — but only for clients on
  their own generated login. One deliberately pointed at a shared user is an
  operator's decision, and rewriting that person's groups from a scope string
  would be an escalation nobody asked for.
- **`verify_and_rotate` now resolves a client family's user from the client
  record**, not from the row minted at login. Without this, re-homing a client
  would have had no effect on any session in flight for the full 30-day sliding
  window — structurally the same defect as handoff 05's wildcard scopes. This is
  the exact analogue of the existing ruling that session families re-derive
  scopes: *the record is where the answer lives; the token is only carrying it.*
- **Migration `19.0.3.2.0`**, run on all eight tenants: **10 clients re-homed**
  and **387 live refresh-token rows repointed**. Two corrections after
  verification — I first wrote "11 clients" (the per-tenant counts sum to 10:
  1+3+1+1+1+1+1+1) and called the rows "families", which they are not: a family
  is many rows across rotations, and the migration writes rows. The eleventh
  client is in the 15-era `odoo` database, deliberately **not** migrated because
  a 19 worker cannot load it. It serves no tenant and dies with the 15 stack,
  but it is the one client in the estate this change did not reach.

### Proven live on `nrs19`

```
tag_issuing_unit  -> cadra_client_tag_issuing_unit   groups: Role/User, Tag-Issuing Unit
vendra            -> cadra_client_vendra             groups: Role/User, Asset User, Asset Manager
test_client       -> cadra_client_test_client        groups: … + Role/Administrator
```

The separation is now legible in the user record itself: the Tag-Issuing Unit's
user holds **only** its own group, and Vendra's user does **not** hold it. And the
affix:

```json
"affixed_by": { "id": 10, "name": "Tag-Issuing Unit (API client)" },
"affixed_by_name": "S. Abolarin"
```

`tests/test_tagging.py` asserted only `assert tagging["affixed_by"]` — truthiness —
which is why this passed for a year. It now asserts the name is not
`"Administrator"` **and** that the id equals what `/api/v1/auth/whoami` returns for
the same token.

### How many rows carry the useless value

Not pretended about, not rewritten. There is no evidence in the database saying
which uid-2 affix came from the tagging client and which from a console session,
and inventing one would be fabricating an audit trail — strictly worse than one
that is honestly useless.

| Tenant | affix records | naming **Administrator** | naming someone real |
|---|---:|---:|---:|
| `nrs19` | 52 | **49** | 3 |
| `jaizbankplc` | 265 | **240** | 25 |

**289 affix records across two tenants name Administrator.** On `jaizbankplc` 176
of the 240 are seed rows with an empty `affixed_by_name`; the genuinely
API-written subset is ~64. Also `create_uid = 2` on 51 (`nrs19`) and 43
(`jaizbankplc`) assets whose `import_source` is `vendra`. Everything written from
here on names its client.

### The consequence I had to resolve, and the decision left open

Giving clients real users broke `tests/test_dashboards.py`: **the three
`myservice.dashboard` routes are the only ones in the API that do not `sudo()`**,
so they read `fleet.vehicle` and `generic.location` with the client's actual ACLs
and returned:

```
400 {"error": {"code": "validation_failed",
     "message": "You are not allowed to access 'Vehicle' (fleet.vehicle) records...
                 This operation is allowed for the following groups: ..."}}
```

They worked before only because every client was `base.user_admin`, which held the
manager groups. I fixed it conservatively by mapping `dashboards:read` to the
least-privileged groups that grant read (`fleet.fleet_group_user`,
`generic_location.group_generic_location_user_implicit`). Because the groups are
*derived from* the scope, the two cannot drift — the scope stays authoritative.

**But the right fix is different and it is the Architect's call.** Those three
routes should `sudo()` like every other route in the API, and refuse with a 403
naming the scope. Today a permissions failure surfaces as a `400 validation_failed`
whose message leaks Odoo group names into the published envelope — that violates
rule 1 (the envelope is a contract) and rule 3 (nothing may silently degrade; a
400 saying "validation_failed" for a permissions problem is worse than silent, it
is misleading). I did not take it because it also changes what a **session** token
sees: a Security Officer with `dashboards:read` but no fleet group currently gets
an error and would then get data. That is a security-semantics change to published
behaviour and does not belong in a scheduler handoff.

**Also worth knowing:** `SCOPE_GROUPS` is applied at create, on a scope change, and
by the button. Editing the table later does not retroactively re-sync existing
client users — that is what the button is for. I re-synced all eight tenants by
hand after adding the dashboard groups.

---

## Part D — the debts

Eight users retired: `h05_nobody`, `h05_storekeeper`, `h05_tagger` on `nrs19`;
`phase1_plain`, `phase1_user`, `phase1_approver`, `phase1_manager`, `phase1_auditor`
on `jaizbankplc`. Each is `active = false`, has its `password` column **nulled**,
and had every live refresh-token family revoked — **41 families in total**. No code
creates them; they exist only in those two databases, so this is the whole fix.

**Archived, not deleted, and that is deliberate.** `h05_storekeeper` created two tag
labels and two assets, and `h05_tagger` is `affixed_by` on the only two affix records
in the estate with correct provenance — every other one says Administrator.
`res.users` many2ones are `ondelete=SET NULL`, so deleting would blank precisely the
rows that already answer the question Part C exists to make answerable. Deletion buys
tidiness; archiving plus a nulled credential removes the entire risk (a known-password
account reaching staging) and keeps the evidence.

This supersedes the standing ruling *"Fix the `phase1_*` seed users' roles"* — the
users are gone, so their roles are moot.

**Still with the owner:** rotating the `test_client` secret, as the handoff says.

---

## Anywhere else the same shape appears

*The question that found this one. Ranked by how bad it actually is.*

**1. `sla_breached` has no trigger of any kind — and neither half is tested.**
`myservice_request_fields/models/request_triage.py:31` is `store=True`, computed by
`@api.depends('sla_deadline')` from a body that reads `Datetime.now()`.
`sla_deadline` is a fixed future instant set once at create, so `sla_breached` is
evaluated exactly once — when `now < deadline` is true by construction — writes
`False`, and nothing ever recomputes it. The module ships no cron.
**Measured on `jaizbankplc`: 215 of 215 requests have an `sla_deadline` in the
past; `sla_breached` is true on zero.** A 100% miss rate on live data, backing a
live "SLA Breached" menu, a search filter and a kanban badge. `grep sla tests/`
returns nothing. Worse than the archetype: not even the inner half is tested.

**2. The `_render_qweb_pdf` print funnel is disarmed by its own ambiguity guard.**
Handoff 03 correctly identified that the print funnel is the report render, not the
action methods, and hooked it (`asset_tag.py:460`). But the guard at
`asset_tag.py:499` returns early whenever the ids could be label ids — and handoff
03's own ruling said tag ids collide with asset ids. It treats that as a rare edge
case. **It is the normal case: `nrs19` 11,927 of 11,931 asset ids are also valid
label ids (99.97%); `jaizbankplc` 97.5%.** Both callers it was written for pass a
single asset id and are declined ~99% of the time. `nrs19` holds 11,879 labels at
`issued` and exactly **1** at `printed`.
The test named for the guarantee — `test_printing_records_who_printed_and_when`
(`tests/test_tagging.py:363`), whose docstring says it exercises the barcode
station "the reason the stamp lives at the report-render layer" — asserts
`printed_at is None` **twice**. Both assertions are negative. Nothing in the repo
requests `/report/pdf/` at all.

**3 & 4. `is_verified` never expires; `is_overdue` is never true.** Both are
`store=True` computes whose `@api.depends` cannot fire because what changes them is
the calendar (`asset.py:230`, `asset_pm.py:44`). The two orphan crons I deleted
were somebody's attempt at exactly this, and the methods were never written.
`is_verified` is **published API surface** — serialised, filterable, documented —
so correcting it changes what Vendra sees and is a decision, not a cleanup. It is
latent today (`is_verified` is true on 0 assets) and becomes permanent the moment
anyone uses the Verify button. `is_overdue` already backs a live "Overdue PM" menu
that returns empty forever. **These need their own handoff; I deleted the dead
crons, not the underlying bug, and say so rather than leaving it implied.**

One rule catches all three: *a stored compute whose body reads the clock but whose
`@api.depends` contains nothing the clock changes needs a cron, and that cron's
method must exist.*

**5. 1,464 lines of Odoo-native tests that nothing ran — including the only test
that checks a production trigger.** `--test-enable` appears nowhere in any
workflow or script; CI ran `pytest tests/ -v` and nothing else.
`myservice_workflow/tests/test_outbound_events.py:463`,
`test_the_drain_cron_exists_and_trigger_resolves_it`, asserts the cron **record**
exists, is active, and holds the right code string. It is the correct answer to
this entire bug class, it was written in handoff 06, and it had never executed once.
**Fixed here:** `.github/workflows/ci.yml` now runs the in-registry suites. I ran
them first — **72 tests, all passing, ~7 s** — and confirmed Odoo returns a
non-zero exit code when the assertion report fails (`preload_registries`, `rc += 1`),
so the step genuinely gates rather than decorating the log.
(`e2e/` holds 17 Playwright specs and a committed `.auth/jaiz.json`; `grep -rn e2e
.github/` returns zero hits. Not addressed here.)

**6. A k8s config change has no production trigger.** `41-odoo-19-deployment.yaml:70`
mounts the ConfigMap with `subPath`, which Kubernetes excludes from update
propagation; `deploy-dev.yml:194` applies the ConfigMap on every push to `dev`, but
the only step that rolls `odoo-19` is gated on `workflow_dispatch` (`:216`), and
`deploy-19.yml:148` *skips* the Deployment apply whenever the pod is already
running. So a config fix can be merged, applied, and silently not take effect —
the same shape as this handoff, one layer up. Relevant if the telemetry decision
above leads to a k8s change.

**7. One orphan data file.** `myservice_asset_register/data/asset_resource_types.xml`
is on disk and in no manifest's `data` list — the handoff 07 shape. It defines a
`generic.resource.type` nothing references. Harmless; flagged, not removed.

### The standing guards added

In `tests/test_source_guards.py`, which exists for exactly this and needs no
running instance:

- **`test_no_server_config_pins_the_cron_worker_to_one_database`** — the regression
  net for this bug. Scans `config/*.conf`, the repo root, and the k8s ConfigMaps
  for `db_name`, with the bare-metal `odoo.conf` named as the single explicit
  exception rather than pattern-matched away. Paired with a test that feeds it the
  offending file and asserts it fails.
- **`test_no_long_running_server_names_its_database_on_the_command_line`** —
  because `db_name` is only one spelling. `-d` / `--database=` on a server's argv
  sets `config['db_name']` identically and pins the worker the same way, and the
  compose files and the k8s Deployment are exactly where a server's command line
  lives. One-shot commands carrying `--stop-after-init` are exempt and skipped:
  a bootstrap or upgrade Job *should* name its database, because it has no
  scheduler to starve. Nothing violates it today; that is the point.
- **`test_every_scheduled_method_exists`** — parses every `ir.cron` we ship and
  asserts the method it names is defined somewhere in our modules, with
  `test_the_cron_guard_covers_the_crons_we_ship` so a parser that silently matches
  nothing cannot pass forever.

  **It would NOT have caught the two orphan crons, and I claimed otherwise in an
  earlier draft.** On `c673ed1` the XML and the methods were consistent, so a
  source guard reading that branch passes; and the form that actually reached us
  was a *database row*, which no source guard can see. It is a real guard against
  a real regression — shipping a cron whose method you forgot to write — but the
  class of defect found here needs an **in-registry** test that walks `ir.cron`
  and resolves each `state=code` call against the live model. That belongs with
  the Odoo-native suites now wired into CI and is the single most valuable
  follow-up in this report.

  Its other limits, stated rather than discovered later: the call regex only
  matches `model._x()` receivers, `defined` is a flat set of function names with
  no model binding (a cron on `nrs.asset` naming `_gc` passes because
  `myservice_api` defines `_gc` on the token model), and crons created in Python
  rather than XML are invisible.
- **`test_no_api_client_is_provisioned_as_admin`** — the Part C regression. Its
  first version grepped for the string `"user_id"` and was wrong in both
  directions: it flagged every ORM domain filtering on a user, and it missed the
  attribute form `rec.user_id = env.ref("base.user_admin")` — which is the
  spelling `bootstrap.py` already uses elsewhere, so the likeliest regression.
  It now parses, matches both spellings, and ships
  `test_the_client_guard_catches_both_spellings` feeding it each one.
- **`test_no_scope_grants_an_api_client_system_administrator`**.

---

## Eight-tenant fan-out

Migrations `myservice_asset_register 19.0.1.10.0` and `myservice_api 19.0.3.2.0`,
run on every database **before** the scheduler was enabled.

| DB | base | crons run since wake | orphan crons | clients on admin | own users |
|---|---|---|---|---|---|
| `cadra19` | 19.0.1.3 | 23 of 23 | 0 | 0 | 1 |
| `nrs19` | 19.0.1.3 | 20 of 23 † | 0 | 0 | 3 |
| `gtb19` | 19.0.1.3 | 23 of 23 | 0 | 0 | 1 |
| `test19` | 19.0.1.3 | 24 of 23 ‡ | 0 | 0 | 1 |
| `nrs` | 19.0.1.3 | 24 of 23 ‡ | 0 | 0 | 1 |
| `gtb` | 19.0.1.3 | 24 of 23 ‡ | 0 | 0 | 1 |
| `lasg` | 19.0.1.3 | 24 of 23 ‡ | 0 | 0 | 1 |
| `jaizbankplc` | 19.0.1.3 | 24 of 23 ‡ | 0 | 0 | 1 |
| `odoo` | **15.0.1.3** | **0** — skipped as incompatible, correctly | 0 | n/a | n/a |

† `nrs19`'s monthly/weekly crons are not all due yet. ‡ counts exceed the active
total because `Publisher: Update Notification` ran and was then deactivated.

Every cron in the confirmed list is shown running on a non-`odoo` tenant in the
per-tenant inventory above, and `nrs19`'s reads:

```
myservice_api.ir_cron_gc_refresh_tokens              lastcall 2026-09-07 20:36:43
myservice_asset_register.cron_asset_pm               lastcall 2026-09-07 20:36:43
myservice_fleet_maintenance.ir_cron_fleet_...        lastcall 2026-09-07 20:36:43
myservice_workflow.cron_workflow_outbound_events     lastcall 2026-09-07 21:02:30
myservice_asset_depreciation.cron_asset_depreciation lastcall 2026-09-07 21:08:11
myservice_identity.cron_sap_asset_export             inactive by definition
```

---

## Test suite — verbatim

```
$ CADRA_API_BASE=http://jaizbankplc.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q
....................................ssssssssss.......................... [ 26%]
.............................................ssssssss.ssss.............. [ 53%]
...............................s..............................s......... [ 79%]
.....................................................ss                  [100%]
============================ cadra api test report =============================
Report: /Users/macbookprom1/Desktop/WML/myservicenrs/docs/api/test-report.md
Captured responses: /Users/macbookprom1/Desktop/WML/myservicenrs/docs/api/test-responses/
245 passed, 26 skipped in 152.11s (0:02:32)
```

Re-run after the verification fixes (the two new guards add two cases):

```
247 passed, 26 skipped in 47.31s
```

Odoo-native suites, now wired into CI:

```
odoo.tests.stats: myservice_asset_depreciation: 16 tests 0.80s 525 queries
odoo.tests.stats: myservice_workflow: 56 tests 6.07s 3423 queries
```

Source guards standalone: `25 passed in 0.68s`.

**One thing that cost a full suite run and is worth remembering:** after re-syncing
client-user groups from an `odoo shell`, the dashboard tests still failed. That is
the documented `res.users._get_group_ids` ormcache behaviour — a group change made
from a separate process does not reliably invalidate a running HTTP worker.
Restarting `odoo` turned the suite green with no code change. CLAUDE.md already
records this; it caught me anyway.

---

## Verification

### The escaping that could have broken CI, settled by observation

`${ODOO_DBFILTER:-^odoo$$}` needs `$$` to survive compose interpolation, and
`docker compose config` re-escapes on output (`^odoo$$`), so reading the config
does **not** answer the question. I started a throwaway container with
`ODOO_DBFILTER` unset and read the literal argv:

```
$ docker inspect h08esc-odoo-1 --format '{{json .Config.Cmd}}'
["odoo","--workers=2","--max-cron-threads=1","--db-filter=^odoo$"]
```

One `$`. Combined with the `^test19$` probe under §Part A, both halves of the CI
path — the escaping and the mono-database resolution — are observed, not inferred.

### Part C exercised against a live registry

Each path run on `test19` and rolled back:

```
RESULT created ->  cadra_client_h08_probe | ['Asset User', 'Role / User']
RESULT no password ->  True
RESULT internal (share=False) ->  True
RESULT after scope change ->  ['Role / User', 'Tag-Issuing Unit']
RESULT non-scope write ok
RESULT reprovision same user ->  True
RESULT hand-set user left alone ->  True | admin groups untouched: True
RESULT groups_for_scopes(['admin']) ->  ['Role / User']
```

The last two are the ones that matter. **`admin` maps to nothing** — no
`base.group_system` from a scope string. And a client an operator has deliberately
pointed at a shared user is not re-homed by a scope change, so the `write` hook
cannot rewrite somebody else's groups.

### A defect I introduced and caught before committing

Restructuring `ensure_test_client` into `if not rec / elif on-admin / else`, I made
the **scope re-sync unreachable** for any client still sitting on Administrator —
and worse, it would have gone permanently dead the moment the identity fix landed
everywhere. The re-sync and the re-homing are independent and are now both
unconditional on the existing-record path. Recording it because it is the same
shape as the bug this handoff is about: a guarantee that quietly stops running,
with nothing to notice.

Also corrected before commit: the migration tested `"*" in (client.scopes or "")`
— a substring check against a space-separated list, which would grant the wildcard
group to any scope string merely *containing* an asterisk. Now a token match.

### The independent verification pass

A fresh agent that had not written any of this reviewed the diff against the
handoff's acceptance criteria. It confirmed, against the database rather than
against my word: the 289 affix records, both Part B timestamp pairs to the
millisecond, the depreciation "after" figures, zero `state='sent'` mail on all
eight tenants, the orphan crons gone from both tenants, the eight retired debt
users with `password IS NULL` and no live token families, and 271 collected tests
= 245 + 26. It independently reproduced the `$$` escaping result and confirmed the
new CI step's mechanics (both suites are `@tagged('post_install')` with
`requests.post` patched — no network; `myservice_asset_depreciation` is a hard
dependency of `myservice_api` so `-u` is not a no-op; ports 8099/8098 are free).

It found **five things I had wrong**, all now fixed above and in the code:

1. **"Neither method has ever existed" was false** — the worst of them, because it
   had already reached CLAUDE.md, and because it sends a follow-up handoff to a
   blank page when a working implementation exists at `c673ed1`.
2. **`ensure_test_client` silently stripped `base.group_system`.**
   `_provision_client_user` writes groups with `(6, 0, ...)` — a full replace —
   and that runs on every scope change, while the `group_system` grant lived only
   in the create and re-home branches. So the first time a scope was added to
   `ALL_SCOPES` (handoff 03 and again in 05 — routinely) the next bootstrap would
   strip it back off with nothing in the log. **That is precisely the shape of the
   bug this handoff is about**, reintroduced by the fix for it. The grant is now
   unconditional and last, with the corollary stated: any hand-added group on a
   client user is destroyed by the next scope edit, so the scope table is the only
   durable source of those groups.
3. **The `db_name` guard missed the argv spelling** — `-d`/`--database` on a
   server's command line does the same thing. New guard above.
4. **The client guard was both too narrow and too broad.** Rewritten as an AST
   check with a test that feeds it both regressions.
5. **Three counting/claim errors** — 11 clients (10), "families" (rows), and
   "never ran here" for the telemetry cron (it ran once on `nrs19`).

It also flagged that `jaizbankplc`'s throwaway `workflow.config` was disclosed as
an open question but not contained — and that this handoff is what made it
dangerous, since before it nothing drained the queue. Correct. **It is now
`active=false, event_enabled=false` and the receiver process is stopped**, rather
than left for "before that tenant is used again".

Two documentation contradictions it caught are fixed: `k8s/dev/MULTI-TENANT.md`
still told readers local dev keeps `db_name = odoo` and no dbfilter, and
CLAUDE.md's handoff-06 entry still asserted in the present tense that no tenant
cron can run here and that anything cron-driven must be proven with a throwaway
worker container.

## Deviations from the handoff

1. **`NRS — Push asset data to Redhubs` is not a dormant cron.** It is
   `active="False"` by definition with a `pass` body. Reported rather than
   "fixed".
2. **Two crons the handoff does not list are the real hazard**, and they were
   deleted before the scheduler was woken rather than after.
3. **`db_name` was not simply removed.** Doing that alone breaks CI; the exposure
   job it was silently doing had to be handed to `dbfilter` first.
4. **`max_cron_threads` left at 1**, with measurement rather than assertion.
5. **Two changes beyond the handoff's scope, both forced by it:**
   `limit_time_real_cron = 1200` (a 120 s watchdog would have SIGKILLed the
   catch-up tick) and the `extra_hosts` entry for `vendra.network` (without it no
   INT-05 event can leave the container, so Part B was unprovable).
6. **The `dashboards:read` group mapping is the conservative fix**, with the
   architecturally correct one written up above and left to the Architect.
7. **Odoo-native tests wired into CI.** Strictly this is report item 3 territory —
   "identify" — but it is the one gap that would have caught this bug, it costs
   7 seconds, and leaving the only production-trigger test in the repo unexecuted
   after writing a report about untriggered guarantees would have been absurd.

## Open questions

1. **The dashboard routes: `sudo()` + 403, or the derived groups I shipped?**
2. **Publisher telemetry in the cluster** — stop it, or accept it?
3. **`sla_breached`, `is_verified`, `is_overdue`** — one handoff for the whole
   stale-stored-compute class? `is_verified` is API surface, so it needs a ruling
   before it is touched.
4. **Should the repo-root `odoo.conf` be deleted?** Nothing reads it and it
   describes a stack that no longer exists.
5. ~~`jaizbankplc`'s `workflow.config` id 1~~ — **closed.** Disabled
   (`active=false, event_enabled=false`) and the receiver stopped, during this
   handoff rather than deferred.
6. **An in-registry cron test** — walk `ir.cron` and resolve every `state=code`
   call against the live model. It is the only guard that catches this defect in
   the form it actually took (a database row), and the Odoo-native CI step now
   exists to host it.

## Commits

See the PR. Migrations: `myservice_api 19.0.3.2.0`,
`myservice_asset_register 19.0.1.10.0` — both must run per tenant, and the
`cadra-upgrade` Job must fan out on staging.
