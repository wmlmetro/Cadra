# Handoff 10 — Report

**Branch:** `fix/print-funnel` → PR into `dev`. **Base:** `dev` at `ee0d866`.

*(Note: `233c419`, the commit carrying this handoff's own instruction file, was
left on `fix/stale-computes` after PR #53 merged and is not on `dev`. It is
cherry-picked as the first commit of this branch, so the handoff arrives with
the work that answers it.)*

**Both suites green.** Odoo in-registry, exactly as CI now runs it —
**171 tests across 8 modules, 0 failures, exit 0**:

| module | tests |
|---|---:|
| `myservice_workflow` | 56 |
| `myservice_asset_register` | 52 |
| `myservice_asset_depreciation` | 16 |
| `myservice_request_fields` | 15 |
| `myservice_security` | 14 |
| `myservice_fleet_maintenance` | 8 |
| `myservice_barcode_station` | 6 |
| `myservice_nrs_base` | 4 |
| **total** | **171** |

pytest API suite: **250 passed, 27 skipped** — the same baseline as report 09.

**The headline is that fixing the id space was not enough.** The handoff
diagnosed a guard that declined 99.97% of prints, and it was right. Underneath
it, Odoo 19 declares the report route `readonly=True`, so the cursor serving a
print **cannot write at all** — and Odoo's own Print menu is exempt, because it
goes through a read/write route that calls the render as a plain Python call.
So printing recorded from the web client and silently did not from the
published URL. Both are fixed, and the second is proved live through the
readonly route: `%PDF`, 13,549 bytes, label `HQ-GF-MR-FF-001` on `cadra19`
going `issued → printed` at 09:20:55.

**The estate before this branch: 16,874 labels at `issued`, 2 at `printed`, and
341 at `affixed` that never passed through `printed` on the way.**

---

## Needs the owner

1. **Merge the PR** (standing — the permission layer refuses `gh pr merge`).
2. **`upgrade-19` for every tenant carrying `myservice_asset_register`, at or
   before the image roll** (carried forward from handoff 10's own Step 0 —
   still true, and this handoff adds nothing that changes it).
3. **The telemetry's cluster half** — `deploy-dev` with `roll_odoo` enabled,
   then `upgrade-19` with `myservice_nrs_base` across every tenant. Also
   unchanged — **but from this branch onward, not doing it makes the deploy go
   RED rather than green.** See Part B.
4. **The first `deploy-dev` run after this merges will FAIL, correctly.** The
   new guard compares the running `odoo-19` pod against the ConfigMaps the run
   just applied. Handoff 09's `publisher_warranty_url` is in the repo's
   ConfigMap and has never been rolled, so the guard's first firing *is* that
   finding, surfaced. Clearing it is item 3.

---

## A · The print funnel

### What was wrong, measured

`nrs.asset.tag.label.label_state` moves `issued → printed` from exactly one
place — `ir.actions.report._render_qweb_pdf` — because the label wizard, the
barcode station's raw `/report/pdf/` URL and Odoo's own Print-menu binding all
bypass every Python action method. That much was right.

The hook then **declined to stamp whenever `res_ids` could be tag-label ids**,
on the reasoning that the two id spaces collide and a wrong guess would
fabricate a print record on an unrelated asset. Measured on `nrs19` today:

| | |
|---|---|
| assets | 11,932 |
| tag labels | 11,932 |
| asset ids that are also valid label ids | **11,928 — 99.97%** |
| labels at `issued` | 11,879 |
| labels at `printed` | **1** |
| labels at `affixed` | 52 |

Every asset mints a label on creation, so the two sequences advance in step and
the collision is not an edge case, it is the shape of the data. The guard fired
on every normal print.

**Estate-wide the number is starker.** Across all eight tenants:

| tenant | issued | printed | affixed | total |
|---|---:|---:|---:|---:|
| `cadra19` | 1,335 | 0 | 0 | 1,335 |
| `nrs19` | 11,879 | **1** | 52 | 11,932 |
| `gtb19` | 156 | 0 | 0 | 156 |
| `test19` | 0 | 0 | 0 | 0 |
| `nrs` | 1,272 | 0 | 0 | 1,272 |
| `lasg` | 150 | 0 | 0 | 150 |
| `gtb` | 150 | 0 | 0 | 150 |
| `jaizbankplc` | 1,932 | **1** | 289 | 2,222 |
| **total** | **16,874** | **2** | **341** | **17,217** |

