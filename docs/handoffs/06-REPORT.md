# Handoff 06 — REPORT: Tag transport (INT-05 outbound)

**Builder:** Claude Code (IDE) · **Branch:** `feat/tag-callback` → PR into `dev`
**Base:** `dev` @ `d5aee2a`

---

## Step 0 — state before the work

PR #48 was already merged (`e9ac0de`, merged 2026-09-06T11:16:46Z), so `dev`
was current. The per-tenant fan-out of `myservice_api` 19.0.3.1.0 ran across
all eight databases:

```
cadra19        19.0.3.1.0  wildcard_session_tokens=0
nrs19          19.0.3.1.0  wildcard_session_tokens=0
gtb19          19.0.3.1.0  wildcard_session_tokens=0
test19         19.0.3.1.0  wildcard_session_tokens=0
nrs            19.0.3.1.0  wildcard_session_tokens=0
lasg           19.0.3.1.0  wildcard_session_tokens=0
gtb            19.0.3.1.0  wildcard_session_tokens=0
jaizbankplc    19.0.3.1.0  wildcard_session_tokens=0
```

The migration logged no narrowing because these databases had already been
upgraded during handoff 05's own work; the end state is what matters and it is
verified directly rather than inferred. **Zero un-revoked `*` session tokens on
any tenant.** The `*` rows that remain are client-credential rows
(`client_id` set) on `cadra19`, which the migration deliberately leaves alone
because their scopes come from the client record.

---

## What was built

The gap named in report 01 and restated in the handoff: `workflow.dispatch.log`
recorded attempts and **nothing retried**. That is now a real outbox.

### B1 · The event

`asset.tag.affixed`, raised on the state *transition* inside
`nrs.asset.tag.label._mark_affixed` — extended in `myservice_workflow` rather
than edited in `myservice_asset_register`, so the capture module stays the
capture module and the transport module is the one that knows about both
requests and assets.

Payload per report 01 §Part C plus the `provenance` block. Two deliberate
departures from the literal proposal, both documented in
`docs/integrations/INT-05-tag-affixed-callback.md`:

- **`affixed_by` and `affixed_by_name` stay separate fields** rather than being
  collapsed into one `"Tag-Issuing Unit / J. Okafor"` string. They are
  different things — the API credential that submitted the confirmation, and
  the human who fitted the label, who is not a Cadra user — and the API
  serialiser already splits them. Collapsing them throws away which is which.
- **`tag.label_id` is included and named as not-an-asset-id**, for the reason
  handoff 05 established: the two id spaces collide numerically.

### B2 · Delivery that survives the other end being down

Built on `workflow.dispatch.log` as instructed. New fields: `event_type`,
`event_id`, `config_id`, `asset_id`, `tag_label_id`, `attempts`,
`max_attempts`, `next_attempt_at`, `last_attempt_at`, `http_status`,
`external_ref`, `delivery_history`. New statuses `acknowledged` and `dead`.

The status set is now **`pending` / `sent` / `acknowledged` / `error` / `dead`**
— deliberately the same five states as Vendra's `Vendra Integration Message`
(`Queued` / `Sent` / `Acknowledged` / `Failed` / `Dead`), three of which the
model already had. The architect asked for the two systems to be recognisably
the same at 2am; they now are, down to the backoff formula
`min(base × 2^(attempts-1), cap)` and the "all 4xx are terminal" rule.

**One row per event, not per attempt.** `event_id` has to be stable across
redeliveries, and "did this event land?" has to have exactly one answer a human
can look at. Each attempt appends a line to `delivery_history` instead.

### B3 · Configuration

`workflow.config` gained a `purpose` (`workspace` | `asset_events`), an event
endpoint, an `event_enabled` off-switch and three retry knobs, so a tenant
points INT-05 wherever it needs to without touching the approval integration.
`get_active_config()` defaults to `workspace`, so every existing caller is
unchanged. An unusable asset-event config is refused at save time by
`_check_asset_event_config` rather than discovered as a dead letter three hours
later.

### B4 · Not claiming more than the event proves

- `printed_at` is `null` when Cadra never observed a render, and the contract
  says so explicitly rather than letting an integrator infer a print.
- A **repeat** affix confirmation raises no second event — the event fires on
  the transition, and `_mark_affixed` already refuses to rewrite the original.
