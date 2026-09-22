# Report 32 — The name and the field

**Branch:** `fix/the-name-and-the-field` · **Base:** `dev` at `65a8a7c`. PR #82 had merged (`6fe9ef6`, 23:54 UTC on the 21st) — the precondition you set.

**Commits:** `fd93a8d` (the work) · this report.

**Needs the owner:**
1. **The PR merge.**
2. **A ruling on the thirteenth door** — `POST /api/sap/employee-sync`, unauthenticated, same unvalidated dict (§3).
3. **A ruling on the four keys you can write and never read back** (§1.3).
4. **GitHub billing**, fifth report.

---

## 1 · The sweep

**Every published key in the API, against the model field it claims to write.**
Three surfaces, because they fail in three different ways.

### 1.1 · The write side — 32 routes, 6 gates, one mismatch

Every non-`GET` route under `/api/v1` was enumerated **from the routing
attribute Odoo stamps on the method**, not from `_ROUTE_REGISTRY` and not by
searching for allow-lists. That matters twice over: the nine pre-envelope
routes never joined `_ROUTE_REGISTRY`, and `POST /home/quick-submit` declares
no allow-list — which is exactly why handoff 31's search for the routes that
drop fields found eleven and not thirteen.

**32 non-`GET` routes**, which is the census — a route that can carry a body,
plus the one `DELETE` that cannot, classified as such rather than filtered
out on a guess. **Ten write a model's fields**, through six gates; the other
twenty-two each say why they do not (an action's arguments, a credential, a
multipart upload, a config parameter, no body at all).

| gate | keys | resolve to a field |
|---|---|---|
| `v1_assets._WRITABLE_FIELDS` → `nrs.asset` | 48 | 48 |
| `v1_requests._WRITABLE_FIELDS` → `request.request` | 18 | 17 + **1 translated** |
| `v1_locations._WRITABLE_FIELDS` → `generic.location` | 18 | 18 |
| `v1_settings._CATEGORY_WRITABLE` → `nrs.asset.category` | 11 | 11 |
| `api.QUICK_SUBMIT_FIELDS` → `request.request` | 7 | 3 + 2 translated + 2 composed |
| `sap_sync_log.SAP_PAYLOAD_KEYS` → `hr.employee` | 22 | 2 + 11 translated + 9 not fields |

**The one mismatch is the one already known**: `location_id` on
`request.request`, whose field is `generic_location_id`, translated by
`v1_requests._location_field` since handoff 31. **No second one exists on
the write side.**

Checked statically against the registry for all 124 keys, and then **run**,
because the handoff said to run it: `POST /locations` with 12 keys, `POST
/assets` with 37, `POST /requests` with 9 — 58 of the 124, chosen as the ones
that need no other record to exist first. Every one came back on the record.
**Not all 124 were sent**: the rest are foreign keys, disposal paperwork and
depreciation figures that need a second record or a particular state, and
saying "every key was sent" when 58 were is the class of sentence this
handoff exists to stop. What the other 66 have is the static check and the
400.

The request probe is also handoff 31's fix confirmed by acting rather than by
reading: `POST /api/v1/requests {"location_id": 7809, …}` → `201`, and
`GET /api/v1/requests/<id>` answers `"location": {"id": 7809, "name": "Sweep
probe location"}`.

### 1.2 · The read side — 22 guarded reads, all resolving

A serializer reading `r.whatever` off a renamed field raises `AttributeError`
and is loud. The quiet ones are the DEFENSIVE spellings — `"x" in rec._fields`,
`getattr(rec, "x", None)`, `hasattr(rec, "x")` — each written to mean *this
optional module may not be installed*, each indistinguishable from *this
field was renamed and we publish `null` now*. That is the shape
`serialize_request` was hiding `location_id` in, among four siblings.

**The FILTERS are the same surface and need no new guard.** `?location_id=`
was ignored by the same bug, but a filter key goes into a domain, and Odoo
answers a domain naming a field it does not have with
`ValueError: Invalid field request.request.nope_id in condition (...)`
— checked, not assumed. That is loud. The only quiet filters are the ones
written with the same `in _fields` guard, and those are now in the table.

