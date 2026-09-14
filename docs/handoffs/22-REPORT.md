# Report 22 — The front end that lies to its own users

**Branch:** `fix/phantom-enums` · **Base:** `dev` at `4ce683e`
**PR:** owner-blocked at merge, as every handoff ending in a PR is.

---

## 1 · What the fresh pass over handoff 21 found

It was worth running. The core work holds up — the validation itself is
correct and closes the defect — but **three of report 21's own acceptance
claims are false**, one guard does not catch the file it was written to catch,
and the API-surface announcement was skipped entirely. The pass was read-only,
against the merged commit `d8bc7a7`.

| # | Finding | Status |
|---|---|---|
| 1 | **No `docs/api/CHANGELOG.md` entry for handoff 21 at all**, for ~26 parameters whose status code went 200 → 400. The file's own rule is "if Vendra could branch on it, it goes here." | **Fixed here** — entry written, marked BREAKING. |
| 2 | **`has_coordinates` puts NULL on the wrong side of the partition.** | **Confirmed and fixed here.** See §5. |
| 3 | The new CI-series guard (`test_deployment_profile.py:315`) skips any line without `odoo` in it. The deleted `.gitlab-ci.yml`'s pin is `SERIES_BRANCH: '15.0'` — no `odoo` on that line. The mutation proof passes only because it writes a *different* variable name (`ODOO_SERIES_BRANCH`) that never existed. The agent restored the real file and **the guard did not fire.** | **Reported, not fixed.** See §7. |
| 4 | **The partition assertion in `test_query_params.py` never ran on `/api/v1/assets`.** `_count()` returned `len(data)`, capped at 50, so the only real assertion was gated behind `if unfiltered < 50` — "only check endpoints smaller than one page". Silently: nothing skipped, nothing printed. | **Fixed here.** See §6. |
| 5 | For both `active` parameters, `no` is computed and **never asserted on** — a dead assignment. The `false` branch report 21 itself calls "arguably the worse failure of the two" had no regression net at all. | **Fixed here.** See §6. |
| 6 | **One `priority` annotation was missed.** `v1.py:2207` on `/home/quick-submit` still published four of five and called `3` "urgent". Report 21 §2 claims all were corrected. | **Fixed here.** |
| 7 | `include` is whitespace-tolerant on `/assets` and `/requests` and **refuses whitespace on `/locations`** — the raw token reached `parse_enum`. `?include=children, ancestors` was a 400 on one route out of three. | **Fixed here.** |
| 8 | `limit` behaviour changed in three unannounced ways: `?limit=0` and `?limit=-5` were `1` and are now 400; `?limit=null` was `50` and is now 400; `/barcode/untagged?limit=1000` was served and is now 400. | **Reported**, and now in the changelog. |
| 9 | The SPA's `condition` filter still under-reported: `new` displayed as "Good" but was excluded from the Good filter. | **Confirmed, measured and fixed here.** See §4. |

It also confirmed a long list of things as sound — the door's purity, the
exception ordering, every enum fallback tuple against its model, an exhaustive
AST sweep for missed call sites (zero), and the `pg_isready` streak logic
hand-traced against twelve probe sequences.

**The lesson worth keeping:** the pass found nothing wrong with the mechanism
and a good deal wrong with the *evidence that the mechanism works*. Four of
the nine findings are tests or guards that pass without testing anything. A
handoff verified by its author is the weaker claim, and this is what it costs.

---

## 2 · Can the front end read the sets rather than declare them?

**It could not. It can now, and that is what shipped.**

Before this handoff there was **no endpoint anywhere that published a field's
accepted values.** `utils.selection_values()` already read the model's live
Selection at request time, but it was only ever called to *validate an inbound
filter* — nothing returned it. The enums in `/api/v1/openapi.json` are
hand-written literals in the route annotations, not reads of the model, which
is a copy with the same failure mode in a second place. So the only way a
client could learn a set was **to send a wrong value and read `allowed_values`
off the 400** — a refusal doing documentation's job, and useless for
populating a control before the user has typed anything.

So the answer to the question is now yes, by construction:

- **`GET /api/v1/meta/enums`** (new, `myservice_api/controllers/v1_meta.py`)
  returns every published Selection as `[{value, label}]`, derived from the
  registry per request. No list is written out in the route.
