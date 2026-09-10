# Report 21 — The filters that answer with everything

**Branch:** `fix/query-params-validate` · **Commit:** `d8e6d98` · **Base:** `dev` at `c62ce92`
**PR:** owner-blocked at merge, as every handoff ending in a PR is.

---

## 1 · The five, first and before anything else

There are **seven**, not five, and two of the seven fail in a shape report 05's
inventory did not describe. Both corrections matter to how the finding reads.

| Parameter | Endpoint | What it filters | What a bad value returned |
|---|---|---|---|
| `is_verified` | `/assets` | whether the last physical verification is still inside its window | **The whole register.** Both branches were membership tests with no `else`, so `?is_verified=1` appended nothing and every asset came back reading as verified. |
| `closed` | `/requests` | open vs closed | **Every request**, open and closed together, to a caller asking for one of the two. |
| `has_deadline` | `/requests` | work with and without a due date | **Every request.** There was no `false` branch at all — `?has_deadline=false`, "which work has nobody put a date on", returned the lot, and every row in it read as undated. |
| `is_staff_bus` | `/fleet` | staff buses vs the rest | **The whole fleet.** |
| `has_coordinates` | `/locations` | mapped vs unmapped sites | **Every location.** Also `true`-only, so the survey-gap question returned the survey. **Report 05's inventory missed this one entirely.** |
| `active` | `/identity/employees` | active vs archived staff | **Not the unfiltered list — the DEFAULT one.** The `else` branch appends `active = True`, so `?active=1` answered with the active roster to somebody who asked for the archived one. |
| `active` | `/locations` | active vs archived sites | Same. |

The two `active` parameters are worth separating out, because they are
arguably the worse failure of the two. An unfiltered list is conspicuously
large. A plausible active-only roster invites no second look at all.

**And `has_deadline` and `has_coordinates` are the reason the tests assert a
partition rather than only a 400.** Both had a `true` branch and no `false`
branch, so a test that checked only the refusal would have called them fixed
while `?has_deadline=false` still returned everything. `false` now filters on
both.

All seven refuse an unreadable value with a `400 invalid_request` naming the
parameter and carrying `details.allowed_values = ["true", "false"]`. The
accepted spellings are exactly the ones `is_tagged` has published since
handoff 01 — `true`, `True`, `false`, `False` — and were deliberately not
widened. Accepting `1` or `yes` would be a second silent reinterpretation of
a value the caller may have meant as something else, which is the same family
of bug one layer along.

`active` keeps its documented default: absent or empty still means
`active = true` on both lists. Only a value that is **present and unreadable**
is refused.

---

## 2 · Whether any published enum starts refusing a value somebody is sending today

**Yes — one, and it is ours.** The Cadra SPA sends `?condition=damaged`, and
`nrs.asset.condition` has never had that value. It is
`new, good, fair, poor, decommissioned`.

So the asset register's "Faulty" filter chip has always answered `200 []` and
the "Damaged" dashboard tile has always shown `0` — reading as "there are no
faulty assets" rather than "that filter does not work". The create form
offered `damaged` too, which the ORM has always rejected. Three broken things,
none of which said anything.

Server-side validation turns that silence into a 400, so the SPA is corrected
in the same commit rather than reported and left: the phantom becomes the
model's real fifth value and the user-visible label becomes "Decommissioned",
which is what it means. `npx tsc --noEmit` is clean and `damaged`/`Faulty`
have zero remaining hits in `src/`.

While fixing it we found the client-side twin of this whole handoff:
`CONDITION_TO_API` was a `Record<string, string>`, so an unmapped label
yielded `undefined`, the parameter was dropped, and the SPA fetched the
**unfiltered** register. It is now typed against the model's set, and the
compiler immediately found a loosely-typed filter feeding it.

**Nothing else starts refusing anything.** Every enum validates against the
model's live Selection through `utils.selection_values`, never against its own
annotation, precisely so the accepted set can never be narrower than what the
model allows. Vendra is unaffected: every value it sends sits inside the
published enums.

**The near miss, and it would have taken our own suite down first.**
`request.request.priority` declares five values — `0 Low, 1 Normal, 2 High,
3 Critical, 4 Very Urgent` — and the route published `["0","1","2","3"]`,
describing `3` as "urgent". `tests/test_requests.py` creates a request with
`priority: "4"`. Validating against the annotation would have 400'd a real
value the model has always accepted. Rule 4 decides it: the model wins and the
documentation is what gets corrected, in the query parameter and in the POST
and PATCH body schemas, labels included.