**Two prints recorded across seventeen thousand labels**, and 341 labels reached
`affixed` — a state that can only be entered through a confirmation carrying a
scanned tag number — without one of them ever passing through `printed`. A
lifecycle that skips its middle state on 341 of 341 occasions is not a
lifecycle. This is the shape the owner met when he tagged five assets by hand
and found `printed_at` null.

### The disambiguation — report question 1

**There is exactly one channel that reaches the renderer, and it is the ids.**
This is the fact the design turns on, and it is not obvious:

`web/static/src/webclient/actions/reports/utils.js` turns a report action into
`/report/pdf/<report_name>/<active_ids>` and posts it to `/report/download`
with `context: JSON.stringify(userContext)` — the **user** context, not the
action's. Everything a caller puts in the action's own context is dropped at
the browser. `web/controllers/report.py:42` then calls
`_render_qweb_pdf(reportname, docids)` and nothing else.

So a context flag, a `data` key, a wrapper method — none of them survive. The
only thing a caller can say is *which numbers*. Which forces the rule, and the
rule is the framework's own:

> **`res_ids` are ids of the report's declared model.** For all four tag
> labels that is `nrs.asset`.

That is enforced **at the boundary**, in an override of
`ir.actions.report.report_action`: for the four tag reports, a recordset whose
`_name` is not the report's model raises a `UserError` naming both models, the
collision, and the fix. A bare int or list carries no model and is left alone —
that is the raw form the HTTP route uses, where the framework's contract
already settles it.

**The two callers that passed tag ids were not merely ambiguous — they rendered
the wrong asset.** The label templates read `o.asset_tag`, `o.asset_code`,
`o.floor_room` and `o.get_barcode_base64` off an `nrs.asset`; handed a tag id,
Odoo browsed `nrs.asset` with it and rendered whichever machine shared the
number. **53 labels on `nrs19` have an id that differs from their own asset's
id**, and those are the ones that would have come out wrong. So the fix is not
"translate for them", it is "stop them lying": `action_print_tag` and the label
wizard now pass assets, and the hook has nothing left to guess.

With the boundary closed, `_stamp_printed_tags` browses `nrs.asset`, maps to
`active_tag_id` and calls `_mark_printed()` — unconditionally.

### Does anything else rely on the two id spaces colliding?

**No.** Every other site that touches both is already collision-aware and
correct, and each says so in a comment:

| Site | What it does |
|---|---|
| `myservice_api/controllers/v1_assets.py:205` | publishes `data.tagging.label_id` precisely so a caller never has to guess |
| `myservice_barcode_station/controllers/main.py` `print_url` | takes a **label** id, returns a URL carrying the **asset** id |
| `myservice_workflow/models/asset_tag_event.py:106` | names the INT-05 payload key `tag.label_id`, not `id` |
| `tests/test_barcode.py:128` | exists because it used to pass an asset id here and went green only by collision |
| `Frontend/.../src/lib/labels.ts` | composes labels client-side; never builds a report URL |

The one place that *did* rely on it was the hook's own guard, which is the bug.

### The stamp moved off the action methods

`action_print_asset_tag`, `action_batch_print_tags` and `action_print_tag` no
longer call `_mark_printed()`. `report_action` only hands the client an action
— the PDF may never be fetched, and on a company with no
`external_report_layout_id` (every tenant here) an admin gets the layout
configurator instead. `_render_qweb_pdf` is the moment a print instruction
actually exists. One funnel, one record.

### Two more things the tests found

Neither was in the handoff. Both were found by writing a test that renders.

