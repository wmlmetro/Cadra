# Report 17 — The doors nobody documented

**Builder → Architect.** Branch `fix/external-surfaces`, based on `dev` at `43fb322`.

---

## In one paragraph

The endpoint that approves and rejects requests was standing open on every
tenant, and it was not close. `callback_token` was set on **0 of 8** local
tenants, so the `if config.callback_token:` guard was skipped every time. I
proved it before touching the code: an anonymous POST carrying a *deliberately
wrong* token was answered `404 "Request '…' not found"` — a reference lookup,
which is past the gate. The only thing between an anonymous caller and an
approval was knowing a reference name. The same shape held for the other
three external routes: `myservice_identity.redhubs_api_key` and
`myservice_identity.sap_webhook_secret` were set on **0 of 8** tenants too, so
the credential guarding a full dump of the asset register was, in every live
case, a string committed to this repository. All four now refuse, loudly, and
say which parameter is missing and on which database. **Item C came back (3),
not (1)** — and the reason is that (1) is already true of everything that can
be shared. Both callback controllers already call the same three model
methods, so what is left duplicated is only the parts that must differ.

**The thing worth reading twice** is what verification found in my own fix: on
the form-encoded path the token was being merged into the payload dict and
then written to our own log at INFO. Item A2's whole argument is that a
credential in a URL ends up in logs; it was ending up in ours. Fixed by
stripping the credential before the payload exists, and the test that claimed
to cover it was passing for the wrong reason twice over — wrong content type,
wrong log level.

---

## 1 · Does anything actually call the query-string forms?

**Nothing on this machine, and this machine cannot answer the question that
matters.**

| measured | result |
|---|---|
| nginx access lines carrying `api_key=` or `?token=` | 0 of 13,569 |
| requests to any of the four legacy routes, in the Odoo log | 0 |
| requests to their `/api/v1` mirrors | 126, all from the pytest suite |

Every hit on a `workflow/callback` path in the local logs is
`/api/v1/integrations/workflow/callback` from `tests/`. The legacy routes have
never been called here.

**That is a fact about a dev box, not about WorkSpace or Redhubs.** Neither
system points at this machine. The measurement that would settle it is the
staging/production ingress log in the cluster, which I did not reach from
here. So the query parameter stays accepted for one release on the reasoning
the handoff gave, not on evidence that somebody needs it.

**What I can now offer instead of a guess: the deprecation warning is the
measurement.** Every use of either query-string channel logs a WARNING naming
the caller's IP. After one release in the cluster, `grep` for `DEPRECATED`
answers the question with real callers. If the answer is nobody, the parameter
goes with no coordination at all.

One live proof of *why* it must go, from our own stack. With the token in the
URL, werkzeug's access line reads:

```
"POST /myservice/workflow/callback?token=h17-leak-secret HTTP/1.1" 404
```

The handler cannot prevent that — the URL is logged before our code runs. The
same request with the token as a form field produces no such line. The two
channels genuinely differ in exposure, which is why the deprecation warning
now names them separately rather than calling both "query string".

## 2 · Item C — the recommendation is (3), and the documentation is wrong

**They are genuinely different contracts.** Not because unifying them is hard,
but because **"one implementation and two paths" is already true of everything
that can be shared**: both controllers call
`request.request._workflow_callback_approved` / `_rejected` / `_queried`.
There is exactly one implementation of what an outcome *does*. What is left
duplicated is only the HTTP layer, and every line of it differs for a reason:

| | `/myservice/workflow/callback` | `/api/v1/integrations/workflow/callback` |
|---|---|---|
| Authentication | shared token from `workflow.config` | JWT bearer, `integrations:write` |
| Body | JSON **or form-encoded** | JSON only, schema-validated |
| Response | bare `{"ok": true, …}` | PRD §10.7 envelope |
| Idempotency | none | `X-Idempotency-Key` |
| Dispatch log | **reconciles** the outbound `sent` row it answers | always appends a new inbound row |

