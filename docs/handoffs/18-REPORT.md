# Report 18 — The callback that answers twice

**Builder** · branch `fix/callback-idempotency` · base `ca81aa4`

---

## What was built

**A · A replayed callback now writes nothing.** Both callback routes acted on
the CALL. They now act on the TRANSITION, from one model method
(`request.request._workflow_callback_disposition`) that both consult **before
either writes anything** — the dispatch-log row included, which is why the
check could not live inside the three outcome handlers: `myservice_api`
appends its row before it calls them, so a check one layer in would still have
left a row per replay.

Three dispositions. `replay` answers success and writes nothing. `conflict`
refuses `409`. `apply` is everything else.

**A(ii) · `myservice_request_core.write` was fixed too, and it is the wider
half.** It branched on `'stage_id' in vals`, so writing a request's current
stage back over itself reset `date_moved` and appended a `stage_changed` row
to `request.event` — the request's own audit trail, which the API publishes.
The callback is only the caller that made it visible. Any caller writing an
unchanged stage has been fabricating events for as long as the method has
existed, so the fix is in the core model and not only behind the callback.
That module had **no tests at all**; it now has eight, and CI runs them.

**B1 · The v1 twin reconciles its dispatch.** Both routes now share
`workflow.dispatch.log._reconcile_callback`, scoped to exclude `event_type`
rows — INT-05 asset events live in the same table and also pass through
`sent`, and one of those is not an answer to an approval request. Handoff 06's
"the drain is scoped by `event_type`, not by status", applied to the reader on
the other side.

**B2 · The v1 twin stopped publishing an internal menu path.**
`503 server_misconfigured` with an opaque body; the configuration sentence
goes to the log. Handoff 15's answer, on the twin.

**C · The credential is out of the image layer.** Default gone from
`Dockerfile.nrs-import`; the entrypoint refuses and names the Secret, the key
and the manifest; the Job reads `cadra-odoo/ODOO_ADMIN_PASSWORD`;
`nrs-import.yml` pre-checks that key, because a missing `secretKeyRef`
otherwise leaves the pod in `CreateContainerConfigError` with no logs at all.
`e2e/config.ts` keeps `admin`/`admin` only while the origin is local.

**D · `request.jsonrequest` is gone**, replaced by `request.get_json_data()`,
with a source guard.

---

## 1 · Is `workspace_ref` reliably populated on both controllers?

**No, on both counts — by contract and in fact. It cannot be the dedup key.**

By contract it is optional in both: the legacy route reads
`data.get('workspace_ref', '')` and the v1 schema declares it
`nullable: True` and leaves it out of `required`.

Measured across all eight local tenants before the design was settled:

| Where | Populated |
|---|---|
| `request.request.workspace_ref` | **0 of 407** |
| `workflow.dispatch.log.workspace_ref`, request-approval rows | 76 of 76 |
| `workflow.dispatch.log.workspace_ref`, asset-event rows (INT-05) | 0 of 75 |

The 76 look like a perfect record and are not one. Every one of them is an
`inbound / queried` row on `jaizbankplc` (74) or `gtb19` (2), and every one
carries the string `PYTEST-WORKSPACE-REF-001` — they are this repo's own
integration suite, not a workflow engine. There is **no outbound
request-approval row on any tenant**, because `_send_to_workflow` has never
run on one; that is also why `request.request.workspace_ref` is empty
everywhere, since only that method writes it.

So the dedup keys on `workflow_status`, which every path that applies an
outcome writes. `workspace_ref` corroborates in the log line and nothing more.

A re-send is what re-opens the door: `_send_to_workflow` sets
`workflow_status` back to `pending`, so a second dispatch is a second question
and its answer is a second transition. Replay suppression bites only where
nothing new was asked.

## 2 · What does a contradicting replay do, and why that?

**It is refused `409`, logged at ERROR, and writes nothing.** Not applied, not
silently absorbed.

`approved` → `rejected`, `rejected` → `approved`, and `queried` after either
are all contradictions. `queried` is included deliberately: it writes no stage
so the damage is smaller, but it moves `workflow_status` off `approved`, which
erases the recorded decision just as completely.

The alternative was to apply it and log a warning. It was rejected because
**nothing in the payload can tell a genuine reversal from a stale redelivery
arriving out of order** — and `workspace_ref`, the field that might have, is
empty on every tenant (§1). Applying it means a retry queue somewhere can
overwrite a recorded decision with an older one and nobody finds out. Refusing
it means a real reversal needs a human: re-send the request to WorkSpace,
which returns it to `pending`, and the next decision applies normally.