**1 · The A4 sheet report has never rendered anything, on any tenant.**
`action_report_asset_tag_sheet` is declared **twice**: in
`data/asset_tag_report.xml` on `nrs.asset`, and again in
`views/asset_tag_views.xml` on `nrs.asset.tag.label` with
`binding_model_id = model_nrs_asset_tag_label`. The views file loads later
(manifest position 24 vs 19), so the second declaration wins — and it defeats
the `<function>` force-update sitting in the data file for exactly this reason.
Verified on all eight tenants before the fix: `report_asset_tag_label_sheet →
nrs.asset.tag.label` everywhere.

The sheet template calls `asset_tag_label_body`, which reads four fields that do
not exist on a tag label. So the "Print Labels" binding on the tag list, and
`action_batch_print_tags` on the asset list, both pointed at a report that
raises. The duplicate is deleted; the `<function>` now resets `binding_model_id`
as well as `model`; and `nrs.asset.tag.label.action_print_labels` — reachable
from a `<header>` button on the tag list — is what the binding was reaching for,
translating the selection to assets first.

A test asserts all four reports declare `model = nrs.asset` and that none is
bound to the tag-label list. A force-update could not carry this: one already
existed and was overwritten again minutes later, every upgrade.

**2 · The barcode station's batch print had the 404 that handoff 05 fixed in
the controller.** `barcode_station.js` built the URL itself as
`/report/pdf/myservice_asset_register/action_report_asset_tag/<ids>` — the
action's **xmlid** with its dot turned into a slash, which matches no report
and does not even match the route. Handoff 05 fixed exactly this in
`get_print_url` and the JS copy was missed. It also did the tag→asset
translation in the browser off a cached `_allTags`.

Both halves now go through `/barcode/print_url`, which gained a `tag_ids` batch
form: it reads `report_name` off the action record and resolves the assets from
the tags server-side, preserving the requested order.

### The bigger half: the cursor serving a print CANNOT write

**This is the finding of the handoff, and fixing the id space would not have
been enough without it.** Odoo 19 declares the report route:

```python
@http.route(['/report/<converter>/<reportname>',
             '/report/<converter>/<reportname>/<docids>'],
            type='http', auth='user', website=True, readonly=True)
```

`readonly=True` puts the request on a **read-only Postgres cursor**. Any write
raises `cannot execute UPDATE in a read-only transaction`. So with the ids
finally unambiguous and the hook finally reaching `_mark_printed()`, the stamp
still could not be recorded through the one path the barcode station and the
published `GET /api/v1/barcode/print-url` actually use.

**And it is worse than "printing never records".** Odoo's own Print menu goes
through `/report/download`, which is read/write and calls `report_routes` as a
plain Python method — a route's `readonly` flag does not apply to a direct
call. So printing records from the web client and silently does not from the
published URL. It looks like it works.

The stamp now takes its own read/write cursor from the registry and commits
independently. That is also the honest transaction boundary: the PDF has been
produced by the time the stamp runs, so the print instruction has been issued
whatever becomes of the request afterwards.

**Proved live, on committed data, through the readonly route.** A real HTTP
session on `cadra19`:

```
POST /web/session/authenticate            → uid 7 (h10_print_proof, group_asset_user)
POST /barcode/print_url {"tag_id": 1}     → /report/pdf/myservice_asset_register.report_asset_tag_label/1
GET  that URL                             → http=200 bytes=13549 type=application/pdf
                                            %PDF-
```

and in the database immediately afterwards:

```
1 | HQ-GF-MR-FF-001 | printed | 2026-09-08 09:20:55 | h10_print_proof
```

`cadra19` went from 1,335 labels at `issued` and 0 printed, to 1,334 and 1.
Nothing but that HTTP request touched it.

**Why this is proved live and not in the suite.** Inside `HttpCase` the
registry hands back a genuinely separate connection, which cannot see records
the test created and never committed — so the stamp lands on nothing and
`label_state` stays `issued` however correct the production behaviour is. The
first version of these tests asserted the stamp there and failed; asserting it
in a way that passed would have meant asserting something else. The HTTP tests
now assert what the HTTP hop really does prove — the URL the route builds, that
it resolves to a report at all, and that the document rendered is the right
ASSET's label — and say so in their own docstring, pointing here for the rest.

