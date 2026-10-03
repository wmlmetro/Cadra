# Report 49 — the auditor's own screens

**Branch:** `fix/the-auditors-own-screens` · **Base:** `dev` (`ffb08c6`)
**Evidence:** `docs/handoffs/49-evidence/` — 29 spec-49 screenshots across `test19`, `boot44` and `nrs19`, the two auditor sidebar shots from the spec-46 re-runs (the Audit group with all five items), the spec-46 matrices for both tenants, and `suite-results.txt` with every runner's own final line

## A · What was built, in plain terms

Zainab Garba can now do her job in the app. Four pages, all reading routes
that have answered her for weeks, none of which changed:

| Screen | Path | Server's gate | What it shows |
|---|---|---|---|
| Configuration changes | `/admin/configuration-changes` | `settings:read` | The last-write-only parameter record: statement and fidelity notes first, then every parameter with its current (or redacted) value, whether it changed after creation, who last wrote it and when. Auto-walks every page, like Access changes. |
| Disposals | `/reports/disposals` | `assets:read` | The whole-period summary (clean count, findings pills, methods, proceeds, the INT-09 statement) above the rows; the UNPLACEABLE disposals — no date from any source — in their own labelled section, never mixed into the period; dated rows behind Load more. |
| Register snapshot | `/reports/asset-register` | `assets:read` | The register as of a day. Per-row `_fidelity.unknown` renders as *not recorded then* (fields the record cannot place on the day; the as-of-today fields are declared on the global fidelity line); the fidelity line says how many fields roll back and since when; **no filters, on purpose** (§C1). Carries the departed-custodians card (§B). |
| Export | `/reports/export` | `assets:read` | A download, not a table — §C2 for every decision the handoff asked for. |

Both gates are registered for each: the nav item declares the server's scope
(`lib/navigation.ts`, Audit group, beside Access changes) and the switch keys
`configuration_changes` / `disposals_report` / `register_snapshot` /
`register_export` are in `SIDEBAR_GROUPS` and the published-keys table,
default on. `myservice_api` → 19.0.3.23.0 — a controller constant only, so a
container restart serves it; no model, view or data changed and **no
per-tenant upgrade was run** (nothing for one to do).

**Scope consequence, stated as the handoff's rule requires:** three of the
four screens are gated on `assets:read`, so they are drawn for — and
answered to — every Asset User, Officer and Manager, not only the Auditor.
Spec 46's matrix now proves exactly that (drawn ⇒ answered, hidden ⇒ 403,
all six personas, both tenants). Whether a Store Officer should be offered
the whole-register export is a **role-model finding for the Architect**
(`docs/GO-LIVE.md` §26); the sidebar does not invent a scope to hide it.

## B · §4 — the 87 assets held by 59 people who have left, now visible

Answerable without a new endpoint, so it was made answerable.
`GET /identity/employees?active=false` already publishes `assets.count` and
`assets.has_pending_retrieval` per person; the register snapshot walks every
page of it and renders a card:

> **87** assets still name **59** people who have left as custodian — **none
> flagged for retrieval**. (207 departed people on record in all.)

with the list of the 59 (name → employee page, department, leaving date,
asset count) behind a toggle. Re-measured on `nrs19` before building
(2026-10-03, SQL): **87 non-disposed assets, 59 archived employees, of 207
archived in all, 0 flagged** — exactly reports 43/45. "Left" means the
employee record is archived (`hr_employee.active = false`); their SAP status
still says active, which is report 45's INT-finding, unchanged here. The
held-assets denominator alone re-measured 6,644 against reports 43/45's
6,646 — the 87 and the 59 held exactly.

Four honesty rules on the card, because the measurement demanded them:
- **The denominator is always shown**, zero included — on `test19` and
  `boot44` it reads *"No assets name a departed person as custodian — of 0
  departed people on record."* A zero without the 0-denominator would be
  exactly the CLAUDE.md shape.
- **It says it is measured NOW**, not as of the snapshot date — the employee
  record has no history to roll back.
- `assets.count` includes a disposed asset still naming the person (0 of the
  87 today); the card's small print says "assets still naming the person".