The refusal names both outcomes (`current_outcome`, `attempted_outcome`) so
the caller knows exactly what Cadra holds — this is past authentication, so
there is nothing to protect. ERROR rather than WARNING, because this is the
one case here where somebody has to look.

**And a repeat carrying the SAME outcome but new data is not silently
dropped.** The verification pass found the hole: the disposition compares
`workflow_status` and nothing else, so a second `approved` carrying a
`payment_ref` the first did not have was discarded and answered `200` — and
both fields are optional in the published schema, so a workflow engine that
sends the approval when it is granted and the reference when it clears is
doing nothing wrong. Rule 3.

It still writes nothing. What changed is that anything discarded is **named**,
at WARNING in the log and in the response (`discarded_fields` on the legacy
route, `data._warnings.discarded_fields` on v1 — the same shape rule 3 already
uses for `rejected_fields`). Whether a late `payment_ref` should actually be
recorded is a contract decision and is open question 3 below.

The same applies to a second `queried` whose comment is a new question rather
than a redelivery — the comment text is the only thing that distinguishes
them. The comparison is against `workflow.dispatch.log.workflow_comment`,
which holds the text verbatim, **not** against the chatter body, which wraps
it in markup: the first version compared the wrong thing, so every ordinary
redelivery came back as a new question and the plain-replay test failed on the
run meant to prove the feature. A warning that fires on the common case is a
warning somebody switches off.

## 3 · Did the guard need a new branch for `ENV`-assigned credentials?

**Three new readers, and the shape rule did not survive the format change.**

The existing guard is an AST walk. A Dockerfile has no AST, so the reader had
to be new — and two more with it, for k8s manifests (an indentation walk;
there is no pyyaml in the test venv, and a guard that silently skips every
manifest on an ImportError is worse than one that reads them as text) and for
JS/TS (`process.env.X ?? "lit"`, which is JavaScript for `os.getenv(x, lit)`).
`_is_baked_value` is shared: a value that defers to something outside the file
(`$ARG`, `${ARG}`, `$(VAR)`) bakes nothing in, and neither does an empty one.

**But the interesting failure was not the reader. `_CREDENTIAL_RE` did not
contain `pw`.** `pwd` was listed; `pw` was not; `password` does not contain
it. So the first version of the Dockerfile reader parsed the instruction
perfectly, found `ODOO_ADMIN_PW=admin`, and classified it as an ordinary
variable — the guard read the exact defect it was written for and called it
nothing. Both fixture cases failed on the first run for that reason. Added as
a segmented word, alongside `auth`, `pass` and `salt`.

That is the finding worth keeping: the roster of what *names* a credential is
this guard's one hand-written list, and the shape rules around it are what
make it look like a rule. The list was wrong about the case in front of it.

**The TypeScript exception needed no waiver, and that was designed rather than
discovered.** `e2e/config.ts` keeps its `admin` default behind an "is this
origin local?" test. A default behind a conditional is not the
`process.env.X ?? "literal"` shape the reader matches, so gating the default
is exactly what takes it out of the guard's reach. The guard rewards the fix
instead of carrying a named exception that rots — CLAUDE.md's own complaint
about the old `odoo.conf` waiver.

## 4 · Wall-clock, correction share, machine

**Wall-clock ~55 minutes**, 11:00 to 11:55 local. Roughly **a third of it was
correction** — three rounds of it, and every round came from a test or a
reviewer rather than from reading the code again:

1. The tracking-message precommit (below), one test failure.
2. The verification pass, thirteen findings, six of them real defects in work
   that had already gone green.
3. The over-reporting comment comparison, one test failure on the run meant to
   prove the fix for finding 1.

**The machine behaved.** Twelve `--stop-after-init` registry loads, all
serialised, **zero Postgres crash-restarts** — the discipline
`docs/ENVIRONMENT-FACTS.md` records, working. Four `docker compose restart
odoo` cycles for Python changes, ~12s each. No denominator collapsed: every
run reported `of N tests` with N in the hundreds.

## 5 · What the verification pass found, and what changed because of it

Thirteen findings. Six were real defects in code that had already gone green,
and they are worth listing because five of them are the same shape — **a fix
that was correct and a claim about it that was not.**

