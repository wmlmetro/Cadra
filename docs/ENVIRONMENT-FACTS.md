# Environment facts — Cadra

**What this is:** things that are true of the machines this repo runs on, that cost somebody time to discover, and that live nowhere anybody would look before starting.

Three of these arrived inside handoff reports in one month. A report is read once, by me, on the day it lands; a fact about the environment is needed by whoever starts next, which is nearly always somebody else. **If you lose time to something that turns out to be a property of the environment rather than of the code, it belongs here** — put it at the top of your report under this heading and it will be lifted, or add it directly.

Each entry says what is true, how it shows itself, and what it is not. The last part matters most: the cost of these is almost never the fault itself, it is the hour spent believing it was something else.

---

## The dev stack

### `cadra19` has a broken filestore and is unusable for anything browser-based

Asset-bundle attachments are missing, so the backend `500`s on `web_tour.interactive.min.js` and never styles. Any browser work — a screenshot proof, a dashboard probe, a login flow — must use another tenant. `jaizbankplc` is the usual choice and has real data volume.

**Not:** a code fault, and not something a migration fixes. Found in handoff 12 while proving a stylesheet relocation, at the cost of an afternoon.

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

### Any `HttpCase` needs `--workers=0`

Not in the documented command. Found in handoff 12.

---

## The test suites

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

### The external suite's 27 skips are expected

Admin-scoped tests the suite's own token cannot reach, plus pagination tests that skip loudly when a tenant fits inside the record cap. A run reporting 27 skips is a healthy run.

---

## The cluster

### One Odoo registry serves every tenant, so schema moves before code

Not a surprise so much as the rule everything else follows from, and it is in `docs/DEPLOYMENT.md` in full. Repeated here because it is the fact that makes a missed tenant an outage for all of them.

### An asset-bundle change does not take effect on restart

It needs the module upgrade. Handoff 11 established this the expensive way — a change that was live in the repo, absent in the browser, and looked like a caching problem.
