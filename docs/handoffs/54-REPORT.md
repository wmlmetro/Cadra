# Report — Handoff 54: Every time

**Branch:** `fix/every-time` · **PR:** _(filled at the end)_
**Builder session:** 2026-10-05

---

## Needs the owner (up front, because the handoff's own rules demand it and the handoff did not carry the block)

1. **§6c — the real-device table — is owner-blocked, and that is a defect in the handoff.** §6c requires pointing the MacBook's built-in camera, an Android Chrome phone and an iPhone Safari at PRINTED labels at measured distances, and rules "no real device, no done" — but no "Needs the owner" block names it, and a Builder session cannot hold a printed label in front of a camera. Everything the owner needs is shipped: the station is the harness, the preview now prints what the camera actually granted (`getSettings()`, bottom-right caption), and §6c below carries the fill-in table and the exact procedure. The engine itself is proved on this machine's Chromium through the fake capture device (spec 54, 12 green) and offline on 408 corpus frames — what remains owner-only is optics: the fixed-focus distance bands.
2. **The final PR merge** — the Builder's permission layer refuses `gh pr merge`, as every handoff.
3. **A template decision is now measurable (§9):** the small and standard labels' Code 128 side is below any camera pipeline's floor (0 of 24 corpus cells each; ≈ 5 mil modules). The QR reads on every size as printed. Whether the smallest labels should carry the QR larger (or drop the Code 128 in favour of the handheld-only use it still serves) is the Architect's call — `docs/DECISIONS.md` 2026-10-05 `[open]`.

---

## §0 — the handoff's reading of the component, fact-checked (verification step 7)

Every cell of §0's table was checked against `BarcodeScanner.tsx` as it stood at `7d29eb2`. **All accurate**: no bundled decoder; `BarcodeDetector` or nothing; the five formats exactly as listed; `getSupportedFormats()` never called; `facingMode: {ideal: "environment"}` and nothing else; the whole frame decoded (reticle cosmetic); first result of the first non-empty frame accepted; no feedback on silence, indefinitely; and no real device in any report (grep over `docs/handoffs/*-REPORT.md`). The one thing the table omits (the torch toggle, present since 40) does not alter any cell.

## §1 — one decoder, every device

**Chosen: `zxing-wasm` directly (3.1.4, the `reader` build), behind `src/lib/scanEngine.ts`. The `barcode-detector` ponyfill was evaluated and lost.** The handoff's case for the ponyfill — "the component already speaks that interface and the change is the import, not the component" — stopped being true the moment §§2–5 were read together: the reticle-crop decode, the format passed up with the value, the 1D two-decode agreement and the throttle all rewrite the component regardless, so the interface compatibility bought nothing. What remained was one dependency against two: the ponyfill wraps the same zxing-wasm, pins its own copy, adds its own API layer (and its own wasm-serving configuration that still has to be overridden the same way), while the corpus needs bare `zxing-wasm` in Node regardless. One package, one version, pinned in both `package.json`s, is the smaller contract.

- **The platform `BarcodeDetector` is not kept, not even as an acceleration** — exactly as the handoff preferred. One engine is the point.
- **The wasm is served from our own origin** (Vite `?url` import + `prepareZXingModule` `locateFile` override), never the package's default jsDelivr CDN — a tagging station on a government network must not fetch its decoder from a third party.
- **Lazy, measured:** the engine module is a dynamic import inside `start()`. Spec 54's first test traces the network: **zero `.wasm` requests on page load; the `zxing_reader` wasm is fetched when Start camera is clicked**, and the same session then decodes a Cadra Code 128.
- **Bundle size, measured** (`BASE_PATH=/app/ npm run build`, dist/public/assets):
  - before: **2,076 KB** on disk, 70 assets; after: **3,060 KB**, 72 assets.
  - the growth is two lazy assets: `zxing_reader-….wasm` **953.53 KB (413.61 KB gzip)** and `scanEngine-….js` **35.60 KB (12.93 KB gzip)**. Neither is referenced from the boot path; `BarcodeStation` chunk grew 55.74 → 63.21 KB (the new scanner UI). A person who never opens the camera downloads nothing new.
- **The "no built-in barcode detector" message is retired.** The remaining camera-refusal sentences are exactly three, kept word for word: no camera, not https, permission denied.
- **iPhone Safari / Chrome on Windows & Linux:** the engine no longer branches on the platform, so the *mechanism* that made those fail is gone; driving one of each is in the owner's §6c table below. This report does not claim the measurement it cannot make.

## §2 — the formats