Two more annotations were **wider** than the data rather than narrower:
`domain` and `asset_level` published no enum at all while the model has always
had one. Adding them is additive — any value outside them already answered
`200 []`.

---

## 3 · The thirteen enums, and which side should own the defence

**Server-side, and Vendra's local validation should become a convenience
rather than a control.**

The argument is the one the handoff makes about the booleans, applied one
degree weaker. An empty list for a value the caller mistyped is
indistinguishable from an empty list for a value that genuinely matched
nothing — and the reassuring reading is the wrong one. That is worst exactly
where it matters most: `?sap_reconciliation_state=exceptions`, the plural and
the natural typo, told an auditor asking to be shown the findings that there
are none.

Client-side validation cannot close that, for three reasons that are all
visible in this diff:

1. **It only defends the client that has it.** Vendra validates
   `tag_label_state`; the SPA does not, and the SPA was the one shipping a
   value the model has never had. A control that lives in one of two clients
   is not a control.
2. **It drifts, and it drifts silently.** Vendra's copy of the enum is a copy.
   The `priority` case shows what that costs even inside one repository: our
   own annotation was a stale copy of our own model for long enough that
   correcting it was a documentation change with a behaviour change hiding
   inside it.
3. **The server has the only authoritative list.** `selection_values` reads
   the model's Selection at request time, so a value the model gains is
   accepted the same day. No client can do that.

So: **Cadra owns it.** Vendra's local check should stay as fast feedback in
its own UI, but it is no longer load-bearing and should not be maintained as
though it were. `docs/reference/cadra-vendra-interface.md` §5 trap 3 exists
because Cadra did not validate; it now does, and that paragraph is the
Architect's to write (C2). The one thing worth saying in it explicitly is
that the refusal carries `details.allowed_values`, so a client never has to
hold its own copy of the set to show a user what to type instead.

---

## 4 · Wall-clock, correction share, and whether the machine behaved

**Roughly two and a half hours**, most of it in five parallel agents
partitioned by file, with every stack operation and every git command
serialised in the main session as CLAUDE.md requires.

**The correction share was low but the two corrections were the valuable
part of the run.**

- One agent's `include` validation was written as a hand-rolled
  `if x not in ALLOWED: return err(...)` rather than through the door.
  Functionally identical, and **invisible to the guard** — which is exactly
  how a deleted check goes unnoticed. Rewritten through `parse_enum`.
- **A partition assertion passed on an empty half.** Reverting `has_deadline`
  to its `true`-only form to check the test caught it produced a *green run*:
  nothing on `jaizbankplc` carries a deadline, so `true` returned 0, the
  broken `false` returned everything, and `0 + everything` still summed to
  everything. That is CLAUDE.md's collapsed denominator one layer up, and it
  is the thing in this handoff most worth remembering. The parametrized test
  now **skips loudly** when either half is empty, and a dedicated test creates
  one request with a deadline and one without, scoped to its own asset so the
  record cap cannot truncate it off the end of the page. Re-mutated: it fails.

**The machine behaved.** No Postgres restarts, no registry contention — this
handoff moved no stored field, so there was no fan-out and no migration. Two
container restarts for mutation checks, each clean.

**One thing did not finish:** the fresh verification agent was terminated by
an API rate limit before it reported. Its checks were done by hand instead —
attribution, enum annotations (nothing removed; `state` and `condition` are
rewrapped with every value intact), the static guards, and a live probe. That
is a weaker verification than a fresh reader, and it is the one place this
report is thinner than it should be.

---

## Acceptance

| Criterion | Verdict |
|---|---|
| The five booleans refuse an unparseable value with a 400 naming it, with a test for each | **Met**, for seven. `tests/test_query_params.py` covers each against eight unreadable spellings, plus a partition assertion. |
| Tests prove the unfiltered list can no longer be returned | **Met, with a caveat stated in §4.** The partition assertion is genuinely vacuous on this tenant for four of the seven and now says so out loud rather than passing. `has_deadline` has a dedicated non-vacuous test, mutation-proven. |
| The thirteen enums and eight integers follow | **Met and exceeded** — thirteen enums, nineteen integer filters (report 05 counted eight; `v1_assets` alone has eight), `limit`, `size` and `include`. |
| The door validator does no database work | **Met.** `query_params.py` imports nothing at all. The guard reads its AST, not its text, so its docstring may name what it forbids. |
| The guard covers every declared query parameter, and fails before it passes | **Met.** Both mutations measured on the real tree: deleting a live `parse_bool` fails it; adding an undeclared parameter fails it. |
| `.gitlab-ci.yml` is gone; a newline-bearing credential is refused by name | **Met.** Both mutation-proven — neutering the newline checks fails seven tests; restoring a 15-pinned CI file fails the new guard. |
| Denominators quoted, suites in CI's order, fan-out if a column moves | **Met.** No column moved, so no fan-out. |