**22 such reads across the controllers, and every one is now classified.**
Twelve are not about a model field at all and say so with a reason — nine
read werkzeug `request` state the API puts there itself, three are `_ref`'s
`name_field="name"` default in its three copies, and two are the dynamic
reads in `_location_field` and `_model_field` whose names are loop
variables. **Ten name a model and a field, and all ten resolve**: seven on
`request.request`/`request.event`, one on `nrs.asset.pm`. So the assertion
is over ten, not twenty-two; the other twelve are held by the
classification test, which is what forces a human to look at a new one.

**The first draft of the parser could not see `_location_field`.** It reads
`for name in ("location_id", "generic_location_id"): if name in Req._fields`
— a loop variable, not a literal — so the helper this entire handoff is
about was invisible to the test written about it. Caught by the table's own
staleness check, which reported two entries the parser had stopped finding.
The parser now reports a dynamic read as its own kind and the table must name
it; `_location_field`'s pair is checked by hand instead, **in both
directions**, because that fallback is only correct while the OLD name is the
absent one.

### 1.3 · The third surface, which the handoff did not ask for and the sweep found anyway

**A key you can write and can never read back.** Handoff 30's
depreciation-method bug was a screen reading one name and writing another. A
field that is writable and published NOWHERE is the same asymmetry with
nothing to compare against — a caller sets it, gets a 201, and has no way to
learn whether it took. Since handoff 31 the other direction is a loud 400;
this one stays quiet for ever.

Four, all pre-existing, none introduced here:

| key | route | what happens |
|---|---|---|
| `salvage_rate` | `POST/PATCH /assets` | published only as the derived amount `financial.depreciation.salvage_value`, never as the rate |
| `verification_notes` | `POST/PATCH /assets` | published only in the response to `POST /assets/<id>/verify`, never on a GET |
| `mobile` → `mobile_phone` | `POST /integrations/sap/employee-sync` | `serialize_employee` publishes `work_phone` and not this |
| `generic_location_id` | `POST/PATCH /requests` | a false positive: read through `_location_field(r)` at runtime, so no parser can see the name |

And the inverse, which is not a defect but is the trap next to it: **six asset
keys are accepted under one name and published under another** —
`depreciation_method` → `financial.depreciation.method`,
`depreciation_start_date` → `…start_date`, `use_category_policy` →
`…uses_category_policy`, `model_name` → `model`, `location_id` →
`current_location`. A screen that GETs an asset, edits it and PATCHes the
whole object back is refused on every one of them, with a 400 since handoff
31. That is `docs/GO-LIVE.md` §16.3 item 5 with names attached; renaming
published keys is breaking, so nothing was renamed.

### 1.4 · Zero of how many

Per published key, on real data, counted directly in Postgres.

**`cadra19`** — 1,335 assets, 80 requests, 754 locations:

- `request_request.generic_location_id`: **80 of 80.** Every request has a
  location, written by quick-submit, the PM scheduler, fleet and the Odoo
  form; the API published `null` for all 80 until handoff 31.
- Zero of 1,335 on `nrs.asset`: `custodian_id`, `legacy_asset_code`,
  `department`, `current_value`, `purchase_value`, `replacement_cost`,
  `manufacturer`, `parent_id`, `maintenance_vendor_id`, `warranty_expiry`,
  `import_date`, `purchase_order_reference`, `last_verified_date`,
  `verification_notes`, `building_id`, `floor_id`, `room_id`, and every
  `sap_*` code, date and amount. The two `sap_*` STATE columns are the
  exception and read 1,335 of 1,335 — they are Selection defaults, which is
  the other way a column lies about having been filled in.

**`jaizbankplc`** — 4,164 assets, 460 requests, 440 locations, 61 employees,
30 vehicles, 591 custody rows:

- `request_request.generic_location_id`: **0 of 460** — the one zero on this
  estate that is a zero because the API dropped it, not because nobody filled
  it in.
- Zero of 4,164: `asset_type_id`, `subcategory_id`, `legacy_asset_code`,
  `department`, `current_value`, `replacement_cost`, `purchase_date`,
  `warranty_expiry`, `parent_id`, `maintenance_vendor_id`, `building_id`,
  `floor_id`, `room_id`, `next_service_date`, and ten of the twelve `sap_*` columns. The other two — `sap_posting_state` and `sap_reconciliation_state` — read 4,164 of 4,164, being Selection defaults, which is the other way a column lies about having been filled in.