- A tenant with no configured target emits nothing and logs it at INFO.

---

## Deviations from the handoff

**1. The drain is scoped by `event_type`, not by status — the handoff's literal
instruction was a defect.**

The handoff says: *"an `ir.cron` draining `pending` and `error`"*. Taken
literally that is dangerous. `request.request._send_to_workflow` writes rows to
this same table with exactly those statuses — `pending` on create, `error` when
an approval dispatch fails. A drain scoped merely by status would have started
**re-POSTing human approval submissions that nobody asked to resubmit**, months
of them on the first run, to the NRS WorkSpace.

The drain therefore requires `event_type != False`, which no legacy row has.
`test_the_drain_never_touches_a_request_approval_row` covers it.

**2. Delivery is never attempted inline, including on the first try.**

The handoff does not say either way, but "an affix confirmation results in a
delivered callback" could be read as a synchronous POST. It must not be:

- POSTing before the transaction commits would announce an affix that a
  rollback then un-does, leaving Vendra holding `Tagged` for an asset Cadra
  does not think is tagged.
- It would make the Tag-Issuing Unit's confirmation latency a function of
  whether Vendra is up, which is precisely what the queue exists to prevent.

`ir.cron._trigger()` books the drain **inside the same transaction**, so
delivery follows the commit by seconds without being part of it. A failed
attempt calls `_trigger(at=next_attempt_at)` so the configured backoff is the
actual backoff rather than a fiction rounded up to the cron interval.

**3. `409` is recorded as a delivery.** Not mentioned in the handoff. A
receiver returning 409 on our `event_id` is saying it already has the event —
the outcome idempotency exists to produce. Treating it as failure would
dead-letter events that landed perfectly.

---

## Acceptance

### 1. An affix confirmation results in a delivered callback, recorded in `workflow.dispatch.log` ✅

Live on `nrs19`, over real HTTP, driven by a real Odoo cron worker.

### 2. With the receiver down, the event queues, retries with backoff, and delivers when it returns ✅

Receiver deliberately not running. Asset created via the `vendra` client, tag
confirmed via the `tag_issuing_unit` client:

```
receiver-check(should fail): 000
CREATE 201
asset_id 11911 tag NRS-ACS-001 is_tagged False
AFFIX 200
{
  "label_id": 11907,
  "tag_number": "NRS-ACS-001",
  "label_state": "affixed",
  "is_tagged": true,
  "printed_at": null,
  "affixed_at": "2026-09-06T19:03:38",
  "affixed_by": {"id": 2, "name": "Administrator"},
  "affixed_by_name": "J. Okafor"
}
```

**The affix returned 200 with the receiver down** — the point of the outbox.
Note `label_id 11907` against `asset_id 11911`: the id collision, live.

The queue then, with the receiver still down, restored mid-flight, and finally
delivering:

```
[20:16:06] error attempts=1 next=2026-09-06 19:16:33 http=0
[20:16:37] error attempts=2 next=2026-09-06 19:18:34 http=503
   ← receiver brought back up here
[20:18:44] acknowledged attempts=3 http=201 ref=VIM-2026-00001
```

Full per-attempt trail off the row itself:

```
[2026-09-06 19:03:38] queued for Vendra (INT-05 asset events)
[2026-09-06 19:15:33] attempt 1 failed, retrying in 60s: ConnectionError: HTTPConnectionPool(host='host.docker.internal', port=9099): Max retries exceeded with url: /tag-events (Caused by NewConnectionError('...: [Errno 101] Network is unreachable'))
[2026-09-06 19:16:34] attempt 2 failed, retrying in 120s: HTTP 503: receiver deliberately down
[2026-09-06 19:18:34] attempt 3 delivered (HTTP 201) ref=VIM-2026-00001
```

Backoff 60s → 120s exactly as configured. Attempt 1 was a connection failure,
attempt 2 a real HTTP 503 from the receiver — both classified retryable.

### 3. A redelivery carries the same `event_id` ✅

Simulated the real case for a redelivery — a worker that died after the
receiver accepted but before Cadra recorded success — by resetting the row to
`pending`. What the receiver recorded across all three deliveries:

