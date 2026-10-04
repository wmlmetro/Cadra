# Report 50 — the consequences

**Branch:** `fix/the-consequences` · **Base:** `dev` (`d9bd730`)
**Evidence:** `docs/handoffs/50-evidence/` — the before/after drives as real
personas, the per-tenant credential and user counts, the write-only-key
measurements, the two red specs' first recorded failure texts, and the final
suite lines.

## A · What was built, in plain terms

All of §§1–4 and all three §5 items. Nothing hit the stop rule.

| Item | What changed |
|---|---|
| Ruling 1 | Taking a copy of the register is its own permission: **`export:read`**, on both export routes, granted by exactly the Auditor; `admin` wildcard covers administrators. BREAKING, announced like 47's. |
| Ruling 2 | **`RouteErrorBoundary`** — any render error is now a sentence, the error's message, and a live sidebar; never a blank page. Proved by a deliberate throw. |
| Ruling 3 | The attribution trailer is **refused by machinery**: a committed commit-msg hook (active in this clone) and a CI job over exactly the new commits of a push or PR. Proved by a live refused commit. |
| §2.1 | `GET /dashboard/map` sends **`locations` only**; the vehicle rows (plate, driver) moved to new **`GET /fleet/map`** under `operations:read`; `recent_requests` deleted unread. BREAKING. |
| §2.2 | Credential counts re-taken on all nine tenants; nothing to widen quietly — the decision list is §F, owner's. |
| §3 | The two red browser specs **named**, with their failure texts recorded for the first time. Neither is 37's defect. |
| §5 B1 | `salvage_rate` and `verification_notes` **published**; `mobile` **stops being accepted** — all three decided by measurement. |
| §5 D1 | The published-names census **widened to every first-party `controllers/*.py`** — 73 body routes of 142 first-party routed declarations, two-way equality, denominator printed every run. |
| §5 D3 | The words guard's **two string classes separated** and the class-1 census drawn over five report endpoints; the class-2 exemption pinned so it cannot be silently reversed. |

Module versions: `myservice_api` 19.0.3.24.0, `myservice_dashboard`
19.0.1.1.0, `myservice_identity` 19.0.1.2.0. No stored field, no view, no
new data record beyond one group-comment correction — a container restart
serves all of it; the `-u myservice_api` fan-out was still run on all nine
local tenants (0 errors each, `50-evidence` not needed: the loop's output is
in §I).

## B · Ruling 1 — the export scope

**The name.** `export:read`, not `assets:export`. `test_auditor_access.py`
pins every Auditor scope to end in `:read` — the pin encodes "the Auditor
changes nothing", an export changes nothing, and a name that forces an
allow-list hole through a standing guard is the wrong name. Recorded in
`docs/DECISIONS.md`.

**The grant.** `GROUP_SCOPES`: the Auditor row alone gains it (the
`SCOPE_GROUPS` documentary row follows the `access:read` precedent). No
register group gains or loses anything else; an Asset User/Officer/Manager
keeps every page read and loses exactly the whole-register copy.

**Driven as each (handoff §4):** on `test19`, Store Officer
`halima.danjuma` — `GET /assets/export` → **403 `forbidden`,
`details.required_scopes: ["export:read"]`**; `export.csv` → **403**; the
same token still reads `/assets?limit=1` 200. Auditor `zainab.garba` — both
routes **200** (her session token carries the scope by group derivation
alone; nothing was provisioned). Before the change the same Store Officer
token got **200 on both** (`50-evidence/before-as-storekeeper.txt`). In the
browser: the Export item is not drawn for the storekeeper, the typed URL
shows the refusal naming `export:read`, and Zainab's download still runs
end to end (spec 49 re-run: the export line on `test19` read 11,173 rows in
0.7 s this run — the register grew 290 rows since report 49's 10,883, both
honest counts of their day).

**Who loses it, with denominators (§F has the tables):** session users are
the real surface — the API export was already capped at 100 rows, so no
API credential ever took a whole register through it.

## C · Ruling 2 — the boundary

`src/components/RouteErrorBoundary.tsx`, mounted in `App.tsx` inside
`AppLayout` around the page Suspense (so a failed lazy chunk is also
caught), keyed on the wouter location (navigating away clears the error),
and around the two shell-less public Suspenses. It renders *"This page
failed to draw."*, *"The rest of Cadra is still working — use the menu to
open another page, or try again,"* the error's own message in small type
(so there is something to report), and a Try-again button.

