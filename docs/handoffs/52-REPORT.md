# Handoff 52 — Report: the Builder's list

**Branch:** `fix/the-builders-list` · **PR:** see *Commits*.
**Evidence:** `docs/handoffs/52-evidence/` — the badge drive with screenshots, the station panel drive, the IT dashboard before/after, both refusal drives with their separate reads, the err-path same-cursor probe, spec 14's cache dumps, the page-ready timings before and after, and both guards red-once-then-green.

## In plain words, first

Six things the last report admitted were still wrong are now right, and each
was proved by using the screen, not by reading the code.

**The number beside Approvals told half the truth.** It counted movement
requests waiting on you and none of the tag replacements waiting on you —
on the test tenant, 214 of them, invisible. It now counts both, and if it
cannot get both numbers it shows nothing at all, because a confident "3"
when the truth is "3 plus an unknown" is the same lie with better posture.
Driven as the Asset Manager: one replacement waiting on them, badge says 1;
they approve it; the badge goes away.

**The tagging station's waiting-list pretended a page was the queue.** It
showed the first 100 and stopped, with nothing saying 114 more existed. It
now ends with a sentence: *Showing the 100 most recent — 114 more on the
Approvals page.* The remainder comes from the server's own count.

**A screen titled "IT Assets Command" was counting Furniture.** The match
was a substring search, and the "it" inside *Furniture* qualified. On the
Jaiz register the page confidently reported 21 Furniture records under an
IT heading — and the category name was printed on the page the whole time;
nobody saw it because the heading said IT and the eye believed the heading.
The match now requires a whole word, and the page leads with *Showing:
IT Equipment (21 assets)* so it can never again count one thing and title
itself another.

**Two refusals that vanished now leave a record.** When the register
refuses to confirm a label — because the label is a scrapped one, or
because the serial on the box is not the serial on record — that refusal
is now written down permanently, like the wrong-number refusal before it,
and each of the three kinds reads differently in the asset's history. The
serial one matters most to an auditor: it is the exact "label going onto
the wrong box" event, and it reveals nothing to the person refused.

**A browser that remembered yesterday's screen trusted it.** The app keeps
a copy of what it last showed so pages paint instantly after a reload. The
ruling: the copy may paint, but it is never trusted — the server is asked
again immediately, every time. The cost was measured: pages paint just as
fast, and a reload makes a burst of refresh requests (up to 15 extra on the
dashboard). Chasing the proof exposed one more thing: the long-red test of
this behaviour used to reload so fast it was cancelling its own save, and
passed only when the remembered copy showed the value the server never
received. It now waits for the save to finish, and passed three runs in a
row.

**And two lists that could drift silently now cannot.** The app's two
copies of the permission-scope list are held to the server's by a test
(one copy was missing two scopes). The API reference's endpoint index is
held to the actual routes by a test — it was missing 51 of 115 routes, an
index an integrator would have built against as if it were complete.

## A · §1 — the badge counts both kinds of waiting work

- `fetchApprovalsWaitingCount` sums the `total_estimate`s of
  `GET /approvals?state=pending&waiting_on_me=true&limit=1` and
  `GET /tags/replacements?state=pending&waiting_on_me=true&limit=1` (both
  `assets:read`, both the cheap-count idiom). Either total `null`, or
  either call failing (one rejection fails the `Promise.all`) → the badge
  draws nothing.
- `invalidateTagQueries` now invalidates the `approval-count` prefix, so a
  replacement decided from either screen moves the badge without a reload —
  the movement dialogs' `invalidateApprovalQueries` already did.
- **Driven on `test19`** (`52-evidence/badge-drive.json`, `badge-before.png`,
  `badge-after.png`): the Asset Manager persona has 0 pending movement
  requests naming them (measured in Postgres: the 488 pending requests name
  uids 2, 6 and 7945), and all 214 pending replacements name the suite
  credential — so one replacement was raised naming the manager
  (`NRS-GEN-11353`). Badge before: **1** — a number that is PURELY the tag
  replacement, which the old badge could never show. Approve on the
  Approvals page → badge after: **not drawn** (zero).

## B · §2 — the station panel stops pretending a page is the queue