- Zero of 460 requests: `service_id`, `impact`, `urgency`, `partner_id`,
  `parent_id`, `vehicle_id`, `date_closed`, `workflow_payment_ref`,
  `workspace_ref`.
- Zero of 61 employees: `work_email`, `work_phone`, `cost_centre`,
  `grade_level`, `employment_start_date`, `employment_end_date`,
  `sap_location_id`, `sap_manager_ir`.
- Zero of 30 vehicles: `vin_sn`, `color`, `seats`, `model_year`,
  `home_location_id`, `last_service_date`, `next_service_date`.

**`nrs19`** — 11,943 assets, **0 requests**, 1,154 locations, 11,386
employees. It is named here only to say what it could not have told anybody:
**a question about requests has no answer on `nrs19`**, and handoff 31 wrote
nine documents on the answer it gave.

**Every zero above except one is a column nobody has filled in.** The
distinction is invisible without the denominator, and it is the whole of
what went wrong last time. `CLAUDE.md` now carries the rule.

---

## 2 · What the guard fails on, proved by breaking it

`myservice_api/tests/test_published_names_resolve.py` — 12 tests. Every one
is driven by something that cannot miss a case: the routing attribute for
routes, a parse of every controller for reads. **A route or a read the tables
do not name fails the test**; it is not skipped.

Proved by renaming one field in the source, in the exact shape of the defect
— `"vehicle_id" in r._fields` → `"vehicle_ref" in r._fields`, a serializer
that now publishes `null` for ever and breaks nothing:

```
FAIL: TestPublishedNamesResolve.test_every_guarded_read_is_classified
AssertionError: ['v1_requests.py:159  serialize_request.r → "vehicle_ref"']
  These reads are guarded against a missing field and this test does not
  know what they guard. Add each to `_GUARDED_READS` with the record's
  model, or None and the reason it is not a record

FAIL: TestPublishedNamesResolve.test_the_table_names_no_guarded_read_that_is_gone
AssertionError: [('v1_requests.py', 'serialize_request', 'r', 'vehicle_id')]
  `_GUARDED_READS` names reads the controllers no longer make — either the
  code went away, or the parser cannot see it any more, which is worse
```

Then the realistic case — a rename sweep that updates the table too, so the
two agree with each other and not with the model:

```
FAIL: TestPublishedNamesResolve.test_every_guarded_read_names_a_field_that_exists
AssertionError: v1_requests.py:159 guards `vehicle_ref` on request.request,
  which has no such field — so everything reading it publishes null and
  nothing fails.
```

Both restored; `git diff` on `v1_requests.py` is empty.

**The guard found two things on its first honest run**, neither of which
anybody had asked about:

1. **`hr.employee.email` and `.phone` exist** and are NON-STORED relateds to
   `user_id.email` / `user_id.phone` — the linked Odoo *user's* login
   address, not the employee's. SAP sends `email` and the sync writes
   `work_email`, which is right; writing `email` would rewrite a user
   account, and for the employees with no user account it would write
   nowhere at all. Recorded with that reason rather than waived.
2. **`mobile` → `mobile_phone`** is accepted and published by nothing —
   §1.3 above.

**Where the guard stops**, said in the file so nobody reads it as more than
it is: the census is `/api/v1/*` on this addon's controllers. It does not see
first-party routes outside that prefix (`docs/api/EXTERNAL-SURFACES.md`).
The public twin `POST /api/myservice/quick-submit` is covered only because it
is the same Python function as the v1 route and shares its declaration.

---

## 3 · The twelfth door — and it was the twelfth and thirteenth

Both routes now name what they accept and refuse what they do not, with the
same 400 as the other eleven, before anything is written.

| route | accepts | declared in |
|---|---|---|
| `POST /home/quick-submit` | 7 keys | `QUICK_SUBMIT_FIELDS`, `myservice_website_theme/controllers/api.py` |
| `POST /integrations/sap/employee-sync` | 22 keys | `SAP_PAYLOAD_KEYS`, `myservice_identity/models/sap_sync_log.py` |