```
mode=fail500  key=633d46ed525c4c848d49b4b18f24b3d7  x-event-id=633d46ed…  x-request-id=WDL-2026-0001  auth=present  dup=False
   body event_id=633d46ed525c4c848d49b4b18f24b3d7  match_header=True
mode=ok       key=633d46ed525c4c848d49b4b18f24b3d7  x-event-id=633d46ed…  x-request-id=WDL-2026-0001  auth=present  dup=False
   body event_id=633d46ed525c4c848d49b4b18f24b3d7  match_header=True
mode=ok       key=633d46ed525c4c848d49b4b18f24b3d7  duplicate=True
distinct event_ids seen: 1 across 3 deliveries
```

The redelivery was answered `409` and Cadra recorded it as delivered:

```
[20:26:39] acknowledged attempts=4 http=409 ref=VIM-DUP-633d46ed
```

`X-Idempotency-Key`, `X-Event-Id` and the body's `event_id` all agree, and
`X-Request-Id` carries the outbox row name for log correlation.

### 4. Dead-lettering after N attempts is visible to a human ✅

Receiver held down, `retry_max_attempts` set to 2, a second asset affixed:

```
[20:27:13] pending attempts=0/2 next=2026-09-06 19:27:05
[20:31:08] error   attempts=1/2 next=2026-09-06 19:32:06
[20:32:10] dead    attempts=2/2 next=CLEARED
```

Visible in three places. The **Failed Deliveries** menu (domain `status=dead`):

```
     name      |    event_type     | asset_id | attempts | http_status |                error
---------------+-------------------+----------+----------+-------------+--------------------------------------
 WDL-2026-0002 | asset.tag.affixed |    11912 |        2 |         503 | HTTP 503: receiver deliberately down
```

The **asset's own chatter**, which is where the person who cares about that
asset is already looking:

> ⚠️ **Integration event not delivered** — Delivery was abandoned after 2
> attempts. Event `asset.tag.affixed` (WDL-2026-0002) could not be delivered to
> Vendra (INT-05 asset events) after 2 attempt(s). The tag record in Cadra is
> unaffected; the downstream system has not been told about it. Last error:
> HTTP 503: receiver deliberately down

And an ERROR-level log line. The human exit was also proven: receiver restored,
**Retry Delivery** pressed, delivered on the next drain with the attempt count
preserved as evidence —

```
RETRY WDL-2026-0002 -> pending attempts kept at 2 budget now 10
[20:32:53] acknowledged attempts=3/10 http=201 ref=VIM-2026-00001
```

### 5. Full suite green, per-tenant loop shown ✅

Quoted below.

---

## Test output, verbatim

**API suite** (`CADRA_API_BASE=http://jaizbankplc.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q`):

```
....................................ssssssssss.......................... [ 29%]
.............................................ssssssss.ssss.............. [ 59%]
...............................s........................................ [ 88%]
.........................ss                                              [100%]
============================ cadra api test report =============================
Report: /Users/macbookprom1/Desktop/WML/myservicenrs/docs/api/test-report.md
Captured responses: /Users/macbookprom1/Desktop/WML/myservicenrs/docs/api/test-responses/
218 passed, 25 skipped in 37.75s
```

**New in-Odoo suite** — 32 tests covering backoff maths, classification,
dead-lettering, event-id stability, the drain's scoping, the ORM guard, the
cron wiring, the REST adapter's request composition, and the config guards:

```
odoo -c /etc/odoo/odoo.conf -d test19 -u myservice_workflow --test-enable \
     --test-tags /myservice_workflow --stop-after-init \
     --http-port=8099 --gevent-port=8098

2026-09-06 19:50:17,368 INFO test19 odoo.service.server: 30 post-tests in 2.26s, 1614 queries
2026-09-06 19:50:17,369 INFO test19 odoo.tests.stats: myservice_workflow: 32 tests 2.25s 1614 queries
```

No `FAIL:` or `ERROR:` lines.

One test in this file was **wrong on the first run and is worth recording**:
both drain tests initially passed for the wrong reason. `FRESH_ROW_GRACE_SECONDS`
was skipping the row before the drain reasoned about it, so
`test_the_drain_skips_a_disabled_target` asserted nothing at all. The grace is
now patched off explicitly in a `_drain` helper whose docstring says why.

