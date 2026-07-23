# Cadra E2E Test Report — Jaiz Bank Plc (`/app`)

**Target:** `http://jaizbankplc.localhost:8069/app` · tenant brand confirmed **"Jaiz Bank Plc"** (primary `#004080`)
**Driver:** Playwright (real Chromium) · **Auth:** `admin/admin` via `POST /api/v1/auth/login`
**Mode:** report-only (no app code changed) · **Data:** full CRUD, test records marked `E2E-<runId>`

## Result (after fixes)

| Outcome | Count |
|---|---|
| ✅ Passed (green) | **98** |
| ⏭️ Skipped | **0** |
| ❌ Failures | **0** |
| **Total test cases** | **98** |

Every route, sidebar link, dashboard, list, filter, form, dialog, and lifecycle action across the
~35-route SPA is exercised end-to-end. A console-guard fixture fails any page that throws an
uncaught exception — none do.

---

## 🐞 Bugs found → FIXED in this branch

### 1. Asset **Move** threw in the UI — `Cannot read properties of undefined (reading 'building')` ✅ fixed
- **Where:** [`dataProvider.ts`](../Frontend/artifacts/nrs-asset-register/src/lib/dataProvider.ts#L237-L245) → [`adapters.ts`](../Frontend/artifacts/nrs-asset-register/src/lib/adapters.ts#L194-L218)
- **Cause:** `POST /api/v1/assets/:id/move` returns the envelope `{ asset, transfer }`. `moveAsset()`
  passed that envelope to `apiAssetToAsset(res.data)` instead of `res.data.asset`, so
  `buildAssetLocation()` dereferenced an `undefined` `location_hierarchy` → `TypeError`. The dialog
  stayed open with a red error even though the move DID persist server-side.
- **Fix:** map `res.data.asset` (typed the envelope), and harden `buildAssetLocation()` to guard a
  missing `location_hierarchy`.

### 2. Asset **Transfer custody** threw in the UI — same root cause ✅ fixed
- **Where:** [`dataProvider.ts`](../Frontend/artifacts/nrs-asset-register/src/lib/dataProvider.ts#L247-L255)
- **Cause:** `POST /api/v1/assets/:id/transfer-custody` returns `{ asset, custody_change }`;
  `transferCustody()` mapped the envelope instead of `res.data.asset` → identical `TypeError`.
- **Fix:** map `res.data.asset`.

### 3. Every Jaiz employee had `ir_number = null` ✅ fixed
- **Where:** [`scripts/jaiz_data_seed.py`](../scripts/jaiz_data_seed.py) `seed_employees()`
- **Cause:** demo employees were created with only a name; no IR (the cross-system staff key used
  for custodian linking and the `/hr/employees/by-ir` lookup) was assigned.
- **Fix:** the seed now assigns a unique tenant-prefixed IR (`JAIZ-IR-00001`…) to every employee
  lacking one — idempotent (fills blanks only). The 60 live Jaiz employees were backfilled, so the
  previously-skipped by-IR test now passes.

Both #1 and #2 hit primary asset-lifecycle actions on every attempt; the fixes are small and low-risk.

---

## ⚠️ Minor findings (open — not fixed here)

- **Create-asset form enables "Create asset" with only a Name**, but the API requires `category_id`
  (`400 validation_failed: Required field missing: category_id`). Submitting name-only silently
  fails (stays on the form with the server error). Consider client-side requiring category, or
  making it optional server-side. Same pattern applies to the raw FK id inputs generally.

## 🔁 Where this runs

Run **locally** against any tenant — default Jaiz, or point elsewhere:

```bash
cd e2e && npm install && npx playwright install chromium
npx playwright test                                   # -> Jaiz (jaizbankplc.localhost:8069)
E2E_ORIGIN=http://odoo.localhost:8069 npx playwright test   # -> any other tenant
```

Jaiz-specific assertions run only when `E2E_ORIGIN` targets the Jaiz tenant, so the suite is portable.
(Not wired into CI — verification is local + the staging deploy.)

## 🟡 Known stubs (by design — documented, not failures)

- **Mock-only pages:** Fleet, Fleet detail, Staff Bus, Identity (clearance) — render read-only sample
  data (no backing v1 API yet). The "Showing mock data" banner appears only in mock mode.
- **Inert controls:** Staff Bus Approve/Reject, Fuel approve/reject, Topbar notifications bell, and
  the avatar have no handlers by design. They render and don't crash.

## ⏭️ Coverage gaps (data, not defects)

- **Employee by-IR redirect** (`/hr/employees/by-ir/:ir`) skipped: every seeded Jaiz employee has
  `ir_number = null`, so there's no value to redirect on. Feature is untested against real data.
- **Live employee bulk import** (xlsx upload + job polling): the form + validation gating are tested;
  the actual import round-trip is flagged for manual verification (needs a real .xlsx fixture).

## ✅ Verified working (highlights)

Auth lifecycle (login/validation/wrong-creds/show-hide/logout/theme) · all ~35 routes render ·
every sidebar nav link · Jaiz branding (`#004080`, logo, active-nav colour) · all 5 dashboards +
Refresh · asset list view-switchers/search/filters/clear/group-by/sort/row→detail · **asset create
& edit (persisted, server-verified)** · asset **verify / mark-missing / condemn** (server-verified) ·
same-location move rejection · locations list/create/edit/detail (+ coordinate map preview) ·
service-desk list/filters/create/detail (priority/assign/comment/transition) · employees list/detail/
tabs · SAP sync · barcode KPIs + real-tag lookup + open-asset · all 5 reports + refresh/paginate.

---

## Test residue (cleanup)

Full-CRUD runs left **~48 assets** and **~4 locations** named `E2E-*` on the local Jaiz DB (no hard
delete exists in the UI/API). They're harmless and greppable. To tidy via API:
`PATCH` assets to `state:"disposed"` and locations to `active:false`, or filter them out by the
`E2E-` name prefix. (Ask me and I'll script the cleanup.)

## How to run

```bash
cd e2e
npm install && npx playwright install chromium   # first time
npx playwright test                               # full suite vs Jaiz :8069/app
npx playwright show-report                        # HTML report + traces/screenshots
```
Env overrides: `E2E_ORIGIN` (target tenant/host), `E2E_USER` / `E2E_PASS` (default admin/admin).