### The test that replaces two negative assertions

`tests/test_tagging.py::test_printing_records_who_printed_and_when` was named
for acceptance criterion 1 and asserted `printed_at is None` **twice**. It could
not have done better: `/report/pdf/` is `auth='user'` and that suite holds a
bearer token, not an Odoo session, so **nothing in the repository could render a
report at all**. It is renamed `test_minting_a_tag_is_not_printing_a_label`,
which is the guarantee it actually holds.

The coverage moved to `myservice_asset_register/tests/test_print_funnel.py`,
where the render happens: every real caller is driven through
`_render_qweb_pdf`, the rendered body is asserted to carry *that asset's* tag
number (so a wrong-record render fails, not just a missing stamp), and one test
passes `force_report_rendering=True` to get past Odoo's own test-mode HTML
fallback and assert a real `%PDF` off wkhtmltopdf.

---

## C · The small ones

### R45 — `_compute_next_due` rewrote its own answer every day

A `nrs.asset.pm` with an interval and no `last_done_date` got
`next_due_date = today`. That is not a due date, it is the absence of one: it
moved with the clock, so `is_overdue` (computed in the same pass) could never
be true, and handoff 09's brand-new daily refresh cron rewrote every such row on
every tick to say nothing had changed. The Architect's phrasing — "the bug you
just spent a handoff fixing, in a different costume" — is exact.

It now anchors on `create_date`: a PM set up today on a 90-day interval falls
due in 90 days and is overdue on day 91. The alternative anchor (creation
itself, so it is due immediately) was rejected — it asserts the asset is
overdue for a service on the day someone typed the schedule in, which is a
claim about a service history nobody supplied.

**Latent when changed:** `select count(*) from nrs_asset_pm` returns **0 on all
eight tenants**, which is what makes it safe to correct now — R29's reasoning,
applied a third time. `data.pm[].next_due_date` is published, so it is in
`docs/api/CHANGELOG.md` anyway.

Three tests in `test_stale_computes.py`, alongside the class they belong to:
the anchor is one interval out; the date does not move when the clock does; and
the cron leaves a settled row's `write_date` alone.

### R46 — `security_tabs.js`, and the thing behind it

R46 said one field. A live-registry audit of **every** `search_read` in the file
— the whole class, not the reported instance — found **eight absent field names
across four tabs, plus six models that do not exist at all**, plus a KPI strip
reading six keys its own controller has never returned.

| Tab | Model | What was wrong |
|---|---|---|
| Guards | `security.guard` | `shift_start`, `shift_end` (never existed — a shift belongs to a roster row), `location_id` (the field is `home_location_id`) |
| Access Logs | `security.access.log` | `name`, `visitor_name`, `entry_time`, `exit_time` (a row is one movement with a `direction` and a `datetime`, not an entry/exit pair; the person is `person_name`), and `order: 'entry_time desc'` |
| Duty Roster | `security.duty.roster` | `name`, `shift_type` (the field is `shift`) |
| Intelligence / Daily Briefs / State Threats / AI Patterns / Watchlist | `osint.feed.entry`, `ai.daily.brief`, `security.state.threat`, `ai.pattern.alert`, `security.watchlist` | **none of these models exists anywhere in the repository** |
| KPI strip | `/myservice/security/kpis` | read six flat top-level keys; the controller returns three nested groups, so every card fell through `|| 0` and the dashboard reported a confident zero for everything |

The guard proves both ways. Green: `myservice_security: 14 tests 29.34s 307
queries`, exit 0. Broken deliberately (`home_location_id` → `location_id`):

```
FAIL: TestSecurityTabsFields.test_every_search_read_names_fields_that_exist
AssertionError: ['.../security_tabs.js:203 — security.guard has no field(s):
location_id'] is not false
EXIT_CODE=1
```

A guard nobody has watched fail is not known to be a guard — handoff 09's R31
habit, applied again.

`search_read` validates the whole `fields` list before reading anything, so one
absent name raises for the entire call — the tab does not render a blank column,
it sits on "Loading…" for ever. `order` is checked for the same reason.