`SAP_PAYLOAD_KEYS` is **derived from `SAP_FIELD_MAP`** rather than copied
beside it, so it cannot drift when the map grows — and the §A guard imports
the same map rather than transcribing its twelve pairs. Three places that
would each have been a copy of one rule are one.

**A batch is refused whole.** `employee-sync` takes a list, and a list is one
request: refusing the eleventh employee after ten had been created would
leave a partial sync under an idempotency key that replays the same answer on
every retry.

### The bare `except: pass` was worse than a dropped key

`quick_submit` swallowed a non-integer `service_id` or `location_id`, and
separately an id naming no record, and submitted the request without it —
**a KNOWN key, silently dropped**, which is rule 3 verbatim. Those are now a
400 too, but deliberately **not** the same 400: `details.unusable_fields`,
not `rejected_fields`, because the repair is different. A caller told
`service_id` is "not writable" would drop the key; what it must do is fix the
value.

### What a refusal looks like on the public form

The same function answers the unauthenticated homepage form
(`POST /api/myservice/quick-submit`). One validator, two renderings.

> Sorry — we could not submit your request. Some of the information sent with
> this form was not recognised. Please reload the page and try again.

Nothing the visitor typed is wrong — the page sent a key the server does not
accept, which means a stale tab or a modified form — so it tells them to
reload rather than to correct something. And for the one refusal a person can
act on:

> Please choose the service from the list on the form, then send your request
> again.

…or, for two, *"the service and location from the lists on the form"* —
plural, because a `", ".join` does not read the sentence and a person does.
No backticks, no `_id`, no key names anywhere a visitor can see them; the key
names live in `details.rejected_fields`, where the reader is an integration.

**The guard that forbids field names in user-facing text does not reach
these strings.** It is `myservice_api/tests/test_asset_history.py::
test_the_statements_are_words_not_field_names`, an in-registry test over the
asset-history statements only. The rule was obeyed and pinned by new tests of
its own; widening the existing guard to cover every user-facing string in the
codebase is a §A-shaped job and is **not done**.

### `status` — the same defect, one route down

**`nrs.sap.sync.log` has never read `status`.** It reads `employmentStatus`,
or `sap_status`. And `status` is what the OpenAPI `SapEmployee` schema
published — with an enum, `active`/`inactive`/`terminated`, of which
`inactive` is not a value this system has — what the endpoint reference's
canonical example sent, what the demo card sent, and what this repository's
own `tests/test_integrations.py` had been sending since it was written.
**Every integrator following our documentation sent an employment status that
went nowhere, under a 200.** Per `CLAUDE.md` rule 4 the model is the
published surface: the schema, the example, the demo card and the test are
corrected, and `status` is now a 400.

### And the same again on quick-submit's own documentation

`docs/api/cadra_api_endpoint_reference.md` §8.2 sent `name`, `email`,
`phone`, `subject` and `description`. **Four of those five the route has
never read**, and it answered 201 to all of them, raising a request carrying
only the description. `docs/api/cadra_api_demo_guide.md` sent `name`,
`email`, `message` and `location_name` — four keys, none accepted, and no
`type_id`. And `tests/test_home.py::test_quick_submit` sent `name`, `email`,
`phone`, `subject`: **four keys, none accepted, 201 every time since the file
was written** — the test was written from the example. All corrected; the
suite now fails if the example drifts again.

### Found while checking the above: neither "required" key is required

The route's schema declares `required: ["type_id", "description"]`. Neither
is enforced. Measured by acting, after the refusals were in place:

```
POST /api/v1/home/quick-submit  {}                          -> 201  REQ-000594
POST /api/v1/home/quick-submit  {"description": "…"}        -> 201  REQ-000595
POST /api/v1/home/quick-submit  {"type_id": 1}              -> 201  REQ-000596
```

An empty body creates a request, titled *"Quick facilities request"*, against
whichever request type is first and active. The delegate falls back for both.
**On the PUBLIC twin that is also an unauthenticated way to create an empty
request** — the homepage form enforces both in JavaScript, and nothing behind
it does.

Not changed: making them required is a breaking change on a public portal
route and the handoff ruled on refusing *unknown* keys, not on enforcing
declared ones. It is the same genre as everything else in this report — a
published contract and a route answering to something else — and it belongs
in the same ruling as §16.3 item 11.

### The THIRTEENTH door, not closed, and why

