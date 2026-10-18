# Environment facts — Cadra

**What this is:** things that are true of the machines this repo runs on, that cost somebody time to discover, and that live nowhere anybody would look before starting.

Three of these arrived inside handoff reports in one month. A report is read once, by me, on the day it lands; a fact about the environment is needed by whoever starts next, which is nearly always somebody else. **If you lose time to something that turns out to be a property of the environment rather than of the code, it belongs here** — put it at the top of your report under this heading and it will be lifted, or add it directly.

Each entry says what is true, how it shows itself, and what it is not. The last part matters most: the cost of these is almost never the fault itself, it is the hour spent believing it was something else.

---

## The dev stack

### `cadra19` has a broken filestore and is unusable for anything browser-based

Asset-bundle attachments are missing, so the backend `500`s on `web_tour.interactive.min.js` and never styles. Any browser work — a screenshot proof, a dashboard probe, a login flow — must use another tenant. `jaizbankplc` is the usual choice and has real data volume.

**Not:** a code fault, and not something a migration fixes. Found in handoff 12 while proving a stylesheet relocation, at the cost of an afternoon.

### `myservice_nrs_base` ships a legacy shim, so `odoo.define` modules requiring `web.AbstractAction` DO load on 19

`myservice_nrs_base/static/src/js/legacy_compat.js` re-provides `web.core`,
`web.rpc`, `web.ajax`, `web.session` and `web.AbstractAction` using the
loader's native three-argument `odoo.define(name, [deps], factory)` form,
backed by real Odoo 19 services. `web.core.action_registry.add` writes into
the genuine OWL `registry.category("actions")`, so a tag registered by legacy
code resolves for an `ir.actions.client`; `AbstractAction` is an OWL
`Component` subclass whose template is
`<div t-ref="root" class="o_client_action o_nrs_legacy_action"/>`. It is
bundled at `myservice_nrs_base/__manifest__.py:30` into `web.assets_backend`,
with jQuery `prepend`ed at line 28.

**How it shows:** measured in a real browser on `jaizbankplc` by
`e2e/probes/odoo-client-actions.mjs` (`node e2e/probes/odoo-client-actions.mjs`):

| tag | registered | mounted | legacy DOM bytes | console errors |
|---|---|---|---|---|
| `myservice_dashboard` | true | true | 20,143 | 0 |
| `barcode_station` | true | true | 47,226 | 0 |
| `nrs_asset_dashboard` | true | true | 24,065 | 0 |
| `myservice_fm_dashboard` | true | true | 48,262 | 0 |
| `bus_dashboard` | true | false | 6,552 | 0 (Access Error dialog) |
| `myservice_fleet_dashboard` | false | false | 0 | 0 |
| `nrs_security_command_center` | false | false | 0 | 0 |
| `nrs_case_management` | false | false | 0 | 0 |
| `myservice_security_dashboard` | false | false | 0 | 0 |

**The measurement trap, which is the more useful half of this entry:**
measuring `.o_action_manager` is **not** a mount test. An unresolvable tag
still renders about **9,716 bytes** of Odoo's own error surface into that
element, which reads as a successful mount and is not one — the first version
of the probe reported all four retired tags as mounted. The sound
discriminator is the shim's own root class, `.o_nrs_legacy_action`, which is
present only when a legacy client action really mounted. And `odoo.loader` is
populated as the backend bundle executes, i.e. **after** the navigation
resolves, so evaluating the registry immediately after login reads
`undefined`.

**Not:** true of Odoo core, and that is the whole trap. The premise *"an
`odoo.define` module requiring `web.AbstractAction` cannot load on 19"* is
correct about stock Odoo and false about this codebase, so a search of the
Odoo source proves the wrong thing with complete conviction. It has now
produced a wrong conclusion in **both** directions across five handoffs —
handoff 10 R46 and handoff 11, which nearly retired a working screen, and
handoff 15 §6.1, which declared a live tab dead. **Not a substitute for the
probe either:** a tag being registered says the shim worked, not that a route
reaches the screen — `myservice_fleet_dashboard` is retired by an empty asset
bundle, not by the shim failing. Report 11 measured this correctly in a
browser and never committed the probe, which is why report 15 had to reason
from the source tree and got it wrong. The probe is committed now; run it
rather than reading either source tree. Handoff 16.

### ProxyFix does not run here, so `remote_addr` is the nginx container

Odoo 19 applies ProxyFix only when the request carries `X-Forwarded-Host` (`odoo/http.py`, `Application.__call__`: `if config['proxy_mode'] and environ.get("HTTP_X_FORWARDED_HOST")`). The dev nginx sends `X-Forwarded-For` and `X-Forwarded-Proto` and **not** that one, so `proxy_mode = True` in all four configs has no effect.

