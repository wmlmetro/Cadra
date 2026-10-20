# Report — Handoff 67: the station captures

Branch `feat/the-station-captures`, from `dev` at `d4666c7` (Step 0
committed the instruction file). Module versions: `myservice_asset_register`
19.0.1.35.0 (five new columns: four on the capture, four on the code ledger,
one on the suggestion — no migration), `myservice_api` 19.0.3.38.0 (three
routes, two widened). Evidence: `docs/handoffs/67-evidence/`. Budget 3 h,
stated at Step 0; not split.

## Needs the owner

1. **The PR merge** (the Builder's permission layer refuses `gh pr merge`).
2. **The deploy:** `upgrade-19` for `myservice_asset_register,myservice_api`
   on every tenant. New columns on the asset-code ledger are written by
   every asset create, so a tenant not upgraded fails asset creation. No
   data is migrated.
3. **For each regional office going live on Lot 6:** the checklist in §6
   below. The parts only NRS can supply are the people, the network and the
   SAP office code per building (66's GO-LIVE §35.1, still open).

## In plain words

A regional office can now run the audit from its **Barcode Station**, not
only from a phone. The station page has a second tab, *Capture*, for anyone
holding the audit capturer role. It is the same capture as handoff 66's,
with three differences that suit a desk with a scanner and a label printer:

- **The station is a registered device.** The Asset Controller registers
  the station computer like a phone and binds it to whoever is signed in.
  The page remembers which device it is.
- **The room is chosen by scanning its room label**, not from a list.
- **The label is printed from the station**, and every print is recorded.

The capture goes through the same route and the same review as a phone's.
No rule changed.

**At a shift change**, the person leaving returns their own block of codes
(unused codes are voided), and the Asset Controller rebinds the station to
the next person and issues them a fresh block. This is 66's rule; the new
part is that the capturer can now return their own block.

Four things the mobile team could not build yesterday now exist:

- **identify a photo already uploaded** for a capture, so it goes up once;
- **void one spoiled code** (a label torn at print), with a reason;
- **return your own block**;
- **GPS on a capture**, optional. It is stored on the capture only and
  never sent to the AI.

Two PRD alignments:

- the photo answer now says the item's **approximate size** (small, medium
  or large, defined in words);
- *Settings → Identify from photo* shows **how suggestions were used** over
  the last 30 days: how many were made, and what share people kept exactly
  as suggested. It is broken down by class, by site and by model, and every
  number says what it counts.

## What was built

**§1 the station (frontend, one subagent).**

- *Scan & print* and *Capture* tabs. *Capture* is drawn only for
  `audit:capture`; the chosen tab is remembered per browser.
- 66's capture screen became one component, `CaptureScreen`, with a `desk`
  and a `station` variant. The Audit capture page is unchanged (spec 66
  re-run).
- The station variant adds:
  - the device line;
  - the room by scanned `LOC-…` code, refused in words outside the
    campaign;
  - the code's *Print label*, through the station's own `printLabels`;
  - *Spoiled label* and *Return my block*.
- **A block code's print is recorded on the ledger.**
  - `POST /audit/codes/printed` (`audit:capture` + `X-Cadra-Device`).
  - The code row now carries `print_count`, first and last printed, and
    by whom.
  - This deviates from "print through the funnel", and Deviation 1 says
    why.
- Both variants:
  - identify by `audit_photo_id` (the bytes no longer go up twice);
  - an optional GPS tick, off by default, read once at send;
  - the size band under the suggested fields.

**§2 the four gaps.**

1. **Identify an audit photo by its id.** `/ai/identify` takes the part
   `audit_photo_id`; exactly one of `photo_id`, `audit_photo_id` or `file`.
   - Only your own photo (`403 not_yours`).
   - The suggestion links the audit photo (`nrs.ai.suggestion.audit_photo_id`).
   - A capture naming that suggestion must carry the photo.
   - No asset save may apply it (`reason: audit_photo`).
2. **Void one code.** `POST /audit/codes/<code>/void`: a reason is
   required, only a block code reserved to you and still `reserved`. It is
   never reissued.
3. **Return your own block.** The return route now takes `audit:manage` OR
   `audit:capture`; the second only for a block issued to you (checked in
   the model, `holder_only`).
4. **GPS.** `gps: {latitude, longitude, accuracy_m}` on the capture, each
   value range-checked, and any other key refused.
   - Stored in three columns plus `gps_recorded` (0,0 is a place).
   - Published only on capture reads.
   - Never on the asset. `/ai/identify` has no part that could carry it,
     and the photo's EXIF was already stripped before sending (64).

**§3.**

- **`size_band`** is in the provider's schema (`small|medium|large|unknown`,
  with `unknown` published as null).
  - The words live in one constant that both the prompt and the response
    read.
  - The answer says *Approximate size* and `approximate: true`.
  - `dimensions` is untouched. Prompt version 67.1.
