# Cadra Checkpoint — 2026-08-11

Feature delta since [CHECKPOINT_2026-06-09.md](CHECKPOINT_2026-06-09.md).

## TL;DR

**Asset depreciation shipped** — PRD §8.6 "Financial properties" is now
implemented rather than merely specified. Policy (method, useful life, salvage)
is configured per asset category and overridable per asset; book value and
accumulated depreciation are computed and stored; the period-by-period schedule
is generated on demand and exposed over the API and in the SPA.

The one thing to take away: **the mechanism works, but the register has no
financial data to feed it.** Verified directly against every tenant database —
not a single asset in any tenant has an acquisition cost or an acquisition date.
Depreciation cannot produce a meaningful figure until costs are captured. That
is a data-collection problem, not a code one, and the feature reports the gap
explicitly rather than presenting empty totals as fact.

---

## What shipped

### New module: `myservice_asset_depreciation`

Depends only on `myservice_asset_register`. Extends `nrs.asset` and
`nrs.asset.category` via `_inherit`, matching how `myservice_identity` and
`myservice_barcode_station` already extend the register.

**No dependency on `account`.** PRD §3.3 lists financial accounting and the
general ledger as explicit non-goals, and §8.6 confirms Cadra "does not produce
the official financial books". Nothing here posts a journal entry. (Odoo's
`account_asset` is Enterprise-only and unavailable on this CE stack in any case.)

Methods match the already-published API enum exactly:
`none | straight_line | declining_balance | erp_managed`.

### Two architectural calls worth recording

**1. The schedule is generated, not stored.** Persisting a board would mean
~12k assets × 60–120 monthly periods ≈ 1M+ rows that are pure derivations of
five fields, plus regeneration churn on every cost edit. Odoo's `account_asset`
persists its board because it posts journal entries that must be auditable — we
post nothing, so that justification does not transfer. Only the summary
(`accumulated_depreciation`, `current_book_value`, `depreciation_state`,
`depreciation_end_date`) is stored, because list views, `read_group` and the
report endpoint need it queryable in SQL.

A useful consequence: because the board is a pure function of its inputs,
`?as_of=` gives a genuine point-in-time view for free — which is what PRD §13.4
asks for ("asset register snapshot at any historical date"). A persisted board
would have made that harder.

**2. The summary fields are plain, not `compute=`.** Two reasons. ERP-managed
assets must keep figures written from outside, and a stored compute would have
to read its own value to preserve it. And these figures drift with *time*, not
just with their inputs — nothing changes in the database when a month passes —
so the monthly cron is required regardless and `@api.depends` would buy less
than it appears.

### ERP-managed mode

NRS spec §6.2 makes SAP FICO authoritative: *"Depreciation method — SAP FICO —
Cadra reads but does not compute."* Assets set to `erp_managed` are skipped by
the engine entirely; `accumulated_depreciation` and `current_book_value` stay
writable so an external system can feed them, and the UI labels them as
externally supplied. This keeps NRS compliant with its own signed spec while
GTB/Jaiz/LASG use the computed methods. No SAP connector is in scope.

### API

- `financial.depreciation` added to every asset payload (extends the existing
  nested `financial` object rather than flattening keys onto the root).
- `GET /api/v1/assets/<id>/depreciation` — the board, with `?as_of=`.
- `GET /api/v1/reports/depreciation` — register-wide totals and breakdowns.
- Policy fields added to `_WRITABLE_FIELDS`. Worth noting that allow-list drops
  unknown keys *silently*, so an omission shows up as an unchanged value rather
  than an error — there is a test specifically for that.

Both endpoints are documented in
[api/cadra_api_endpoint_reference.md](api/cadra_api_endpoint_reference.md)
(§3.10 and the new §10) with captured real responses.

### SPA

Depreciation card on the asset detail page (with an explicit warning when the
start date was inferred, and a distinct note for ERP-managed assets), and a new
**Depreciation & Book Value** report at `/reports/depreciation`.

### Verification