**The tabs whose models do not exist were removed** (7 tabs across two client
actions). This is the one place this handoff widened, and it is a
product-visible removal, so it is flagged rather than buried: a tab advertising
"State Threats" that can only ever spin is the same false-completeness claim as
a `label_state` that reads `active` from creation. Reverting it is a one-line
change per tab if the Architect disagrees.

**And the finding that reframes R46 entirely.** Neither `security_tabs.js` nor
`security_dashboard.js` is in **any asset bundle** — `myservice_security`'s
manifest ships only three CSS files — and both are written in Odoo 15
`odoo.define` syntax against `web.AbstractAction` and `web.rpc`, **neither of
which exists in Odoo 19**. Verified in the container: no file under
`web/static/src/` defines either module. So the RPC does not raise when the tab
is opened; **the tab cannot be opened, because the JavaScript never loads.**

The same is true of `myservice_barcode_station/static/src/js/barcode_station.js`
— that one IS in `web.assets_backend`, but it depends on the same two dead
modules, so the client action fails to load on 19 as well.

The code is now true, which is worth having and is what R46 asked for — and the
guard will fail the moment someone ports the file and gets a name wrong. It does
not make the Security Command Center work, and saying otherwise would be the
"reports success having changed nothing" defect in prose. **Open question 1
below asks whether these two client actions are being revived on 19 or retired.**

`views/dashboard_views.xml` already carries the comment *"replaces broken JS
dashboard"* — so this was known at the time and the JS was orphaned rather than
removed.

**A correction to a handoff 05 claim, while we are here.** Report 05 recorded
the `dict(field.selection)` fix on `/barcode/lookup` as also repairing "the
barcode station's own scan box". The station's JS cannot load on 19, so that fix
only ever reached the API and portal paths.

**Two more, found and not fixed**, both named rather than left for the next
reader to assume they were covered:

* **`security_dashboard.js` is the same defect, larger** — `search_read` /
  `read_group` against four models that do not exist, plus `rpc.query` to
  `/myservice/security/osint` and `/state_threats`, neither of which is a route
  in that module's controllers (it has `kpis`, `map_data`, `trend`, `recent`).
  Widening the guard's `JS_PATH` to it today would make the suite red, so it is
  named in the test's own module docstring instead.
* **`security_tabs.xml`'s "Open in full view" buttons carry hard-coded numeric
  action ids** (331, 332, 336, 333). Database ids are not portable across
  tenants, so on any tenant but the one they were read from these open the wrong
  action or none.

**One replacement I would have got wrong.** The brief suggested showing
`active_duty_id` on the Guards tab in place of the invented shift fields.
`security.duty.roster` has no `name`, so its `_rec_name` is None and
`display_name` renders as the literal `security.duty.roster,5` — a column of
those is worse than no column. The tab shows badge, base location and
specialisation instead, and the shift stays where a shift lives.

### R47 — two badges

The chain was exactly two rungs (`t-if sla_breached` → `t-elif` priority in
`('2','3')`); there were no "due soon"/"on track" rungs to reason about. Split
into two independent `t-if`s, breached first. Nothing else was split, because
nothing else was chained, and no rung was added.

Two things came out of the test rather than the change:

* The first version of the data-level tests **passed on the pre-fix arch**.
  They evaluated the two conditions in isolation, where both are true of a
  breached Critical request even while the `t-elif` hides one — green tests of
  nothing, the failure mode handoff 09 named. Rewritten to walk the container
  the way QWeb does, skipping a `t-elif` whose chain already took a branch:
  three of the five now fail on the old arch. The arch is read through
  `get_view` rather than `arch_db`, so a re-chaining from an inheriting view is
  caught too.
* `badge-danger` / `badge-warning` are **Bootstrap 4** class names and Odoo 19
  ships Bootstrap 5 — verified in the container: `_badge.scss` has no colour
  variants and `helpers/_color-bg.scss` defines `.text-bg-#{$color}`. Both
  badges were rendering as plain grey pills. Two grey words are not two badges,
  so they are now `text-bg-danger` / `text-bg-warning`. These were the only two
  Bootstrap-4 badge classes in the repository's views.