- **`GET /settings/ai-identify/acceptance?days=`** (`settings:read`) returns
  totals, by class (as suggested), by site (the campaign location covering
  the room) and by model. Its `definitions` say what each count counts,
  and the screen prints them verbatim.

## The numbers

| | |
|---|---|
| HTTP, new (`tests/test_the_station.py`) | **9 of 9** on `test19f` — each §2 route with its refusals, the print record, the dashboard's counts moving by exactly 3 made / 2 used / 1 unchanged |
| HTTP, affected after the verification fixes (station + query-param guard + audit + photo) | **58 of 58** |
| In-registry `TestAiSuggestion` (the size band; an audit-photo suggestion refused on an asset save; the dashboard against a SEEDED set: 4 made, 3 identified, 2 used, 1 unchanged, share 0.5) | **0 failed, 0 error(s) of 19 tests** |
| Browser, on `test19f` (46 every persona × every item, 66 the desk capture, 67 the station capture end to end — the reviewer accepts in the Audit screen) | **17 of 17**, 8.2 min, after the fixes |
| Browser, station specs on `test19` (10, 39, 40, 54, 61 room codes, 64) | **23 passed, 6 skipped**; 46, 66 and 67 refused there at a precondition — `test19`'s personas file has no audit personas (0 of 2; `test19f`'s has them), predating this handoff — and run on `test19f` above |
| Fan-out (8 tenants + template) | clean, `67-evidence/fanout.txt`; template 155.6 s |
| Final local pytest (fresh `test19f`, gates OFF — no gate code changed) | **1 failed, 1538 passed, 10 skipped of 1,549** in 11 m 0 s — the one: `test_query_param_guard` wanted the new `?days=` in its inventory; added, rerun green (above) |
| CI | **39383419099 on `2790fbe`: green, both switch states** — 1,534 passed, 16 skipped of 1,550 each; in-registry passed (details in § CI) |

## Deviations and findings

1. **"Print through the station's existing print funnel (handoff 10)".**
   - The funnel of handoff 10 is Odoo's PDF report, and it records prints
     of a tag LABEL. The station has never used it: it draws labels in the
     browser and records them with `POST /tags/printed` (61).
   - A block code has no label row until an asset carries it, so neither
     road can record it.
   - The capture prints through the station's same `printLabels`, and the
     print is recorded on the code's ledger row by a new route.
2. **Shift change: the simpler rule, recorded in DECISIONS.** Return the
   block, rebind, issue a new block. Block-per-person would need a device
   holding several open blocks, which is a new rule. The cost is codes
   voided at each shift (gaps in a sequence).
3. **The desk capture now checks a typed room code against the campaign**
   (a small behaviour change the frontend subagent made for both
   variants): the room list first, then the server's own slice refusal.
4. **Two of spec 67's first-draft assertions were wrong**, not the code:
   - it expected 200 from identify, which answers 201;
   - it expected the void reason verbatim, but the ledger stores *Spoiled,
     voided by its holder: <reason>*.

   Both were fixed in the spec.
5. **Verification pass** (a fresh agent, read-only over the diff). It
   found no blocking defect; the write order, authorisation and GPS
   handling were traced clean. Fixed:
   - **Removing a photo left its suggestion behind** (desk and station
     alike), and the server then refused the send. Now, leaving a photo
     out drops a suggestion made from it.
   - **A failed call could be named by a capture**, and the dashboard
     counted it as used and accepted unchanged. A capture now refuses a
     suggestion that identified nothing (`not_identified`), as an asset
     save already does. This is a behaviour change on 66's route,
     announced. The dashboard skips any such capture made before.
   - **Two prints of one code at the same instant could count once.** The
     count is now one SQL `UPDATE … + 1`.
   - Test gaps: an audit-photo suggestion refused on an asset save
     (in-registry); a failed call named by a capture (HTTP).

   Left:
   - **Two captures naming one suggestion**: the last read decides its
     dashboard outcome. Nothing refuses the reuse, and refusing it would
     be a new rule on 66's route.
   - **Void takes no device header**, on purpose (DECISIONS).

## §6 — What a regional office needs on the day, for Lot 6

**Hardware**

- [ ] A computer with Chrome or Edge (current), signed in to Cadra
  through the browser. Nothing is installed.
- [ ] A handheld USB scanner that reads QR and Code 128 and sends Enter.
  The camera works too but is slower.
- [ ] A webcam or phone camera for item photos. A photo is at most
  300 KB; the app resizes.
- [ ] A label printer that prints from the browser's print dialog, with
  labels at 50×25, 50×30 or 100×60 mm. QR on every size; Code 128 only on
  100×60.
