# Handoff 03 — Report

**From:** Builder (Claude Code, IDE) · **To:** Architect
**Handoff:** `docs/handoffs/03-tag-capture.md`
**Branch:** `feat/tag-capture` · **Date:** 2026-09-05

---

## Summary

Part A's three carry-overs are done. Part B is built: an asset now becomes
"tagged" only when someone physically confirms a label on it, and the
confirmation is checked rather than trusted.

**The handoff's one wrong assumption was the print funnel.** It says of
`action_print_tag` / `action_batch_print_tags`: *"Cheap; the hooks are already
the single funnel."* They are not — **three separate paths print a tag without
touching either method**:

> the label wizard calls `report.report_action(tags)` directly; the barcode
> station hands the browser a raw `/report/pdf/<report>/<asset_id>` URL, so no
> Python of ours runs at all; and the four tag reports carry
> `binding_model_id` on `nrs.asset`, so they fire from Odoo's own Print menu.

Stamping only the two methods would have under-recorded printing badly — a
`printed_at` that is silently incomplete is the same class of defect as the
tag state this handoff exists to fix. The real funnel is
`ir.actions.report._render_qweb_pdf`, and that is where the catch-all now
lives, with explicit stamping kept at each known call site.

Also worth your attention: **`jwt_secret` is a provisioning hole, not two
missing rows**, and I found a live credential-leak path in the repo that is
unrelated to this work but nearly fired during it.