| # | Finding | Outcome |
|---|---|---|
| 1 | A second `approved` carrying a late `payment_ref` was silently dropped, against rule 3 | **Fixed** — `_discarded_by_replay`, named in the log and the body |
| 2 | A second, distinct `queried` question was swallowed the same way | **Fixed** by the same change; raised as open question 4 |
| 3 | The generated OpenAPI declared neither the new `409` nor the `503` | **Fixed** — `cadra_route(error_statuses=…)`, with a test |
| 5 | The k8s reader was defeated by a trailing comment on the `- name:` line | **Fixed**, plus flow mappings; 4 fixtures added |
| 6 | The JS reader missed destructuring defaults, `import.meta.env`, a wrapped line and the ternary | **Fixed** — whole-file, four spellings; 7 fixtures added |
| 7 | The Dockerfile reader reported a line five above the defect, and the report quoted it | **Fixed** — the finding now names the assignment's own line |
| 8 | A pytest test `return`ed instead of skipping, so it passed having asserted nothing on every run | **Fixed** — `pytest.skip` |
| 10 | `sap_employee_sync` did not get the type guard its own twin got | **Fixed** |
| 11 | The changelog said an empty POST reached `request.jsonrequest`; the dispatcher refuses that first | **Corrected** |
| 13 | "Writes nothing at all" is true of the five listed effects, not literally | **Qualified** |
| 4 | The `request_core` change alters `data.dates.moved` and `include=events`, unannounced | **Added to the changelog** |
| 9 | One test cannot fail under a single revert | Acknowledged below |
| 12 | Item C's acceptance criterion is not met as written | Stated plainly below |

**The OpenAPI test then caught a mistake of my own.** `error_statuses=(409,
503)` landed on `/api/v1/barcode/generate` instead of the callback, because
that route's decorator has a byte-identical three-line prefix. The test failed,
naming the codes it could not find. Written to hold a contract, it earned its
keep before the commit that introduced it.

---

## Deliberate deviations and things the handoff did not say

**1 · The `queried` outcome on the v1 route now refuses on an unconfigured
tenant, where it used to succeed.** Item B2 says "apply the same answer here",
and the legacy route's answer is a refusal for all three outcomes. The v1
route only ever failed on `approved`/`rejected`, because only those two
handlers call `get_active_config()`. Making the twins agree therefore changes
`queried` too. It is announced as **BREAKING** in `docs/api/CHANGELOG.md`
rather than smuggled in — a callback from a workflow engine a tenant is not
wired to is not a thing to half-apply, but it is a behaviour change and a
consumer could branch on it. **No tenant is affected today**: all eight have
zero active workspace configurations, so every one of them is already in the
refusing state for `approved` and `rejected`.

**2 · `myservice_request_core` was changed, and the handoff only named the
symptom.** Item A.3 says `write` "branches on `'stage_id' in vals` rather than
on the value changing" and describes it as part of the replay damage. Fixing
only the callback would have satisfied the acceptance criteria — the replay
never reaches the handler now, so no stage write happens either way. It was
fixed at the core anyway, because the defect is not the callback's: an import,
a bulk edit, or `api_move_request` on a route that ends where it starts all
fabricate the same `stage_changed` event. `myservice_request_core` is now
named in CI's `-u` list; it was previously reached only as transitive coverage
that would vanish the day a dependency moved.

**3 · The credential guard was NOT widened to compose files or
`.env.example`, and here is what that leaves.** The same rule would flag four
more sites:

| File | Line | Assignment |
|---|---|---|
| `docker-compose.yml` | 20 | `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-odoo}` |
| `docker-compose.yml` | 42 | `PASSWORD: ${POSTGRES_PASSWORD:-odoo}` |
| `.env.example` | — | `POSTGRES_PASSWORD=odoo` |
| `.env.example` | — | `ODOO_MASTER_PASSWORD=admin` |

They were left alone. Changing them changes the local bring-up for every
checkout, which is not this handoff's business, and `.env.example` is a
template whose own header says every value must be overridden in production —
a weaker argument than an image layer's, but a different one. The guard is
scoped so these do not fail it today. `docs/DEPLOYMENT.md` tells a prod
operator to generate strong values with `openssl rand`, so the current
position is "prod overrides it" — which is the promise the rule exists to stop
relying on. **Saying the criterion is met would be false, so it is recorded
here as unmet rather than filed as an open question.**