### Suites, in CI's order

```
$ CADRA_API_BASE=http://jaizbankplc.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q
657 passed, 32 skipped in 137.42s (0:02:17)

$ docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
    odoo -c /etc/odoo/odoo.conf -d jaizbankplc \
      -u myservice_workflow,myservice_asset_depreciation,myservice_nrs_base,\
myservice_asset_register,myservice_request_core,myservice_request_fields,\
myservice_security,myservice_fleet_maintenance,myservice_barcode_station,\
myservice_api,myservice_identity \
      --test-enable --stop-after-init --workers=0 --http-port=8099 --gevent-port=8098
0 failed, 0 error(s) of 378 tests when loading database 'jaizbankplc'
```

Baseline before this branch: `483 passed, 28 skipped`. The denominator is
**378**, unchanged from report 20, and no `of 0 tests` or `CRITICAL` appears
in the run.

The four extra skips are the vacuity skips of §4 plus one deliberate one:
`is_tagged` published `"null"` as "no filter" before this rule existed and
keeps it, so it is excluded from the `"null"` refusal case rather than made
an exception inside it.

### Live probe

```
GET /api/v1/assets?condition=damaged     400
GET /api/v1/assets?condition=poor        200
GET /api/v1/assets?is_verified=1         400
GET /api/v1/assets?category_id=laptops   400
GET /api/v1/assets?state=active          200
GET /api/v1/requests?priority=4          200
GET /api/v1/openapi.json                 200
```

---

## Deviations, and what was added beyond the brief

1. **Seven booleans, not five**, and `active` is a different failure from the
   one report 05 described. Both stated in §1.
2. **Nineteen integer filters, not eight.** Report 05's figure counted one
   controller.
3. **`include`, `limit` and `size` were added to the scope.** All three are
   the same defect in a different costume: an unknown `include` section was
   dropped, so a body missing the section a caller asked for was
   indistinguishable from a record that has nothing in it; `?limit=all`
   served fifty rows to somebody who believed they had asked for everything;
   and `?size=sheets` on the label printer fell back to `medium`, which is
   not a wrong list but a **wrong piece of paper**, printed, stuck to an
   asset, with a 200 saying it worked.
4. **`limit` keeps its silent clamp.** `?limit=100000` is still clamped
   without complaint — the ceiling is per-credential, so a caller cannot know
   it in advance and refusing them for asking would be unhelpful. Clamping
   and refusing are different answers to different inputs.
5. **`cadra_endpoint` catches `BadFilter` as a floor**, without a rollback,
   so a route written next year answers 400 rather than the 500 a bare
   exception produces. The absent rollback is the point, not an omission.
6. **The SPA was fixed, not just reported** (§2). Shipping validation that
   breaks our own front end and saying so in a report would have been the
   letter of the instruction and not its purpose.
7. **`README.md`'s CRND assembly section was fact-checked** under the new
   convention from C3, since deleting `.gitlab-ci.yml` touched what it
   describes. It linked to `odoo_packager.yml`, which does not exist — the
   file is `odoo-packager.yml` — so the link had been dead since it was
   written.

---

## Open, and not ours to close

**The SPA has four more phantom enums, and two are worse than `condition`
was** — they are write paths, so they fail as 500s rather than as an empty
list.

- **`location_type`**: the location form offers `state` and `office`;
  `generic.location.location_type` is `building, floor, wing, room, zone`.
  Saving either raises. `wing` is never offered, so a wing loaded for edit
  shows a blank select and cannot be re-selected.
- **`domain`**: the asset form takes the FM domain as **free text**, with a
  placeholder advertising a value that is not a member of the set and not
  even the right shape. The correct eight-value list already exists two files
  away and was never adopted.
- **`priority`**: the keys match but every label is shifted one step against
  the model. The blank request form defaults to `"2"`, so **every request
  created from the SPA without touching the dropdown is filed as High.**