- Drawn only for holders of `identity:read` (the employees route's own
  scope — the Auditor has it); without it the snapshot is complete and the
  card is simply absent.

## C · The two decisions the handoff asked me to state

### C1 · The snapshot screen has no filters

The route takes fourteen; the screen offers one date. The response's own
`filters.note` says filters select on the asset's **current** values while
the rows are rolled back — a filtered snapshot reports a different
population from the one it selected. A reconciling register with a quiet
population mismatch is the exact shape this programme keeps catching, so the
page says why on its face instead of offering the trap.

### C2 · The export

- **What the button does:** fetches `GET /api/v1/assets/export.csv` with the
  session's bearer token (`lib/api.ts#apiGetRaw`, new — a plain `<a href>`
  carries no token and `apiGet` refuses non-JSON) and hands the browser the
  blob. One click, one file.
- **What the file is called:** whatever `Content-Disposition` names —
  `nrs_assets.csv` — twelve columns, every state included (a disposed or
  missing asset is a row like any other).
- **What a large tenant does:** nothing special — the server builds the body
  in one piece and a frontend session is uncapped. Driven end to end on
  `nrs19`: the page said *"This register holds 11,951 assets"* before the
  click, the browser's download event fired, and the saved file held
  **11,951 data rows, 1,242,781 bytes, 1.2 s click-to-done** — screen count
  = file rows = register. `test19`: 10,883 rows / 1.1 MB / 0.7 s. `boot44`:
  231 / 23 KB / 0.4 s.
- **What the person sees while it is produced:** the register's size before
  the click; a disabled button with *"Preparing the export…"* and a sentence
  saying the download starts by itself; then name / rows / bytes / seconds
  in green — or the refusal in words, with *"Nothing was saved."* If the
  server ever cuts the file (an API credential's cap is 100; a frontend
  session should never see it), the `X-Cadra-Truncated` header renders in
  amber naming cap and total, because a file quietly missing most of the
  register is worse than no file.
- **The JSON twin stays API-only.** `GET /assets/export` has no filename, no
  truncation header and no ids; the CSV is the route shaped like a file.

## D · Verification, with denominators

- **pytest, `test19`, full suite:** `1 failed, 1289 passed, 9 skipped`
  **of 1299** in 378 s — the one failure being
  `tests/test_sidebar_settings.py`'s published-key-count pin (26), i.e. the
  guard catching the four new keys as designed. Pin moved to 30 with the
  handoff-49 comment; the file re-runs **21 passed of 21**. Final whole-suite
  re-run after every change: see §G. The 9 skips are `test19`'s documented
  set (CLAUDE.md's categories, unchanged).
- **Spec 49 (new), `test19`: 4 passed of 4. `boot44`: 4 passed of 4.**
  1. *Zainab reaches all four screens, and the export downloads* — signed in
     through the real login, each page renders the server's answer, each nav
     item is drawn for her, the download event fires with `nrs_assets.csv`,
     no truncation.
  2. *An empty report says so in words* — period/date **1990** (§E1), the
     three empty-state sentences assert, zero rows, nothing invented.
  3. *Refused on the typed URL and by the server* — the Tag-Issuing Unit on
     all four (scope refusal rendered AND 403 from the probe); the Store
     Officer on configuration-changes (403) while disposals answers them
     (not 403) — the server's own gate, named in §A.
  4. *The tenant switches, off and on* — all four keys off: gone from the
     auditor's sidebar, the typed URL still answers with data (presentation,
     not permission); back on: drawn again. `finally` restores.
- **Spec 46 (extended with the four paths) + spec 48, re-run:**
  **11 passed of 11** on `test19`, **11 passed of 11** on `boot44`.
- **Static guards:** `test_sidebar_catalog.py` + `test_nav_scopes.py` +
  `test_source_guards.py`: **228 passed of 228**.
- **Screenshots** (`49-evidence/shots/`): all four screens as Zainab on both
  tenants; all three empty states on both; five refusal shots per tenant;
  hidden-but-answering; the `nrs19` export completion.

## E · What the verification found (and one fix in the diff because of it)