**4 · `myservice_request_core.write` changes published API behaviour, so it is
in the changelog too.** `date_moved` is `data.dates.moved` on the request
serialiser and `request.event` rows are `include=events`. After the change, a
`stage_id` write whose value is unchanged produces neither. The reachable
caller is `api_move_request`, which validates only that the route starts at the
current stage — a route whose `stage_to_id` equals its `stage_from_id` is legal
and now returns success with the timeline standing still. Correct behaviour,
and a consumer could branch on it, so it is announced.

**5 · One new test cannot fail under a single revert, and it should not be
counted as holding the fix.**
`test_writing_the_stage_a_request_already_holds_is_not_a_move` sits over two
redundant guards — `_set_workflow_stage`'s own check and `request_core`'s
moved-subset — so reverting either alone leaves it green. The redundancy is
deliberate and the model comment says so ("belt and braces"). The tests that
genuinely fail on a revert of the core fix are three in
`myservice_request_core/tests/`:
`test_writing_the_same_stage_logs_no_event_and_does_not_move_the_clock`,
`test_re_writing_a_closing_stage_does_not_restamp_date_closed` and
`test_in_a_batch_write_only_the_records_that_moved_are_recorded`. Four others
in that file pass under the old code too — correctly: they are the
over-suppression guards, and a fix that silenced real stage moves would fail
them.

**6 · "A replay writes nothing" is true of the five effects on the acceptance
list, not literally.** A v1 replay still stamps `last_used_ip` /
`last_used_at` on the calling `myservice.api.client`, and inserts an
idempotency row when the caller supplies `X-Idempotency-Key`, because it
returns a success envelope. Neither is on the acceptance list and neither
touches the request. The claim is qualified wherever it is made.

**7 · The v1 route's SUCCESS path now has no pytest coverage.** Item B2 made
an unconfigured tenant refuse `queried`, and `queried` was the only outcome
that used to succeed there — so `test_workflow_callback` takes the 503 branch
on every tenant and the replay test skips. The success path is covered in the
registry instead, where the config can be created and rows can be counted.
Worth knowing before somebody reads 419 green pytest tests as covering it.

---

## Evidence

### Item B2, live on `jaizbankplc`, before and after

The finding report 17 read from source, confirmed by probe. Every tenant is an
unconfigured tenant, so it turned out cheap.

```
BEFORE  HTTP 400
{"error": {"code": "validation_failed",
           "message": "No active Workflow integration configuration found for
                       \"workspace\". Please configure one under Settings →
                       WorkSpace Integration.",
           "details": {"http_status": 400}}}

AFTER   HTTP 503
{"error": {"code": "server_misconfigured",
           "message": "Workflow integration is not available",
           "details": {"http_status": 503}}}
```

### Item A, live on `test19`, across real committed transactions

The `HttpCase` tests run inside one shared transaction, so they prove "a
replay writes nothing" within a transaction. This is the same thing across
separate committed ones, over the published route, against a tenant standing
up a real `workflow.config` with an `approved_stage_id`.

```
start        status=not_sent  stage=6  date_moved=False  log=0 events=1 msgs=1
POST 1  200  {"ok": true, "replayed": false, "message": "Outcome 'approved' applied…"}
after 1      status=approved  stage=7  date_moved=11:31:04  log=1 events=2 msgs=3
POST 2  200  {"ok": true, "replayed": true,  "message": "…was already applied…; nothing changed"}
after 2      status=approved  stage=7  date_moved=11:31:04  log=1 events=2 msgs=3
             REPLAY WROTE NOTHING: True

a human moves the request onward
             status=approved  stage=8  date_moved=11:31:05  log=1 events=3 msgs=4
POST 3  200  {"ok": true, "replayed": true, …}
after 3      status=approved  stage=8  date_moved=11:31:05  log=1 events=3 msgs=4
             NOT DRAGGED BACK: True

POST 4  409  {"error": "Request 'H18-LIVE-8c3fd93f' is already 'approved';
              refusing to apply 'rejected'",
              "current_outcome": "approved", "attempted_outcome": "rejected"}
after 4      unchanged.  CONFLICT WROTE NOTHING: True
```

The probe's config and two of its three stages were removed afterwards and
`test19` is back to zero active workspace configurations. **The probe request
and its one dispatch-log row were deliberately left**: `workflow.dispatch.log`
refuses `unlink` for every group — "never deleted, permanent audit trail" —
and `request_id` is `ondelete='set null'`, so deleting the request would have
left that row orphaned rather than cleaned up. The request says what it is in
its description.

### Guards proven to fail before they pass

Both new guards were run against the real defect restored into the real file,
not only against fixtures.