**And the verification pass earned its keep three times over.** It found the
render hook I had just built writing *fabricated* print records onto
unrelated assets, a repeat confirmation destroying the original affix
evidence, and a tag awaiting replacement reading as never tagged. All three
are audit-trail integrity bugs — in the module written to fix audit-trail
integrity bugs — and all three are fixed and re-verified. Details under
[Verification pass](#verification-pass--it-found-three-defects-of-the-same-class-this-work-exists-to-remove).

---

## Step 0 — verification across all eight databases

Everything from #44/#45 was already in place; nothing needed re-applying.

```
db           cons/8   in_ir_model  vendra   prov_cols  null_codes  jwt        api
jaizbankplc  8        8            1        3          0           set        200
lasg         8        8            1        3          0           set        200
nrs          8        8            1        3          0           set        200
gtb          8        8            1        3          0           set        200
cadra19      8        8            1        3          0           set        200
nrs19        8        8            1        3          0           MISSING    200
gtb19        8        8            1        3          0           set        200
test19       8        8            1        3          0           MISSING    200
```

The two `MISSING` are Part A item 3 and are now fixed. Zero null asset codes
made Part A item 1 safe to apply.

### Needs the owner

- **Merging the PR.** As `CLAUDE.md` now records, `gh pr merge` is refused by
  my permission layer. Branch pushed, PR opened, merge is yours.
- **The staging/production per-tenant deploy of #44 and #45 is DONE** — you
  merged, and I ran `upgrade-19` for all four live tenants (`jaizbankplc`,
  `lasg`, `staging`, `gtb`), verified each against its live host. That item
  can come off the list. **This PR needs the same treatment**: it adds seven
  stored columns.
- **`upgrade-19.yml` has two traps** I hit doing it, both worth fixing before
  the next schema change: its roll-up step re-applies the deployment with the
  new image, so the *first* tenant's run puts every tenant on new code while
  the rest still have the old schema; and `target_db` is a single string, so
  four dispatches are needed and GitHub silently cancels a *queued* run when
  another is dispatched (`cancel-in-progress: false` only protects the
  in-flight one — `gtb` was cancelled this way and needed re-dispatching).

---

## Part A — carry-overs

### A1 · `asset_code` is `NOT NULL`

`required=True` on the field, so the unique constraint means what INT-06/07
assumes rather than "one asset per *non-null* code". Re-checked before
applying — zero nulls, empties or `'/'` placeholders in any tenant — then
fanned out. `is_nullable=NO` in all eight.

**I also removed the `or '/'` fallback**, which is a small deviation worth
naming. `create()` fell back to the literal `'/'` when the `nrs.asset`
sequence was missing. With the column now unique *and* NOT NULL, that
placeholder makes the first asset look fine and every one after it fail on a
constraint whose message says nothing about the real fault. It now raises a
`ValidationError` naming the missing sequence. A NOT NULL + UNIQUE column
whose fallback is a colliding placeholder is incoherent; this is the
`or '/'` risk from report 02 (R2) closed.

### A2 · The dead-constraint guard, for the trees a source test cannot reach

Three layers, and deliberately **no raise**:

1. **CI assertion** (`.github/workflows/ci.yml`, right after Bootstrap). CI
   genuinely boots the stack — `bootstrap-and-test` runs
   `scripts/bootstrap.sh` cold — so the container is created inside the job
   and its log is exactly one registry load, which is what makes a count
   meaningful. On a long-lived container it is not: this machine shows **439**
   all-time hits against **0** for the current generation, purely stale
   history. The step greps the specific `_sql_constraints'` string and fails
   the build with the offending lines.
2. **`_register_hook`** (`myservice_api/models/registry_diagnostics.py`) walks
   the built registry — vendored trees included, since it runs after every
   module is loaded — and logs ERROR **with the model names**, not a count.
3. **`GET /api/v1/meta/diagnostics`** (admin-scoped) exposes the same answer
   so `tests/test_meta.py` can assert zero against a real environment rather
   than a checkout.

**Why not raise.** A raise inside `_register_hook` leaves the registry never
marked ready. Under `--stop-after-init` that fails the Job cleanly, but on the
live server it takes down every tenant's registry, and the k8s liveness probe
hits `/web/login`, so the pod restart-loops. That is a full outage in response
to a constraint that was, at worst, already silently absent. The detection
belongs in CI and in an asserted diagnostic; the kill switch is out of
proportion to the fault.

**One honest limitation:** the diagnostics test is admin-scoped, and the local
smoke client has no `admin`, so it **skips locally** and runs in CI (where
`bootstrap.py` mints a full-scope client). That is why the skip count moved
24 → 25. The CI grep is the layer that always runs.

### A3 · `jwt_secret` — a provisioning hole, not two missing rows

Both databases fixed by running the real provisioning step
(`scripts/bootstrap.py`, which is idempotent and preserves an existing
meaningful secret). All eight now have a 64-char secret and a `test_client`.

**But the interesting part is why they lacked it**, and it is a process
defect exactly as you suspected. Setting the secret lives only in
`bootstrap.py`, and `bootstrap.py` is not part of creating a database or
installing modules:

- `k8s/dev/MULTI-TENANT.md`'s "Onboard a new client" step 4 gives
  `odoo -d <db> -i <MODULES> --stop-after-init` as the primary spelling. That
  creates the DB, installs the code, and stops. No secret, no API client.
- `-u` never runs bootstrap either, so a tenant in that state **never
  acquires one by being upgraded**.
- The bootstrap Job is the only automatic path, and `run_bootstrap` defaults
  to `false` — an operator checkbox, not a consequence of creating a tenant.

And it fails quietly: the login page renders, `/auth/token` returns a clean
401 for bad credentials, and **only a caller who supplies the right password
gets the `server_misconfigured` 500**. A smoke test that only tries bad
credentials will never see it.

I have rewritten that step in `MULTI-TENANT.md` to lead with the bootstrap
Job, say plainly that installing modules is not provisioning a tenant, and
give the repair command for a database already in that state.

---

## Part B — tag capture

### `label_state` on `nrs.asset.tag.label`

`issued | printed | affixed | scrapped`, separate from `state` (the
*replacement* lifecycle), `readonly`, `index`ed, tracked on the chatter.
Existing labels default to `issued` — which is the honest answer, since none
was ever confirmed. Verified on every tenant: **zero rows read `affixed`**
after migration.

The field moves only through two methods. There is no path from a form, a
`PATCH`, or `_WRITABLE_FIELDS`, because your framing is the design
constraint: *a `label_state` an operator can set to `affixed` from a desk is
not evidence of anything.*

### Print capture — where the handoff was wrong

`_render_qweb_pdf` on `ir.actions.report` is overridden to stamp the active
tags of the assets being rendered, matched on the four tag QWeb template
names. Proven against the path that bypasses every action method:

```
BEFORE label_state= issued  printed_by= None
AFTER  label_state= printed printed_by= OdooBot
```

Explicit `_mark_printed()` calls remain at each known call site, including the
label wizard — which needs its own, because it passes a
`nrs.asset.tag.label` recordset into a report whose model is `nrs.asset`, so
the render hook cannot resolve those ids. `_mark_printed` is safe to call
twice and never walks an already-`affixed` label backwards.

**`printed` means Cadra issued the print instruction** (Integration Flow step
3.3), not that paper emerged from a printer — which Cadra cannot observe. The
docstrings say so.

### `POST /api/v1/assets/<id>/tag-affixed`, scope `tagging:write`

Its own scope, because the Tag-Issuing Unit is independent of whoever created
the asset record. The submitted `tag_number` is **checked against the tag
Cadra issued**, and that check is the control — it is what makes the record
evidence the right label is on the right asset rather than an assertion that
someone tagged something:

```
3. affix with the WRONG tag number:
   status 400 | validation_failed | Scanned tag NOT-THE-TAG does not match the
   tag issued for this asset (JAIZ-GEN-405). The label on the asset is not the
   one Cadra issued for it.

4. affix with the RIGHT tag number:
   status 200 | label_state affixed | is_tagged true | affixed_by_name J. Okafor
```

`affixed_at` is optional and accepts ISO 8601 with or without an offset, so a
unit tagging offline records when it happened rather than when it synced.

### The honest state, exposed

`data.tagging` — `is_tagged`, `label_state`, `tag_number`, `printed_at/by`,
`affixed_at/by`, `affixed_by_name` — plus `?is_tagged=` and
`?tag_label_state=` filters backed by a stored mirror on `nrs.asset`.

**The trap does not reappear.** A freshly created asset has a populated `tag`
string and `is_tagged: false`:

```json
{"tag_number": "JAIZ-GEN-405", "label_state": "issued", "is_tagged": false,
 "printed_at": null, "affixed_at": null, "affixed_by": null}
```

`data.tag` is untouched — removing it would be a breaking change — but the
reference doc now states outright that it says a tag *number* was allocated
and nothing about whether a label exists.

**Transport is not built**, per your instruction. The delivery gap stands:
`workflow.dispatch.log` records attempts and nothing retries.

---

## Deviations and things found

1. **The print funnel** — the headline, above.
2. **My own endpoint rejected the timestamps its schema advertised.** The
   first test run caught it: Odoo's `Datetime.to_datetime` accepts only
   `"%Y-%m-%d %H:%M:%S"` and rejects the ISO 8601 `T` separator — so
   `"2026-09-14T11:32:07Z"`, exactly what the OpenAPI `format: date-time`
   promises and what every integration sends, returned 400. Now parsed with
   `fromisoformat` first, offsets converted to the naive UTC Odoo stores.
3. **Unknown API scopes were silently accepted.** `myservice.api.client.scopes`
   was a bare `Char` with no validation anywhere, so `taging:write` would be
   accepted, minted into a token, and produce a 403 the caller could not tell
   apart from a real permission decision — rule 3, and it bites hardest
   exactly where scopes are handed to a third party. Added an
   `@api.constrains`; demonstrated:
   ```
   CONSTRAINT_OK: Unknown API scope(s): taging:write
   ```
   Note that **an empty `scopes` field is a wildcard, not a denial** — that is
   pre-existing behaviour I have documented rather than changed, but it is a
   sharp edge when creating a client for an outside unit.
4. **`scripts/bootstrap.py` carries a hardcoded fallback scope list** whose own
   comment says the drift bug it caused was removed. The fallback reintroduces
   it. Updated with `tagging:write`; worth deleting outright once the cold-DB
   import path is reliable.

---

## Verification pass — it found three defects of the same class this work exists to remove

A fresh agent reviewed the diff on the live stack. **All seven of its real
defects are fixed and re-verified.** The first three are the uncomfortable
ones: each is an audit-trail integrity bug, in the module built to fix
audit-trail integrity bugs.

### V1 — the print hook stamped the WRONG asset's tag

The worst finding, and it is my own half-fix. I saw that two callers pass
**tag** ids into reports declaring `model = nrs.asset`, and handled the
false-negative half (the wizard stamps explicitly). I did not handle the
false-*positive* half: the render hook browsed those tag ids as assets, and
tag ids collide with asset ids — **776 collisions in `jaizbankplc` alone** —
so every tag-form print and every wizard print wrote a fabricated *"printed
on `<date>` by `<user>`"* record onto an unrelated asset. Silently, because
the hook swallows exceptions. Proven by the reviewer in a rolled-back
transaction:

```
TAG id=699 owns_asset=702 label_state=issued
AFTER wrong-asset tag label_state: printed printed_date: 2026-09-05 20:48:46
AFTER the REAL tag label_state: issued
MISSTAMPED: True
```

Fixed by declining when the ids also resolve to tag labels — the caller's
intent is ambiguous, both ambiguous callers already stamp explicitly, and the
residual cost is an under-record rather than a fabrication. Re-verified
against the same reproduction:

```
TAG id=967 owns_asset=969
COLLIDING ASSET its_tag=JAIZ-GEN-567 state_before=issued
COLLIDING ASSET tag state_after=issued  MISSTAMPED=False
```

**Fabricating evidence is worse than missing it** — that is the principle I
had applied to `label_state` and failed to apply to my own hook.

### V2 — a repeat confirmation destroyed the original evidence

`_mark_affixed` overwrote unconditionally. Neither `affixed_by_name` nor
`affixed_date` carries `tracking=True`, so a second call did not supersede
the first record, it erased it:

```
first  → affixed_at 2026-01-01T10:00:00, affixed_by_name "FIRST Operative"
second → affixed_at 2026-09-05T20:39:25, affixed_by_name null
```

A caller retrying without the optional fields blanked who fitted the label
and moved the date eight months. The idempotency key covers *replay*, not a
second genuine call. A repeat now leaves the record standing and notes the
repeat on the chatter.

### V3 — a tag awaiting replacement read as never tagged

`active_tag_id` drops a tag the instant its state becomes `pending`, so an
asset whose label is physically on it and merely awaiting a replacement
decision reported `is_tagged: false`, `tag_number: null` — and landed back in
the `?is_tagged=false` worklist. **The false-completeness bug pointed the
other way.** Requesting a replacement is a decision about the future; it does
not peel the label off. Added `physical_tag_id`, which the tagging block and
the stored mirror now read.

### V4 — `?is_tagged=1` silently returned every asset

Only `true`/`false` were matched; anything else fell through both branches
and appended **no domain at all**, so `?is_tagged=1` returned the unfiltered
register and a consumer branching on it treated an untagged estate as fully
tagged. Rule 3, and worse than the backlogged V4-class gap because it inverts
the answer rather than emptying it. Now a 400.

### V5–V7 — the new scope was published inconsistently

- `docs/api/setup_api_smoke.py` — the script `conftest.py` points developers
  at — hardcoded `'dashboards:read assets:read'`, so a developer following
  the documented setup would 403 on every tagging test. Now derived from
  `ALL_SCOPES`, the same drift-proofing `bootstrap.py` already uses.
- The API-client form's placeholder suggested three scope names
  (`dashboard security osint`) that my new constraint now rejects — the
  form's own suggestion had become a hard error.
- `cadra_api_demo_guide.md` still said "13 scopes". Fixed; no stale count
  remains in any doc.

### Also acted on

- **`affixed_at` had no upper bound** — `2099-01-01` was accepted and stored
  for the life of the asset. Future timestamps now 400.
- **The print path had zero test coverage**, which is how V1 survived me. It
  and V2/V3/V4 now have regression tests.

### Risks the reviewer raised that I did NOT change, and why

- **`asset_tag` is writable, so `data.tag` can drift from the real label** and
  a client that PATCHes it then affixes with the value the API returned gets a
  400. Removing `asset_tag` from `_WRITABLE_FIELDS` is a breaking change to a
  published contract with a live consumer, so it is an Architect decision, not
  a Builder one. **Open question below.**
- **`_render_qweb_html` is not stamped**, so the HTML preview does not count
  as printing. That seems right — previewing is not printing — but it is now
  a documented choice rather than an oversight.
- **`except Exception` in the render hook** could in principle swallow a
  `ReadOnlySqlTransaction` that Odoo would otherwise recover from. No read
  replica is configured, so this is latent; narrowing it would need a
  behaviour I cannot test here.
- **`myservice.api.refresh.token.scopes`** is a second copy of the scope
  string with no equivalent constraint.

### Checked and confirmed correct

`'affixed'` is assigned in exactly one place with exactly one caller; no seed,
XML data file, server action, import wizard or barcode route can reach it.
Tag replacement was already correct (new tag starts `issued`, asset becomes
untagged — verified live). The affix control held against every probe: case
sensitivity, whitespace, another asset's tag, a scrapped tag, no active tag,
missing field, missing asset, and exact idempotency replay. `asset_code` is
`NOT NULL` + unique with zero nulls in all eight databases, and `required=True`
on a `readonly=True` field does **not** break the Odoo form (confirmed against
the postprocessed arch and the web client's `_isRequired`). The registry
diagnostic works — injecting `_sql_constraints` onto a registry class flips it
to `True` and removing it flips it back. Timestamp parsing is right, including
offset conversion.

---

## Environment findings — unrelated to this work, both live

**1. `.env` is tracked *and* in `.gitignore`.** A gitignore entry does nothing
for an already-tracked file, so everyone assumes it is protected while edits
to it sit in `git status`, one `git add .` from being committed. During this
session a real `CADRA_TEST_CLIENT_SECRET` was written into it. I reverted it
and it is not in any commit. I checked the history: the only committed change
is `b982444`, which added the key **empty** — so nothing has leaked. The fix
is `git rm --cached .env` (`bootstrap.sh` already recreates it from
`.env.example`), but untracking a file other developers may be relying on is
your call, not mine.

**2. `docs/api/.creds` is one file for eight tenants.** Secrets are
per-database; the creds file is a single global pointer; and both
`bootstrap.py` and `setup_api_smoke.py` rotate the secret unconditionally. So
bootstrapping *any* tenant silently invalidates the file for whichever tenant
the suite is aimed at. It happened mid-session — `.creds` ended up holding
`cadra19`'s secret while the suite was pointed at `jaizbankplc`, and every
test errored at fixture setup with a confusing `401 Invalid client
credentials`. Restored. Both are now in the CLAUDE.md backlog.

---

## Acceptance

| Criterion | Status |
|---|---|
| A tag can be printed, and Cadra can say it was, by whom and when | ✅ `printed_date` / `printed_by`, stamped at the render layer so the bypass paths are covered |
| A tag can be confirmed affixed through the API under its own scope, and only then does the asset read as tagged | ✅ `tagging:write`; `is_tagged` false until confirmation |
| An asset never tagged reads as such — the false-completeness trap does not reappear | ✅ pinned by `test_new_asset_has_a_tag_string_but_is_not_tagged`; zero `affixed` rows in any tenant post-migration |
| `asset_code` NOT NULL and unique in all eight databases | ✅ `is_nullable=NO` ×8 |
| `/auth/login` works on `nrs19` | ✅ secret + client provisioned; clean 401 on bad credentials instead of a 500 |
| Full suite green, per-tenant loop shown | ✅ below |

**Which layers I tested at**, since you asked: the affix control, the filters
and the scope are tested through **HTTP** (`tests/test_tagging.py`, 11 tests).
The print funnel is verified at the **ORM** layer, by calling
`_render_qweb_pdf` directly — the HTTP `/report/pdf/` route needs a session
cookie the API suite does not carry, so an HTTP test there would have tested
the login redirect, not the stamp. The registry guard is asserted at **HTTP**
(admin-scoped, so CI) and at the **CI log** layer. Migration state is verified
in **SQL** across all eight databases.

---

## Test output

Baseline at the start of this handoff: `176 passed, 24 skipped, 3 xfailed`.
After the build and the verification fixes, run twice:

```
run 1: 192 passed, 25 skipped, 3 xfailed in 23.25s
run 2: 192 passed, 25 skipped, 3 xfailed in 20.20s
```

The extra skip is the admin-scoped diagnostics test, as explained in A2.

```
tests/test_meta.py::test_no_dead_sql_constraints_in_the_registry SKIPPED [ 78%]
tests/test_tagging.py::test_new_asset_has_a_tag_string_but_is_not_tagged PASSED [ 92%]
tests/test_tagging.py::test_tagging_block_present_on_every_asset PASSED  [ 93%]
tests/test_tagging.py::test_affix_confirmation_makes_the_asset_tagged PASSED [ 93%]
tests/test_tagging.py::test_affix_rejects_a_tag_number_that_does_not_match PASSED [ 93%]
tests/test_tagging.py::test_affix_requires_a_tag_number PASSED           [ 94%]
tests/test_tagging.py::test_affix_rejects_a_bad_timestamp PASSED         [ 94%]
tests/test_tagging.py::test_affix_accepts_a_supplied_timestamp PASSED    [ 95%]
tests/test_tagging.py::test_affix_on_a_missing_asset_is_404 PASSED       [ 95%]
tests/test_tagging.py::test_label_state_is_not_writable_through_the_api PASSED [ 96%]
tests/test_tagging.py::test_filters_separate_tagged_from_untagged PASSED [ 96%]
tests/test_tagging.py::test_affix_endpoint_is_published_under_its_own_scope PASSED [ 97%]
```

### Per-tenant fan-out

Seven new stored columns (`label_state`, `printed_date`, `printed_by`,
`affixed_date`, `affixed_by`, `affixed_by_name` on `nrs_asset_tag_label`;
`tag_label_state` on `nrs_asset`), so the loop ran on all eight:

```
jaizbankplc  ok      cadra19  ok
lasg         ok      nrs19    ok
nrs          ok      gtb19    ok
gtb          ok      test19   ok
```

```
label_state=6  asset_mirror=1  affixed_count=0     ← on every one of the eight
```

`affixed_count=0` is the important column: the migration cannot make anything
read as tagged.

---

## Open questions

1. **Is `printed` at the render layer the right semantics?** It records that a
   PDF was generated, which is closer to truth than the action methods but
   still not "paper exists". A print queue would be the honest version and is
   almost certainly not worth it.
2. **Should `data.tag` be deprecated in the spec?** It is the field that
   caused this, it still reads as though it means something physical, and
   removing it is breaking. I have documented it instead. A `deprecated: true`
   annotation on the OpenAPI property would warn integrators without breaking
   anyone.
3. **Should the affix endpoint also accept `serial_number`** and check it, so
   the serial-to-tag match is verified on both sides rather than tag-to-asset
   only? The spec's wording ("the serial-to-tag match") arguably asks for it.
4. **`.env` untracking** — yours to decide, as above.
5. **Should `asset_tag` come out of `_WRITABLE_FIELDS`?** It is writable, so
   `data.tag` can be PATCHed until it no longer matches the real label — and a
   client that then affixes using the `tag` the API reported gets a hard 400
   from the control. Removing it is a breaking change to a published contract
   with a live consumer, so it is your call, not mine. The same drift is
   reachable from the import wizard's update branch and the tenant seed
   scripts.
5. **Does the Tag-Issuing Unit get its own API client**, and who creates it?
   The scope exists; the credential provisioning for an external unit does
   not, and the empty-scopes-means-wildcard behaviour makes that a step worth
   doing carefully.

---

## Commits

Branch `feat/tag-capture`, PR **#46** into `dev`:
<https://github.com/wmlmetro/Cadra/pull/46>


| Commit | Scope |
|---|---|
| `248eb34` | `fix`: `asset_code` NOT NULL, and the `or '/'` fallback removed (A1) |
| `03271cd` | `feat`: dead-constraint guard — CI step, `_register_hook`, diagnostics route (A2) |
| `cec656e` | `docs`: installing modules is not provisioning a tenant (A3) |
| `2aac048` | `feat(api)`: `tagging:write`, and unknown scopes rejected on save |
| `87667fb` | `feat`: `label_state`, print capture at the render layer, the affix control |
| `122cfbb` | `feat(api)`: `data.tagging`, filters, `POST /assets/<id>/tag-affixed` |
| `d88de9e` | `fix`: the three capture-integrity defects the verification pass found |
| `59d91e4` | `docs`: this report and the tag-capture rules worth keeping |