`myservice_identity/controllers/sap_webhook.py` — `POST /api/sap/employee-sync`,
`type='json'`, **`auth='none'`** — hands the same unvalidated dict to
`process_sap_payload`, as do `/api/sap/employee-sync/test`, the xlsx import
job and the SAP import wizard. The accepted-key set is on the model now, so
each is a two-line change.

**Left alone on purpose**, and here is the measurement rather than a guess.
`nrs.sap.sync.log.sync_type` records which door each sync came through.
Across all eight local databases, measured at the close of this handoff:
**`webhook` = 0 rows**, on every one of them. `api` = 179 — 98 on
`jaizbankplc`, 79 on `test19`, 1 each on `cadra19` and `gtb19` — and all
four of those are databases this repository's own suites write to, so **none
of the 179 is evidence of a real SAP feed either**. The `api` figure rises
every time the suite runs (it was 163 three hours earlier, and the
verification pass moved it again); the `webhook` zero is the number that
matters and it has not moved. Nothing on this machine has ever used the unauthenticated door, and
nothing here can say what NRS's SAP will use when INT-06 goes live.

So the reason to leave it is not that closing it would break something
measurable; it is that it is an **unauthenticated** external surface
(`docs/api/EXTERNAL-SURFACES.md`), the handoff ruled on two named routes, and
a refusal on the door a live upstream system may be pointed at is a decision
about an outage, not a tidy-up. The §A census is `/api/v1/*` and does not
watch it either. **It needs a ruling, and it should have one before anything
else goes near `myservice_identity`.**

---

## 4 · The two disposal-date holes

Both closed in `nrs.asset`, beside `_assert_disposed_is_terminal`, where
every writer passes.

**C1 — the date cannot be taken off.** `_assert_disposed_is_terminal` guards a
fourth field, before `super()`, so nothing is written:

> *"… has been disposed of, and the day it was disposed of cannot be taken
> off its record. Correcting it to another day is a proper thing to do;
> leaving the disposal with no day at all is not — the register would no
> longer be able to say when the asset left it."*

**One deviation, and it is the right one: this is a COMPARISON, not a
presence check.** An asset that is *already* undated may still be sent an
empty date without a refusal. Refusing on presence would make every legacy
undated disposal uneditable from the Odoo form, which re-sends every field it
displays — the same argument the three refusals beside it already turn on,
that naming a protected field is not changing it. Pinned by
`test_an_undated_disposal_may_be_saved_from_the_form`.

### C2 — yes, the reading was available, and here is the proof rather than the claim

`_stamp_disposal` now takes the write's own `vals`. **The handoff asked to be
told if the model could not tell the two dates apart**, so it was checked four
ways rather than assumed:

- **One call site.** `_stamp_disposal` is called exactly once in the
  repository, inside `for record in self:` after `super().write(vals)`, with
  `vals` in lexical scope. No other caller, no override.
- **No other `write` override injects the key.** All five overrides on
  `nrs.asset` were read; none adds `disposal_date` to `vals` before
  `super()`. So what `NRSAsset.write` sees is what the caller sent.
- **`create` never reaches it**, which is what keeps an asset *registered* as
  already disposed correctly undated.
- **Every door into `disposed` was walked**: the API PATCH, `POST
  …/condemn`, `action_condemn` (which sends no date and so is stamped today,
  which is what it always wanted), the Odoo form, the importer and the shell.

`vals` is a **required positional** argument, so a future second caller has to
decide rather than inherit the old behaviour by leaving it out.

One path the guard genuinely cannot see, and it is not an approximation:
`{"state": "disposed", "disposal_date": null}` in ONE write. The asset is not
yet disposed when C1 runs, so C1 does not fire — and C2 covers it exactly,
because no date was sent and the server dates it.

### What this costs, and it is worth a sentence

**C2 reverses a test handoff 31 shipped with a stated justification** —
*"paperwork written up BEFORE the act: the date was agreed at the board of
survey, and the status follows a week later."* Under the ruling, that board of
survey now loses its agreed date to today unless it sends the date in the same
write or corrects it afterwards. Both remain possible; **nobody is told at the
time.** The date is a tracked field, so the day that was there before survives
in the record.

### What `no_disposal_date` means now