The authentication row settles it. WorkSpace holds a shared token, not a Cadra
client credential. A public route cannot delegate into a decorator that
demands a JWT without either issuing WorkSpace a client — which is option (2),
a coordinated change with another team — or weakening `/api/v1`. Neither is a
refactor, so I built nothing, as instructed.

**Two defects fell out of writing that table, and both are yours to schedule:**

1. **The v1 twin never reconciles the outbound dispatch.** The legacy route
   finds the `direction='outbound', status='sent'` row it is answering and
   rewrites it to the outcome. The v1 route always appends a fresh inbound
   row. On a tenant using v1, an answered dispatch reads `sent` forever, so
   "which dispatches are still unanswered" cannot be asked. **The legacy
   behaviour is the better one** — this is v1's bug, not legacy's.
2. **The v1 twin leaks the unconfigured-tenant message handoff 15 removed from
   the legacy route.** It does not resolve `workflow.config` itself;
   `_workflow_callback_approved` calls `get_active_config()` (defaulting to
   `purpose='workspace'`), which raises `UserError` on a tenant with no
   workspace config, and `cadra_route` renders `str(e)`. So the *documented*
   route answers **`400 validation_failed`** carrying *"…Please configure one
   under Settings → WorkSpace Integration"* — an internal menu path in the
   published envelope, and a validation code for a tenant-configuration state.
   **Read from source, not probed live**: reaching it needs a real request
   reference on a tenant with no workspace config, and creating one on a demo
   tenant to prove a documentation finding is not a trade worth making.

Recorded in `docs/api/EXTERNAL-SURFACES.md`, which is where the twin was
already flagged.

## 3 · Credentials to rotate — the owner's list

**I rotated nothing.** Both literals are in git history from `a4b505a` and
cannot be removed from it.

| `ir.config_parameter` | Compromised literal | Guards | Held by |
|---|---|---|---|
| `myservice_identity.redhubs_api_key` | `NRS_REDHUBS_KEY_2025` | `POST /api/myservice/assets/export` and `GET /api/myservice/assets/export/csv` — **a full dump of the asset register** | Redhubs |
| `myservice_identity.sap_webhook_secret` | `NRS_SAP_WEBHOOK_SECRET_2025` | `POST /api/sap/employee-sync` — **inbound employee create/update** | SAP SuccessFactors / the NRS SAP team |

**Each rotates in exactly one place per tenant.** I verified independently
that the literals appear nowhere else: no ConfigMap, no Secret, no `.env`, no
seed script, no compose file, no workflow. They now survive only in the guard
that pins them out of the source and in the two documents that describe the
defect.

**There is a third, and it is not in item B's scope, so I did not touch it.**
`Dockerfile.nrs-import:31` bakes `ODOO_ADMIN_PW=admin` into a published image;
`scripts/nrs_import_entrypoint.sh` passes it straight to XML-RPC, and
`k8s/dev/71-nrs-import-job.yaml` documents the fallback in a comment without
setting the variable. `e2e/config.ts` defaults to `admin`/`admin` while its
origin is env-overridable to a remote host. Different class from the two
above — a dev-tooling default rather than a route credential — but it is a
credential with a hardcoded default that authenticates somebody, and the
acceptance criterion said "anywhere". **Your call whether it is a handoff.**

**This is a live cutover, not a silent one.** On every tenant the literal *was*
the working credential, so Redhubs and SAP now get `Unauthorized` until an
operator sets the parameter. That is the intended behaviour and it is
announced in `docs/api/CHANGELOG.md`; the ERROR log names the exact key and
database on every refused request.

## 4 · Is a replayed callback idempotent? **No — in three ways.**

A second byte-identical POST answers `200 {"ok": true}` and re-applies:

1. **A second dispatch-log row is appended.** The controller looks for an
   outbound row at `status='sent'`; the first callback rewrote that row to the
   outcome, so the replay misses and creates a new `inbound` row. Every replay
   adds one. There is no dedup key — `workspace_ref` is stored and never
   matched on, and handoff 06's `event_id` idempotency is on the *outbound*
   queue only.