**The honest cap won over paging, and here is why.** The Barcode Station
is a scan console; its pending panel is a glance-list beside the scan box.
The full record — paged, filtered, decided-included — has been the
Approvals page since handoff 51. Paging the panel would mean a second
queue UI at a station whose user's next act is a scan, not a scroll; the
cap with the true remainder tells the tagger everything the panel owes
them: what is newest, and where the whole queue lives.

- `fetchPendingTagReplacements` now returns `{ tags, totalEstimate,
  nextCursor }` instead of throwing the pagination block away. When
  `next_cursor` is non-null the panel ends with
  *Showing the 100 most recent — N more on the Approvals page*, N =
  `total_estimate − rows shown` (`data-testid="pending-replacements-truncated"`).
  If the server ever sends a cursor without a total, the line still says
  more are waiting rather than inventing a number.
- **Driven on `test19`** (`52-evidence/station-panel-drive.json`,
  `station-panel-truncation.png`): 100 rows rendered, line reads
  *"Showing the 100 most recent — 114 more on the Approvals page."*
  100 + 114 = 214, the tenant's whole pending set.
- The cached shape of `tag-pending` changed, so the persister's buster is
  bumped (v5 → v6): a restored v5 array has no `.tags`, and the panel
  would have read it as "Nothing waiting" for one round trip.

## C · §3 — a screen called IT does not count Furniture

- **The match**: `/\b(IT|computer|laptop|server)\b/i`. The old unanchored
  `/IT|computer|laptop|server/i` was satisfied by *Furn**it**ure* and
  *Secur**it**y/CCTV*.
- **The stable key was measured and lost.** `nrs.asset.category` carries
  `code` AND `domain`, and `domain='it'` marks the seeded IT categories —
  but both are SEED values: on `jaizbankplc` 20 of 29 categories carry
  them and the nine client-created ones carry neither, **including "IT
  Equipment" (21 assets), the only IT-populated category on the tenant
  that showed the defect**. A `domain` match would have missed every real
  IT asset exactly where the substring match was counting Furniture. The
  name is the only key every tenant fills in; the word boundary is what
  keeps it from matching the inside of one. (Same shape on all eight
  tenants measured: 20 seeded rows with code+domain each, client-created
  rows bare.)
- **The page names its denominator**: first line under the title, every
  render — `Showing: {category} ({N} assets)`
  (`data-testid="it-dashboard-category"`).
- **Driven on `jaizbankplc`** (`52-evidence/it-dash-before.png` /
  `it-dash-after.png`): before — header line *"21 Furniture records · 21
  active — 0 verified, 21 not yet"* (the Architect's measurement,
  reproduced verbatim from the old bundle); after — *"Showing: IT
  Equipment (21 assets)"*. The two categories holding 21 assets each is a
  coincidence of the tenant; the screenshots carry the category names.
- **The other two dashboards in the group**: Fleet Command reads
  `/fleet/dashboard` and `/fleet/map`, which select on `fleet.vehicle` —
  a model, not a name. The Facility Command Center reads `/dashboard/kpis`
  and `/dashboard/map` — register aggregates, no category selection.
  Neither has the pattern; nothing to fix.

## D · §4 — the two refusals that stopped vanishing