```
Dockerfile.nrs-import:39 (Dockerfile) assigns ODOO_ADMIN_PW the literal 'admin'
myservice_identity/controllers/sap_webhook.py:108 reads request.jsonrequest —
  an attribute of the JSON-RPC dispatcher, not of request; use
  request.get_json_data()
```

**Line 39 is the assignment.** The first version said 34, because it joined
the continuations and then numbered the joined text — five lines off, pointing
at a comment. A finding that names the wrong line sends whoever reads it to
the wrong place, which is most of what a guard's output is for.

Both pass with the fixes in place. The parametrised fixtures carry **35** more
cases across the three readers, half of them **negative** — `secretKeyRef` in
both block and flow form, `ENV X=$ARG`, `ENV X=""`, `ARG X` with no value, a
non-credential literal, a downward field reference, a non-credential
destructuring default, a gated TypeScript default — because the two shapes a
fix takes are exactly the shapes a careless guard punishes.

Eleven of those cases came from the verification pass, which wrote them
against the first version of the three readers and measured them being
accepted: a trailing comment on a `- name:` line (the spelling this repo's
heavily-commented manifests actually use), a YAML flow mapping, the ordinary
`const { E2E_PASS = "admin" } = process.env` destructuring idiom, a fallback a
formatter had wrapped across two lines, Vite's `import.meta.env` — which is
the spelling the `Frontend/` app uses, so the reader covered the test harness
and none of the product — and the pre-`??` ternary. All six are caught now.

### The `e2e/config.ts` origin gate, tried against evasions

Transpiled and run, thirteen origins. The interesting ones are the six that
must NOT be local:

| Origin | Verdict |
|---|---|
| `http://jaizbankplc.localhost:8069` | local — the default target |
| `http://localhost:8069`, `http://127.0.0.1:8069`, `http://[::1]:8069` | local |
| `https://LOCALHOST:8069` | local — case is folded |
| `https://staging.app.cadra.ng` | **remote** |
| `https://localhost.cadra.ng` | **remote** — `localhost` as a left label |
| `https://notlocalhost` | **remote** — not a label boundary |
| `https://evil.com#localhost` | **remote** — fragment |
| `https://evil.com/?x=localhost` | **remote** — query |
| `https://user:pw@evil.com` | **remote** — userinfo |
| `https://cadra.ng/localhost` | **remote** — path |
| `not a url` | **remote** — an origin we cannot parse is one we cannot vouch for |

A remote origin with no `E2E_PASS` throws, naming the variable and the origin.
A remote origin WITH the variables set uses them. `endsWith("localhost")`
alone would have called three of those six local, which is why the check is on
`URL.hostname` at a label boundary rather than on the string.

### Suites, in CI's order, denominators quoted

```
pytest tests/ -q            419 passed, 28 skipped in 82.12s
```

27 of the 28 skips are the documented admin-scope skips; the suite's token has
no `admin` scope. The 28th is new and deliberate: the v1 replay test now
**skips** on a tenant with no workflow configuration rather than `return`ing.
It used to return, which made it pass having asserted nothing — on every run,
because no tenant has one.

```
odoo -d jaizbankplc -u myservice_workflow,myservice_asset_depreciation,
     myservice_nrs_base,myservice_asset_register,myservice_request_core,
     myservice_request_fields,myservice_security,myservice_fleet_maintenance,
     myservice_barcode_station,myservice_api,myservice_identity
     --test-enable --stop-after-init --workers=0

366 post-tests in 63.12s, 31730 queries
0 failed, 0 error(s) of 366 tests when loading database 'jaizbankplc'
```

**366, not 0.** No `CRITICAL` in the run. The five
`cannot execute INSERT in a read-only transaction` lines are Odoo's own
`retrying with a read/write cursor` on the refresh-token insert in
`TestPaginationCap`, and predate this branch.

Per-module, including the two that grew: `myservice_workflow` 97 tests
(was 80), `myservice_request_core` 10 (was 0 — the module had no `tests/`
package at all). 25 new tests across the two files, plus 12 in the pytest
source guards and 1 in `tests/test_meta.py`.

### One test that failed for the right reason

