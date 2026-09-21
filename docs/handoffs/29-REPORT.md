# Report 29 — Every control on the asset page

**Branch:** `fix/asset-page-controls` · **Base:** `dev` at `e0808f8` (handoff 28 merged as PR #78 before this started — the precondition you set).

**Needs the owner:**
1. **The PR merge.**
2. **GitHub billing — still.** Every workflow on `wmlmetro` has been refused since 2026-09-18 14:13 UTC, zero steps run, *"recent account payments have failed or your spending limit needs to be increased"*. Checked again on PR #78's merge commit: same. **CI has not tested handoffs 27, 28 or this one**, `uptime-check` has not probed the live sites in three days, and `deploy-dev` is refused too, so nothing merged since the 18th has reached staging.

Nothing to migrate: no stored field, no module version bump. Front end, one route's date check, docs.

---

## 0 · A retraction first, because you ruled on it

Handoff 28 §D told me to register that *"`require_jwt` checks scopes and discards them, so no route can see what its caller holds… it forecloses per-scope shaping anywhere in this API"* — *"as an architectural fact, not as a to-do."* I registered it. **It is false.** The last two lines of `require_jwt`:

```python
    _set_request_user(int(uid))
    request.jwt_claims = claims
```

The whole validated token is on the request, and three places already read it. **The statement was mine before it was yours:** handoff 27's reviewer wrote it in a summary, I searched for three attribute names that do not exist (`cadra_scopes`, `cadra_claims`, `cadra_token`), never opened the function, and put it in report 27. You ruled on what I told you. I found it in this handoff by reading `GET /auth/whoami` for an unrelated reason — it reads `request.jwt_claims`.

**What it changes:** the asset history withholds a maintenance request's reference from everybody because it supposedly could not be shown only to holders of `requests:read`. It can. Withholding under-publishes, so nothing was exposed — but the reason was wrong, and anything you have since designed around *"per-scope shaping is impossible here"* should be re-read. GO-LIVE §14.1 is now the retraction; the two DECISIONS entries are annotated in place. Whether to publish the reference is yours (Q1).

Report 27: a grade from a summary. Report 28: a count nobody looked inside. This: a constraint on the design of our own API, from a grep for the wrong words. **Five handoffs, one defect.** It happened twice more inside this handoff and was caught both times by something other than me — §4.

---

## 1 · The inventory — every control, by acting

**How.** A Playwright harness signs in to `test19` as a person, creates a fresh asset through the test credential (so it is labelled a fixture), snapshots that asset's rows straight from Postgres — the `nrs_asset` columns, and the counts of custody, movement, transfer, chatter and tracking rows — clicks the real control, snapshots again, and prints the difference beside what the page says and what the **register list** says. *"DB"* below is that difference. **BEFORE** is the app as handoff 28 left it; **AFTER** is this branch. My list of controls came from a read-only pass told to assume yours was incomplete; it was.

### The header actions

| Control | What it promises | What it calls | DB — the row that changed | What the person saw BEFORE | AFTER |
|---|---|---|---|---|---|
| **Mark verified** | the asset is verified | `POST /assets/<id>/verify` `{}` | `is_verified f→t`, `last_verified_date`, **`last_verified_by → 2` (Administrator)**; 2 tracked values | pill *Review → Cleared*; **a rejected call showed NOTHING** — the error was never rendered | same, and a refusal is shown inline. History: *Verified · Verified By: — → Administrator* |
| **Mark missing** | the asset is missing | `PATCH {"state":"missing"}` | `state active→missing`; 1 tracked value. No custody, movement or transfer row | **the browser's grey `confirm()`**, then a **GREEN *Cleared* pill** and the stepper on *Cleared* | app dialog; **red *Missing***, no step lit, list row *Missing*. Disabled on an asset already missing — where it used to send a PATCH, get a 200 and change nothing |
| **Condemn** | the asset is condemned | `PATCH {state, disposal_date, disposal_reason}` | `state active→disposed`, date, reason — **and `condition` stayed `good`** | ***Good · Cleared***, stepper on *Cleared*: a disposed asset, in good condition, cleared | now also sends `condition: decommissioned` (as Odoo's own action of that name does): ***Decommissioned · Disposed***, step *Disposed*, list row *Disposed · Decommissioned* |
| **Move** | the asset is moved | `POST /assets/<id>/move` | `location_id 65→66`, **`movement_rows 1→2`**, `transfer_rows 0→1` | correct. History at once: *Location moved · **Cannot be altered** · TRF/2026/0146* | unchanged. **Handoff 28's record sees what the UI does** — the first real test of it |
| **Transfer / Assign custodian** | custody changes | `POST /assets/<id>/transfer-custody` | `custodian_id → 1`, **`custody_rows 0→1`** | correct. History: *Custodian changed · Cannot be altered*, with the reason | unchanged |
| **Edit → Save** | the fields I changed are saved | `PATCH /assets/<id>` | `name` changed. **`asset_tag`: typed `H29-FORGED-TAG`, saved, 200 — row unchanged** | lands on the asset, **no message**. A control reporting success while part of it did not happen | the tag is read-only with the reason beside it, and is no longer sent |
| **Back to Asset Register** | the register | `nav("/assets")` | — | lands on the **KPI dashboard** | lands on the list, `/assets/list` |

### Dialog controls, tabs and links

| Control | What happens — acted |
|---|---|
| Move / Custody / Condemn **Cancel** | closed, but reopened **pre-filled** with the last selection. Now resets, and clears a stale error |
| Move → same location | **400**, shown inline in the dialog, nothing written. Correct |
| Custody employee search | needs 2+ characters and says so. Correct |
| Tabs: Details · Custodian & Assignment · Audit & Review · Provenance | each renders. Tab state is not in the URL — a reload returns to Details. *Left* |
| Depreciation tab · *Show year-by-year schedule* | the tab appears only with a depreciation block. On `38875` (36 periods): *Show… → Hide…*, 4 yearly rows. Correct. *(My first probe reported "no toggle" and I wrote down a reason — "no periods" — that was false: it had looked before the schedule loaded. Re-acted with a wait.)* |
| Record links ×4 (location and custodian, on two tabs) | each lands on the right record — the destination's heading matches the link |
| History **sort** | refetches `?sort=oldest`; top row *Custodian changed → Registered* |
| History **label → legend**, **What Cadra does not record** | open by tap; 30 → 1,606 characters shown |
| **Global search**, typed on an asset page | leaves the page for `/search?q=…` after 220 ms. Surprising, not wrong. *Left* |
| Theme toggle | `light → dark` |
| **Notifications bell** | **did nothing, under a PERMANENT unread dot.** Removed: there are no notifications in this app |
| **"Admin User / Administrator"** | hard-coded for every session, beside a Verify button that writes the SIGNED-IN person into the register. Now reads `GET /auth/whoami` — which existed and nothing called — and says *Signed in* rather than a name when it cannot |

Every read-only control above was exercised in one signed-in pass that recorded its network traffic: **zero write requests.** Not on this page, though your list had them: *Generate tags* and *Raise a request*. Tags live only on the Barcode Station; `requestCount` is a number that links nowhere.

## 2 · What the pill shows now

**The shape: one status slot.** When `state` is anything but `active` the slot shows the LIFECYCLE pill; otherwise the data-quality pill. *"Missing · Cleared"* side by side is a contradiction on its face, and a data-quality verdict about an asset nobody can find is not a fact anyone holds. Underneath, `deriveStatus` returns a new member, **"Not in service"**, for every non-active asset — which is what stops the register's *Cleared* filter and *Group by status* sweeping disposed assets into Cleared; a rendering-only fix would have left both. The label is read from the model (`useEnumLabel("asset_state")`); only the colour is declared, in one file the enum guard waives by name.

| `state` | Detail page | Register list & card | Review-queue table | Stepper |
|---|---|---|---|---|
| active, verified | *Cleared* (green) | *Cleared* | not listed | *Cleared* |
| active, unverified | *Review — data quality* (amber) | same, amber card edge | listed | *In Review* |
| **missing** | ***Missing*** (red) — *was green Cleared* | *Missing*, red edge — *was Cleared* | **not listed** — *it was* | none lit |
| **disposed** | ***Disposed*** (slate) — *was green Cleared* | *Disposed* — *was Cleared* | not listed | *Disposed* — *was unreachable* |
| in_repair · transferred | *Under Repair* · *Transferred* — *both were green Cleared* | same | not listed | none lit |

**The stepper no longer paints earlier steps green.** It marked every step before the current one as passed — so driving it from lifecycle would have drawn a green *Cleared* on every condemned asset, breaching your fixed requirement *through the fix*. The front-end pass caught that; I had not asked.

**And the fix had to outlive the browser.** The app persists its query cache for six hours with `refetchOnMount: false`, and that cache holds objects AFTER the adapter has run. Every browser that had opened the register was holding assets already stamped *Cleared*. The cache version is bumped `v1 → v2`; without it the fix ships and the green pill stays on screen, out of the user's own localStorage.

## 3 · The three unreachable statuses: all dead, none missing wiring

| Status | The back end | Verdict |
|---|---|---|
| *allottee not in nominal roll* | zero hits for `allottee`; `nominal` only in prose about the employee import. No reconciliation, no flag | **dead** |
| *VIN not verifiable* | `vin_sn` is `fleet.vehicle`'s. **An asset has no VIN** — the page's *"Serial / VIN"* row is `serial_number` | **dead** |
| *possible duplicate* | no detection. The SAP-number check RAISES; it does not flag | **dead** |

Deleted from the type, the pill, the register's Status filter — where choosing one returned zero rows and no explanation — the dashboard's colours, the mock rows and the CSS. The *Audit & Review* tab's *Possible Duplicate Detected* panel went with them, and its heading *"Approval Status"* is now *"Status"*: no approval record exists in this system and the heading claimed one. `StatusPill` also indexed its style map unguarded and would have white-screened on an unmapped value; it has `ConditionBadge`'s fallback now.

**One real audit signal the front end has never shown:** `sap_reconciliation_state = exception`. Not wired. It is the honest candidate for a second review status (Q3).

## 4 · One screen out (§D), fixed and left

**Measured first.** On **`nrs19` the app reported *Verified: 1* — and that asset is the MISSING one**: zero assets there are both verified and active. On `jaizbankplc`, 140 disposed assets, every one rendered *Cleared*, and every one still carrying a condition other than *decommissioned*.

**Fixed.** *Unverified* was `is_verified=false` with no state filter and *Verified* was `total − unverified`, so every disposed asset counted as verified — both now count ACTIVE assets, on the asset dashboard and the IT dashboard. The strip gains a **Missing** tile in place of a permanently blank *PM Overdue* and is relabelled *On register*. **It adds up for the first time**, checked against the table on `test19`: `1,105 + 0 + 6 + 144 = 1,255`. The home dashboard's **Review Queue** showed **open service-desk tickets** under *"Assets pending data quality review"*, above a table reading *"Showing 8 of {that ticket count}"* while listing assets; it shows assets. Its ***Approval Breakdown*** donut plotted **five hard-coded numbers** — 10,842 / 985 / 673 / 418 / 232 — as percentages of the LIVE total; it plots three real ones. Every figure on the strip, the donut and the review card was read off the screen and matched to SQL (§6). Four map-filter tabs set state nothing read (removed); the review card had `onClick={() => {}}` (navigates); both `window.confirm`s are app dialogs, and a test fails if a native dialog ever fires.

**Left, with the reason** — GO-LIVE §13.5, eleven entries. The ones that want a ruling:
- ***Mark missing* takes no reason, and cannot.** You suspected *why is this missing* is an auditor's first question. It is — and the API accepts nothing: `PATCH {"state":"missing"}`, and the model has no field FOR a reason; its three free-text fields each mean something else. Not added, because there is nowhere true to put it (Q2).
- **A disposal from the app is dated by the BROWSER, never approved, and I could not fix the first.** See below.
- **On a disposed asset the page still offers *Mark missing*** — which would overwrite `disposed` with `missing`, un-disposing it in the register. I disabled only the two no-ops. What a disposed asset may still have done to it is a rule for the model, not for which buttons are grey (Q4).
- **Every other *Total* counts missing and disposed assets** — `Asset.search_count([])`, and the model has no `active` field. A back-end change.
- `_warnings.rejected_fields` is read by nothing, so any other rejected field fails as silently as the tag did · assets with no custodian are shown as held by *"Pool"*, which exists nowhere in the data · the register's Status and Category filters work only on rows already loaded, under a register-wide count · *"All systems operational"* and *"7 zones · 38 states · 857 offices"* are fixed text.

### Twice more, inside this handoff

**I told the front-end pass to drop Condemn's `disposal_date`, asserting the server stamps it.** I had a grep hit and had not read the six lines around it: the stamp is inside `action_condemn`, which the API never calls. **The pass refused**, citing the repository's own test. I settled it by acting: `PATCH {"state":"disposed"}` → `disposal_date = None`. Following my instruction would have put a `no_disposal_date` finding on every disposal made from the app. The date stays — wrong for one hour a night — until there is a condemn route.

**And my harness read the "register row" from `/assets` for its whole first run. That is the KPI dashboard.** Every *register row* line in the baseline proved nothing. Found when the control map came back with the routes; re-run against `/assets/list`.

Both times the instrument was mine, and both times something else caught it — a subagent told to say so, and a map I had asked for. **I now brief every delegation with *"if this turns out to be wrong, say so rather than improvising."*** It is the only reason the first one was caught.

## 5 · Found at 00:50, and not this handoff's subject

Nine tests in `tests/test_audit_reports.py` went red: *"`as_of` cannot be in the future"*. **Not flaky — the route was wrong.** The register snapshot defines its day as a LAGOS day (*"'As it stood on 31 March' is a sentence spoken in Lagos"*), but the future-date check compared against the UTC date. For the first hour of every Lagos day, somebody asking for today's register was told the date had not happened. **CI runs in UTC on both sides and can never see it.** `snapshot_today()` beside `snapshot_cutoff()`; the same nine passed at 00:51, still inside the hour. The front end has the mirror image in Condemn's date, above. Both are in `ENVIRONMENT-FACTS.md`: *if a run goes red just after midnight, read it before re-running it.*

## 6 · Tests — denominators first

In CI's order, against `test19`:

| Suite | Result |
|---|---|
| `pytest tests/` | **873 passed, 8 skipped, 0 failed** |
| In-registry, CI's 11 modules, `--workers=0` | **0 failed, 0 error(s) of 615 tests** |
| Playwright — **the whole suite**, 127 specs | **121 passed, 2 failed, 4 skipped** — both failures reproduce on `dev`'s front end (§7) |
| `tsc --noEmit` / `BASE_PATH=/app/ vite build` | clean / built |

**881 collected** = report 28's 880 + 1: the enum guard's *"a waived styling map has a fallback"* now also runs for `LifecyclePill`. **615** = 614 + the Lagos-day test. No `of 0 tests`, no `CRITICAL`; the 8 skips are report 28's 8. The run before the last was **9 failed** — §5. The 3 Playwright skips are the MOVE specs, which need two *building* locations `test19` lacks; the move was acted by hand in §1.

**A silent instrument, fixed on the way:** e2e's *"filter dropdowns open and clear"* asked for `filter-Category` / `filter-Status` / `filter-Condition`; the component renders those test ids in lower case, and the spec guarded each with `if (count)` — so it had never opened a dropdown and had always passed. It opens them now, and passes.

```
$ CADRA_API_BASE=http://test19.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q -rs
873 passed, 8 skipped in 87.10s (0:01:27)
# the run before it, at 00:50 +0100 / 23:50 UTC:
9 failed, 864 passed, 8 skipped        all nine: "`as_of` cannot be in the future" (400)

$ odoo -d test19 -u <CI's 11 modules> --test-enable --stop-after-init --workers=0
odoo.tests.result: 0 failed, 0 error(s) of 615 tests when loading database 'test19'

$ E2E_ORIGIN=http://test19.localhost:8069 npx playwright test          # the whole suite
  121 passed, 2 failed, 4 skipped (4.7m)
  ✘ 13-asset-depreciation › a computed asset charts its value over time      } both fail identically against
  ✘ 14-settings-depreciation › the straight-line switch persists across a reload } dev's front end — §7
  ✓ after marking an asset missing, the dashboard count and the edit form both know      (NEW — one page session)
  ✓ the top bar offers no dead controls, and names who is signed in                     (was: asserted the dead bell)
# …of which, the specs this handoff wrote or rewrote:
  ✓ mark missing via the app dialog, and the page stops saying Cleared (UI)
  ✓ mark missing fires no native browser dialog
  ✓ condemn sets state and condition, and the page stops saying Cleared (UI)
  ✓ a cancelled condemn does not reopen pre-filled
  ✓ back goes to the register list, not the KPI dashboard
  ✓ the Status filter offers only statuses a record can carry
  ✓ the KPI strip names what it counts · ✓ the review-queue card goes somewhere
  ✓ the status breakdown plots statuses a record can carry
  - move persists server-side (API) · - move via UI · - move to the same location is rejected
  (3 of the 4 skips are the MOVE specs — two building locations, which test19 lacks)

# The acting harness — AFTER. BEFORE, the same two lines read "Good · Cleared".
=== MISSING  DB: {"state":"active -> missing"}     screen: "Good · Missing", no step lit          native dialogs: none
             register row: … ¦ Missing ¦ Good
=== CONDEMN  DB: {"state":"active -> disposed","condition":"good -> decommissioned",…}
             screen: "Decommissioned · Disposed", step "Disposed"     register row: … ¦ Disposed ¦ Decommissioned

# The dashboard, read off the screen, against the table:
ON REGISTER 1,255 | ACTIVE 1,105 | UNDER REPAIR 0 | ACTIVE, UNVERIFIED 1,084 | MISSING 6 | CONDEMNED 144
DB:     1255      |    1105      |       0        |          1084           |     6     |    144
```

## 7 · What the verification pass found — three blocking, and the first is the one to read

**Blocking 1 — my fix did not hold in the most ordinary flow, and my harness was built so that it could not tell.** The app set `refetchOnMount: false`. `invalidateQueries` refetches a query that is ON SCREEN and merely flags one that is not — and a flagged query that is never refetched on mount is shown from cache for ever. At the moment of any action the user is on the asset's page; the list and every count are off screen. So: mark an asset missing, go to the dashboard — and it still says what it said before. **I reproduced it by acting before touching it: *Missing: 8* on screen, 9 in the database, same session.** My harness had never seen it because it loaded every page fresh, *after* acting — I had written "list row *Missing*" in this report on the strength of a cold cache — and the helper's docstring, which I had approved, claimed the cure. It is not specific to this handoff: **with that setting, every mutation in the app invalidated nothing that was off screen.** `refetchOnMount: true` refetches on mount only when stale, so a revisit inside `staleTime` is still instant. Re-acted: 12 → 13 on screen, 13 in the table. An e2e spec now walks list → asset → act → dashboard in ONE page session; nothing did before.

**Blocking 2 — the Edit form could silently un-miss an asset.** It hydrates from a cached copy and sends `state` and `condition` on every save. Open Edit once, mark the asset missing, open Edit again — **acted: the State select read *Active*.** Saving any field would have written `active` back, with a 200. And my new dialog *sends people to Edit* to reverse it. The form now never hydrates from a cached copy; re-acted, it reads `missing`.

**Blocking 3 — an e2e spec still asserted the bell I removed.** Worth a sentence more than that: `12-mock-pages` clicked the bell, confirmed nothing crashed, and annotated it ***"inert by design"***. A test written to bless a control that does nothing. Inverted.

**Should-fix, all fixed:** the top bar could show the PREVIOUS user's name — the cache was cleared on sign-out only, and the ordinary end of a session on a shared PC is a token expiring with the tab closed, so A's cache was restored under B, beside a Verify button that records B. *Worse than the hard-coded name I had just replaced.* Cleared on sign-in too; `whoami` is never persisted · with an API configured, the review-queue table listed **invented mock assets** under the live heading while loading or on error · the KPI strip read *Missing 0 · Condemned 0* over a failed request; it reads "—" · Condemn's date was the UTC date, yesterday for the first hour of a Lagos day with a correct clock; it is the local date now · **"the only free text on an asset is its `notes`" — false, and I had written it in five places.** There are three such fields and Condemn writes one of them four lines further down; the conclusion stands, the sentence did not · a dialog closed mid-request lost its outcome · two specs still passed vacuously.

**And one of those fixes broke every dialog in the app.** "A dialog cannot be closed while its request is in flight" went into the close handler — which the SUCCESS handler also goes through, while `isPending` still reads true in its closure. Every dialog stayed open after a successful save. Typecheck clean, build clean. **Found on the first act**, which is the whole argument of your §C in one line.

**Not mine, and I checked rather than assumed either way:** the full e2e suite is **121 passed, 2 failed, 4 skipped**, and both failures are depreciation specs in files I did not touch. I had just changed global cache behaviour, so I could not call them pre-existing by reasoning. I built `dev`'s front end in a scratch worktree, served it, and ran them: **both fail identically on `dev`.** GO-LIVE §13.5.13; not investigated.

**Left:** the home dashboard's *Review Queue* card opens the register list unfiltered — the list has no server-side filter for it · the IT dashboard's condition tiles count across every state · `ITAssetsCommand` calls a hook after three early returns (pre-existing, untouched).

## 8 · Wall-clock and the correction share

**About 1 h 30 min**, Step 0 at 00:08 to the last green run at 01:32, continuous.

**Correction share: about half, and almost none of it was found by a test I had written.** In the order they cost time:

1. **The verification pass** — three blocking, ten should-fix, a second build and a second full run of everything. The first blocking finding meant the headline fix did not hold in the ordinary flow.
2. **A fix that broke every dialog** — found on the first act after it.
3. **Two depreciation e2e failures I could not attribute by reasoning** — a scratch worktree, `dev`'s front end built and served, both reproduced there.
4. **Nine red tests at 00:50** that turned out to be a real one-hour-a-night bug.
5. **My own false instruction about `disposal_date`**, refused by the front-end pass; **my harness reading the wrong page** for its whole first run; **a reason I invented** for a toggle my probe had simply looked at too early (the depreciation row in §1).

**What I would tell the next Builder.** Your §C was the right standard and it is stricter than it sounds. *Acting* found what reading could not — the pill, the silent tag, the dialogs that stayed open. But **acting from a cold start proves only the cold start**: my harness clicked the real button and read the real row, and still missed that the same session's other screens were lying, because it never stayed in one session. The flow a person actually takes — list, asset, act, back — is the instrument.

## Questions

1. **Publish a maintenance request's reference in the history to holders of `requests:read`?** It was withheld for a reason that was false (§0). It can be shown by scope.
2. **A reason for *Mark missing*** needs a field — and, if it is to be evidence rather than a note, the custody treatment. Which?
3. **`sap_reconciliation_state = exception`** as a second review status? It is the one real audit signal the front end has never shown.
4. **What may be done to a disposed asset?** Today: anything, *Mark missing* included.
5. **`POST /assets/<id>/condemn`**, calling `action_condemn` as `/verify` calls `action_verify`? It dates the disposal on the server and sets the condition in one place.

## Commits

- `e0808f8` — docs: handoff 29 — every control on the asset page (the instruction file, on `dev`)
- `3e0d95c` — fix: every control on the asset page — a missing or disposed asset never reads as Cleared
- this report, in the commit after it