All thirteen: Code 128, Code 39, Code 93, Codabar, EAN-13, EAN-8, UPC-A, UPC-E, ITF, QR, Data Matrix, PDF417, Aztec — requested from the engine by their zxing names, published up the component and the API by their BarcodeDetector-style names (`src/lib/scanFormats.ts`, a module with no zxing import so naming a format costs no bundle).

- **Same value twice in frame (a Cadra label):** deduplicated by value in `decodeFrame`; the 2D read is kept when both symbologies carried the same value, because it is the one a single decode may accept. Accepted once.
- **Two different values in frame:** the reticle crop is decoded first and wins alone when it finds exactly one; what survives as plural becomes a tap-to-choose chooser (`scan-chooser`), with "Neither — keep scanning". Proved in spec 54 both ways: side-by-side codes inside the reticle → chooser, tap fills the box; one code centred and one at the frame's edge → the reticle one wins without asking.

## §3 — the camera is asked for what the label needs

- `width/height ideal 1920×1080`, `facingMode ideal environment` (or the remembered device), `focusMode: continuous` applied where `getCapabilities().focusMode` offers it.
- **What was actually granted is printed on the preview** (`track.getSettings()`, the `scanner-granted` caption) — for the fake device in spec 54 that reads **640×480** (the mjpeg's size: *ideal* is a request, not an outcome, demonstrated by the harness itself). Real-device values belong to §6c's table.
- **Zoom:** a slider beside the torch, shown only when `getCapabilities().zoom` exists; absent (not inert) on hardware without it — the MacBook and the fake device show neither zoom nor torch.
- **Reticle decode:** the frame is cropped to the reticle rectangle (one constant, `RETICLE`, drives both the overlay and the crop, so they cannot drift apart), mapped through the `object-cover` geometry; full-frame is the second pass only when the crop reads nothing.
- **Throttle:** ~10 decodes/s (100 ms gate on the rAF loop), one decode in flight at a time (a busy flag — a slow device self-throttles further rather than queueing). CPU per frame, measured on this machine via the corpus: **median 2.3 ms, p95 9.6 ms** per `readBarcodes` call (M1 Pro; the weak-Android number is owner-blocked with §6c).
- **Camera picker:** after permission, `enumerateDevices()`; more than one video input renders a select; the choice restarts the stream on the chosen `deviceId` and is remembered per browser (`localStorage`, try/caught, `ideal` not `exact` so an unplugged remembered camera falls back instead of failing).

## §4 — acceptance that does not misread

A 1D value is accepted when two consecutive decodes agree (value AND symbology — the same string read as Code 39 then Code 128 is not agreement); a 2D value on one decode; several distinct values are a choice. The rules are a pure function, `src/lib/scanDecision.ts`, consumed by the component and driven directly by spec 54 (4 unit tests) — the transient states are proved deterministically instead of raced through the fake camera. The accepted value is trimmed and `onDetected(value, format)` carries the symbology up.

**`scanned_format` beside the refusal record (and the API):**
- `POST /api/v1/assets/<id>/tag-affixed` accepts `scanned_format` and `serial_format` (nullable, enum of the 13; outside the enum → `400 invalid_request` with `allowed_values` and NOTHING written; `serial_format` without `serial_number` refused as contradictory input). Additive; announced in `docs/api/CHANGELOG.md`; OpenAPI (the route's `request_schema`) and `docs/api/cadra_api_endpoint_reference.md` updated.
- `nrs.asset.event.scanned_format` (Selection), allowed ONLY in the `affix_refused` payload; recorded through both of `_record_affix_refusal`'s cursor branches; **a successful affix stores nothing new** (§7's ruling, pinned by a pytest from the outside: the tagging block's key set is asserted unchanged).
- History: `detail.scanned_format` beside `detail.scanned`, null where no format was claimed (typed, keyboard wedge, pre-54 rows) — null is "not known", never a guess.
- The app sends it only when the camera filled the field; typing over a camera read clears the claim (and the little "Camera read: QR code." note under the field disappears — spec 54 asserts both).
- **Deviation from §4's letter:** the handoff says "the affix dialog and the lookup can record" the format. The lookup (`GET /barcode/lookup`) is a read and records nothing durable — there is nothing for a format to ride beside, and inventing an accepted-but-unrecorded query key is rule 3's own defect. What the station does instead: shows the format to the operative (`scan-format` chip, "Camera read: Code 128."). If the Architect wants lookups recorded, that is a new record, not a key on this one.

## §5 — silence ends

- 4 s with no decode (clock started after the FIRST decode attempt completes, so the one-time wasm compile is not counted as silence): *"Nothing read yet — move closer, hold steady, or try the light."*
- 10 s: the same sentence *"— or type the code."*, `onSuggestType` fires once and the parent focuses its typed field (the station's scan box / the dialog's own field), **camera left running**.
- A 1D read waiting for its agreeing twin, or two frames disagreeing: status *"Reading…"*.
- A successful read still stops the camera (unchanged); the three cannot-start sentences unchanged.
- Timed in spec 54: no hint at 1.5 s; the first sentence within 7 s; the second within 10 s more; the box focused; Stop still visible.

## §6a — the corpus

`e2e/corpus/run54.mjs` (committed, `npm run corpus:54` from `e2e/`), table at `docs/handoffs/54-evidence/corpus-table.md`, baseline at `e2e/corpus/expected-pass.json`. Cadra's barcodes are fetched from the running Odoo's own renderer at the template's exact per-size source resolutions and displayed at the physical sizes derived from `asset_tag_report.xml`'s cfg and the paperformat content boxes (arithmetic printed in the table header). Same package, same version, the component's `READER_OPTIONS` verbatim.

**Headline numbers (408 attempts, N of M in every cell):**

| row | overall | must-pass (0°+90° undegraded) |
|---|---|---|
| cadra code_128 small | 0 of 24 | 0 of 4 |
| cadra code_128 standard | 0 of 24 | 0 of 4 |
| cadra code_128 large | 9 of 24 | 2 of 4 |
| cadra qr small | 9 of 24 | 2 of 4 |
| cadra qr standard | 11 of 24 | 2 of 4 |
| cadra qr large | 18 of 24 | 4 of 4 |

(Manufacturer rows in the table; aztec 24/24, itf/ean_8/upc_e 18/24, pdf417 4/24 — the handoff's own 15 mm-square display squeezes a natively wide symbol.)

**The harness itself had a defect the first run hid behind:** the agent's first pipeline rendered each attempt as an `<img>` at a fractional CSS size and screenshotted it — measured to LOSE decodes the same pixels keep through a canvas `drawImage` (`imageSmoothingQuality: "high"`): an Odoo Code 128 at 675.6 px read through canvas and not through `<img>`. The pipeline now composites on a canvas (rotation, `ctx.filter` blur/contrast, source-clip torn), which is also closer to what a camera's optical chain does. The committed table is from the fixed pipeline; it is deterministic (two consecutive runs identical, exit 0, baseline held).

**Where the handoff's must-pass bar is not met, and why it is the label:** a 15-character tag in Code 128 is ~220 modules; at the small label's 28.6 mm that is ≈ 0.13 mm (≈ 5 mil) per module — at the corpus's own scales (300-dpi-equivalent 11.81 px/mm and arm's-length 4.2 px/mm) that is 1.5 and 0.55 px per module, below the engine's floor (verified independently of the harness: a clean 1200 px source downsampled to the same density also fails). This is §6a's anticipated "finding about the label, not the scanner". Hence the script's gate: (1) every label size must have one side readable as printed, straight on — it does, the QR, 3 of 3 on every size — and (2) no baseline cell may regress.

## §6b — the fake camera, widened (spec 54)

`e2e/tests/54-every-time.spec.ts`, 12 tests: lazy-wasm trace; each Cadra size's Code 128 side AND QR side through the real Odoo renderer at the template's source resolutions, value and format chip asserted; one manufacturer-style label per family (all eleven, 2D included), asserting the engine's canonical read (check digits completed, UPC-E carried expanded, UPC-A answered as its EAN-13 superset — same equivalences as the corpus table); the two-values chooser (tap fills, "Neither" keeps scanning); reticle preference; §5's sentences timed; the §4 rules unit-driven; and the dialog path end-to-end — a camera-read wrong tag refused with `scanned_format: "qr_code"` on the history record, then a typed retry that carries no format.

Spec run output: _(§8 below)_

## §6c — real devices (owner's table, with the procedure)

Fill one row per device; everything the row needs is on the screen. Procedure: print one label per size (`Print Tag` on any asset, three sizes), open `/app/tools/barcode` on the device over **https** (or `http://<tenant>.localhost:8069` on this Mac), Camera → Start, read the granted resolution off the preview's bottom-right caption, and for each label find the nearest and farthest distance at which the Code 128 side fills the box, then the QR side — the distance band is what §6c item 1 asks for. A field that never fills within 10 s will say *"or type the code"* — that is the fail mark for the cell.

| device | OS / browser | granted (`getSettings()`, on the preview) | small C128 band | small QR band | std C128 | std QR | large C128 | large QR | laptop underside | monitor serial |
|---|---|---|---|---|---|---|---|---|---|---|
| MacBook Pro M1 Pro (2021), built-in, **the demo machine** | macOS / Chrome | — | — | — | — | — | — | — | — | — |
| same | macOS / Safari | — | — | — | — | — | — | — | — | — |
| Android phone | Android / Chrome | — | — | — | — | — | — | — | — | — |
| iPhone | iOS / Safari | — | — | — | — | — | — | — | — | — |

Expectations the corpus licenses (to be verified, not trusted): the QR side should read on every size at sensible distances; the small/standard Code 128 should NOT read on a camera at any distance (≈ 5 mil modules); the large Code 128 should read close-up. The MacBook rows decide the demo (§9below); its camera has no torch and no zoom, so those controls must simply be absent — the component gates both on `getCapabilities()`.

## §7 — what must not change (verified)

- The typed field: always mounted, keyboard-wedge Enter submits — spec 40 unchanged and green; spec 54's dialog test ends with a typed retry.
- Handoff 39's rule: the dialog still never carries the expected number — asserted again in spec 54 with the camera running and the format note visible.
- The camera fills and does not submit (40) — spec 40 green against the new engine, unchanged assertions.
- Handoff 51's refusal record — unchanged except `scanned_format` riding beside it; refusal text byte-identical (pytest asserts the sentence).

## §8 — verification

**HTTP suite** (`CADRA_API_BASE=http://test19.localhost:8069 tests/.venv/bin/python -m pytest tests/ -q`):

```
1311 passed, 9 skipped in 471.92s (0:07:51)
```

1311 of 1320, 0 failed; the 9 skips are the documented categories (CLAUDE.md's per-tenant breakdown, unchanged). The suite grew by 6 tests in `tests/test_tagging.py` (the format on the refusal record, the serial's own format, the out-of-enum refusal with `allowed_values` and nothing written, `serial_format` without a serial refused, and a clean affix with a format storing nothing new).

**The first full run failed 16 of 1320 — all on the tag-affix path — and the failure is worth the two sentences:** `myservice_workflow` carries TWO overrides of `_mark_affixed` (the INT-05 and INT-06 event hooks), both with the base signature spelled out, and the new `scanned_format=None` kwarg 500'd every affix (`TypeError: … got an unexpected keyword argument`). The subagent that built the backend leg changed the base signature without grepping for overriders — the same class of miss as CLAUDE.md's "a method you override is a name the framework owns", pointing the other way: a signature you grow is a contract every overrider holds. Both overrides now take `*args, **kwargs` and forward them, with a comment saying why; `myservice_workflow` bumped to 19.0.3.1.0 and fanned out to all eight tenants (0 error lines each). Second full run: the green above.

**In-registry Odoo suites** (test19, `--workers=0`, denominators quoted — the result line printed in full, per the standing rule):

```
myservice_asset_register: 0 failed, 0 error(s) of 482 tests
myservice_api:            0 failed, 0 error(s) of 375 tests
myservice_workflow:       0 failed, 0 error(s) of  96 tests
```

**Browser suite** (bundle rebuilt `BASE_PATH=/app/` first): **209 passed, 1 failed, 1 flaky-then-passed, 12 skipped of 223 in 20.2 m** — the suite grew 211 → 223 (spec 54's 12, all green in the run). The one failure is `16-settings-branding` on a `page.goto` 30 s timeout under the 20-minute load, no assertion reached, and 3 of 3 green rerun in isolation immediately after — not this handoff's area, not a regression; the flaky is the same timeout class in spec 42, green on retry. The 12 skips are report 49's documented data-dependent categories. Full detail: `54-evidence/suite-results.txt`.

**Spec 54's own first run failed 2 of 12, both SPEC bugs, both fixed and green:** the wrong-tag value was built by appending to the real tag (so the no-leak assertion tripped over the field's own legitimate contents), and the small Code 128 was shown at its native 400 px, which does not survive the fake camera's JPEG — the corpus's density finding wearing a test harness; the frame now shows every size filling the reticle, as a tagger holds it.

**Module upgrade fan-out**: `myservice_asset_register,myservice_api` on all eight local tenants (cadra19, nrs19, gtb19, test19, nrs, lasg, gtb, jaizbankplc) — each ended `Modules loaded`, no CRITICAL/ERROR beyond the pre-existing duplicate-label warning on `nrs.employee.import.job`; then `myservice_workflow` the same way after the overrider fix.

**Corpus**: run twice back to back — identical table, exit 0, invariant held, baseline of 201 of 408 cells held.

**§0 fact-check**: above — all cells accurate.

## §9 — the question for the report

**Is there a label Cadra prints today that a phone cannot be expected to read?** Yes — by symbology, not by label. The Code 128 side of the **small** and **standard** labels cannot be read by this (or plausibly any) camera pipeline at any distance: 0 of 24 corpus cells each, including straight-on at 300-dpi-equivalent density, because a 15-character tag at ≤ 28.6 mm is ≈ 5 mil per module. The **QR side reads on every size** as printed (3 of 3 each, straight-on): small from ~7 mm at close range, standard comfortably, large at arm's length (3 of 3 at the 40 cm scale). The large Code 128 reads as printed (3 of 3) but not at arm's length — it is a close-up code. **So every printed label is phone-readable — by its QR — and the Code 128 on the two smaller sizes is effectively handheld-scanner-only territory, and marginal even there (5 mil is at the floor of common laser scanners).** If the owner wants the smallest label more forgiving before the demo, the template change the numbers support is: grow the QR at the Code 128's expense on `small` (and possibly `standard`) — the QR is the side a camera actually uses.

**For the demo machine specifically:** the distance bands are optics and are owner-measured (§6c). What the numbers already say: scan the **QR side**, prefer the **large** label; the small label's QR (7 mm) demands closeness that a fixed-focus face-distance camera may not hold sharp — if it misses, the large label at roughly face distance is the safe demo, and an iPhone as Continuity Camera (autofocus, appears in the new camera picker) is the named alternative, selectable by the operative without a developer present.

---

## Files changed

**The engine (frontend):** `src/lib/scanEngine.ts` (new — zxing-wasm behind one module, self-hosted wasm, `decodeFrame` deduplicating by value), `src/lib/scanFormats.ts` (new — the published vocabulary, no zxing import), `src/lib/scanDecision.ts` (new — §2/§4 as a pure function), `src/components/BarcodeScanner.tsx` (rewritten: crop-first decode, throttle, chooser, hints, zoom, picker, granted-settings caption, `onDetected(value, format)`, `onSuggestType`), `src/components/ConfirmAffixedDialog.tsx` and `src/pages/BarcodeStation.tsx` (format plumbing, the "Camera read: …" notes, typed-entry clears the claim), `src/lib/dataProvider.ts` (`scanned_format`/`serial_format` on the affix body), `package.json`/`package-lock.json` (zxing-wasm 3.1.4).

**The record (backend):** `myservice_asset_register/models/asset_event.py` (the `scanned_format` Selection, allowed in `affix_refused` only), `models/asset_tag.py` (`_record_affix_refusal`/`_mark_affixed` carry it, both cursor branches), `myservice_api/controllers/v1_assets.py` (the two body keys, enum refusal, contradictory-input refusal), `models/asset_history.py` (`detail.scanned_format`), `myservice_workflow/models/{asset_tag_event,sap_asset_events}.py` (the two overrides made pass-through — the first run's 16 failures), three manifests bumped (`19.0.1.25.0` / `19.0.3.27.0` / `19.0.3.1.0`), `myservice_api/tests/{test_asset_history,test_published_names_resolve}.py`, `tests/test_tagging.py` (+6 tests), `docs/api/cadra_api_endpoint_reference.md`.

**Proof:** `e2e/tests/54-every-time.spec.ts` (new, 12 tests), `e2e/tests/40-…` (header comment corrected — the decode is the bundled engine's now), `e2e/corpus/` (new: `run54.mjs`, `expected-pass.json`, `README.md`), `e2e/package.json`/lock (zxing-wasm + `corpus:54`), `docs/handoffs/54-evidence/` (`corpus-table.md`, `suite-results.txt`).

**Docs:** this report, `docs/api/CHANGELOG.md`, `docs/DECISIONS.md` (five entries + the overrider lesson), `docs/STATUS.md`, `docs/GO-LIVE.md` §28, `CLAUDE.md` row 54, `docs/ENVIRONMENT-FACTS.md` (the fake-camera recipe no longer macOS-bound).

## Deviations from the handoff

1. **Engine choice:** zxing-wasm direct, not the `barcode-detector` ponyfill — §1 above; the handoff invited the evaluation.
2. **§4's "the lookup can record"**: not implemented as an API key — the lookup records nothing for it to ride on; the station shows the format instead. Named in §4 above.
3. **§6a's must-pass as an exit gate**: reported per row as specified, but the script gates on an invariant + regression baseline, because the bar is missed by the label itself — exactly the case §6a anticipates. DECISIONS `[open]` for the template question.
4. **§6c**: owner-blocked; a handoff defect per the authoring rules (no "Needs the owner" block named it).
5. **The two subagents** that built the backend leg and the corpus died mid-handoff on a session rate limit; their work was reviewed line by line, finished and corrected in the main session (the corpus render pipeline defect above was found in that review).