---

## B · Changes that never take effect

**Chosen: LOUD.** `deploy-dev` and `deploy-19` now end by comparing the
**running `odoo-19` pod** against the two ConfigMaps the run just applied, and
**fail the job** on any difference, naming the button to press.

Rolling automatically was rejected. `odoo-19` is `strategy: Recreate` on an RWO
filestore, so a roll briefly interrupts **every live tenant**; doing that on
every merge, to pick up a comment change in `odoo.conf`, would be a worse defect
than the silent no-op it replaces. That trade-off is written into the failure
message itself, so whoever meets it understands why it is a button.

**How it compares, and why not a checksum annotation.** The obvious shape —
stamp `cadra.ng/config-checksum` on the pod template and `sed` it in — was
tried and rejected on a fact I had not accounted for: **`upgrade-19.yml` is a
third applier of `41-odoo-19-deployment.yaml`**, and it would apply the manifest
with the placeholder still literal. Handoff 10's own "Needs the owner" item 2
requires an `upgrade-19` fan-out across every tenant, so the annotation would go
stale immediately after a *routine, correct* operation, the next push would go
red for a non-reason, and everyone would learn to ignore it. **A marker only
some appliers set is worse than no marker.**

So the guard measures the thing directly and is applier-agnostic:

* `kubectl exec deploy/odoo-19 -- cat /etc/odoo/odoo.conf.template` against the
  cluster's `odoo-config-19`, diffed;
* `printenv <KEY>` against every key of `odoo-bootstrap-19` — which covers the
  `envFrom` half an annotation over the two files would have covered less
  honestly.

It also covers `deploy-19`'s skip-the-roll branch (`run_bootstrap=true` on an
already-running `odoo-19`), which produces the same applied-but-inert state.

**A second, smaller instance of the same defect, fixed in all three appliers.**
`sed "s|REPLACE_ME/cadra-odoo-19:dev|...|"` that matches nothing applies a
manifest with the placeholder intact and reports success. All three sites now
refuse to apply a render still containing `REPLACE_ME`. The third — the one I
added outside the agent's ownership — is `upgrade-19.yml`, which runs
`if: always()` including on the rollback path, where getting the image wrong is
least likely to be noticed.

**Proof (static only — there is no cluster access on this machine):** every
touched YAML parses; `bash -n` over every extracted `run:` block in all three
workflows (24 + 9 blocks) passes; `k8s-lint`'s own kubeconform run passes
17/17; the `sed` pipeline was dry-run against the real manifest showing the
before/after image line, plus a negative control where a deliberately wrong
pattern is caught and would exit 1; and the guard step itself was extracted and
run against a stubbed `kubectl` in five scenarios — match, `odoo.conf` drift
(using the real pending `publisher_warranty_url` case, which produced the
unified diff), env drift plus a key absent entirely, no Deployment, and
`kubectl exec` failing — each with its own message and exit code.

**Expect the first `deploy-dev` after this merges to be RED, and that is the
point.** Handoff 09's `publisher_warranty_url` is in the repo's ConfigMap and
`odoo-19` has never been rolled to pick it up. The guard's first firing *is*
handoff 10's owner-blocked item 3, surfaced instead of assumed.

**Not fixed, flagged:** `upgrade-19` scales `odoo-19` to 0 mid-run, and the
three workflows sit in three separate concurrency groups, so an overlap would
fail the guard on `kubectl exec` with "is the pod running?". Rare, real, and
closed by a shared concurrency group across the three. Also: the guard needs
`pods/exec`, which today's full cluster token has and a future least-privilege
deploy identity must keep.

**`docs/GO-LIVE.md` did not exist in this repository.** Handoff 10 refers to it
as carrying items 2 and 3 "on the Vendra side as well"; there was no Cadra copy,
and `docs/DEPLOYMENT.md` is entirely about the Compose profiles and does not
mention the cluster. It is now written: the tenant-fan-out-before-image-roll
ordering with the INT-03 incident that proves it, the ConfigMap propagation rule
with both remediations, the outstanding telemetry state, the Turnstile pairing,
and "installing modules is not provisioning a tenant". The same instructions
also live in the guard's failure message, its comment block and both workflow
headers, because a runbook nobody opens is not where a failing job should send
someone.