- **`asset_level`** is missing `group`, so a group-level asset silently
  demotes if somebody touches the dropdown; **`fuel_type`** collapses nine
  backend values into three on display, so `electric` and both plug-in
  hybrids all render as "CNG".

These are on the backlog in `CLAUDE.md`. None is a query-parameter defect and
none is fixed here.

**`cursor` is the one silent degradation left in this family and it was left
deliberately.** `utils.decode_cursor` returns `{}` for anything it cannot
decode, so a caller paging with a corrupted cursor silently restarts at page
one while believing they are on page three. It is the same shape as the
filters — but unlike them it is *documented* behaviour, and turning it into a
400 is a breaking change that wants a ruling rather than a Builder's decision.

---

---

## Addendum — the CI failure after the PR was opened

**CI went red on this branch, and it was not this branch.** The
`bootstrap-and-test` job died in 1m40s with two lines a hundred milliseconds
apart:

```
  postgres ready after 2s
FATAL: postgres did not become ready
```

The identical code passed on the very next run, which is the signature of a
race rather than a defect in what was being tested. The deployment workflows
(`deploy-dev`, `k8s-lint`) were green throughout and are unaffected.

**The race is in the postgres image and the fault is in our wait.** `initdb`
starts a TEMPORARY server to create the database and run init scripts, then
shuts it down before starting the real one. `pg_isready` answers yes to that
temporary server. `scripts/bootstrap.sh` broke its wait loop on the first
yes, then ran a **second, independent confirmation probe with no retry** —
which landed during the shutdown.

A check that passes, followed by the same check failing. **This repository
has been here before**: the first prod start-up shell refused every correct
configuration because `set -e` killed it on the check that PASSED, and
`tests/test_prod_entrypoint.py` exists because that shell was not runnable by
anything.

So it gets the same treatment.

- The wait now requires readiness to **hold** — three consecutive successful
  probes, tunable by `CADRA_PG_READY_STREAK` — and carries the loop's own
  outcome forward instead of asking a second time. The `pg_ready=0` /
  `pg_ready=1` assignment is written out longhand rather than as
  `check && pg_ready=1`, because that form is what killed the prod
  entrypoint's first draft under `set -e`.
- The failure now says how close it got (`the last streak reached N`) and
  dumps the last 50 lines of the database's log, so an operator can tell a
  slow start from a dead container.
- The reported second is when readiness was **confirmed**, not when the
  first hopeful answer arrived. "ready after 2s" on a build that then failed
  was a number about the wrong server.
- `tests/test_bootstrap_pg_wait.py` **executes the shipped block**, extracted
  between two markers, against a stubbed `docker` that replays a scripted
  sequence of probe results. No docker and no database required.

**Mutation-proven.** Restoring the original wait loop byte for byte
reproduces the CI failure deterministically:
`test_the_initdb_blip_no_longer_fails_the_build` fails with "the wait failed
on a server that came up after a normal initdb blip", along with two others.
Ten tests cover the blip, a lone probe, a flapping server, a database that
never arrives, a healthy fast start, and the two shape guards — no second
probe after the loop, and not the `&&` assignment form.

**Same defect, not fixed, and here is why.** The three k8s init containers
(`k8s/dev/50-bootstrap-19-job.yaml`, `51-upgrade-19-job.yaml`,
`52-depreciation-job.yaml`) run the same single-probe wait. They do **not**
have the double-probe bug — each `exit 0`s on the first success — so they
cannot produce the failure above. They can still latch onto the temporary
server, in which case the main container fails to connect and the pod
restarts into a working database. That is self-healing rather than a red
build, and rewriting three deployment manifests to fix a hypothetical, on a
branch whose subject is query parameters and with no way to test them here,
is a worse trade than naming it. **It is named.**

Suites after the fix: `246 passed` across the five static files
(`test_bootstrap_pg_wait`, `test_prod_entrypoint`, `test_deployment_profile`,
`test_query_param_guard`, `test_source_guards`).

## Three things for the owner, unchanged and still true

- **The Odoo `admin` password is set by nothing in this repository, on any
  tenant.** `ODOO_MASTER_PASSWORD` is a different credential; the new
  line-break refusal covers that one, not this one.
- **The `ODOO_ADMIN_PASSWORD` Secret** must exist before the next
  `nrs-import` run.
- **The two live-cutover credentials from report 17 §3** are still unrotated,
  and they are in git history.