**No first-party door can produce it on a new disposal.** Every write into
`disposed` is dated — the caller's date if it arrived in that write, otherwise
today in Lagos — and the date cannot be taken off afterwards. A
`no_disposal_date` row is now one of exactly three things, all honest:

1. a legacy row disposed of before handoff 31's stamp existed;
2. an asset **registered** as already disposed with no date, because `create`
   is deliberately not stamped — the system never saw the day it happened;
3. something that wrote the column outside the ORM, which is how
   `test_disposal_report.py` builds its legacy fixture, and it says so.

The opening balance on real data was zero and stays zero.

---

## 5 · Results

| Suite | Result |
|---|---|
| `pytest tests/` on `test19` | **1028 passed, 8 skipped** — 0 failed |
| in-registry, CI's eleven modules, CI's order | **0 failed, 0 error(s) of 796 tests** |
| `myservice_asset_register` alone | **0 failed, 0 error(s) of 309 tests** |
| Playwright on `test19` | **141 passed, 4 skipped, 2 failed**, zero flaky |

The two browser failures are the two depreciation specs already recorded as
failing on `dev` (`docs/GO-LIVE.md` §13.5 item 13). Nothing else changed.

**Denominator reconciled**: 796 = handoff 31's 775 + 12 (the sweep guard) + 9
(the disposal-date tests: seven new in `TestADisposalsDateCannotBeTakenAway`,
two beside it, and one rewrite that replaced an existing test rather than
adding one).

**No fan-out was needed and that is a measurement, not an assumption**: the
diff adds no field, touches no view and changes no manifest, so there is no
column for an un-upgraded tenant to be missing. All eight databases were
checked serving afterwards — `/app/` and `/api/v1/brand` both `200` on
`cadra19`, `nrs19`, `gtb19`, `test19`, `nrs`, `lasg`, `gtb`, `jaizbankplc`.

### A denominator that was never printed

`myservice_asset_register` was run twice without `--workers=0`, and **both
runs ended without the `N failed, M error(s) of X tests` line at all** — just
`odoo.tests.stats: 411 tests` and *"Stopping workers gracefully"*. `411` is
not the denominator; it counts class-level entries. The third run, with
`--workers=0`, printed `0 failed, 0 error(s) of 309 tests`.

`CLAUDE.md` said to pass `--workers=0` for any `HttpCase`. It now says to pass
it on every in-registry run, because without it **the number the rule tells
you to read is not printed** — which is the collapsed-denominator trap with
the collapse hidden one level further down.

---

## 5a · The verification pass, and the one thing it got wrong

A fresh pass that wrote none of this code re-ran every count in §1.4 against
all three databases, read the whole diff, and attacked both the guard and the
disposal logic. Everything in §1.4 came back true. Three findings changed the
code and one changed nothing but is the most interesting.

### It found two ways past the guard, and both are now shut

**1 · A new controller file escaped the route census entirely.** The module
list was a hand-written dict of ten. The READ side walked the directory; the
WRITE side walked the dict. So a new `v1_*.py` with a `POST` route handing
its body straight into `create()` would have had its reads parsed and its
routes missed, and all twelve tests would have passed — **a maintained list
beside a mechanical one, inside the file written against exactly that.**
Both halves now list the same directory. Proved by adding a real controller
file with a real route and watching the census name it:

```
FAIL: TestPublishedNamesResolve.test_every_route_that_takes_a_body_is_classified
AssertionError: {('POST', '/api/v1/probe-tmp'): 'v1_probe_tmp.probe_tmp'}
```

then removing it and re-running green.

**2 · A route declaring no `methods` was read as GET and skipped.** In Odoo
such a route accepts every method, so it takes a body. Latent — every route
in these controllers declares one today — but the nine pre-envelope routes
use bare `@http.route`, which is precisely where the next one would be
written. A methods-less route is now reported as `ANY` and must be
classified.

**What it could not get past**: a gate written as an expression rather than a
literal (`_resolve` reads the live object), a serializer reading a field
through a variable, or a serializer not named `serialize` — the last two fail
in the safe direction, reporting the key as unreadable rather than hiding it.

### And the thing it got wrong, which is this handoff's own lesson pointed back at us