---

## Per-tenant fan-out

`myservice_asset_register`, `myservice_barcode_station`, `myservice_security`
and `myservice_request_fields`, one tenant at a time, as one-off containers
with the resident workers stopped (see deviation 2):

| tenant | exit | ERROR/CRITICAL lines | time |
|---|---|---|---|
| `cadra19` | 0 | 0 | 19s |
| `nrs19` | 0 | 0 | 22s |
| `gtb19` | 0 | 0 | 65s |
| `test19` | 0 | 0 | 213s |
| `nrs` | 0 | 0 | 45s |
| `lasg` | 0 | 0 | 43s |
| `gtb` | 0 | 0 | 45s |
| `jaizbankplc` | 0 | 0 | 18s |

**The verification that matters** — the A4 sheet report's `model` and
`binding_model_id`, which were `nrs.asset.tag.label` on **all eight** tenants
before this branch:

| tenant | `action_report_asset_tag_sheet` |
|---|---|
| `cadra19` | `model=nrs.asset` `binding=nrs.asset` |
| `nrs19` | `model=nrs.asset` `binding=nrs.asset` |
| `gtb19` | `model=nrs.asset` `binding=nrs.asset` |
| `test19` | `model=nrs.asset` `binding=nrs.asset` |
| `nrs` | `model=nrs.asset` `binding=nrs.asset` |
| `lasg` | `model=nrs.asset` `binding=nrs.asset` |
| `gtb` | `model=nrs.asset` `binding=nrs.asset` |
| `jaizbankplc` | `model=nrs.asset` `binding=nrs.asset` |

`action_report_asset_tag` is `nrs.asset`/`nrs.asset` everywhere and the `small`
and `large` variants carry no binding, as designed — checked in the same query.

**No data migration ships and none is needed.** The `<function>` in
`data/asset_tag_report.xml` corrects both fields on every `-u`, which is what
the table above shows; and `_compute_next_due`'s new anchor touches zero rows
because there are zero `nrs.asset.pm` rows on any tenant.

---

## Report question 2 — the R43 number

Measured on `nrs19`'s largest category, which is the real scale the ruling
asked about — **`IT Equipment`, 10,259 assets**, no rows created for the test:

| | |
|---|---|
| `category.write({'verification_interval_days': …})` returns in | **0.133s** |
| flush complete (every dependent compute written) at | **1.766s** |
| statements issued | 15, of which **1** is an `UPDATE` on `nrs_asset` |

**The trade is settled: keep the dotted `@api.depends`.** 1.8s is comfortably
inside any proxy timeout, so `PATCH /api/v1/settings/categories/{id}` stays
synchronous and does not become a queued job returning `202`. Shortening a
category's window keeps biting immediately.

The single `UPDATE` is the part that makes this safe rather than lucky: the
recompute is batched, so cost grows with one statement's row count and not with
the number of assets. A regression to row-at-a-time is what would turn 1.8s into
minutes, and that is what the test asserts — with a `assertTrue(seen)` guard,
because the first version of this test counted zero statements and zero is
indistinguishable from a counter that never ran.

`myservice_asset_register/tests/test_verification_window_scale.py` measures
whatever scale the database it runs on actually has, topping up to a floor of
1,500 only where there is nothing real to measure — `nrs19` (10,259) and
`jaizbankplc` (1,778) both clear it on their own data and create nothing.

---

## Deviations from the handoff

1. **The handoff's Step 0 could not be followed literally.** `233c419` — the
   commit carrying handoff 10 itself — was left on `fix/stale-computes` after
   PR #53 merged, so `git checkout dev && git pull` produces a tree with no
   handoff 10 in it. Cherry-picked as the first commit of this branch. Not a
   defect in the handoff's content; worth saying because the next one will hit
   the same thing if the pattern repeats.