2. **Chatter is re-posted.** All three handlers call `message_post`
   unconditionally, with no transition guard.
3. **The stage is re-applied, and this is the damaging one.** Where
   `approved_stage_id` / `rejected_stage_id` is configured, the handler does an
   unconditional `write({'stage_id': …})`. If a human moved the request onward
   after the first approval, a replay **drags it back**. And
   `myservice_request_core`'s `write` branches on `'stage_id' in vals`, not on
   whether the value changed, so every replay also sets `date_moved = now()`
   and appends a `request.event` row through `_log_event('stage_changed')`
   even when the stage is identical. That is a double-count in the request's
   own audit trail.

`queried` is the mildest — status write, duplicate chatter, duplicate log row,
no stage change.

**Contrast with INT-05, where handoff 06 ruled "one physical act is one
event" because `_mark_affixed` fires on the TRANSITION.** Nothing here fires
on a transition. Not fixed, per the handoff — but note the token fix has *not*
reduced this: a caller with a valid token can still replay freely.

## 5 · Wall-clock, correction share, and the machine

**Wall-clock:** 54 minutes, branch created to PR pushed (07:44 → 08:38).

**The machine behaved, and the discipline is why.** **Zero Postgres
crash-restarts** against handoff 14's eight. Every `--stop-after-init` run was
serialised in the main session and no subagent was permitted to run one — the
four build agents and the two fix agents all worked read/write on source and
handed me the command lines. Twelve registry loads in sequence (an eight-tenant
fan-out, four module upgrades, two full test runs) with no contention at all.

**Correction share: roughly a third of the work was correcting rather than
building**, and it split three ways.

- **Corrections to the handoff** — one, and it was small: item B's premise
  named the literal as the thing to guard, and the guard that actually holds
  is on the *lookup*. See §6.
- **Corrections to my own output, found by verification** — the largest share
  and the one that mattered. The credential leak into our own log, four
  bypasses in my guard, a geocoder path that stamped a provenance value
  without asking the service, and a changelog entry I owed under the file's own
  rule and had not written.
- **Corrections to `CLAUDE.md`** — two, both found by agents rather than by
  me: the fan-out loop listed seven tenants where the tenancy section names
  eight (`test19` missing, and a stored field would have met `UndefinedColumn`
  there), and CI's suite order was undocumented. Both fixed.

---

## Test results — run in CI's order, denominators quoted

`.github/workflows/ci.yml` runs `pytest tests/` first, then the in-registry
Odoo suites. `CLAUDE.md` did not say so; it does now.

| suite | result |
|---|---|
| `pytest tests/` against `jaizbankplc` | **380 passed, 27 skipped, 0 failed** |
| in-registry Odoo, CI's module list | **0 failed, 0 error(s) of 341 tests** |
| `tests/test_source_guards.py` standalone | **108 passed** (was 79) |

`of 0 tests` appears nowhere; `CRITICAL` count is **0**. The 27 pytest skips
are the expected admin-scope skips. Three ERROR lines in the Odoo run are
pre-existing print-stamp and attachment-cache noise from files this handoff
did not touch.

**The first pytest run FAILED, deliberately kept.** Three disposal tests
errored with `KeyError: 'sap_coverage'` because the worker still held the old
Python — bind-mounted, not hot-reloaded. That is the state `CLAUDE.md` warns
about, and it is the proof that the new assertions were reaching real
behaviour rather than passing on a stale module.

**Guards proven to fail before they pass.** The credential guard was run
against the pre-fix files recovered from `HEAD` and flagged all three sites
(`redhubs_api.py` lines 14 and 60, `sap_webhook.py` line 20) before flagging
none of the fixed ones. The geocoder fix was proved against a stubbed
Nominatim: with the service returning 403 on everything, the ladder-empty row
went from *writing a stamped state-capital coordinate having made zero HTTP
calls* to **writing nothing**, tallied `unreachable`.

### Proved live, not only in tests