`test_a_replay_does_not_drag_a_request_back_from_where_a_human_moved_it`
failed on its first run, reporting one message more than the snapshot. The
replay had not posted it. `stage_id` is `tracking=True`, and `mail.thread`
materialises a tracking message from a **precommit callback**, not at flush —
so the manual stage move the test makes posted its message later, during the
next callback's request, and the footprint taken straight after the move
under-counted by one. `env.flush_all()` is not enough; `env.cr.precommit.run()`
is, which is `mail`'s own `flush_tracking()`. Every footprint now settles that
way. Handoff 09's "a stored compute is not stale until it has been WRITTEN",
one mechanism on.

---

## Needs the owner

- **The PR merge.** The Builder's permission layer refuses `gh pr merge`.
- **`cadra-odoo/ODOO_ADMIN_PASSWORD` must be created in the cluster before the
  next `nrs-import` run**, or the Job's pre-check fails naming it.

  **What it is.** The password of the Odoo **`admin` user** — a `res.users`
  login — on the target tenant database. `scripts/nrs_import_entrypoint.sh`
  passes it as `--password` to `migrate_nrs_locations.py` and
  `seed_nrs_assets.py`, which `common.authenticate(db, 'admin', pw, {})` over
  XML-RPC against `odoo-19:8069` and then write the location tree, the asset
  categories, ~11.4k employees and ~11.9k assets.

  **It is not `ODOO_MASTER_PASSWORD`**, which is already in this Secret. That
  one is `admin_passwd` in `odoo.conf` — the database manager's master
  password, used to create, duplicate and drop databases. Different
  credential, different job. Conflating them is easy and the old comment in
  `71-nrs-import-job.yaml` did not help.

  **The `cadra-nrs-import` Job is its only consumer**, in the cluster or
  anywhere else. Nothing else authenticates as the admin user over XML-RPC:
  `backfill_external_ids.py` accepts a `--password` but is wired into no Job
  and no workflow.

  ```bash
  kubectl -n cadra-dev patch secret cadra-odoo --type merge \
    -p '{"stringData":{"ODOO_ADMIN_PASSWORD":"<password>"}}'
  ```
  Documented in `k8s/dev/CLUSTER-SETUP.md`.

- **AND THE VALUE IS THE POINT. Taking the default out of the image stopped
  PUBLISHING the credential; it did not rotate it.** Setting this key to
  `admin` restores exactly the security position that existed before, minus
  the image layer. Whether that is acceptable depends on the next item.

- **Nothing in this repository ever sets the Odoo `admin` user's password, on
  any tenant.** `scripts/bootstrap.py` adds `base.user_admin` to groups and
  never touches its password; no seed, migration, Job or workflow does either.
  Measured on this machine: `admin`/`admin` authenticates as uid 2 on
  `jaizbankplc`, `nrs19`, `cadra19` and `test19`. **The cluster was not
  probed** — I have no access to it from here — but the same code provisions
  it, so the same is likely true of `staging19`, `staging`, `gtb`, `lasg` and
  `jaizbankplc` there.

  That is a larger finding than the one this handoff was given, and it is not
  the Builder's to fix: changing a live tenant's admin password is an
  operational act with a blast radius (anyone signing in as `admin`, any
  saved session, any script somebody keeps locally). It is recorded here as
  the thing the image-layer fix uncovered rather than the thing it solved.
- **The two live-cutover credentials from report 17 §3 are still unrotated.**
  Not this handoff's work; still true.

## Open questions

1. **The four compose / `.env.example` credential defaults above.** Widen the
   guard and change the local bring-up, or write the exception down? Either is
   defensible; leaving it unstated is not.
2. **`workspace_ref` is a stored field nothing populates and nothing matches
   on.** It is now corroboration in a log line. If WorkSpace is ever expected
   to send it reliably, making it required on the v1 schema is a one-line
   change and turns a second, sharper dedup key on. If it is not, the field is
   documentation of an intention.
3. **Should a late `payment_ref` on a replay be RECORDED rather than reported?**
   Today it is discarded and named — in the log at WARNING and in the response
   — which satisfies rule 3 but still loses the reference. Writing only
   `workflow_payment_ref` would violate none of the five things the acceptance
   list forbids a replay from writing, and it would close the loss. It is a
   contract decision and it was not mine to make inside this handoff.
4. **A second `queried` carrying a NEW question is discarded.** The handoff
   said `queried` "gets the same treatment for the same reason", and it does —
   but a decision arrives once while a question can legitimately arrive twice
   with different text. The discard is reported rather than silent. If repeat
   queries are a real WorkSpace behaviour, `queried` should probably dedup on
   `(outcome, comment)` rather than on outcome alone; the machinery to compare
   the comment is already there.