2. **I fanned three subagents out onto the same Odoo stack, which CLAUDE.md
   forbids, and it cost about forty minutes.** "Serialize anything sharing
   state ... run one at a time in the main session" exists for exactly this:
   three concurrent `-u <module> --test-enable` runs plus the Frappe stack on
   the same machine took the host to load average 54–76 and crash-looped
   postgres four times, killing all three runs mid-registry-load. One of the
   agents diagnosed it and told me to serialize. Partitioning by FILE was
   right and held perfectly — no agent touched another's files. Partitioning
   the DATABASE is the part the rule is about, and I read it as being about
   correctness when it is also about capacity.

3. **Scope widened in three places, each argued rather than assumed:** the
   duplicate sheet-report declaration and the barcode station's batch-print 404
   (both found by writing a test that renders — Part A); the whole
   `security_tabs.js` class rather than R46's one field, including removing
   seven tabs whose models do not exist (Part C); and the Bootstrap 5 badge
   classes, without which R47 delivers two grey words rather than two badges.

4. **`upgrade-19.yml` was edited outside the Part B agent's ownership**, to add
   the same `REPLACE_ME` render check its two siblings got. It is the third
   applier of that manifest and the only one running `if: always()`.

---

## CI would not have run the new tests

`myservice_barcode_station` was **not in CI's `-u` module list**, and CI does
not pass `--workers=0`. Both are fixed in `.github/workflows/ci.yml`, and the
second matters more than it looks: under the prefork server every test in an
`HttpCase` errors in `setUpClass` before it runs, and the run still reports
"6 tests" and exits 0. A suite that looks green while proving nothing is the
exact failure the CI step's own comment says it exists to end — *"1,464 lines
of tests were running nowhere; implicit is how that happens."*

The `ERROR: cannot execute INSERT in a read-only transaction` lines in the log
are Postgres refusing Odoo's own attachment write during the forced real-PDF
render on the readonly route. Core swallows it, the tests pass, and it is the
same finding as Part A seen from the framework's side.

---

## Open questions

1. **Are the Security Command Center and the barcode station's backend client
   action being revived on Odoo 19, or retired?** Both are `odoo.define` modules
   requiring `web.AbstractAction` and `web.rpc`, neither of which exists on 19;
   `security_tabs.js` and `security_dashboard.js` are additionally in no asset
   bundle. Everything R46 asked for is done and the code is now true, but no
   pixel of either changes until they are ported to OWL. This is a bigger
   decision than a handoff item and it is not mine to take. If they ARE being
   revived, `security_dashboard.js` is the worse of the two — it reads four
   models and calls two routes that do not exist — and it is deliberately not
   covered by the new guard, which is named in that test's docstring rather
   than left for the next reader to assume.

2. **Should the three deploy workflows share one concurrency group?**
   `upgrade-19` scales `odoo-19` to 0 mid-run; the new config guard reads the
   running pod. They are in three separate groups today, so an overlap fails the
   guard with "is the pod running?". Rare and real.

3. **`docs/GO-LIVE.md` is now written on the Cadra side** — the handoff's
   phrasing ("on the Vendra side *as well*") reads as assuming one exists here,
   so I wrote it rather than asking and shipping nothing. If the intent was a
   single shared file in the Vendra repository, this one should be deleted and
   its content moved; it is four sections and no code depends on it.

---

## Report question 3 — wall-clock

| | |
|---|---|
| Elapsed, start of Step 0 to PR opened | **~2h30m** |
| Of which, lost to the host's memory starvation | **~1h15m** — four postgres crash-restarts, six killed runs, and the serialisation that followed |

The machine, not the work, was the cost centre. The Docker VM has 7.75 GB and
runs the nine-container Frappe/Vendra stack alongside Odoo; the Mac was down to
tens of MB free. The host OOM killer took postgres backends out from under six
separate runs (`server process exited with exit code 2`,
`statistics collector … terminated by signal 9`). Stopping the resident Odoo
service and running every upgrade and test as a one-off
`docker compose run --rm --no-deps` container fixed it outright — the eight
tenant upgrades that had been dying then took 18–213s each. That is worth
knowing for the next handoff: **on this machine, serialise and use one-off
containers, and do not assume a failed run means a failed change.**