- 36 engine unit tests, no Odoo runtime required — `tests/test_depreciation_engine.py`.
  These are the first Odoo-side unit tests in the repo; the engine is pure
  Python precisely so this was possible.
- 13 API tests — `tests/test_depreciation.py`. All passing.
- Module installed and exercised against `cadra19`; report page and detail card
  confirmed rendering in a real browser.

Two properties worth calling out because they are the classic failure modes:
a schedule always sums to *exactly* `cost - salvage` (the final period absorbs
the rounding remainder, so the register reconciles to the kobo), and declining
balance terminates cleanly at salvage instead of leaving a dangling stub.

---

## The data problem

Checked directly in Postgres across every tenant:

| DB | assets | with cost | with acquisition date |
|---|---|---|---|
| nrs19 | 11,878 | 0 | 0 |
| cadra19 | 1,272 | 0 | 0 |
| jaizbankplc | 221 | 0 | 0 |
| gtb19 | 156 | 0 | 0 |

The NRS import CSVs (`docs/seed/NRS_asset_seed/`) do carry an
`acquisition_cost` column on all 11,878 rows — but **every value is `0.0`**, and
there is no acquisition or purchase date column at all. Earlier notes describing
this cost data as "100% populated" were reading column presence, not values.

Consequences:

- Book values will be zero everywhere until costs are captured.
- `depreciation_start_date` falls back through
  `acquisition_date → purchase_date → create_date`, and
  `depreciation_start_source` records which one won. Anything resolving to
  `created` is an inferred date, not a real capitalisation date. The report
  surfaces the count as a backfill queue, and the asset form shows a warning.
- For NRS specifically this matters less than it looks: their spec puts them on
  `erp_managed` anyway, and SAP FICO is the only place those figures exist.

## Rollout

`myservice_asset_depreciation` is a **new** module, so it needs
`-i myservice_asset_depreciation` via the upgrade Job
([k8s/dev/51-upgrade-19-job.yaml](../k8s/dev/51-upgrade-19-job.yaml)) against
each tenant DB — a pod restart will not pick it up. `myservice_api` gained the
dependency, so it needs `-u` alongside.

Then run `scripts/backfill_depreciation.py` per tenant (dry-run by default;
`BACKFILL_APPLY=1` to write, `BACKFILL_ERP_MANAGED=1` for NRS).

**Why a script rather than data files:** both `asset_categories.xml` and the new
`depreciation_policy_defaults.xml` are `noupdate="1"`, so shipped defaults reach
fresh installs only — Odoo skips noupdate records on upgrade. This was confirmed
in practice on `cadra19`: after `-u`, all 20 categories were still unset. The
flag is deliberate (without it every upgrade would overwrite policies a tenant
had tuned by hand), so the script applies the same values directly. It also
reports loudly when a tenant has categories the shipped defaults don't cover —
on `cadra19` that is all 1,283 assets, which sit in a tenant-specific
"Furniture & Fittings" category.

## Still open

- **Unchanged from the last checkpoint:** webhooks, audit log, the PRD §8.4
  10-state asset lifecycle, and tag schema. This work did not touch them.
- `current_value` (the old hand-typed field) is left in place and relabelled
  rather than repurposed, so no existing consumer breaks. It should be retired
  once tenants have migrated to `current_book_value`.
- `acquisition_cost` vs `purchase_value` and `acquisition_date` vs
  `purchase_date` remain two unreconciled parallel pairs on `nrs.asset`. A
  computed `depreciable_cost` encodes the precedence explicitly; reconciling the
  underlying fields is a separate data-cleanup job.
- Two judgement calls the spec does not settle, both isolated to one place and
  worth confirming with whoever owns the tenant relationships: the **whole-month
  proration convention** (depreciation starts the month after the start date, no
  day-count apportionment) and using **`acquisition_cost` before
  `purchase_value`** as the depreciable base.
- `accumulated_depreciation` appears in NRS spec §6.5 but not in the PRD §8.2
  attribute table — a pre-existing inconsistency between the two canonical docs
  that this work makes concrete.