1. **"Empty period" had to be measured, not assumed.** The spec's first
   empty-state run used 2020 and failed: **every local tenant's fixtures
   backdate disposals to exactly 2020-01-01** (`test19` answered 37 for
   2020, `min(disposal_date)` is 2020-01-01 on `test19` AND `boot44`). The
   spec drives 1990, which `test19` holds 0 of its 2,0xx disposals in. The
   same instinct as the denominator rule, pointed at a date.
2. **A null `value.book_value` white-screened the entire app.** The
   snapshot's first page on `test19` contains rows whose depreciation value
   is `null` (not computed — not zero); `fmtValue` threw in render, and with
   **no React error boundary anywhere in the tree** the whole app unmounted
   to a blank page with no words. Fixed in this diff (a null prints as a
   dash, and the type now says `number | null`); the missing boundary is
   recorded for the Architect (`docs/GO-LIVE.md` §26) — one route-level
   boundary turns any future render bug from a blank page into a sentence.
3. **The unplaceable disposals forced a third empty state.** With a period
   that holds no dated disposals, `summary.total` can still be non-zero on a
   tenant with undated ones — so "no disposals in the period" and "no DATED
   disposals, the rows above sit outside every period" are different
   sentences and the screen says the right one.

## F · Deviations from the handoff

- §5 asked each screen driven on a tenant where the underlying data is
  EMPTY. Done for three of the four with a measured-empty period/date
  (1990); **the export has no empty drive**, because no local tenant has an
  empty register — its non-invention is proven the other way round, by the
  file's row count equalling the register on all three tenants driven.
- Disclosure, same shape as the one §0 noted: the Step-0 commit of the
  instruction file (`ffb08c6`) went out with the harness's attribution
  trailer before the committer caught it — the repo rule is no AI reference
  in commits. Per §0's ruling the past one is left and the rule is kept from
  there: every commit after `ffb08c6` in this branch carries none.
- One addition the handoff did not ask for:
  `tests/test_sidebar_settings.py`'s key-count pin moved 26 → 30 (the suite
  caught the new keys; moving the pin with a comment is the test's own
  protocol), and a one-paragraph additive entry in `docs/api/CHANGELOG.md`
  because the sidebar's published key set is consumer-visible surface.
- §6 (clearance) was not built, per the handoff. One observation for the
  Architect from being in the data, as §6's last line asked: the departed-custodians card now gives the clearance
  conversation its live number on a screen NRS can open — 87/59/0-flagged —
  which may be useful in the room when NRS answers the "what does clearance
  mean" question. Custody remains employee-record-based (1 of 11,386 NRS
  employees has a login, report 43 §G.2), and nothing in these screens
  implies account-switching-off.

## G · Final whole-suite runs (after every change in this report)

- Playwright, whole suite on `test19`: **2 failed, 12 skipped, 188 passed
  of 202** in 12.3 m. The two failures are exactly the §13.5 baseline pair,
  red on `dev` before this branch (both depreciation specs); the 12 skips
  are all pre-existing data-dependent skips in specs 06/08/35/38/39 — none
  in 46, 48 or 49. Named one by one in `49-evidence/suite-results.txt`. The
  §13.5 baseline said 4 skips of 169; the suite is 202 tests now and the
  skips are a function of the tenant's data, not a constant — CLAUDE.md's
  standing sentence said the old pair of numbers as if fixed and has been
  updated to say the rule instead (this is the verification pass's finding,
  the project's own denominator shape pointed at the suite itself).
- pytest `tests/` on `test19`, final whole-suite re-run after every change:
  **1290 passed, 9 skipped of 1299** in 377 s — 0 failed, and the 9 skips
  are `test19`'s documented categories, count unchanged.

## H · Commits

- `ffb08c6` — docs: handoff 49 instruction file (Step 0, on `dev`; carries
  the trailer disclosed in §F)
- `693c022` — feat(app): the four screens, both gates registered, the null
  `book_value` guard; `myservice_api` 19.0.3.23.0
- `95f05ed` — test(e2e): spec 49, and spec 46's `ITEMS` extended
- the commit carrying this report — docs: report 49, evidence, DECISIONS /
  STATUS / GO-LIVE §26 / CHANGELOG / CLAUDE.md row 49 and the browser-suite
  skip sentence