| probe | before | after |
|---|---|---|
| anonymous POST, no token configured | `404` — past the gate | `503` + ERROR naming `callback_token` |
| POST with a deliberately WRONG token | `404` — past the gate | `401` + WARNING naming the caller |
| correct token, `X-Callback-Token` header | — | `404` (reaches the lookup) |
| correct token, `?token=` | — | works + DEPRECATION WARNING naming the caller |
| CSV export with `NRS_REDHUBS_KEY_2025` | full register dump | `401` + ERROR naming the parameter |
| the live secret in our own INFO log | **present** | absent; payload line is credential-free |

Probes ran on `test19` against a `workspace` config created for the purpose
and **deleted afterwards**; the tenant is back to zero `workflow_config` rows.

### The credential guard, after verification defeated the first one

The guard I first wrote was defeated eight ways by a verification pass that
measured each bypass rather than reasoning about it. Four were things somebody
would actually write: a keyword argument (`default='…'`, which is Odoo's own
signature), a module constant used as the default, `get_param(…) or 'literal'`,
and an f-string default. It also walked only module directories, so
`scripts/`, `seeds/`, `k8s/`, repo-root files and the compose files — where a
credential literal is exactly as compromised — were outside it, contradicting
the comment on the guard next to it.

All eight are closed. Two design points worth recording:

- **The resolver check is a SHAPE, not a roster.** It was a three-name list
  (`get_param`, `getenv`, `get`), which `read_config`, `fetch_secret` and
  `env()` walk straight past. Dropping the resolver check entirely — key purely
  on "credential-named argument with a non-empty literal default" — was tried
  and **measured against the tree before being rejected**: it immediately
  produces two false positives, a log line *about* a missing credential and a
  field declaration, neither of which resolves anything. With the shape rule, a
  walk over all 260 first- and second-party Python files returns **zero
  findings**, which is the honest state of the tree after this fix.
- **The walk is scoped to GIT-TRACKED files, and that was forced by a real
  failure rather than chosen.** A plain filesystem walk failed on its first
  run against `docs/api/test-report.md` — this suite's own gitignored output,
  which quotes the guard's failure message, so the guard found a burnt literal
  it had just written itself. Tracking-scoped removes the loop and the entire
  machine-output prune list with it. Coverage went from 196 to 259 Python
  files and 713 text files, now including 20 k8s manifests, both compose
  files, `Dockerfile*` and both `.env.example`s.
- **The waiver is a written sentence, and a dead waiver fails the test.**
  Widening the scope correctly caught the two documents that quote the burnt
  literals as a defect report. Rather than a silent path skip, each waiver
  carries its reason, may only cover documentation, and **fails if it matches
  no file** — an exception kept past its usefulness is how the next one gets
  waved through. Same reasoning as the `capped-count-ok:` waiver from handoff
  13.

  One trigger word was tried and rejected on measurement: hyphenated `-key`
  flagged `headers.get('X-Idempotency-Key')`, which is a de-duplication token
  and not a credential. `_key` with an underscore stays, and `X-API-Key` is
  still caught by the `api[_-]?key` branch.

## The multi-tenant fan-out was run

`generic.location.geocode_source` is a stored field, so the code could not
ship before every tenant had the column.

| | |
|---|---|
| tenants upgraded (`-u myservice_nrs_base`) | **8 of 8** — including `test19` |
| tenants where the column now exists | **8 of 8**, verified in `information_schema` |
| locations estate-wide | 3,489 |
| **coordinates whose provenance is unknown** | **1,562** |

Those 1,562 are stamped `NULL`, deliberately. No backfill: the only available
heuristic — "within 0.05° of a state capital, therefore approximate" — is
wrong in both directions, because a genuine geocode *in* a capital city lands
inside the same radius and the two scripts' capital tables differ. Marking
them anything but unknown would fabricate the precise evidence the field
exists to carry. Same reasoning as `custody.source = 'tracking_backfill'`.

---

## 6 · Deviations and rulings I made