The pass reported, as its single most important finding, that
`nrs.asset.disposal_date` is **not** tracked — and therefore that §4's
overwrite destroys a board-of-survey date with no record of what it was. Its
evidence: `myservice_asset_register/models/asset.py:156` declares the field
with no `tracking=True`, `grep tracking=True` on that file does not list it,
and `asset_disposal.py`'s own module docstring calls it *"an untracked
`disposal_date`"*.

**All three are true and the conclusion is false.** `asset_disposal.py:285`
declares `disposal_date` a **second time**, on `_inherit = 'nrs.asset'` —
the same model — with `tracking=True`, which handoff 16 §B2 added for this
exact reason. The docstring sentence describes what INT-10 measured *before*
that module existed. Proved by acting rather than by grepping:

```
disposal_date now: 2026-09-22
chatter: disposal_date old=2025-01-31 new=2026-09-22
```

— a stale date PATCHed onto a live asset, the status written afterwards, the
date overwritten by today, and the day that was there before sitting in the
record where an auditor can read it. **The sentence stands.**

It is worth writing down because it is the same failure this handoff is named
for, committed by the pass looking for it: a field declared in one file and
answering to a second declaration somewhere else, and a conclusion drawn from
the file that was opened first. The rule that caught it is the one in
`CLAUDE.md` — a claim of exclusivity is a guess unless a search backs it, and
one file is not a search.

---

## 6 · Wall-clock, and the correction share

About **two hours ten minutes** from Step 0 to the closing push, three
workers in parallel: the sweep and its guard in the main session, the twelfth
door and the disposal dates in subagents partitioned by file.

**The correction share is high and most of it is mine.** In rough order of
cost:

1. **The guard could not see the helper it was written about.** Corrected by
   the guard's own staleness check. §1.2.
2. **The guard's translation table hand-copied SAP's twelve pairs.** A second
   copy of a rule, in the file whose entire subject is second copies of
   rules. Replaced with an import of `SAP_FIELD_MAP`; the guard failed on two
   of those pairs the moment it was reading the real thing, and both failures
   were real findings.
3. **A sentence in this report claimed every published key had been sent
   through its route.** 58 of 124 were. Narrowed before it was committed —
   which is the only reason it is a footnote rather than an entry in
   `DECISIONS.md`.
4. **The new guard's test class derived from `TransactionCase`**, which an
   existing guard refuses — every in-registry class must derive from the
   base that asks which database it is about to write to. Caught by
   `tests/test_source_guards.py`, not by me.
5. **The sweep's own probe records broke `tests/test_locations.py`**, and the
   test turned out to be wrong: it asserted `?q=` only matches the name when
   the route searches four fields. Corrected. §17.2 item 5.
6. **Three audit-report tests were failing before any of this work and got
   worse with every run**: `test19` crossed 330 disposals on one date, and
   the disposal schedule is capped to the first 100 of a period by ascending
   asset id, so a freshly created fixture always fell outside the window it
   was created to be found in. Fixed by giving the fixture a day of its own
   rather than "yesterday" — which also **un-skipped two tests** that had
   been skipping on `truncated` and are now comparing what they were written
   to compare.

And two corrections of work that was not this handoff's:

7. **`tests/test_home.py::test_quick_submit` had been sending four keys the
   route has never read, since the day it was written**, because it was
   written from the endpoint reference's example — which was also wrong.
8. **`tests/test_integrations.py` had been sending `status`**, for the same
   reason.

**What that adds up to.** Of the defects this handoff closed, the ones found
by the sweep were found by a guard; the ones found in the sweep's own output
were found by things the programme already had — an existing source guard, a
test that broke, a staleness check inside the new guard itself. Nothing in
this report was caught by reading the code carefully, and that is the argument
for the guard rather than for the afternoon.

---

## 7 · Needs the owner

1. **Merge the pull request.** The Builder's permission layer refuses
   `gh pr merge`.
2. **A ruling on the thirteenth door** — `POST /api/sap/employee-sync`,
   unauthenticated, same unvalidated dict. §3 and `docs/GO-LIVE.md` §17.2
   item 2.
3. **A ruling on the four keys you can write and never read back**, and on
   the six accepted under one name and published under another.
   §17.2 item 1.
4. **GitHub billing still blocks all CI.** Fifth report.
