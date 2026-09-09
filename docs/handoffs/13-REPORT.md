# Report 13 — The rest of the numbers that are not true

**Builder → Architect.** Branch `fix/honest-counts` off `dev`. Handoff 12's PR
(#57) **had merged** before this started, so Step 0 needed nothing beyond the
branch. Handoff 13's own instruction file was committed to local `dev` but
never pushed; it rides in on this branch's first commit.

---

## Environment facts

Two for `docs/ENVIRONMENT-FACTS.md`, both cost time here.

**Odoo 19 runs ProxyFix only when the request carries `X-Forwarded-Host`.**
`odoo/http.py`, `Application.__call__`: `if config['proxy_mode'] and
environ.get("HTTP_X_FORWARDED_HOST")`. The dev nginx sends `X-Forwarded-For`
and `X-Forwarded-Proto` and not that one, so **ProxyFix never runs on the dev
stack** even though `proxy_mode = True` is set in all four configs. The visible
consequence: `last_used_ip` reads `172.20.0.4` — the nginx container — on every
API client row in every local tenant, and has since the field was added.

**Postgres crash-restarted mid-session** while an `odoo shell` and a pytest run
overlapped. It recovered on its own ("database system was not properly shut
down; automatic recovery in progress" → "ready to accept connections") and no
data was lost: all ten databases are present and the row counts match the
pre-work baseline. `RestartCount=0` on the container, and the same
"all server processes terminated; reinitializing" line appears repeatedly in
this log going back to August — so it is a standing condition of this dev
stack, not something this work introduced. It cost twenty minutes and one
discarded test run.

---

## What was built, in plain terms

Six numbers this product publishes were being worked out from a sample and
presented as facts about the whole register. They are now counted over the
whole register. Two of them turned out not to be samples at all — they were
permanently zero, and had been on every tenant since they were written.

The four the handoff named:

1. **The facilities dashboard's SLA percentage.** It divided overdue requests
   by open requests, taking both from the newest 500 requests only. It is
   published at `GET /api/v1/fm/dashboard` and it wears the name of a
   compliance figure.
2. **The four facilities KPIs beside it** — open, overdue, escalated, in
   progress — same 500-row sample, standing next to a fifth that was a real
   count.
3. **The fleet dashboard's breakdowns by state and fuel type**, tallied over
   the first 100 vehicles and returned next to a real total, so the columns did
   not add up to the headline in the same response.
4. **The operations dashboard's vendor count.**

And two things found while fixing them, neither of which the handoff knew
about, and both worse than the defect they were hiding behind:

5. **The "in progress" KPI has always been zero, on every tenant.** It filtered
   on a stage code of `progress`. Every tenant ships `new, triage, in_progress,
   resolved, closed`, and the string `'progress'` appears nowhere else in this
   repository. A windowed number at least moves; this one sat beside four that
   did and was never questioned.
6. **The vendor count has always been zero too**, and so has the vendor list
   under it. The code that builds each vendor row reads a field called
   `state_id` off the vendor model, and that model has no such field — its
   columns are name, contact, email, phone, specialisation, approved, active,
   notes. The resulting error went into a bare `except Exception: pass`, the
   list came back empty, and the count was the length of the empty list. The
   web page told tenants "No approved vendors yet. Add via Fleet → Vendors"
   whether they had vendors or not. This is the third member of the family that
   already contains the print funnel: **a guard or a fallback that swallows the
   thing it was meant to protect.**

Also built: the two rulings. A client's tokens are now revoked when its
pagination limits change, and the source IP is on `/auth/token` failure log
lines with a label saying how much it is worth.

---

## 1 · Did the guard catch anything I had not already found?

**Yes — one, in the file the handoff was pointing at.** `team_workload` on the
facilities dashboard, a per-assignee tally accumulated inside a loop over the
same 500-row window. The handoff named lines 35 and 53-57 and 89-99; this is
line 122, and it is the same defect. It is fixed.

It did not find a sixth file. That is a real answer rather than a null one: the
scan covers every first-party module, and the shape genuinely does not occur
elsewhere.

Run against the three files as they stand on `dev` and as they stand now:

```
BEFORE (dev)  myservice_fm_dashboard/controllers/dashboard.py: 9 finding(s)
    line 53: len() of all_open, a capped window
    line 54: len() of overdue, a capped window
    line 55: len() of escalated, a capped window
    line 56: len() of in_progress, a capped window
    line 69: len() of category_groups, a capped window
    line 89: len() of reqs, a capped window
    line 90: len() of a comprehension over a capped window
    line 92: len() of a comprehension over a capped window
    line 122: a tally over a capped window          <-- the one nobody had found
AFTER  (HEAD)  myservice_fm_dashboard/controllers/dashboard.py: 0 finding(s)

BEFORE (dev)  myservice_fleet_maintenance/controllers/fleet_dashboard.py: 2 finding(s)
    line 73: a tally over a capped window
    line 104: a tally over a capped window
AFTER  (HEAD): 0 finding(s)

BEFORE (dev)  myservice_dashboard/models/dashboard.py: 1 finding(s)
    line 325: len() of vendors, a capped window
AFTER  (HEAD): 0 finding(s)
```

**It is a shape guard, not a pinned list.** It walks every first-party function
in **source order**, tracking which names hold a bounded fetch, and flags three
things: `len()` of a limited `search()`, `len()` of anything derived from one,
and a `+ 1` tally accumulated inside a loop over one. Source order with a kill
on rebinding matters — a flow-insensitive first version flagged an honest tally
forty lines below an unrelated capped search purely because the loop variable
was also called `v`.

**On your "if the AST cannot distinguish, say so".** It cannot, and it does not
try. `len(records) > limit` inside a paginator is correct code with a byte-for-
byte identical shape. So the four honest sites carry an inline
`capped-count-ok:` comment stating why, in the contiguous comment block
immediately above the line — contiguous so a waiver cannot drift onto a
statement it was never written for. Removing the comment fails the guard; there
is a test that does exactly that. A waiver somebody has to write out turns a
silent wrong number into a sentence somebody chose to write. The four:

| site | what it counts |
|---|---|
| `utils.paginate` | the page it just fetched; `total` beside it is the register |
| `v1.assets_export` | `count` = rows in this response, `total` = the register |
| `asset_tag._next_tag_number` | a sequence number, not a count of anything |
| `workflow_dispatch_log` drain | "the window came back full, book another pass" |

**Proven to fail before it passes**, four ways: the parametrised shapes from
this handoff (each of A1-A4 as it actually appeared), five honest shapes it
must not flag, the waiver-removal test, and the before/after over the real
files above.

---

## 2 · The eight remaining routes with no envelope handler under them

All nine are `type="http"`, so an unhandled exception does not produce a Cadra
envelope — it produces Odoo's own HTML error page with a 500, which is what
handoff 12 met on `/auth/token`. Every one of these is reachable, and five of
them are reachable **unauthenticated**.

| route | auth | what an unhandled exception returns, and the most likely way in |
|---|---|---|
| `POST /api/v1/auth/login` | none | HTML 500. `get_params()` is called before any validation, so a non-string `login` or `password` reaches `authenticate()`. It has an `except AccessDenied` and a broad `except Exception` around the secret lookup, so it is better covered than most — the exposure is the parse and the pre-auth path. |
| `POST /api/v1/auth/refresh` | none | HTML 500. `refresh_token` is checked for truthiness and then hashed; a non-string reaches `hashlib.sha256(...encode())` and raises `AttributeError`. Exactly the `/auth/token` defect, one route over. |
| `POST /api/v1/auth/revoke` | none | HTML 500, and **no try/except anywhere in the function.** Same non-string path as refresh. Advertised as always answering `200 {"revoked": true}`, which it does not under a malformed body. |
| `GET /api/v1/openapi.json` | none | HTML 500. It builds the spec by reflecting over every registered route; a malformed annotation on any future endpoint takes the whole document out, unauthenticated. No try/except. |
| `GET /api/v1/docs` | none | HTML 500. Renders the Swagger shell. Lowest severity of the nine — static. |
| `GET /api/v1/assets/export.csv` | JWT inline | HTML 500 **mid-stream**. Auth is enforced inline, then rows are written into a response; an exception after the first byte gives the caller a truncated CSV or a 500 depending on buffering. The artefact that gets saved and emailed. |
| `POST /api/v1/integrations/employees/import` | JWT inline | HTML 500. Takes a caller-supplied payload of employee rows and has no try/except; a bad row type raises inside the loop, after earlier rows may already have been written. |
| `GET /api/v1/brand` | none | HTML 500. Resolves the tenant from the Host header and returns branding. Unauthenticated and hit by the SPA on every cold load, so a failure here is a blank-branded app rather than an error anybody reads. |

The pattern worth costing: the four `/auth/*` routes share one shape — parse an
unauthenticated JSON body, then use a value from it before checking its type.
`/auth/token` was fixed with a two-line type check. The same two lines apply to
`login`, `refresh` and `revoke`, and would close the unauthenticated 500 on all
four without the larger `@cadra_route` refactor. The other five need the
refactor, or at least a handler.

---

## 3 · What the IP actually resolves to

**Locally: `192.168.65.1`, labelled `,infra`.** That is Docker Desktop's host
gateway — the nearest address our own proxy vouches for. Before this change the
same request recorded `172.20.0.4`, the nginx container, because ProxyFix never
runs here (see Environment facts). One hop closer to the truth, and the label
says out loud that it is still a private address rather than a caller.

Live, on `jaizbankplc`, all four failure shapes:

```
WARNING jaizbankplc cadra.auth: request_id=2103f403... client_id=... outcome=no_such_client   ip=192.168.65.1 ip_source=xff+1,infra
WARNING jaizbankplc cadra.auth: request_id=223f06e1... client_id=no_such_client_here outcome=no_such_client ip=192.168.65.1 ip_source=xff+1,infra
WARNING jaizbankplc cadra.auth: request_id=b7d6ec2c... client_id=TEST_CLIENT outcome=case_mismatch matched=test_client ip=192.168.65.1 ip_source=xff+1,infra
WARNING jaizbankplc cadra.auth: request_id=064771ae... client_id=test_client outcome=bad_secret ip=192.168.65.1 ip_source=xff,infra
WARNING jaizbankplc cadra.auth: request_id=88df9375... client_id=test_client outcome=bad_secret ip=192.168.65.1 ip_source=xff+2,infra
```

Read the last three lines together. The fourth had no forwarded header from me,
so nginx added one entry: `xff`. The third had my forged
`X-Forwarded-For: 102.89.44.17`, which nginx appended the real peer to — and
**the forged value is not in the log**, because only the right-most entry is
used and the count of the rest is reported as `+1`. The fifth had two forged
entries: `+2`. A caller cannot make us record a claim as an observation.

**In the cluster I could not verify it** — no kubeconfig on this machine, so
this is reasoning, not measurement. ingress-nginx does set `X-Forwarded-Host`,
so ProxyFix will run there and `remote_addr` agrees with what we compute. The
open question is what ingress-nginx itself sees: with DigitalOcean's load
balancer at the default `externalTrafficPolicy: Cluster` and no proxy protocol,
the client address is SNAT'd at the node and the right-most entry will be a
node address — private, therefore printed as `ip_source=xff,infra`. With proxy
protocol or `externalTrafficPolicy: Local` it will be the real caller and read
`ip_source=xff` with a public address. **Which one you have is visible in the
line itself**, which is why the `,infra` label exists rather than a comment in
the docs. First failing login from staging answers it in one grep.

One thing I hardened beyond the ruling, because adding this field would
otherwise have reopened the hole `log_safe` was written to close: **`ip=` is the
last field on the line, and spaces are legal in a header value.**
`X-Forwarded-For: 1.2.3.4 outcome=ok` would have written a second field under
our own logger name. An IP field may contain an IP or nothing, so the value is
printed only after `ipaddress` has parsed it; anything else logs
`ip=? ip_source=xff,unparsable`. Two tests cover it.

---

## 4 · Wall-clock

**1h 40m**, branch creation (10:45 UTC) to the last green suite. Roughly: 20m
reading and scoping, 25m the four fixes and the two zeros, 25m the guard (most
of it on false positives — the flow-insensitive first version was unusable),
20m tests and the fail-before-pass proofs, 15m the live seed-measure-unseed on
`jaizbankplc`, 15m lost to the Postgres crash. The final full pytest run took
9m 4s of that on its own, competing with the cron worker catching up on
`cadra19`.

---

## What was proved, and how

### The counts, live at volume — `jaizbankplc`

The handoff asked for a tenant past 500 open requests or a seed. **I seeded**:
`jaizbankplc` held 261, so 400 marked probe rows took it to 661, with 120
overdue and 90 escalated in a second category. Same data, both versions of the
code, through the published endpoint with the tenant's real service credential:

| number | old code | new code | SQL truth |
|---|---|---|---|
| `kpis.open` | 500 | 661 | 661 |
| `kpis.escalated` | 116 | 158 | 158 |
| `kpis.overdue` | 120 | 120 | 120 |
| `kpis.in_progress` | 0 | 0 | 0 |
| Emergency Response · open | 100 | 261 | 261 |
| Emergency Response · escalated | 26 | 68 | 68 |
| H13 probe · open / overdue / sla_pct | 400 / 120 / 70 | 400 / 120 / 70 | 400 / 120 |
| sla columns sum to `kpis.open` | 500 ≠ 661 | 661 = 661 | — |
| workload columns sum to `kpis.open` | 500 ≠ 661 | 661 = 661 | — |

The tenant's own real category was reported as holding **100** open requests
when it holds **261**. Its SLA percentage happened to survive at 100% because
it has no overdue requests at all — which is the point worth making about
`sla_pct`: it goes wrong when a **category** straddles the window, and nothing
in the response tells you whether yours did.

**The 400 probe rows and the probe category were deleted afterwards.**
`jaizbankplc` is back to 261 open, 261 total, zero H13 categories, verified
through the same endpoint.

### In-registry, on `test19`

Three new test files, 15 tests, seeded past each window in a transaction that
rolls back. Every one proven to fail on the pre-fix code first:

```
0 failed, 0 error(s) of 8 tests    myservice_fm_dashboard          (fixed)
4 failed                            myservice_fm_dashboard          (pre-fix)
    AssertionError: 500 != 520      kpis.open answered the window
    AssertionError: 0 != 7          in_progress: the stage code that does not exist
    AssertionError: 200 != 220      a category understated by 20
    AssertionError: 150 not <= 50   the overdue LIST was unbounded

0 failed, 0 error(s) of 15 tests   myservice_fleet_maintenance + myservice_dashboard  (fixed)
7 failed                            (pre-fix)
    AssertionError: 100 != 130      the state breakdown vs its own headline
    AssertionError: 100 != 130      the fuel breakdown vs its own headline
    AssertionError: 34 != 44        one state column
    AssertionError: 0 != 9   x3     kpis.vendors — ZERO, not six
    AssertionError: [] is not true  the vendor sample was empty

0 failed, 0 error(s) of 29 tests   myservice_api                   (fixed)
```

`0 != 9` on the vendor tests is how the second structural zero surfaced. I had
written the assertion expecting the old code to answer 6.

### The two rulings, live on `test19`

```
cap claim in the minted token:              {'total_record_cap': 500}
refresh BEFORE the cap change:              200
CAP NOW 25  LIVE FAMILIES 0
refresh AFTER the cap was narrowed:         401
cap claim on the NEXT token:                {'total_record_cap': 25}
```

### Suites

```
tests/test_source_guards.py                    52 passed
CADRA_API_BASE=http://jaizbankplc.localhost:8069 pytest tests/ -q
                                               285 passed, 27 skipped in 544.81s
```

The 27 skips are the usual admin-scoped tests the suite's token cannot reach,
plus the pagination tests that skip loudly when a tenant fits inside the cap.

**One piece of noise worth naming so nobody else chases it.** The in-registry
runs log `ERROR: cannot execute INSERT in a read-only transaction` dozens of
times and pass anyway — Odoo 19 dispatches on a readonly cursor and retries on
a read/write one. It is not caused by anything here: `TestPaginationCap`, which
this handoff did not touch, produces 21 of those lines on its own and reports
`0 failed`.

---

## Deviations and decisions

**1 · I fixed `in_progress` as well as making it honest.** A2 asked for four
KPIs counted truthfully. Counting `stage_id.code = 'progress'` truthfully still
returns zero forever, so "honest" would have meant a rigorously correct count
of nothing. Changed to `in_progress`, the code every tenant actually ships. This
changes a published number from a constant zero to a real count.

**2 · I fixed the vendor row builder, not just the vendor count.** A4 asked for
`kpis.vendors` to agree with `get_kpis()`. Making the count a `search_count`
does that, and would have left the sample beside it permanently empty for the
same reason it always was. The `state` now comes from the vendor's contact
record, which has the field, and the bare `except Exception: pass` logs a
warning instead of swallowing — that except is legitimately there for tenants
without the fleet module, and it was hiding a `AttributeError` for three years'
worth of tenants that have it.

**3 · The overdue list is now capped at 50 rows; it was unbounded within the
window.** It could return every overdue request in the register, and on a real
NRS estate that is a payload nobody asked for. `kpis.overdue` beside it reports
the true number, so a reader sees 50 rows against a count of 215 and knows what
they are looking at. This is a behaviour change to a list, and I would rather
flag it than have you find it.

**4 · `last_used_ip` now uses the same resolver as the failure log.** B2's
reasoning is that logging the IP on failure "only makes the two paths
consistent" because `last_used_ip` already records it on success. It did not —
it recorded the proxy. Implementing only the failure half would have left the
two paths inconsistent in the other direction, which is the opposite of the
stated goal.

**5 · I did NOT change the dev nginx to send `X-Forwarded-Host`.** It would
make dev match the cluster and fix `remote_addr` product-wide, but it also
switches on ProxyFix's host and protocol rewriting on every local request, and
that is a change to how the dev stack routes tenants — not something to slip
into a counting handoff. The resolver does not depend on it. Flagged above as
an environment fact instead.

**6 · No module version bumps and no per-tenant upgrade.** Nothing added a
stored field, a view or a data file; this is Python and tests only, so a
container restart is the whole deployment step. The 8-tenant fan-out in
CLAUDE.md is for column changes and there are none.

---

## Where B1 does not reach, stated plainly

Revoking the refresh families is built and proven. **It does not make a reduced
cap take effect on the next request**, and the acceptance criterion says it
should. The cap is stamped into the access JWT as a claim, and an access token
is unrevocable for its lifetime by design — so a caller holding a live token
keeps the old ceiling until it expires, whatever we do to its refresh family.
The three things that could close that gap are: read the cap off the client
record per request (which B1 explicitly and correctly rejects), read it only for
requests whose token claims MORE than the default (few callers, fails safe,
still a read on Vendra's hot path), or shorten `token_ttl_seconds`.

**Measured before saying so:** every API client on every local tenant is at the
3600-second default — `cadra19`, `nrs19` (all three clients), `gtb19`,
`jaizbankplc`. That is the window your own ruling calls acceptable. The
86400 you called indefensible is configurable and is configured nowhere. So the
gap is real and currently empty, and I would rather you rule on it than have me
pick.

---

## Open question

**The bare `except Exception: pass` is a repo-wide pattern and it has now
concealed two published defects** — the vendor list here, and report 12's
`except: pass` on integer query parameters. `get_fleet_command` alone has three
more. Each one is a live path where a field rename, a missing module or a typo
returns a plausible-looking empty answer instead of an error. This is the same
class as the capped counts and it is bigger: a count that is too small is at
least a number, while this returns "there are none". Worth a handoff of its own,
and worth a guard, but the guard is harder — some of those excepts are load-
bearing for tenants without the fleet or asset modules.