**How it shows:** `last_used_ip` reads `172.20.0.4` on every API client row on every local tenant, and has since the field was added. Anything reasoning about caller addresses locally is reasoning about a container.

**Not:** true of the cluster. ingress-nginx does set `X-Forwarded-Host`, so ProxyFix runs there. **What the cluster's own right-most forwarded entry resolves to is still unverified** — with DigitalOcean's load balancer at the default `externalTrafficPolicy: Cluster` and no proxy protocol, it will be a node address rather than a caller. The first failed login from staging settles it with one grep. Handoff 13 §3.

**Deliberately not fixed:** making the dev nginx send the header would switch on ProxyFix's host and protocol rewriting for every local request, which changes how the dev stack routes tenants. That is its own change, not a line in a counting handoff.

### Postgres crash-restarts under concurrent load, and recovers

An `odoo shell` overlapping a pytest run has produced *"all server processes terminated; reinitializing"* → *"automatic recovery in progress"* → *"ready to accept connections"*. No data loss observed: all ten databases present, row counts matching the pre-work baseline, `RestartCount=0` on the container.

**Not new, and not caused by whatever you were running.** The same line appears repeatedly in this log going back to August. Budget twenty minutes and one discarded test run; do not go looking for what you broke.

**The cause, measured in handoff 14: it is the Docker VM's OOM killer, and the trigger is TWO Odoo registry loads at once.** The `db` log carries `statistics collector process … was terminated by signal 9: Killed` immediately before every *"all server processes terminated"*, and the container itself reports `OOMKilled=false` with no memory limit — so the kill comes from the VM's kernel, not from Docker's per-container accounting.

**The VM is not the tight resource; the Mac is, and it is far past tight.** Containers were using ~1.5 GiB of the VM's 7.7 GiB when this fired. On the host at the same moment:

| | |
|---|---|
| free pages | ~60 MB |
| swap used | 21.1 GB of 22.5 GB |
| pages in the compressor | 3.5 million |

The host also runs the **Frappe/Vendra stack — eleven containers, ~1.2 GiB** — alongside this one, plus a browser and several editor sessions. Under that pressure the guest's pages are swapped out from underneath it and its kernel starts killing. A second Odoo registry load is what tips it, but the machine is already over the line before anything Odoo does.

**What this means in practice: never run two `--stop-after-init` upgrades or test runs at the same time.** Handoff 14 lost roughly ninety minutes to six consecutive crashes, every one of them while a subagent's `-u myservice_api` run overlapped the main session's `-u myservice_asset_register` run **against a different tenant**. Different databases do not help — the memory is the shared resource, not the registry lock.

**What worked, and is the recipe for any multi-tenant fan-out here:**

```bash
docker compose -f docker-compose.yml -f docker-compose.19.yml stop odoo
# then, one tenant at a time, in a throwaway container:
docker compose -f docker-compose.yml -f docker-compose.19.yml run --rm --no-deps -T odoo \
  odoo -c /etc/odoo/odoo.conf -d <db> -u <module> --stop-after-init \
  --workers=0 --max-cron-threads=0 --http-port=8199 --gevent-port=8198
docker compose -f docker-compose.yml -f docker-compose.19.yml start odoo   # when done
```

Stopping the long-running server first is what makes the difference: it is three Odoo processes on its own, and `run --rm` then leaves exactly one registry in memory.

**It reduces the crashes; it does not end them.** `nrs19` still crash-restarted twice on the 77-module registry load with the server stopped and nothing else of ours running — because 21 of the host's 22.5 GB of swap were already in use before any of this started. **Build a retry into any fan-out** (three attempts, waiting for the database to come back between them) and it gets through. Retry a *crash*; do not retry a code fault, or you get the same error twice and the second copy buries the first.

**And a false green to watch for.** A run whose database died before the test phase reports `0 failed, 0 error(s) of 0 tests` **and exits 0**. It is indistinguishable from a pass unless you grep the output for `of 0 tests` and for `CRITICAL`. One agent's retry wrapper here declared success on a log whose entire content was `service "odoo" is not running`.

### The `.env.example` database is `odoo`, and a 19 worker cannot load it

`odoo` on this machine is a 15-era leftover. A 19 worker refuses it with `ERROR: operator does not exist: character varying ->> unknown`, then `Failed to load registry` — an error that names nothing relevant to the actual cause.