Same recorder, two more call sites, and the payload now says WHICH refusal
(`reason`: `number_mismatch` / `scrapped` / `serial_mismatch` — the event
model's existing `reason` column, so no schema change and no fan-out). A
row written before this handoff has no stored reason and is published as
`number_mismatch`, the only kind recorded then. Three reasons, three
history sentences:

- *…the number read off the asset (X) is not the label issued for it*
- *…the label presented (X) has been scrapped and is no longer valid for
  any asset*
- *…the serial read off the asset (X) is not the serial on record for it;
  the label may have been going onto the wrong asset*

**The err-path placement was measured, not inherited — and the answer is
the OPPOSITE of 51's** (`52-evidence/same-cursor-probe-err-path.txt`): a
probe row written on the REQUEST cursor beside the serial-mismatch `err()`
**survives into a separate read** (event 11335, read back over HTTP after
the 400), because `err()` returns a response — no exception, no decorator
rollback, and Odoo commits the request transaction. So either placement
works there. The shared own-cursor recorder ships anyway: one mechanism,
one test-mode branch, and a row that stays final if that `err` is ever
turned into a raise. The probe line was removed after the measurement.

**Both driven over real HTTP on `test19`, separate read after each 4xx
(the 51 §2b discipline):**

- **Serial mismatch** (`52-evidence/serial-refusal-http.txt`): asset
  81404, wrong serial → 400, refusal text byte-identical (still names
  both serials — existing surface, unchanged); a separate request reads
  event 11337: `reason: "serial_mismatch"`, `scanned` as entered,
  `append_only`, `source: "test"`; the label untouched.
- **Scrapped label** (`52-evidence/scrapped-refusal-http.txt`): the route
  cannot reach this refusal on its own (it confirms against
  `active_tag_id`, and a scrapped label no longer is one — report 39), so
  the state was crafted by SQL on the test tenant: asset 81405's active
  label set `scrapped` underneath it, then the real
  `POST /assets/81405/tag-affixed` with the label's own number → 400
  *"Tag NRS-GEN-11352 has been scrapped…"*, and the separate read shows
  event 11338 with `reason: "scrapped"` and the dead-label sentence. In
  the product this site is reached by the Odoo form, a script or a shell —
  every caller of the CHECK passes it, which is why it records.
- **Named and left**: the route's third refusal — a scanned serial against
  a record that has NO serial on file — still records nothing. It is a
  *cannot check*, not a mismatch; the handoff scoped §4 to the two, so it
  is named here rather than silently widened.

Tests in the same commit: the HTTP suite's serial-mismatch record test
(with the wrong-then-right sequence), and two in-registry tests — the
scrapped refusal through the real replacement flow, and all four
reason-to-sentence mappings including the pre-52 NULL row.

## E · §5 — the cache ruling, and what enforcing it exposed

**The ruling as shipped**: `onSuccess` on `PersistQueryClientProvider`
calls `queryClient.invalidateQueries()` once, when the restore completes.
At that instant the cache holds exactly the restored entries; every one is
marked stale, the mounted ones refetch at once, the rest as they mount
(`refetchOnMount: true` has been global since handoff 29). Instant paint
is preserved; the server's answer replaces it within one round trip. The
exclusion list is untouched, the 1 s write throttle is untouched, no key
was excluded to make a spec pass. The 5-minute `staleTime` still governs
what the running session fetched itself.

**The cost, measured** (`52-evidence/page-ready-before.json` /
`page-ready-after.json`, warm cache, 3 reloads per screen on `test19`):

| screen | content paint before → after | API calls per reload before → after |
|---|---|---|
| asset dashboard (`/assets`) | 374–451 ms → 365–371 ms | 4 → 19 |
| register list (`/assets/list`) | 421–542 ms → 410–474 ms | 4 → 7 |
| approvals | 349–382 ms → 354–370 ms | 5 → 8 |

Paint did not move — the burst happens behind the painted cache. The
dashboard's +15 is its six KPI counts, four warranty counts, map, KPIs and
recent-tags all refetching at once, which is the ruling working as asked.

**Spec 14: green three runs in a row, instrumentation kept — after its own
race was found.** The first three runs under the ruling failed
CONSISTENTLY, and the dumps said why: the toggle flips optimistically
(`onMutate`), so the spec's first assertion passed while the PATCH was
still in flight, and `page.reload()` then ABORTED it. The server never
received the write. The old spec went green anyway whenever the persisted
copy restored the post-click sketch — **it was passing on a value the
server never held**, and the ruling, by refetching, made the screen tell
the server's truth and exposed it. The spec now waits for the PATCH
*response* — the act under test, not the throttle — before reloading
(and the restore in its `finally` does the same, so a failed run cannot
flip the tenant for the next). The persister window is untouched: the
PATCH answers inside the 1 s throttle, so the copy the reload restores is
still typically PRE-click, and the green is the refetch's doing. Dumps
(`52-evidence/spec14-persisted-cache.jsonl`, three runs): the restored
entry's `dataUpdatedAt` moves after the reload in every run — refetched,
not absent, not trusted.

**The buster** is bumped for §2's shape change, not for the ruling — the
ruling changes when a cached object is trusted, not what it means.

## F · §6 — two guards, both proven able to fail

- **§6a `tests/test_scope_maps.py`** — static, the sidebar-catalog
  pattern: the 19 scopes in `utils.py` (constants cross-checked against
  `ALL_SCOPES` by AST, so the census itself cannot drift) vs the `SCOPE`
  map in `use-scopes.ts` vs `SCOPE_WORDS` in `Users.tsx`, set equality
  both directions, denominators in every message, and every parse asserts
  a plausible count so a reformat fails as itself. Landing it required
  completing the SCOPE map: it carried 17 of 19 (`ingestion:write` and
  `webhooks:admin` missing — report 50 §J.10's finding, now closed).
- **§6b `tests/test_endpoint_reference.py`** — static census (AST over
  every `myservice_*/cadra_brand_*/controllers/*.py`, `cadra_route` and
  `http.route`, methods expanded, placeholders normalised) vs the
  reference's endpoint index, both directions, each failure naming its
  routes. Scope: `/api/v1` only — the outside routes are
  `EXTERNAL-SURFACES.md`'s own charter. The exclusion table demands a
  sentence per entry and a staleness test fails on any exclusion that
  stopped excluding; **it ships empty**, because the index was brought to
  the code instead: **it carried 64 rows of 115**, and the 51 absentees
  included `POST /assets/<id>/tag-affixed`, `GET /assets/<id>/history`,
  six of eight auth routes, all five report routes, and the whole §12/§13
  users-roles-sidebar surface. The index was rebuilt from the census with
  each route's declared scope (two inline-checked `http.route` handlers'
  scopes set by hand and said so in the doc).
- **Red once, green after** (`52-evidence/guards-red-once.txt`): §6a with
  `exportRead` removed — *"use-scopes.ts SCOPE and the server's 19 scopes
  disagree (SPA carries 18): server only: ['export:read']"*; §6b with the
  tag-affixed row deleted — *"1 of 115 first-party /api/v1 routes have no
  row in the endpoint index"*, naming the route and its declaration site.
  Both restored, both green.

## G · Verification

- **HTTP suite on `test19`, first, CI's order**: first run **1 failed, 1305 passed, 9 skipped of 1315** in 480 s — the failure a 30 s client `ReadTimeout` on `test_approvals.py::test_the_requester_can_withdraw_and_nobody_else_can`, a route this handoff never touched, which passed alone in 3.2 s; whole-suite re-run **1306 passed, 9 skipped of 1315, 0 failed** in 426 s. The 9 skips are the documented categories (handoff 46's count).
- **In-registry, `--workers=0`**: `myservice_api` **0 failed, 0 error(s) of 374 tests** (report 51's 372 + this handoff's two) ·
  `myservice_asset_register` **0 failed, 0 error(s) of 482 tests** · `myservice_workflow` **0 failed, 0 error(s) of 96 tests** (the deadlock-risk suite; no hang).