**Per-tenant fan-out of `myservice_workflow` 19.0.2.0.0** — this change adds
stored columns, so every tenant was upgraded before the code ships:

```
cadra19       cols=8/8   nrs           cols=8/8
nrs19         cols=8/8   lasg          cols=8/8
gtb19         cols=8/8   gtb           cols=8/8
test19        cols=8/8   jaizbankplc   cols=8/8

(all eight at myservice_workflow 19.0.2.0.0, cron registered on each)
```

The `UNIQUE (event_id)` constraint is real on 19, not merely declared —
confirming the `models.Constraint` pattern held:

```
"workflow_dispatch_log_event_id_uniq" UNIQUE CONSTRAINT, btree (event_id)
```

No `_sql_constraints is no longer supported` warning appeared on any tenant.

---

## Finding: no `ir.cron` fires on the local dev stack

Worth its own heading because it is not caused by this work and affects
everything cron-driven.

The first live attempt sat at `pending` for 200 seconds and never moved. The
cause is in `config/odoo.19.conf:7`:

```
db_name = odoo
```

which pins Odoo's cron worker to a single database called `odoo`. The container
log says so once a minute:

```
WARNING odoo odoo.addons.base.models.ir_cron: Skipping database odoo as its base version is not 19.0.1.3.
```

**No tenant cron has ever run on this machine** — that includes
`cron_asset_pm`, `cron_asset_depreciation` and `ir_cron_gc_refresh_tokens`, not
just the new one. `jaizbankplc` has 28 crons and 0 that have ever executed.

**Production is unaffected.** `k8s/dev/10-configmap-odoo-19.yaml:13-14` says
*"db_name is intentionally NOT set — the DB is chosen per-request by dbfilter"*,
so the deployed cron worker enumerates every tenant normally.

The live proof above was therefore driven by a throwaway worker container
(`--database=nrs19`, no `db_name`, `--max-cron-threads=1`) on the compose
network — the pattern `k8s/dev/MULTI-TENANT.md:147-158` already documents for
testing dbfilter. That is a genuine scheduler driving genuine HTTP, not a
manual method call.

I have **not** changed `config/odoo.19.conf`. Changing local cron behaviour is
outside this handoff and would silently start running the depreciation and PM
crons against eight local databases. Flagging it for a decision instead.

---

## Notes and open questions

1. **`webhooks:admin` remains a declared, unused scope**
   (`myservice_api/controllers/utils.py:130`). An API view over the outbox
   would be its natural home. Not built — the handoff did not ask, and the Odoo
   menu covers the "visible to a human" requirement.
2. **`workflow.dispatch.log.status` carries `tracking=True` on a model with no
   `mail.thread`**, which logs a warning on every module load on every tenant.
   Pre-existing; left alone to keep the diff to the handoff's scope.
3. **`nrs19` keeps its `asset_events` config row, disabled.** The proof
   receiver is gone and Vendra's endpoint does not exist yet, so leaving it
   enabled would make every future affix on the demo tenant dead-letter. The
   wiring is in place for whoever builds the Vendra side: set the base URL and
   event endpoint, switch *Emit Asset Events* on.
4. **Demo assets 11911 and 11912 remain on `nrs19`**, consistent with the
   suite's existing no-teardown convention.
5. **The stale `workflow_dispatch_log__event_id_index` was dropped by hand on
   all eight local databases.** It only exists because I shipped `index=True`
   in an intermediate state of my own working tree and Odoo does not drop an
   index when the flag is removed. Production goes from 19.0.1.0.0 straight to
   19.0.2.0.0 and never creates it, so there is no migration to write — but
   the local databases would otherwise have carried an index a fresh deploy
   does not.

---

## What Vendra needs to implement

Written up in full as `docs/integrations/INT-05-tag-affixed-callback.md` — the
payload, the headers, and the response table. The short version:

1. **A whitelisted endpoint** (e.g. `vendra_network.api.tag_event`) using the
   same credential model INT-03 already uses in reverse.
2. **Dedupe on `X-Idempotency-Key`** — store it, and on a repeat return **409**
   with the original message name. Cadra reads 409 as a successful dedupe.
3. **Resolve the receipt line** from `provenance.import_ref` (the Purchase
   Receipt name Vendra sent on INT-03) plus `asset.serial_number`, or from
   `asset.id` against the unit's `cadra_asset_id`.