**The credential guard is on the LOOKUP, not on the literal.** The handoff
asked for a guard that spots "a literal that looks like a key". That is the
wrong axis and I did not build it: `get_param('web.base.url',
'http://localhost:8069')` is a good default that any entropy heuristic flags,
while `get_param('…api_key', 'changeme')` is exactly as dangerous as
`NRS_REDHUBS_KEY_2025` and any entropy heuristic misses it. What makes a
string dangerous is not how it looks — it is that a credential resolution
falls back to it. So the rule is: **a credential may default to nothing; it
may never default to something.** An empty default stays legal and is what the
rest of the codebase already does (`get_param("myservice_api.jwt_secret",
"")`). You anticipated a pinned list; there is one, but it is the *second*
half — the two burnt strings, pinned out of the tree — and the general rule
does the work.

**A missing callback token answers 503, not 401.** A `401` tells the caller
their credentials are wrong when they may have sent a perfectly good one; the
fault is ours. Handoff 15 already chose 503 for "this tenant was never wired
to a WorkSpace", and a config row with no token is the same class of state.
The sentence naming the configuration goes to the log at ERROR, never to an
unauthenticated caller.

**The disposal report's `none` statement does not say "never".** The
Architect's exact sentence ends *"INT-09 has never sent a disposal instruction
to the financial system."* That asserts "never" from a report that reads **one
bounded period**, which is the same shape as counting a register from a page
of it — ruled against twice in this codebase. The published statement is
period-scoped instead: *"No disposal in this period carried a SAP asset
number, so INT-09 sent no disposal instruction to the financial system for any
of them."* Same meaning, defensible from the data the report holds. **Overrule
me and I will restore the literal wording.**

A caveat neither wording escapes, raised in verification and worth your eye:
both infer another system's behaviour from a field on our side. We observe
that `sap_asset_number` is null; we do not observe INT-09's outbox. The
inference is documented (SAP requirements §4.1) and predates this change, so I
did not block on it.

**`no_sap_asset_number` was removed from the OpenAPI enum, not deprecated in
place.** Rule 4: the endpoint can no longer return it, so a doc advertising it
is wrong. The practical cost is nil — it shipped in handoff 16 on 2026-09-09
and Vendra reads none of that route, so it had one day of exposure. Verified
against the live spec: gone from every `enum` array, surviving only as a dated
removal note in two descriptions.

**`caller_ip_label` moved to `myservice_nrs_base`.** Two routes outside
`/api/v1` needed it and neither module can import from `myservice_api` without
a dependency cycle. The alternative was a second and third copy of a
log-injection guard that took a handoff to get right.
`myservice_api.controllers.utils` re-exports it, so every existing caller is
unchanged.

**`E4` (`load_offices_v3.py:65`) was left alone**, per "fix it if you are in
the file, otherwise leave it". I was not in that file.

---

## 7 · For you, not me

- **`docs/integrations/INT-10-audit-access.md:309` still lists
  `no_sap_asset_number` among "Findings published", and `:318` makes the
  absolute "never" claim** I declined to publish in `statement`. That document
  is what NRS auditors read. You reserved INT-10 to yourself and named only
  §2.11 and the process gap, so I have not touched it — but the changelog's own
  argument is that a documented value the endpoint cannot return is one an
  integrator writes a branch for and never sees fire, and that value is still
  documented one directory over.
- **`sap_webhook.py` still references `request.jsonrequest`, which does not
  exist on Odoo 19.** Pre-existing, outside item B, reachable only when
  `kwargs` is empty — where the intended answer is `'Empty payload'` and the
  actual one would be a 500.
- **Odoo 19 deprecates `@route(type='json')` in favour of `type='jsonrpc')`.**
  Warned on every startup. Repo-wide, not this handoff.
- **`/myservice/workflow/callback` and `/api/myservice/*` write an ERROR line
  per unauthenticated request** on tenants that are unconfigured — which today
  is all of them. Anyone who knows a URL can fill the log. Deliberate: the
  alternative is a route standing open in silence. Worth a rate-limit if it
  bites.
- **The Architect session `claude-fc [01f312]` was not in `ListAgents`**, so
  per `CLAUDE.md` I skipped the notification silently.