**Proved by throwing (spec 50, test a):** the spec feeds `/assets` a
well-formed envelope whose `locations` is a string; the register dashboard
throws in render; the boundary renders BOTH sentences with the sidebar
alive; clicking All Assets draws the next page normally. 3 of 3 on `test19`
AND `boot44`. One intercept subtlety became a design fact worth keeping:
the bad payload had to be installed before sign-in, because the 60-second
fresh cache would otherwise mask the crash — the same cache behaviour §H
names on spec 14.

## D · Ruling 3 — the trailer is refused by machinery

Three pieces, one pattern list (`scripts/check_commit_messages.sh`):

- **`scripts/git-hooks/commit-msg`** — refuses at commit time. Activated
  per clone with `git config core.hooksPath scripts/git-hooks`, which is
  set in this clone. `--no-verify` skips any hook, which is why the next
  piece exists.
- **CI job `commit-messages`** (`.github/workflows/ci.yml`) — fetch-depth
  0, checks exactly the new commits (PR `base..head`; push
  `event.before..sha`, falling back to `origin/dev..HEAD` on a new
  branch). **Never full history**: 206 of the 209 commits reachable from
  `dev` carry a trailer from before the rule was mechanical and stay as
  the owner ruled.
- Patterns (case-insensitive): `co-authored-by:.*claude`,
  `generated with.*claude`, `noreply@anthropic\.com`, `anthropic\.com/claude`.

**Proved (handoff §4):** a live `git commit` carrying the exact trailer was
refused — exit 1, both matching patterns named with the offending line, and
`git log` confirms no commit was created; a clean commit passes; range mode
flags the historical range (exit 1) and passes the clean Step-0 range
(exit 0). Every commit on this branch was made with the hook active.

## E · §2.1 — the map

**What the register dashboard needed was measured, not assumed:** every
first-party consumer of `/dashboard/map` except one reads only `locations`
(Dashboard, register dashboard, IT command, inventory report — file:line in
the diff). The one exception is the Fleet Command Center — an
`operations:read` screen — so the vehicle rows were a fleet screen wearing
the register's scope, and they MOVED: new `GET /fleet/map`
(`operations:read`), same row shape. `recent_requests` was read by nothing
and its documented shape had drifted (it declared `priority` and
`create_date` the server never sent); deleted. The back-office twin
`/myservice/dashboard/map` keeps the full shape — administrators-only since
handoff 45.

**Before/after as a real Store Officer** (`50-evidence/`): no tenant holds
a geocoded vehicle (0 of 3,338 across nine tenants — the leak was the
shape, never yet a row), so one evidence vehicle with a named driver was
seeded on `test19` (test-class), and the same token read:

- before: `keys: [fleet, locations, recent_requests]`, one fleet row —
  `{'plate': 'EV50-TEST', 'driver': 'Evidence Driver (handoff 50)'}`;
- after: `keys: [locations]`, the raw body containing neither `"plate"`
  nor `"driver"`; `/fleet/map` → 403 for the Store Officer, 200 with the
  row for an administrator. The evidence fixtures were then removed and
  the location's coordinates zeroed (state as found).

The register dashboard still draws (spec 46's rows now probe
`/dashboard/map` on `/`, `/assets` and `/dashboards/it` — a recorded gap:
pages that called the map never probed it). The SPA's persisted-cache
version was bumped v4 → v5 so no browser resurrects a pre-change payload
with fleet rows in it.

## F · §2.2 — credentials provisioned under the old scopes

Re-counted 2026-10-03, all nine local databases, whole-token SQL match
(`50-evidence/credential-scopes.txt`, 21 credentials in all, 14 active).
Report 47 §B's conclusions hold unchanged:

- **`identity:read` and `dashboards:read` (47's splits):** the affected
  non-admin active credentials are `test_client` on **gtb, gtb19,
  jaizbankplc, lasg, nrs** (5 — each holds `identity:read` +
  `dashboards:read` + `assets:write`, none holds `access:read`,
  `operations:read` or `tagging:write`), plus `vendra` on **nrs19 and
  boot44** (`assets:write` only — Vendra registers assets, never minted a
  label, needs nothing).
- **This handoff adds a fourth row to the same decision:** the **8** active
  non-admin credentials holding `assets:read` (the 5 `test_client`s,
  `vendra` ×2, `nrs_approver` on nrs19) lose the two export routes unless
  given `export:read`. None is known to call them, and an API credential's
  export was already a 100-row sample.
- **Nobody is affected in a way that blocks anything today**: every
  credential above is a demo/suite credential or an integration that does
  not use the moved routes. So per the handoff — *"if nobody is affected on
  any tenant, say so with the counts and we are done"* — the counts say no
  quiet widening is needed; if a demo needs one of these credentials on a
  moved route, the fix is that credential's scope row and a named decision.
  `[open]`, owner, unchanged in GO-LIVE §25 with the new counts.

**Session users who lose the export screen** (direct memberships; on 19
implication writes no rows — denominators are register-group holders):
test19 **9 of 11**, boot44 **4 of 7**, jaizbankplc **5 of 7**, gtb **4 of
6**, lasg **4 of 6**, nrs **4 of 6**, gtb19 **1 of 2**, nrs19 **2 of 4**,
cadra19 **0 of 2** — many of them demo personas, all of them people whose
job the ruling says is not taking register copies.

## G · §3 — the two red specs, named

Full write-up with both failure texts (recorded for the first time — no
prior evidence file carried either): `50-evidence/red-specs-13-14.md`.
The §3 question answered directly:

- **Neither is handoff 37's defect**, in browser form or otherwise. Both
  predate it (red since report 29), fail at every hour (37's was red one
  hour a night), and neither disposes anything.
- **Spec 13** (*a computed asset charts its value over time*) is a
  fixture-selection defect in the SPEC: it takes the first computed-method
  asset without checking it has a cost or useful life; on `test19` that
  asset has neither, the product renders its honest *"No schedule yet —
  this asset needs an acquisition cost and a useful life"* empty state, and
  the spec's assumption fails. The first-computed ≠ first-chartable — the
  denominator instinct pointed at a fixture.
- **Spec 14** (*the straight-line switch persists across a reload*): the
  flip PASSES; the post-reload state stays unchecked for the full 30 s with
  no refetch — which matches GO-LIVE §16.3 item 8's persisted-cache
  hypothesis point for point (restored cache inside `staleTime` renders as
  fresh; the persister's write throttle can restore the pre-click payload).
  Handoff 29's family — a screen lying to its own session from cache — not
  a depreciation defect; the switch merely lives on that settings page.
  Still labelled a hypothesis: nobody has read the localStorage payload
  mid-test, and saying so is the §3 rule.

Not fixed, per the handoff. The fixes are a spec fixture and a cache-policy
decision; both now have enough on record to be picked up cold.

## H · §5 — the three absorbed items

### B1 · The three write-only keys — measured, then decided

(`50-evidence/write-only-keys-measurements.txt`, nine tenants, 2026-10-03)

- **`mobile` — stop accepting it.** 0 of 15,780 employees hold a mobile
  number (nrs19's real 11,386-employee extract included); 0 of 321
  sync-log payloads ever carried the key. Removed from `SAP_FIELD_MAP`
  (`SAP_PAYLOAD_KEYS` is derived from it, so one removal closes all six
  callers) and from the OpenAPI `SapEmployee` schema. BREAKING on a
  contract that is live on no tenant (secret on 0 of 8, report 37) —
  announced in `CHANGELOG.md`, and the change lands in the contract before
  NRS's SAP team builds against it rather than after.
- **`salvage_rate` — publish.** 10,364 of 11,173 assets on `test19` carry
  one (3,777 of 4,164 jaiz, 227 of 231 boot44): real data nobody could
  read back. Now in the asset's `financial.depreciation` block beside the
  `salvage_value` it derives.
- **`verification_notes` — publish.** 193 of 11,173 on `test19`, sparse
  but real. Now on the asset GET beside the verification fields.
- Their `_WRITE_ONLY` waivers are deleted, so the census's read-back test
  ENFORCES both publications — the guard proves the fix. The list is down
  to the one recorded false positive (`generic_location_id`).

### D1 · The census widened — and a correction to the handoff's premise

`test_published_names_resolve.py` now walks **every first-party
`controllers/*.py`** (`myservice_*` + `cadra_brand_*`, globbed from the
addons root), with no `/api/v1` prefix filter. **Denominators, 2026-10-04:
73 body routes of 142 first-party routed declarations — 48 under
`/api/v1`, 25 outside — plus 4 back-office overrides of core routes, each
classified in a two-way table (every body route classified; no table entry
for a route that is gone; every bare override named).** Outside the prefix,
3 routes resolve to declared key sets (quick-submit, the two SAP doors) and
22 carry named-edge entries with the reason the key-level check cannot or
need not apply (JSON routes whose params bind to the signature,
administrators-only station routes, the HMAC-signed callback, a 301
redirect, an X-API-Key body-ignoring export). The docstring names what is
still outside: core Odoo routes, `dist/`, raw model methods, and the read
side, which deliberately stays `myservice_api`-only. The census prints its
denominator every run so the next report quotes it with a date rather than
from memory.

**Correction the Architect should have back:** §D1's *"163 → 179 → 286"*
figures are not this census. They are the **SAP sync-log row counts** (the
identity-door usage census, report 37: 0 `webhook` of 287 rows), a
different measurement that moved because the suites write sync rows. The
route census was never those numbers. Both now state denominator and date;
nothing else needed correcting.

### D3 · The words guard — separated, then drawn

Report 36's ruling implemented rather than re-argued, in
`myservice_api/tests/test_words_classes.py`:

- **Class 1 — composed statements** (keys named `statement`, `meaning`,
  fidelity notes, `filters.note`): words only — no backticks, no
  field-path shapes. The census is drawn by LIVE calls across the register
  snapshot, disposals, configuration-changes and access-changes reports
  plus the one composed history key the existing test does not collect;
  the existing `test_the_statements_are_words_not_field_names` is
  untouched (reports cite it by name) and delegated to. User-entered
  content is excluded structurally — named keys are collected, payloads
  are never swept.
- **Class 2 — refusals** (error-envelope `message`/`details`): may name a
  field, a key or a literal command, on `mark_command`'s recorded
  reasoning. Deliberately uncovered, and the exemption is PINNED: a test
  asserts the gated-write refusal still composes
  `set_command(self.env.cr.dbname)`, so the ruling cannot be reversed by a
  well-meaning cleanup without a test failing.
- **Found by drawing it:** 4 snapshot fidelity notes
  (`myservice_asset_register/models/asset_snapshot.py` — `tracked_from`,
  `custodian_id`, `value`, `tag_label_state`) carry backticked key paths
  today. Outside §5's file set, so they are NAMED in a standing-violations
  table (a new violation anywhere fails; fixing one forces its row out)
  rather than fixed — the Architect gets a clean worklist. Two defensive
  future branches say *"see `fidelity`"* and will fail the guard the day a
  tenant reaches them — which is the guard working, recorded so nobody is
  surprised. One string in my own file (`filters.note`) violated the rule
  and was reworded.

## I · Verification, with denominators

- **pytest, `test19`, full suite — final re-run after every change:**
  **1294 passed, 9 skipped of 1303** in 378 s, 0 failed
  (`50-evidence/final-suites.txt`). The first run had 1 failed of 1303 — a
  30 s ReadTimeout on
  `test_clearing_a_custodian_is_not_a_grant_and_is_not_gated` (untouched
  by this branch, first run after a container restart), which passed alone
  in 3.4 s and passes in the final run. The 9 skips are `test19`'s
  documented categories, count unchanged.
- **In-registry, `--workers=0`, each denominator line printed:**
  `myservice_api` **0 failed, 0 error(s) of 371 tests** ·
  `myservice_identity` **of 30** · `myservice_dashboard` **of 9**.
- **Spec 50 (new): 3 passed of 3 on `test19` AND `boot44`.**
- **Persona matrix re-run (§4):** specs 46 + 48 + 49 — **15 passed of 15**
  on `test19`; with spec 50, **18 passed of 18** on `boot44`.
- **The two red specs:** 2 failed exactly as §G names, **7 passed of 9**
  in their two files — the suite-level standing pair, unchanged.
- **Whole browser suite** on `test19`, after this report's last code
  change: **2 failed, 1 flaky (passed on retry), 12 skipped, 190 passed of
  205** in 12.6 m. The 2 failures are exactly the §13.5 standing pair §G
  names; the 12 skips are the pre-existing data-dependent set (specs
  06/08/35/38/39, categories unchanged from report 49); the flake is
  spec 00's session chip, passed on its retry. The suite grew 202 → 205:
  spec 50's three tests.
- **Fan-out:** `-u myservice_api` on all 9 local databases, **0
  ERROR/CRITICAL lines on each**.
- **OpenAPI:** `/assets/export` → `x-cadra-scopes: ["export:read"]`,
  `/dashboard/map` → `["dashboards:read"]`, `/fleet/map` →
  `["operations:read"]`, read from the served spec.

## J · Deviations, corrections and findings

1. **CHANGELOG surgery:** report 37's commit (`eb52157`) had deleted the
   handoff 47 section heading, so 47's three BREAKING scope moves read as
   part of the 37 entry. Restored, with a note saying who broke it and who
   fixed it.
2. **`docs/api/EXTERNAL-SURFACES.md` fact-checked** (the census touches its
   area): the 2026-09 derivation figures (36 routes, 65 `@cadra_route`)
   had gone stale and four table line-citations pointed at moved code.
   Re-derived with today's numbers and re-pointed; the count is now
   guarded by the widened census rather than maintained by hand.
3. **`api_groups.xml`'s Auditor comment** said "the six read scopes" —
   stale since 47 made it seven, wrong again when 50 made it eight. It now
   points at the pin (`test_auditor_access.py`) instead of carrying a
   count that goes stale.
4. **Spec 50's crash intercept installs before sign-in** — the 60 s fresh
   cache otherwise masks the deliberate crash. Same cache behaviour §G
   names on spec 14.
5. **OpenAPI property annotations for the two published keys were not
   added**: the `Asset` schema is declared PARTIAL
   (`additionalProperties: true`) and the depreciation block carries no
   property-level schema anywhere — `salvage_value` itself is unannotated.
   The CHANGELOG documents the contract change.
6. **Session-user counts are direct memberships** (handoff 24: implication
   writes no membership rows on 19), so a hypothetical user holding only an
   implying group outside the three register groups would be uncounted;
   the three register groups imply only each other, so the counts stand.
7. **One evidence vehicle (brand, model, driver partner, one geocoded
   location) was created on `test19` and removed after capture**; the
   location's coordinates were zeroed back. `test19`'s geocoded-location
   count moved 165 → 166 across the session from the e2e suites' own
   fixtures, not from this.
8. **The pytest transient:** one 30 s ReadTimeout immediately after a
   container restart, §I. Not reproducible alone; named rather than
   hidden.
9. **A self-inflicted loss, caught by reading the commit's own stat line:**
   the hook's live proof used `git commit --allow-empty` followed by
   `git reset --hard HEAD~1` — which also discarded the then-uncommitted
   `ci.yml` edit (a tracked file; the builders' files were verified intact
   by every later drive and suite). Noticed because the `ci:` commit
   reported 2 files where 3 were expected; the job was re-applied, the
   commit amended before push, and the workflow YAML re-validated (4
   jobs). A reset --hard in a tree carrying uncommitted work was the
   mistake; it is named here so the next session does not repeat it.
10. **Finding, not fixed (frontend):** the SPA's `SCOPE` map
   (`use-scopes.ts`) and `SCOPE_WORDS` (`Users.tsx`) have no test holding
   them in step with `utils.py` — both were already missing scopes before
   this branch (e.g. `ingestion:write`). A drift guard here is a
   candidate for the next frontend handoff.

## K · Needs the owner

- **The PR merge** (as every handoff: the Builder's permission layer
  refuses `gh pr merge`).
- **The credential-scope decisions** (§F) remain `[open]` — no row was
  touched, per the handoff's "named decision, not a quiet widening".
- **The cluster**: this branch changes no deployment shape; the staging
  deploy and per-tenant upgrades follow the standing runbook when merged.
- **Other clones of the repo** that want the LOCAL half of ruling 3 run
  `git config core.hooksPath scripts/git-hooks` once; CI needs nothing.

## L · Commits

Listed in the PR; every one made with the commit-msg hook active, none
carrying a trailer.