4. **Set `cadra_status = "Tagged"`** on the unit and let the existing
   weakest-link roll-up move the line. That value already exists in Vendra's
   select and nothing has ever been able to set it.
5. **Return an identifier in the body** (`name`, `id`, `reference`, `ref` or
   `event_id`, optionally inside Frappe's `message` wrapper) so Cadra records
   `Acknowledged` rather than merely `Sent`.
6. **Return 4xx only when the payload is genuinely unusable.** Cadra
   dead-letters any 4xx except 408/425/429 on the **first** attempt. Anything
   transient must be a 5xx or a 429.

Once that exists, the C4 readback deferred since handoff 04 becomes buildable:
Vendra will hold a real `Tagged` rather than inferring one.

---

## Verification pass

A fresh reviewer (not an author) read `CLAUDE.md`, the handoff and the full
diff. It found **two blockers**, and one of them proves a claim I had made in
this report was false. Both are fixed; everything below was re-run afterwards.

### Blocker 1 — the grace period defeated the trigger it was meant to protect

`_enqueue_event` calls `ir.cron._trigger()`, which books a run for *now* and
fires `pg_notify` on commit, so a worker wakes within about a second. That run
then evaluated a drain domain that **excluded the very row it had been booked
for**: a `FRESH_ROW_GRACE_SECONDS = 20` clause required `attempts > 0` or a
`create_date` at least 20 seconds old, and a freshly queued row is neither.
The drain found nothing — and Odoo *consumes* the trigger before running the
action (`ir_cron._clear_schedule`), so the wake-up was spent on an empty pass
and the first attempt fell through to the 5-minute periodic sweep.

Retries were unaffected (`attempts > 0` satisfied the clause), so all the
backoff evidence above is real. **Only the first attempt was broken — the
common case.**

**This invalidated note 5 of my own report.** I had written that the ~4-minute
and ~12-minute first-attempt latencies were "governed by the throwaway cron
worker's wake cycle rather than by the design", and that "in-process,
`_trigger()` fires the drain within seconds of the commit". That was wrong: the
worker woke within seconds every time and my domain threw the row away. I had
read a symptom of my own bug as an artefact of the test rig. The note is
removed.

The grace period is deleted rather than narrowed. It guarded against a race
that cannot happen: Odoo holds `FOR NO KEY UPDATE SKIP LOCKED` on the `ir.cron`
row for the whole action, so two workers cannot run this drain concurrently.
`_deliver_once` now carries a comment recording that this guarantee holds only
while the cron is the sole entry point.

**Re-proven live**, same rig, receiver up:

```
AFFIX 200
ASSET_ID=11913
[+6s]
[+11s] acknowledged attempts=1 http=201
```

**Delivered on attempt 1, about 11 seconds after the affix** — against 12
minutes for the first event in this report. `test_a_queued_row_is_eligible_for_the_very_next_drain`
and `test_queueing_an_event_books_an_immediate_drain` now fail if it regresses.

### Blocker 2 — any internal user could forge an outbound event

`access_workflow_dispatch_log_user` grants `perm_create` to every user with an
empty `group_id`, and there are no record rules on the model. Before this work
that meant "anyone can write an audit row", which is inert. After it, a row
carrying `event_type`/`config_id`/`payload_sent`/`next_attempt_at` is a **send
instruction**: the drain POSTs it verbatim to Vendra with the tenant's own
credentials.

So `h05_nobody` — the account handoff 05 deliberately gave zero API scopes —
could call `workflow.dispatch.log.create(...)` over `call_kw` and have Cadra
sign a forged `asset.tag.affixed`, marking a receipt line `Tagged` in Vendra.
That walks straight around the `tagging:write` separation handoffs 03 and 05
exist to enforce.

This is the repo's own ruling applied to a new model: *"`readonly=True` is a
web-client hint, not an ORM guard."* The fix is the same pattern
`nrs.asset.tag.label` uses — a `create`/`write` override over `_EVENT_FIELDS`,
keyed on a `cadra_event_dispatch` context flag that only the queue sets.

I did **not** drop `perm_create` from the ACL, which was the reviewer's
suggested fix: `request.request._send_to_workflow` creates its audit row as the
acting user rather than as sudo, so removing it would break the approval flow
for every non-admin. The ORM guard is the narrower control and protects the
fields regardless of ACL. `test_a_hand_crafted_event_row_is_refused` and
`test_an_ordinary_audit_row_is_still_writable` cover both halves.

### Should-fixes, all applied

| # | Finding | Fix |
|---|---|---|
| 3 | The `attempts` increment was flushed, not committed — a worker killed mid-POST rolled it back, the exact poison-event loop the docstring claimed to prevent | `_count_attempt()` commits (guarded by `_in_test()`) |
| 4 | A raise escaping `_deliver_once` (its own writes and `_get_adapter()` sit outside the inner try) aborted the batch and left the row at the head of an oldest-first window **forever**, starving everything behind it | the loop catches, rolls back, and defers the row by one backoff |
| 5 | `error` relabelled "Failed — Will Retry" is a **false promise on approval rows**, which are never retried; and `sent` moved to green, so an approval genuinely awaiting a human decision rendered as resolved | labels back to neutral `Pending`/`Failed`; `sent` back to info |
| 6 | `max_attempts` was snapshotted but the backoff base and cap were read live, so a mid-backlog retune rescheduled every in-flight event | `retry_base_seconds`/`retry_cap_seconds` snapshotted too |
| 7 | An event raised while `event_enabled` was off was **discarded permanently** — switching the target back on silently lost every affix in between | the enqueue path passes `include_disabled=True`; the drain already excludes disabled targets, so events queue and wait |
| 8 | `_trigger_drain` and `WorkflowRestAdapter.deliver` were never called by any test — blocker 1 lived in exactly that gap; and the approval-row test proved the wrong clause (its row had a NULL `next_attempt_at`, so it was excluded regardless of `event_type`) | 9 tests added, including cron wiring, adapter request composition, the ORM guard, and a real `IntegrityError` assertion on `UNIQUE (event_id)`; the approval row now has a due `next_attempt_at` |

### Nits, applied

`index=True` dropped from `event_id` (the UNIQUE constraint already builds a
btree); receiver-controlled text escaped before it enters the chatter HTML; the
no-config early exit now counts its attempt so the note does not read "abandoned
after 0 attempt(s)"; a full drain window re-triggers so a backlog does not
clear at 50 per five minutes.

### Not applied

The reviewer's nit 10 — that the payload docstring implies interchangeability
with the API serialiser while `affixed_by` is a string here and an object
there, and timestamps carry `Z` here and not there — is correct. Both event
choices are the better ones, and the differences are already spelled out in
`docs/integrations/INT-05-tag-affixed-callback.md`, so an integrator reading
the contract is not misled. Left as is.

### Confirmed sound by the review

The `models.Constraint` dual spelling (source guards: `16 passed`); `UNIQUE`
on a populated table needing no `_auto_init` dedup because every legacy row is
NULL; `_trigger(at=)` and the cron XML's omission of `numbercall`/`doall`; the
`test_enable` commit guard; no dependency cycle and all 7 `get_active_config()`
callers unaffected; no `/api/v1` surface change; no secret leak path into
`error_message` or the chatter; and no way for two concurrent affixes to
produce two events.

---

## Commits

Branch `feat/tag-callback`, PR **#49** → `dev`
&lt;https://github.com/wmlmetro/Cadra/pull/49&gt;

| Commit | |
|---|---|
| `c2b124a` | `feat: deliver asset.tag.affixed to Vendra with retry (INT-05)` |
| `2b95b4c` | `docs: record handoff 06 and publish the INT-05 contract` |

---

## Needs the owner

- **Merging the PR** — `gh pr merge` is refused by the Builder's permission
  layer, as standing.
- **The production deploy of #48 must still fan out per tenant.** Unchanged
  from handoff 06's own "Needs the owner" block, and still the security fix.
- **Rotating `test_client`'s secret on `nrs19`** — still outstanding.
- **The three handoff-05 test users** (`h05_storekeeper`, `h05_tagger`,
  `h05_nobody`) are still on `nrs19` and must not reach staging.
- **A decision on `db_name = odoo` in `config/odoo.19.conf`** — see the finding
  above. Local crons are all dormant; production is fine.