- **`src/lib/enums.ts`** is the one module, and **`useEnum(name)`** is how a
  component gets a set. Seven sets, one import.
- **`tests/test_frontend_enums.py`** is the guard, and it is the deliverable.

**This closes the family rather than correcting it.** A value added to the
model appears in every dropdown the same day with no front-end release, and a
value the model never had cannot appear at all.

The seed in `enums.ts` still exists, because a form has to render something
before the fetch resolves and something correct if it never does. A seed is a
copy, so it does not get to rot quietly: the guard parses the Odoo model
source and the TypeScript and fails on any disagreement in **values, order or
labels**. Order is checked deliberately — `priority`'s keys read like a scale,
so a set that is right as a bag and wrong as a sequence is precisely the bug
that shipped, and a membership comparison would have passed it.

### The guard, proven to fail before it passes

Four mutations, each an exact reconstruction of a bug that really shipped:

| Mutation | Result |
|---|---|
| `priority` `"2"` relabelled `Normal` | **FAILED**, printing both lists |
| `wing` dropped from `location_type` | **FAILED** |
| `ENUM_DEFAULT.priority` back to `"2"` | **FAILED** — *"a blank form would record something other than what the model considers unset"* |
| `fuel_type` collapsed to three values | **FAILED** |

It also failed for real, twice, during the work — once on the `condition`
copies that were still outstanding, and once on two wire-type unions
(`ApiAsset.condition/state`, `Asset.lifecycleState`) nobody had listed. Both
are now read from the model.