- [ ] Spare labels, and tested printer margins (print one room label
  first).

**Network**

- [ ] HTTPS to the tenant's address from the station.
- [ ] If *Identify from photo* is on: the server, not the station, reaches
  the AI provider. The station needs nothing extra.

**People and roles** (granted on the Users screen; the role exclusions
refuse a capturer who is also a reviewer)

- [ ] An **Asset Controller**, who can be at HQ: registers the station,
  binds it, issues blocks, opens and closes the campaign.
- [ ] One **Audit Capturer** per shift at the station.
- [ ] An **Audit Reviewer** who is not the capturer. They can be remote,
  in the Audit review screen.
- [ ] A **Tag-Issuing Unit** member reachable, for reprints of
  on-register items whose label is missing (66 Deviation 5, still open).

**The station as a device, and its codes**

- [ ] The station registered (*Devices and codes*) and bound to the first
  capturer.
- [ ] A block issued to it, sized to a shift (e.g. 50–200; at most 500).
- [ ] The shift-change routine written down: the outgoing capturer
  returns their block; the controller rebinds and issues a new one.

**The campaign and its rooms**

- [ ] A campaign over the office's building(s), with the SAP office code
  each answers to (NRS supplies the mapping).
- [ ] The capturers and reviewers named on it.
- [ ] Room-code labels printed (*Barcode Station → Room labels*) and
  fixed at each room's door.
- [ ] *Identify from photo* switched on with a key on the server, if
  wanted, and NRS's written acceptance of the provider (GO-LIVE §33.1).

## Time

Started 06:48; budget 3 h. The report was pushed at about 07:32, roughly
45 minutes in.

- **Build** 06:51–07:02: the server myself, the frontend in one subagent
  in parallel.
- **Tests and fixes while building** 07:02–07:06.
- **Final suite** 07:07–07:18 (11 min), run in parallel with the
  **verification pass** (07:07–07:13) and the station browser specs.
- **Verification fixes and affected reruns** 07:18–07:28; the browser rerun
  on `test19f` took 8 min.
- **Report** 07:08–07:31, written while those ran.
- **CI** 07:32–08:11. The in-registry guard was found by reproducing
  locally (07:44–07:57), the fix pushed at 07:58, green at 08:11. The
  report was pushed marked *CI pending* first, with no idle wait.

## CI

**After the report: the PR check on `5dec8a8` went red in one leg (gates
off), 1 failed of 1,550**, while the push run on the same commit was green.
The failure was `tests/test_sap_mirror.py::test_a_reimport_is_unchanged_and_hands_a_sync_nothing`,
a timing flake present since handoff 63:

- the test took `since` in whole seconds, in the same second as the
  fixture's own import (07:15:54.x);
- the filter is inclusive, `write_date >= since`, so it counted the
  untouched records as changed;
- its one-second sleep came after taking `since`, not before.

Fixed in the test (sleep first); the API is unchanged. On the way, the same
file's `test_one_record_and_the_asset_side_of_the_link` failed when run
alone on a fresh tenant: it read "the first asset" from a register with 0
assets, leaning on an earlier file to have made one. It now makes its own.
The file passes 20 of 20, twice, on a fresh `test19f`.
**CI on the fix, `ab15799`: green in both runs and both switch states.**
The push run 39400286342 and the PR run 39400290325 each gave pytest
1,534 passed, 16 skipped of 1,550 in each leg, and the in-registry step
passed.


PR #128.

- **39380829526 on `986fd8f`** (the verification fixes): pytest passed in
  both legs. The in-registry step was red in both, with its result beyond
  GitHub's truncated log, as in report 66.
- **Reproduced locally** with CI's exact command on a fresh `test19f`:
  - The guard `TestPublishedNamesResolve.test_every_route_that_takes_a_body_is_classified`
    fails and names the two new body routes, `POST /audit/codes/printed`
    and `…/<code>/void`. Each needed a line in `_BODY_ROUTES` saying what
    its keys are.
  - After that line: 1 failed of 14 in that class. The one left is the
    known isolation-only `…bare_override…` test (reports 64–66).
  - The full command gives 1 failed of 1,309. The one is
    `TestAssetHistoryMoves.test_a_located_asset_with_no_record_says_so`,
    which needs some movement row on the database; a freshly restored
    `test19f` has none until CI's pytest step (which runs first) writes
    them. It was not seen in CI's order.
- **39383419099 on `2790fbe` (the fix): green, both switch states.**
  pytest 1,534 passed, 16 skipped of 1,550 in each leg. The in-registry
  step passed in both, and so did every other job.
  https://github.com/wmlmetro/Cadra/actions/runs/39383419099