- **The census**: *“route census: 73 body routes of 143 first-party routed declarations (48 under /api/v1, 25 outside), plus 4 inherited-route overrides with no path of their own”* — unchanged from report 51, as it should be: this handoff added no route. Found and left, named: run ALONE, the census class reports 0 overrides and fails its own override name-check — `original_routing` exists only after an `HttpCase` has built the routing map, so the override half of the walk is readable only in a run that contains one, which the module suite and CI always do. Pre-existing, not this handoff's, surfaced by quoting the census from an isolated run.
- **Browser suite on `test19`**: **199 passed, 12 skipped, 0 failed of 211** in 13.6 m — the standing red pair is now zero: spec 13 went green in 51, spec 14 goes green here, in the full suite, under the ruling. The 12 skips are report 49's documented data-dependent categories. Spec 14 individually: 5 passed of
  5, three consecutive runs.
- **Fan-out**: no stored field, no selection value, no source value
  changed — the `reason` column existed (status_changed's), the
  `affix_refused` selection entry is handoff 51's, and `_PAYLOAD_OF_TYPE`
  is Python. No per-tenant upgrade was required; the manifests are bumped
  (`myservice_api` 19.0.3.26.0, `myservice_asset_register` 19.0.1.24.0)
  so the deploy Job upgrades as usual.
- **TypeScript**: `tsc --noEmit` clean; bundle rebuilt with
  `BASE_PATH=/app/` and served for every drive above.

## H · §9 — the landing dashboard, every number traced

The screen is `/assets` (`AssetRegisterDashboard.tsx`), every persona's
landing page. Five queries feed it; every tile below is traced to the
request that produces it. `countAssets(f)` is
`GET /api/v1/assets?limit=1&<f>` reading `pagination.total_estimate`,
which `paginate()` guarantees is a count of the caller's whole domain,
never of the returned window (handoff 13).

| tile | query | denominator visible? |
|---|---|---|
| On register | `countAssets({})` | it IS the denominator; label says "On register", not "Total assets", deliberately (includes disposed + missing) |
| Active | `countAssets({state: "active"})` | beside On register |
| Under Repair | `countAssets({state: "in_repair"})` | beside On register |
| Active, unverified | `countAssets({is_verified: false, state: "active"})` | label carries its own filter ("Active,") |
| Missing | `countAssets({state: "missing"})` | beside On register |
| Condemned | `countAssets({state: "disposed"})` | beside On register |
| Warranty ×4 (with / none / expired / expiring) | one `countAssets(warrantyToServerFilter(v))` each | each tile OPENS `/assets/list?warranty=v` — the exact query it counted; the expiring tile prints its own window dates (Lagos) |
| Asset Locations map | `GET /dashboard/map` → `locations` | the caption says *"N distinct sites · pins reflect locations with API-mapped coordinates"* — it does NOT say how many sites lack coordinates |
| Recently added | `GET /barcode/recent-tags?limit=5` | "recently" is the honest frame; no denominator claimed |
| Asset Categories | `GET /dashboard/kpis` → `assets.categories` | per-category counts printed; bar widths relative to the largest, counts beside them |
| PM Due (14 days) | **no query — a static empty card** | its own small print says *API endpoint pending* |

Every number a user sees on that screen is a `total_estimate` over the
caller's own filter or a row the server returned; nothing is computed by
subtracting one request from another except nothing — the strip's old
`total − unverified` derivation died in handoff 29 and did not come back.
A failed count renders "—", never 0 (the `Kpi` null rule).

**Three findings from the trace, none fixed here** (GO-LIVE §27.2):

1. **The header hardcodes `staging.app.cadra.ng` and an unconditional
   green dot** — a host claim wrong on every other tenant and an
   instrument-free health signal, the *All systems operational* class
   (handoff 47) one specimen smaller.
2. **"PM Due (14 days)" is a card that can never say anything** — static,
   permanently empty, honest in small print and dead since the screen was
   built.
3. **The KPI strip does not partition and does not say so**: `transferred`
   is a live `nrs.asset` state with no tile. Measured today it is 0 of
   12,422 (`test19`), 0 of 11,951 (`nrs19`), 0 of 4,164 (`jaizbankplc`) —
   the sum happens to close, which is exactly when the gap is invisible.
   ("Last updated" is the counts query's clock standing for a five-query
   page — same family, smaller.)

## I · Deviations and the sentence check

- **Spec 14 was modified beyond the handoff's letter** — it now awaits its
  own PATCH before reloading. Said plainly in §E: the alternative was a
  spec whose green depends on the server losing the write, and the ruling
  itself is what exposed it. Instrumentation kept; a third dump ("after
  settle") added as §5's proof instant.
- **The endpoint index was rebuilt, not patched** — renumbered 1–115,
  grouped by area. The old mixed numbering (`10a`, `44b`…) was itself a
  record of patches; nothing is known to reference index row numbers.
- **No e2e spec was added for §§1–3** — the handoff asked for drives with
  numbers recorded, which are committed probes and evidence
  (`e2e/probes/badge-counts-both.mjs`, `page-ready.mjs`) rather than suite
  specs; the §4 behaviours have suite tests on both sides of the HTTP
  boundary.
- Sentence check: *"zero of how many"* holds everywhere a zero appears in
  this report (0 movement approvals **of 488 pending**, 0 transferred **of
  12,422/11,951/4,164**, 0 geocoded-vehicle claims untouched); the §3
  measurement carries both numerator and denominator per tenant.

## Commits

- `ca62262` feat(api): every affix refusal leaves a record naming its reason
- `a6b1268` feat(app): the badge counts both queues, the panel says what it shows, IT matches a word, restored cache is never fresh
- `1078816` test(guards): the scope maps and the endpoint index cannot drift silently
- the docs commit carrying this report, the evidence, `docs/api/CHANGELOG.md`, `DECISIONS`, `STATUS`, `GO-LIVE` §27 and `CLAUDE.md` row 52