**And the guard itself had the flaw it exists to catch.** Its first version
matched raw text, so it flagged the explanatory comments of the very files it
was checking — the trap `test_query_param_guard.py` names out loud ("a guard
that flags its own explanation is a guard somebody satisfies by deleting the
explanation"). It now strips comments and reads code. Styling maps are waived
by name with a stated reason, and a second test checks each waived file
actually has the `??` fallback its waiver claims — `conditionConfig[condition]`
was an unguarded index that would have thrown inside render, white-screening
the asset register from a Python change.

---

## 3 · How many records carry a wrong priority

**Uncomfortable, as expected, and smaller than it looks — because these are
demo tenants, not an estate.**

Model: `0=Low, 1=Normal, 2=High, 3=Critical, 4=Very Urgent`, `default='1'`.
The form displayed `0=Very low … 4=Urgent` — every label one step low — and
its blank state was `priority: "2"`.

**35 requests are stored at `"2"` = High**, across three tenants:

| Tenant | at `"2"` (High) | total requests |
|---|---|---|
| `jaizbankplc` | 14 | 388 |
| `cadra19` | 20 | 80 |
| `gtb19` | 1 | 8 |
| **Total** | **35** | **477** |

On `jaizbankplc` every one of the 14 was written by `cadra_client_test_client`
— the API credential, which is the path the SPA posts through. `nrs19`, `nrs`,
`lasg`, `gtb` and `test19` hold no affected rows.

**The display damage is much wider than the write damage.** `RequestsList`
mislabelled `2`, `3` and `4` (and rendered `"2"` in calm blue). That is
**225 of 477 requests shown under the wrong severity** — 190 on
`jaizbankplc` alone.

Per `CLAUDE.md`, these numbers size a fixture, not a customer. Every real
client gets its own single-tenant server; what this measures is how easily the
defect produces wrong rows, not how many wrong rows exist in the world.

---

## 4 · What was fixed

**A · Priority.** The blank form now starts on `ENUM_DEFAULT.priority`, which
the guard pins to the model's `default='1'`. Every option list and label in
`RequestForm`, `RequestDetail` and `RequestsList` is read from `useEnum`.
`PRIORITY_COLOR` stays — colour is a choice the front end legitimately owns —
but is re-keyed to real severity, with an unknown-value fallback that is no
longer `PRIORITY_COLOR["2"]`.

> One correction to a subagent's work: it wrote `ENUM_DEFAULT.priority ?? ""`
> to satisfy an optional type. An unset value renders a `<select>` showing its
> **first** option, "Low", while an untouched form records the model's default,
> "Normal" — the same display/record mismatch one value along. `ENUM_DEFAULT`
> is now typed with `satisfies` so the key is guaranteed and the fallback is
> gone.

**B · The other four, as one change.** `location_type` (dropped the phantom
`state`/`office`, gained `wing`), `asset_level` (gained `group`), `domain`
(free text → select; the two byte-identical eight-value copies 630 lines apart
in one file are gone), `fuel_type` (the regex that showed `electric` and both
plug-in hybrids as **CNG**, and `hydrogen` as **Petrol**, is deleted — the
model's key is carried and the model's label rendered).

Also: a `withCurrent()` helper so a value this build does not recognise stays
selected instead of being silently retyped by the act of opening the record —
which is exactly what the missing `wing` did.

**C · A fifth set nobody had listed: `condition`.** The verification pass
found it and it is the same defect with a measurable cost. `CONDITION_MAP`
collapsed **`new → "Good"`** for display while `CONDITION_TO_API` sent
`condition=good` for the filter. So **282 assets** — 204 on `jaizbankplc`, 54
on `nrs19`, 24 on `cadra19` — were labelled "Good" on screen and excluded from
the Good filter, with **no way to reach them at all**, since "New" was not
offered. Both maps are gone; the model's key runs end to end.

**D · The cursor — `400`, announced as BREAKING.** `decode_cursor` returned
`{}` for anything it could not decode, and `{}` means "start at the
beginning", so a caller paging with a corrupted cursor silently restarted at
page one while believing it was on page three. It now refuses. Three inputs
that gave three different wrong answers now give one right one:

| cursor | before | now |
|---|---|---|
| not decodable | `200`, page one | `400 invalid_request` |
| JSON that is not an object (`[1,2]`) | `200`, page one | `400 invalid_request` |
| `{"last_id": "abc"}` | **`500`** | `400 invalid_request` |

An absent or empty cursor is a different input and keeps its answer. The
refusal needed no new plumbing: handoff 21's `BadFilter` floor in
`cadra_endpoint` turns it into a 400 on every route that paginates. The decode
was moved ahead of the disposal report's expensive pass so the refusal happens
at the door, and the `cadra_endpoint` comment claiming "before the request has
touched the database at all" was corrected rather than left to become false.

---

## 5 · The thing I did not expect to find

**`?has_coordinates=false` — "which sites has nobody mapped" — answered
`0` on a tenant where 250 of 380 sites are unmapped.**

`latitude`/`longitude` are declared with no `default=`, so an unset coordinate
is **SQL NULL and never `0.0`**. On `jaizbankplc`, 250 of 380 locations have
NULL coordinates and **zero** have `0.0`. Odoo renders `('latitude','!=',0.0)`
as `(latitude != 0 OR latitude IS NULL)`, so every unmapped site landed on the
*has-coordinates* side:

```
before:  true → 380 of 380      false → 0
after:   true → 130             false → 250        (130 + 250 = 380)
```

Handoff 21's comment asserted the two branches "partition the register between
them with nothing falling through". The De Morgan reasoning was sound; the
premise it rested on — that these are "plain Floats defaulting to zero" — was
not, and the negation was checked against the comment rather than against the
column.

**This is the handoff's own warning, one layer up, and it is the best thing in
this report.** The old behaviour *passed a naive partition check*: 380 + 0 =
380. The two halves summed to the whole register while one was empty and the
other was everything. So the regression test asserts the sum **and** that
neither half is degenerate — a partition assertion that cannot pass on an
empty half is the entire point.

---

## 6 · The tests that were not testing anything

**`_count()` now reads `pagination.total_estimate`, not `len(data)`.** The old
count saturated at the 50-row page limit, so the partition assertion sat behind
`if unfiltered < 50` and never ran on `/api/v1/assets` — the endpoint with
3,621 rows. That gate is gone, and the assertion is unconditional.

**Mutation-proved.** With `is_verified`'s `false` branch reverted to appending
nothing — the original defect:

```
E   AssertionError: `is_verified=true` (1) and `is_verified=false` (3621) do not
    partition the 3621 rows of /api/v1/assets. One branch of the filter is
    missing, which is the unfiltered-list defect wearing a 200.
1 failed, 5 passed, 3 skipped
```

Restored: `6 passed, 3 skipped`. Before this change the same mutation passed.
The three remaining skips are honest — `has_sap_code`, `closed` and
`is_staff_bus` genuinely have an empty half on this tenant, and each says so
by name and count in the skip message.

`has_deadline` and `has_coordinates` now **execute** rather than skipping — the
first because the real count replaced the page count, the second because §5
made it a real partition.

**The `active` dead assignment** now carries an assertion that `active=false`
does not return the active set, which is what would actually catch an
unconditional `("active","=",True)`.

---

## 7 · What I did not fix, and why

**The CI-series guard (finding 3).** `tests/test_deployment_profile.py:315`
does not fail on the `.gitlab-ci.yml` it was written to delete, and its
mutation proof passes against a variable name that never existed. It is a
guard that guards nothing. I left it because fixing it properly means deciding
what the guard is *for* — every `N.0` token in any CI file, or only Odoo image
pins — and that is a ruling, not a repair. It is small and it is wrong today.

**`adapters.ts` maps the FM `domain` into a field the asset page renders as
"System Domain"** (a subagent found this). Those are not the same field: on a
live tenant that row reads `it` for every IT asset. I deliberately did **not**
"fix" it with a label lookup, which would only have made a wrong field read
convincingly. It needs a product ruling — does the FM domain belong on that
page under its own label, or does `systemDomain` need a real backing field?
Flagged in the code, marked NOT VERIFIED.

**`v1_settings.py:134` refuses an unknown FM domain with `details={"allowed":
...}`** where everything else publishes `allowed_values`. One-word
inconsistency in a published error body; a client keying on `allowed_values`
gets nothing there. Left alone because changing a published details key is
itself a breaking change and belongs in a versioned decision, not a drive-by.

---

## 8 · Test results — denominators quoted, CI's order

**`pytest tests/` first, then the in-registry Odoo suites**, which is the order
`.github/workflows/ci.yml` runs them in and is load-bearing rather than
cosmetic.

```
730 passed, 32 skipped in 133.04s          (762 collected)
```

The skip count is **unchanged from report 21's 32** while the passing count
rose by 73. The skips are the documented scope facts about this tenant's
credential, not new gaps.

```
0 failed, 0 error(s) of 378 tests when loading database 'jaizbankplc'
EXIT=0
```

**378 is a real denominator**, not a collapsed one. Grepped for `of 0 tests`
and for `CRITICAL`: neither appears. Run with `--workers=0` as CI does, so the
`myservice_barcode_station` HttpCase actually executes rather than erroring in
`setUpClass` and reporting green.

`npx tsc -p tsconfig.json --noEmit` — **exit 0, no diagnostics**, after
`rm -f .tsbuildinfo` to force a full rebuild.

`tests/test_frontend_enums.py` — **21 passed**, and see §2 for the four
mutations proving it fails first.

**No per-tenant fan-out is owed.** The diff touches controllers, tests and the
SPA only — no model, view or manifest change, and no stored field. A new
controller needs a container restart, not a module upgrade, so the multi-tenant
migration obligation in `CLAUDE.md` does not apply to this handoff. Nothing was
run against the other seven databases and nothing needed to be.

---

## 9 · Wall-clock, correction share, and whether the machine behaved

**Roughly two and a half hours**, most of it in the front end.

**Correction share was high and worth it.** Of five subagents, four produced
work that needed amending: the `?? ""` default (§4), a `withCurrent` helper
duplicated into two files (hoisted into `enums.ts`), two wire-type unions
nobody had listed, and a fifth condition copy in `fetchCategoryDashboard` that
wrote the Selection out as five consecutive `countAssets` calls — the quietest
copy of all, since a bar chart with a missing bar looks exactly like a bar
chart. **The guard found three of those four**, which is the argument for
building the guard before finishing the corrections rather than after.

**The machine behaved.** No Postgres crash-restarts; `--stop-after-init` was
never needed, because nothing here changes a model, a view or a manifest — a
new controller only needs a container restart. Six restarts total, each under
five seconds, each waited on with an until-loop rather than a fixed sleep.
Denominators are quoted throughout and no run collapsed to `of 0 tests`.

The one genuine friction: the verification agent reported the stack as down
and could not execute finding 2, so it reported it as SUSPECTED with the exact
query to settle it. The stack was up. That was the right call anyway — it
named what it could not verify instead of guessing, and the query it handed
over settled the question in one command.