CI is unaffected because it creates the database fresh. **The command `CLAUDE.md` documents cannot be run verbatim on a developer machine**; use `test19`, which also carries the post-install test set (133 tests against CI's 72).

### `ir.config_parameter.get_param` can answer with a value the database no longer holds

It is `@ormcache`d **per worker**, and `config/odoo.19.conf` sets `workers = 2`. The invalidation signal does not reliably reach a worker sitting between requests, so two workers can disagree about the same parameter at the same instant, and both can disagree with the row.

Measured while proving handoff 25's database-class guard. The parameter row was deleted; the route — hitting one worker — kept answering `"test"`, and the suite ran **24 writing tests to a green pass against a database carrying no mark at all**. A moment later the same route on the other worker answered `"client"`, a value that had been set and then removed.

**So anything a safety decision turns on must read the row, not the cache:**

```python
env.cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", (key,))
```

`get_param` remains right for everything else — a brand colour served one request stale costs nothing. The rule is about what the answer is *used for*, not about the parameter.

### Any `HttpCase` needs `--workers=0`

Not in the documented command. Found in handoff 12.

---

### A plain `npm run build` silently breaks the locally served app

**Build the front end for local serving with `BASE_PATH=/app/ npm run build`, never a bare `npm run build`.**

`Frontend/artifacts/nrs-asset-register/.env.local` sets `BASE_PATH=/`, so a bare build emits asset URLs under `/assets/…`. The dev proxy bind-mounts that same `dist/public` (`docker-compose.19.yml`) and `config/nginx.dev.conf` serves it under **`/app/`** — where `/assets/…` is not the bundle at all: it falls through to Odoo and 404s. `http://<tenant>.localhost:8069/app/` then loads a blank page, with nothing in any log that mentions a base path. `dist/` is gitignored, so it never shows in a diff, and the person it breaks is whoever opens the app next.

An environment variable beats `.env.local` in Vite's `loadEnv`, which is why the prefix works. Check the result, not the exit code:

```
grep -o 'src="[^"]*"' dist/public/index.html | head -1     # must begin /app/assets/
```

`npm run typecheck` writes nothing and is always safe. `Dockerfile` sets `BASE_PATH=/app/` itself, so an image build was never affected — only a local one. Measured in handoff 27, when a verification build did exactly this; it is also the reason to give any subagent the full command rather than "run the build".

**And look at the screen.** Typecheck and build prove the bundle compiles. Two defects in two consecutive handoffs — an asset changing hands before it was registered (27), and a dialog whose wording had gone stale (28) — passed every test and were found by driving the real page. `e2e/` has Playwright installed: `E2E_ORIGIN=http://test19.localhost:8069 npx playwright test …`. **Its default origin is `jaizbankplc`, a client-marked database, and the e2e suite is NOT covered by the database-class guard** — name `test19` explicitly.

### A browser with no camera can be shown a label, and the decode is the bundled engine's

Handoff 40 put the station's camera scanner into the confirm dialog, and the Mac it was built on has no camera a test can point at a label. The facts that make the proof real, each learned by a probe:

1. **`http://<tenant>.localhost:8069` is a secure context** (`window.isSecureContext === true`), so `getUserMedia` works over plain http locally. **Since handoff 54 the decoder is bundled** (`src/lib/scanEngine.ts`, zxing-wasm) — the platform's `BarcodeDetector` is not used at all, so the proof no longer depends on macOS Chromium's Vision-framework shim, which was the one macOS-only leg of handoff 40's recipe. (Historical, kept because it explains reports 40–52: Playwright's Chromium on macOS HAS `BarcodeDetector`; Linux's does not, and until 54 that made the camera specs macOS-only. The fake device itself works anywhere.)
2. **Chromium's fake capture device plays a file**: launch with `--use-fake-device-for-media-stream --use-fake-ui-for-media-stream --use-file-for-fake-video-capture=<path>.mjpeg`. An `.mjpeg` is a run of JPEG frames, so **one JPEG written by `page.screenshot({ type: "jpeg" })` is a one-frame loop** — no ffmpeg, no raster library (the repo has neither; `tests/.venv` has no Pillow). **The file is read when a stream OPENS, not at launch**: it may not exist at launch, and rewriting it between a Stop and a Start puts a different label in front of the lens. **Each spec file that uses it needs its OWN file path** — spec files run in parallel workers, and two specs sharing one frame file show each other's labels. `e2e/tests/40-…` renders the label Cadra would PRINT for the tag (`code128Svg`, the printer's own encoder, imported from the app's source); `e2e/tests/54-…` adds every other symbology through `zxing-wasm`'s writer and the real Odoo renderer via `/report/barcode`. Probed 2026-10-01 with `e2e/probes/fake-camera-decode.mts` (kept; run it from `e2e/` with `node`): `NRS-ACS-733` decoded in 228 ms on the first frame.
3. **With a label in front of the lens the scanner has stopped itself before Playwright looks.** `BarcodeScanner` calls `stop()` and unmounts on detection, so a helper that clicks *Start camera* and then waits for the *Stop* button flakes exactly when the decode succeeds (one run in three on the first attempt). Wait for *Stop* only with a blank frame in front of the camera; with a label, wait for the field to fill. Since handoff 54 a **1D** value needs two agreeing decodes (~100 ms apart on the looped frame) and a **2D** value one; the one-frame loop satisfies both, but the stop-button race is unchanged.

A stubbed decoder would have proved the dialog's wiring and nothing about the decode; the fake device proves both and costs one launch flag per spec file (`test.use({ launchOptions })`).

### Three move specs in `e2e/tests/06-asset-actions.spec.ts` skip on `test19`

They need two locations of type *building* (`api.twoBuildings()`), and `test19` has none, so *"move persists server-side"*, *"move via UI"* and *"move to the same location is rejected"* report `skipped`, not `passed`. That is a fact about the tenant, the same kind as the pytest skips below. The move path was verified by hand in handoff 28 for that reason; a test tenant with two buildings would let those specs run.

## The test suites

### The suites refuse any database not marked as a test database — and this is what they used to do instead

**CLOSED by handoff 25.** Both suites now read `cadra.database_class` from the target database and refuse unless it is `test`; absent refuses too. There is no bypass flag. Run against `test19`:

```
CADRA_API_BASE=http://test19.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q
```

`jaizbankplc`, `nrs`, `lasg` and `gtb` are marked `client` and refuse. `cadra19`, `nrs19` and `gtb19` are unmarked and therefore also refuse. To mark a database of your own, run the command the refusal prints.

**What it did before, because the measurement is the reason the guard exists.** `CADRA_API_BASE` was the only thing deciding which database the pytest suite wrote to, and there was no guard of any kind — no allowlist, no refusal, no confirmation, no dry run. The suite read that one variable and wrote wherever it pointed.

In practice it points at `jaizbankplc`, because that is the only tenant carrying a full `CLIENT_ID`/`CLIENT_SECRET` pair (`docs/api/.creds.jaizbankplc`); `.creds.nrs19` holds two scoped clients and fails the fixture's own check. `jaizbankplc` is a replica of a live client's register.

**It also has no teardown, by documented policy** (`tests/README.md`: *"leave them in the dev DB"*) — and it could not have one if it wanted: the API publishes exactly one `DELETE` route, for asset categories. There is none for assets, locations, requests, custody links or disposals.

Measured on 2026-09-15, after roughly 154 sessions accumulating since 2026-08-26:

| | |
|---|---|
| assets named `pytest-*` | **3,584 of 4,056 (88%)** |
| chain-of-custody rows on fixture assets | **413 of 569 (73%)** |
| entries in the **public homepage** location dropdown | **354 of 420 (84%)** |
| fabricated approved disposals in the auditor-facing report | **6** |

**What it is not.** It is not a production incident: every captured response in `docs/api/test-responses/` names `jaizbankplc.localhost:8069`, so nothing has ever reached the production host, and no *real* asset carries a fabricated approval or custody link. CI is unaffected — it creates its own throwaway `odoo` database on a runner that is discarded.

**The residue is still there.** `scripts/remove_test_residue.py` is dry-run by default and measured 3,779 of 3,894 fixture assets removable and 115 refused — 99 carrying chain-of-custody rows (`ondelete='restrict'`, so the asset cannot be released at all), 6 carrying approved disposals, 10 pointed at by a service request. 96 fixture LOCATIONS are refused by the database itself on a foreign key from the transfer log. Both it and `scripts/mark_test_fixtures.py` are owner-run — the Builder's permission layer refuses a committing write to a client-derived tenant. **Neither had been run as of handoff 25**, verified rather than assumed.

**The pattern that worked, and why.** The chain of custody already handles this correctly: `myservice.api.client.is_test_credential` drives `nrs.asset.custody.source = 'test'`, so 330 of its rows self-label and a reader can tell. Nothing equivalent exists for assets or disposals. `scripts/mark_test_fixtures.py` marks the artefacts that are already there.

**Disposal approval cannot be undone.** There is no `action_unapprove_disposal`, a second approval is a published 409, and the approver fields are read-only over the API. It is correctable only by a human on the Odoo form, under tracking — by design.

### A `TransactionCase` that writes a tracked field finds no tracking row

Odoo 19 defers tracking to `cr.precommit` — `addons/mail/models/mail_thread.py:534`
does `self.env.cr.precommit.add(self._track_finalize)` and stashes the initial
values, so `mail.tracking.value` rows are created when the cursor is about to
commit and **not** on flush. A `TransactionCase` never commits.

**How it shows:** you write a tracked field, `flush_all()`, then
`search_count` on `mail.tracking.value` and get **zero** — for a field you can
see carries `tracking=True` and which has thousands of rows in the live
database. The idiom that works is Odoo's own:

```python
self.env.flush_all()
self.env.cr.precommit.run()
self.env.flush_all()
```

**Not** a sign that tracking is broken, and **not** harmless to work around by
weakening the assertion. Two tests in handoff 16 would have passed for the
wrong reason without it: a date-fallback test that reads back the `state`
transition it just made, and a fingerprint that was supposed to prove a report
writes nothing — the fingerprint would have missed a tracked write entirely,
which is the one thing it exists to catch. Same family as the two lessons
below it: `create_date` is written by Postgres so `freeze_time` cannot move it,
and a stored compute left pending is evaluated on the later flush. In all three
the test is green and has tested nothing. Handoff 16.

### In-registry runs log `cannot execute INSERT in a read-only transaction` and pass

Dozens of lines, and they are noise. Odoo 19 dispatches on a readonly cursor and retries on a read/write one. `TestPaginationCap` produces 21 of them on its own and reports `0 failed`.

**Not:** a symptom of anything. Do not chase it.

### A read/write route gets a READ-ONLY cursor in test mode, and a controller-level `except Exception` defeats the retry

The entry above is right that the `cannot execute INSERT in a read-only
transaction` lines are noise — **for a route whose exception reaches Odoo.**
Odoo dispatches on a read-only cursor and `http.py` catches
`ReadOnlySqlTransaction` and re-dispatches on a read/write one. That catch is
ABOVE the controller. A route wrapped in a decorator that ends
`except Exception: return a 500` never lets the exception out, so the retry
never happens and the route answers `500` instead of succeeding.

**How it shows:** an `HttpCase` `POST` fails with the envelope's own
`internal_error` while an unwrapped route — `/auth/token`, which is not
wrapped by `cadra_route` — hits the same condition in the same run, on the
same cursor, and retries into a `200`. The unwrapped route is the one that
works, which is the wrong way round and makes it look like a fault in the
wrapped route's own logic.

**Not visible from the live server**, because a route that does not declare
`readonly` is served a read/write cursor there — so the external pytest suite
passes and only an `HttpCase` sees it. `service/model.retrying` sits in the
same position for `OperationalError` and `ConcurrencyError`, and that one
DOES bite in production: it is how two callers writing the same row both
succeed. Handoff 15 added a clause re-raising all three, guarded by
`tests/test_source_guards.py::test_the_envelope_lets_odoos_own_retries_through`.

### A suite that fails only between midnight and 01:00 in Lagos is telling you something

This machine's clock is Lagos (+01:00); Odoo's is UTC. For the first hour of every Lagos day the two disagree about the DATE, and any code that says "today" on one side and compares it with "today" on the other is wrong for that hour and right for the other twenty-three. **CI runs in UTC on both sides and can never see it.**

Handoff 29 hit it at 00:50: nine tests in `tests/test_audit_reports.py` failed with *"`as_of` cannot be in the future"*. It was NOT a flaky test — the route was wrong, refusing a Lagos user today's register because UTC had not got there yet (fixed: `asset_snapshot.snapshot_today()`). **If a run goes red just after midnight, read the failure before re-running it**, and grep for `Date.today()` / `date.today()` next to anything the specification defines as a Lagos day. The front end has the mirror-image defect in one known place: `condemnAsset` dates a disposal from the browser's UTC clock (`GO-LIVE.md` §13.5).

### The external suite's skips are expected — check the CATEGORIES, not the count

Admin-scoped tests the suite's own token cannot reach, plus pagination tests that skip loudly when a tenant fits inside the record cap.

This said "a run reporting 27 skips is a healthy run", and a bare number is the wrong thing to check. The total moves with the **tenant**, not with the code: how many scopes that tenant's `test_client` holds, whether Turnstile is configured on it, whether any of its assets carries a SAP asset number, whether it has an active `workflow.config`. A Builder who treats the number as a constant either chases a phantom regression or, worse, stops reading the list.

**The default tenant changed in handoff 25**, and with it the skip list: the suite now runs against `test19`, whose credential holds `admin`, so the admin-scope category is **empty** and those tests actually execute. Measured on `test19`, 2026-09-15, **9 skips**: 2 Turnstile-not-configured, 4 partition-data-absent (`is_verified`, `is_staff_bus`, `has_sap_code`, `closed`), 1 no active `workflow.config`, 1 no asset carrying a SAP asset number, 1 documented `is_tagged`. A run reporting ~28 skips is a run against the old tenant.

**Re-measured on `test19`, 2026-09-20, 8 skips — and the difference is an instance of the rule, not an exception to it.** The `is_verified` partition skip went: handoff 27's Playwright spec clicks **Verify** on a `test19` asset, so `?is_verified=true` matches a row for the first time and the test runs. The same run was 9 skips an hour earlier, before that spec had ever been pointed at this tenant. Remaining partition-data-absent skips: `is_staff_bus`, `has_sap_code`, `closed`. Anything that writes to the test tenant — the e2e suite included — can move this number without touching `tests/`.

The earlier measurement, kept because it is the one that shows the total is a tenant fact — `jaizbankplc`, 2026-09-10, **28 skips**, every one named:

| Count | Reason |
|---|---|
| 24 | the token lacks the `admin` scope (branding, depreciation settings, `/meta`) |
| 2 | Turnstile is not configured on this deployment |
| 1 | no asset on this tenant carries a SAP asset number yet |
| 1 | this tenant has no active `workflow.config`, so the v1 callback refuses 503 |

`pytest -rs` prints the reasons. A skip whose reason is not in that table is the thing to look at.

### `test19` sends INT-05 to the local Vendra bench, with `nrs19`'s bearer key — on local test tenants only

Since handoff 60 `test19` has an asset-event target (`workflow.config`,
purpose `asset_events`) pointing at the local Vendra bench
(`http://vendra.network:8080`), carrying the SAME bearer key as `nrs19`'s
target, copied from it. Ruled acceptable by the Architect (handoff 61,
ruling 7 on report 60) **on local test tenants only**: the bench is this
machine's, the key opens nothing but that bench, and `test19` is a test
database. Every affix the suites make on `test19` is therefore queued to the
bench and recorded there as an unmatched delivery — noise in Vendra's
message log, harmless.

**Do not copy this pattern to a cluster tenant.** A cluster tenant's
INT-05 target and its key are that tenant's own, provisioned for the
Vendra it actually pairs with; a key copied from another tenant makes two
Cadras indistinguishable to the receiver and sends one tenant's events
under another's name.

---

## The cluster

### One Odoo registry serves every tenant, so schema moves before code

Not a surprise so much as the rule everything else follows from, and `docs/DEPLOYMENT.md` now carries it in full — it did not when this line first claimed it did. Repeated here because it is the fact that makes a missed tenant an outage for all of them.

Note what the runbook adds: on a **client's own server** this rule collapses to an ordinary migration. There is one database there, so "schema before code" is the usual ordering and the blast radius of a missed tenant is zero. The fan-out is a development obligation, not a property of the product.

### An asset-bundle change does not take effect on restart

It needs the module upgrade. Handoff 11 established this the expensive way — a change that was live in the repo, absent in the browser, and looked like a caching problem.

## `upgrade-19`'s `image` input is used VERBATIM — a bare tag is a 22-minute outage

Handoff 35, 2026-09-22. The workflow's `image` field is only defaulted when
it is **blank**:

```yaml
IMAGE="${{ inputs.image }}"
[ -z "$IMAGE" ] && IMAGE="registry.digitalocean.com/${{ vars.DO_REGISTRY_NAME }}/cadra-odoo-19:dev-latest"
```

So a value you supply is passed to Kubernetes exactly as typed. Passing
`cadra-odoo-19:dev-b280bc4` — the tag as `deploy-dev` prints it — sends the
pod looking on Docker Hub. **The right form is fully qualified:**

```
registry.digitalocean.com/vendra-registry/cadra-odoo-19:dev-<sha>
```

**Why this is expensive rather than merely wrong.** `scale_down=true` takes
every tenant to 0 replicas BEFORE the first Job runs. The pod then sits in
`image can't be pulled`, and the per-tenant poll is `seq 1 40` at 30s — so
the step waits the full **20 minutes** for a container that can never start,
with Cadra down the whole time, and then fails on the first tenant. The guard
behaves correctly at every step (no tenant upgraded, replicas restored, image
rolled back) and the outage is total anyway.

**The failure mode to recognise:** the run passes `Scale odoo-19 down`, then
sits in `Run cadra-upgrade-19 Job for every tenant` far longer than the ~6
minutes five tenants take. If it is past ~8 minutes on the FIRST tenant,
it is not slow — check for `image can't be pulled` before waiting it out.

**The remedy that costs nothing:** leave `image` BLANK unless you need a
specific build. Blank resolves to `dev-latest`, which is whatever `deploy-dev`
last pushed — correct whenever you are deploying the merge you just made.

### `docker compose up -d --force-recreate <service>` recreates its DEPENDENCIES too — and drops `ODOO_DBFILTER` unless it is exported

Found in handoff 43. `… up -d --force-recreate proxy`, run without
`ODOO_DBFILTER='^%d$'` in the environment, recreated the `odoo` container as
well (the proxy depends on it and its config hash had changed) with the
committed default `--db-filter=^odoo$`. Every tenant host then answered
*"No database is selected"* for `/api/v1/*` and `/web/login` redirected to
itself, while `exec … odoo -d test19 -u …` kept working because it names the
database. `docker inspect myservicenrs-odoo-1 --format '{{.Config.Cmd}}'`
shows the filter the container actually runs with. Any `up` or recreate of
ANY service goes with the export, every time — the rule in `CLAUDE.md` is not
only for bring-up.

### The dev proxy passed `Host $host`, so every tenant's `web.base.url` lost its port

`config/nginx.dev.conf` forwarded `proxy_set_header Host $host`, which drops
the port; Odoo rewrites `web.base.url` from the request on every
system-administrator login, so all 8 local tenants carried
`http://<db>.localhost` — and any absolute link Odoo built from it (the
sign-up link in an invitation, a reset link) pointed at port 80, where
nothing listens. Fixed in handoff 43 to `$http_host` (and `X-Forwarded-Host` is now set
explicitly, so a client cannot supply its own); the invitation path
no longer reads `web.base.url` inside an authenticated request anyway
(`myservice_api/models/invitation.py`), but anything else that does will
still be wrong on a tenant whose last administrator login predates the fix.

### Receiving mail locally: Mailpit on `host.docker.internal:1025`

No local tenant has an outgoing mail server, so anything that sends can only
be proved queued — unless you give it a catcher. Handoff 43 used Mailpit:

```
docker run -d --name cadra-mailpit -p 8025:8025 -p 1025:1025 axllent/mailpit
```

then an `ir.mail_server` row on the TEST tenant (`smtp_host =
host.docker.internal`, `smtp_port = 1025`, `smtp_encryption = none`,
`smtp_authentication = login` — `none` is not a valid value on 19 — no
user). Inbox UI at `http://localhost:8025`, JSON at
`/api/v1/messages` and `/api/v1/message/<id>` (HTML and Text parts
separately). The sender ALSO needs a From: a tenant whose company has no
email, sending as an API credential (no email either), fails with Odoo's
*"You must either provide a sender address explicitly or configure using the
combination of `mail.catchall.domain` and `mail.default.from` ICPs"* — the
letters now fall back to the recipient's own address, as core's reset path
always did. `test19`'s company was given `facilities@nrs.gov.ng` for the
drive, and keeps it; the Mailpit `ir.mail_server` row stays too, so the
"mail works" branches of the HTTP and browser suites depend on the
container being up.

### On Odoo 19 `Savepoint.close()` ROLLS BACK by default

`odoo/sql_db.py:118`: `def close(self, *, rollback: bool = True)`. So
`with contextlib.closing(cr.savepoint()):` — the pattern core's own
`auth_signup._action_reset_password` uses around the send — undoes
everything inside it on exit. Core gets away with it because the row it
discards is an `auto_delete` mail that would have been deleted anyway, but
in a test the `MockEmail` gateway then holds a `mail.mail` id that no
longer exists (`MissingError` on the first read). Use the context manager
form, `with cr.savepoint():`, which releases on success and rolls back on
an exception.

### In test mode a write route runs twice, and the mail mock sees both

A corollary of *"A read/write route gets a READ-ONLY cursor in test mode"*
above: the first attempt creates a `mail.mail` the rollback removes, the
retry creates the one that stays, and `MockEmail._new_mails` holds both
ids. Read it through `.exists()`.

### A tenant's login page goes blank: an asset bundle's file is gone from the filestore (handoff 45)

**Symptom.** `/web/login` renders the website frame with an empty body; the
login form is in the HTML (`curl … | grep oe_login_form` finds it) but carries
`d-none`, because Odoo 19 hides it until a script widget (`web.user_switch`)
mounts — and the script bundle answers **500**:
`FileNotFoundError: … /filestore/<db>/xx/<sha>` in `ir_attachment._to_http_stream`.
Seen on `test19` on 2026-10-03 after several in-registry runs, each of which
logs *"filestore gc N checked, N removed"*; 1 of 67 bundle files was missing.

**Not:** the back-office door of handoff 45 (`/web/assets/*` is
`auth='public'` and never reaches it), nor a code fault.

**Repair** — bundles are generated, so drop the records and Odoo rebuilds them
on the next request:

```
docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
  odoo shell -c /etc/odoo/odoo.conf -d <db> --no-http --http-port=8099 --gevent-port=8098 <<'PY'
env['ir.attachment'].sudo().search([('url', '=like', '/web/assets/%')]).unlink(); env.cr.commit()
PY
```

A missing NON-generated file (a website logo) cannot be rebuilt this way.

### A full HTTP run fails by the hundred with `401 Invalid token`: the Mac slept (handoff 45)

The suite mints ONE bearer token per session (TTL 3600 s) and a full run on
`test19` takes 30–37 minutes. If the laptop sleeps mid-run, the token is stale
on wake and everything after fails `401`; pytest's own duration does not count
the sleep, so the summary looks like a short run. The server log says
`JWT rejected (Token expired)`; `pmset -g log | grep -E 'Sleep|Wake'` shows the
gap. Run long suites under `caffeinate -i -t 7200`.

### A fresh local browser is "signed in" before anybody types: `.env.local` (handoff 46)

`Frontend/artifacts/nrs-asset-register/.env.local` (gitignored, dated July)
sets `VITE_API_TOKEN`, and `lib/auth.ts` treats that as a session whenever
nothing is stored and nobody has signed out. Every `BASE_PATH=/app/ npm run
build` on this machine compiles it in. The token has expired, so the first
request answers 401, the app signs out and the sign-in page appears — at
whatever URL the app had reached by then. Handoff 46's first front-door
redirect judged that phantom session (no scopes) and sent every visitor to
`/no-access` before they signed in; the spec caught it by recording every
URL the browser passed through. If a sign-in lands somewhere odd only on
this machine, look here first. Removing the file is the owner's call.

### The HTTP suite slows down as `test19` fills with tags (fixed in handoff 46)

Until handoff 46 every `POST /api/v1/assets` walked every tag number already
issued under its prefix past 999 — one `COUNT` each, ~11 s per asset on
`test19` once it held 8,237 `NRS-GEN-*` labels — and the full suite crawled
(17 % in an hour, against 37 minutes for the whole run in handoff 45). If the
suite is suddenly slow, sample `pg_stat_activity` before blaming the load:
`docker exec myservicenrs-db-1 psql -U odoo -d postgres -Atc "select left(query,200) from pg_stat_activity where state='active'"`.

### Vendra answers `401` for any path its auth hook does not cover (handoff 62)

Cadra's INT-05 target sends `Authorization: Bearer …`. Frappe's
`validate_auth` (`frappe/auth.py:613-628`) answers ANY two-part
`Authorization` header that nothing authenticated with `401
frappe.exceptions.AuthenticationError`, before routing — whether or not the
method exists. `vendra_network.api.cadra.tag_event` works only because
Vendra's `auth_hooks` (`vendra_network/hooks.py`) include
`authenticate_cadra_callback`, which authenticates that ONE path. Cadra
classifies a 401 as final, so an event sent to a Vendra path the hook does
not cover is dead-lettered on its first attempt, and it reads like a bad
credential. Before rotating keys, check that Vendra's auth hook covers the
path. (Handoff 62 first wrote "a method it does not know"; the verification
pass corrected it from Vendra's own `hooks.py`.)

### A code change reaches every tenant before its schema does — even mid-handoff (handoff 63)

The `odoo` container bind-mounts the working tree and its prefork workers
are recycled on their own schedule; a recycled worker imports the Python ON
DISK. So a new stored field written into a module is live on every tenant
within minutes, with no restart, and every tenant not yet upgraded answers
`503 server_misconfigured` (`GET /api/v1/meta/readiness` lists the columns).
Handoff 63 broke `test19` this way for another session working on it, before
anything was committed. **Write a schema change and fan its upgrade out in
the same sitting**, and tell anyone else using the bench first.

### `docker compose … up -d` of ANY service can recreate `odoo` without the db filter (handoff 63)

`docker compose -f docker-compose.yml -f docker-compose.19.yml up -d
--force-recreate proxy` recreated `odoo` as well, and without
`ODOO_DBFILTER` exported it came back with `--db-filter=^odoo$`: every
`<tenant>.localhost` answered *"No database is selected"* (HTML 404).
`docker inspect myservicenrs-odoo-1 --format '{{json .Args}}'` shows the
filter in force. Export `ODOO_DBFILTER='^%d$'` on every `up`, not only the
first.

### An Odoo cron job is killed after 60 s of CPU here (handoff 63)

`config/odoo.19.conf` sets `limit_time_real_cron = 1200` but not
`limit_time_cpu`, whose default is **60 s**, and `WorkerCron` applies it per
unit of work (`odoo/service/server.py`, `RLIMIT_CPU`). The cluster sets 600.
A job longer than that is SIGXCPU-killed and retried forever. The SAP
mirror's import (a 52 s parse of the October file) runs in ticks of ≤ 25 s
of CPU for this reason. Odoo 19's own cron progress API does not help: its
`_run_job` calls a job that reports work remaining at least ten times in
the same process.

### After a bulk SQL load, `ANALYZE` the table (handoff 63)

Loading 211,699 rows into `nrs_sap_asset` by `execute_values` left the
planner's estimates stale until autovacuum caught up; with a join against
`nrs_asset` it also mis-estimated the assets carrying a SAP number (6,999
guessed, 2 real) and hashed the whole mirror on every matcher call (370 ms
instead of 1 ms). The import now runs `ANALYZE nrs_sap_asset` when it ends;
a hand-loaded table needs the same.

### The local proxy takes uploads up to 200 MB (handoff 63)

`config/nginx.dev.conf`'s `client_max_body_size` was 50m, which refused SAP's
75 MB export with nginx's own HTML 413 before Odoo saw it. It is 200m, the
cluster ingress's figure. It is a bind-mounted single file: recreate the
proxy after editing it (and see above about the db filter when you do).
